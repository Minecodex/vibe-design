import sys
import types
from types import SimpleNamespace

sys.modules.setdefault("fcntl", types.SimpleNamespace(LOCK_EX=1, LOCK_NB=2, LOCK_UN=8, flock=lambda *args: None))

import pytest

from app.core.config import Settings
from app.core.redis_coordination import DisabledRedisCoordinator, InProcessRedisCoordinator
from app.services.model_worker import ModelWorkerServer


class _DummyWorker(ModelWorkerServer):
    def __init__(self) -> None:
        super().__init__("dummy", "/tmp/dummy.sock", "/tmp/dummy.lock")

    def _create_model(self, config: dict):
        return object()

    def _handle_request(self, model, request: dict) -> dict:
        return {"ok": True}


def test_release_model_resources_attempts_heap_trim(monkeypatch):
    worker = _DummyWorker()
    trimmed = []

    monkeypatch.setattr(worker, "_trim_process_heap", lambda: trimmed.append(True))

    worker._release_model_resources()

    assert trimmed == [True]


def test_start_accepts_recycle_on_idle_unload_flag():
    worker = _DummyWorker()
    worker._start_process = lambda: None  # type: ignore[method-assign]
    worker._wait_until_ready = lambda **kwargs: True  # type: ignore[method-assign]

    worker.start(config={}, session_ttl=123, recycle_on_idle_unload=True)

    assert worker._recycle_on_idle_unload is True


def test_start_accepts_recycle_after_request_flag():
    worker = _DummyWorker()
    worker._start_process = lambda: None  # type: ignore[method-assign]
    worker._wait_until_ready = lambda **kwargs: True  # type: ignore[method-assign]

    worker.start(config={}, recycle_after_request=True)

    assert worker._recycle_after_request is True


def test_start_waits_for_socket_after_starting_worker(tmp_path, monkeypatch):
    worker = _DummyWorker()
    worker.socket_path = str(tmp_path / "dummy.sock")
    worker.lock_path = str(tmp_path / "dummy.lock")
    calls: list[str] = []

    monkeypatch.setattr(worker, "_start_process", lambda: calls.append("start"))
    monkeypatch.setattr(worker, "_wait_until_ready", lambda **kwargs: calls.append("wait") or True)

    worker.start(config={})

    assert calls == ["start", "wait"]


def test_start_waits_for_socket_when_another_process_holds_lock(tmp_path, monkeypatch):
    worker = _DummyWorker()
    worker.socket_path = str(tmp_path / "dummy.sock")
    worker.lock_path = str(tmp_path / "dummy.lock")
    calls: list[str] = []

    def _locked(*args):
        raise OSError("locked")

    monkeypatch.setattr(
        "app.services.model_worker.fcntl",
        SimpleNamespace(LOCK_EX=1, LOCK_NB=2, LOCK_UN=8, flock=_locked),
    )
    monkeypatch.setattr(worker, "_start_process", lambda: calls.append("start"))
    monkeypatch.setattr(worker, "_wait_until_ready", lambda **kwargs: calls.append("wait") or True)

    worker.start(config={})

    assert calls == ["wait"]
    assert worker._lock_fd is None


@pytest.mark.asyncio
async def test_submit_waits_for_socket_ready_before_retry(monkeypatch):
    worker = _DummyWorker()
    calls: list[str] = []

    async def fake_to_thread(fn):
        calls.append("request")
        if calls.count("request") == 1:
            raise FileNotFoundError("socket missing")
        return {"ok": True}

    monkeypatch.setattr("asyncio.to_thread", fake_to_thread)
    monkeypatch.setattr(worker, "_ensure_alive", lambda: calls.append("ensure"))
    monkeypatch.setattr(worker, "_wait_until_ready", lambda **kwargs: calls.append("wait") or True)

    result = await worker.submit({"cmd": "warmup"}, timeout=10)

    assert result == {"ok": True}
    assert calls == ["request", "ensure", "wait", "request"]


class _WarmupWorker(_DummyWorker):
    def __init__(self) -> None:
        super().__init__()
        self.started = 0
        self.submitted = 0

    def start(self, *args, **kwargs) -> None:
        self.started += 1

    async def submit(self, request: dict, timeout: float = 300) -> dict:
        self.submitted += 1
        assert request == {"cmd": "warmup"}
        return {"ok": True, "status": "ready"}


@pytest.mark.asyncio
async def test_warmup_uses_ephemeral_guard_to_suppress_duplicate_model_load(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    worker = _WarmupWorker()

    first = await worker.warmup(config={"device": "cpu"}, session_ttl=60)
    duplicate = await worker.warmup(config={"device": "cpu"}, session_ttl=60)

    assert first == {"ok": True, "status": "ready"}
    assert duplicate == {"ok": True, "status": "ready", "deduplicated": True}
    assert worker.started == 1
    assert worker.submitted == 1


@pytest.mark.asyncio
async def test_warmup_continues_when_redis_disabled(monkeypatch):
    coordinator = DisabledRedisCoordinator(settings=Settings(REDIS_ENABLED=False, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    worker = _WarmupWorker()

    result = await worker.warmup(config={"device": "cpu"}, session_ttl=60)

    assert result == {"ok": True, "status": "ready"}
    assert worker.started == 1
    assert worker.submitted == 1
