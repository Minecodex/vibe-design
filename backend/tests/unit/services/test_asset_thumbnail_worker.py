from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.asset_thumbnail_worker import (
    AssetThumbnailWorkerServer,
    ThumbnailTaskRegistry,
    generate_canvas_tile,
    generate_list_preview,
)
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator


def test_thumbnail_task_registry_only_accepts_one_inflight_task():
    started: list[str] = []
    deferred: list[callable] = []
    registry = ThumbnailTaskRegistry(
        start_background_task=lambda fn: deferred.append(fn),
    )

    first = registry.submit("asset-1:list", lambda: started.append("first"))
    second = registry.submit("asset-1:list", lambda: started.append("second"))

    assert first == "queued"
    assert second == "pending"

    deferred[0]()
    third = registry.submit("asset-1:list", lambda: started.append("third"))

    assert started == ["first"]
    assert third == "queued"


def test_generate_list_preview_writes_atomically(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    target = tmp_path / "source__list_320.webp"
    source.write_bytes(b"source")

    written_paths: list[str] = []

    class FakeImage:
        width = 640

        def autorot(self):
            return self

        def resize(self, scale: float):
            assert scale == 0.5
            return self

        def write_to_file(self, path: str, **kwargs):
            written_paths.append(path)
            Path(path).write_bytes(b"preview")
            assert kwargs["Q"] == 75

    fake_pyvips = SimpleNamespace(
        Image=SimpleNamespace(
            new_from_file=lambda path, access="sequential": FakeImage(),
        )
    )
    monkeypatch.setitem(sys.modules, "pyvips", fake_pyvips)

    generate_list_preview(
        source_path=source,
        target_path=target,
        max_width=320,
        quality=75,
    )

    assert target.exists()
    assert target.read_bytes() == b"preview"
    assert written_paths[0] != str(target)
    assert not Path(written_paths[0]).exists()


def test_generate_canvas_tile_writes_atomic_cropped_tile(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    target = tmp_path / "source__tile_256_2_3_1.webp"
    source.write_bytes(b"source")

    calls: dict[str, object] = {}

    class FakeTile:
        def resize(self, scale: float):
            calls["resize_scale"] = scale
            return self

        def write_to_file(self, path: str, **kwargs):
            calls["written_path"] = path
            calls["write_kwargs"] = kwargs
            Path(path).write_bytes(b"tile")

    class FakeImage:
        width = 1024
        height = 512

        def autorot(self):
            calls["autorot"] = True
            return self

        def crop(self, left: int, top: int, width: int, height: int):
            calls["crop"] = (left, top, width, height)
            return FakeTile()

    def fake_new_from_file(path: str, access: str = "sequential"):
        calls["new_from_file"] = (path, access)
        return FakeImage()

    fake_pyvips = SimpleNamespace(
        Image=SimpleNamespace(
            new_from_file=fake_new_from_file,
        )
    )
    monkeypatch.setitem(sys.modules, "pyvips", fake_pyvips)

    generate_canvas_tile(
        source_path=source,
        target_path=target,
        z=2,
        x=3,
        y=1,
        tile_size=256,
        quality=80,
    )

    assert target.exists()
    assert target.read_bytes() == b"tile"
    assert calls["new_from_file"] == (str(source), "random")
    assert calls["autorot"] is True
    assert calls["crop"] == (768, 256, 256, 256)
    assert calls["resize_scale"] == 1.0
    assert calls["written_path"] != str(target)
    assert calls["write_kwargs"] == {"Q": 80, "strip": True}
    assert not Path(str(calls["written_path"])).exists()


def test_generate_canvas_tile_rejects_out_of_range_coordinates(tmp_path: Path, monkeypatch):
    source = tmp_path / "source.png"
    target = tmp_path / "source__tile_256_2_0_0.webp"
    source.write_bytes(b"source")

    class FakeImage:
        width = 1024
        height = 512

        def autorot(self):
            return self

    fake_pyvips = SimpleNamespace(
        Image=SimpleNamespace(
            new_from_file=lambda path, access="random": FakeImage(),
        )
    )
    monkeypatch.setitem(sys.modules, "pyvips", fake_pyvips)

    with pytest.raises(ValueError, match="Invalid canvas tile coordinates"):
        generate_canvas_tile(
            source_path=source,
            target_path=target,
            z=2,
            x=4,
            y=0,
            tile_size=256,
            quality=80,
        )

    assert not target.exists()


@pytest.mark.asyncio
async def test_thumbnail_worker_uses_redis_guard_to_suppress_duplicate_submissions(
    tmp_path: Path,
    monkeypatch,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    source = tmp_path / "source.png"
    target = tmp_path / "source__list_320.webp"
    source.write_bytes(b"source")
    submissions: list[dict] = []

    class FakeWorker(AssetThumbnailWorkerServer):
        async def submit(self, payload, timeout=10):
            submissions.append(dict(payload))
            return {"ok": True, "status": "queued"}

    worker = FakeWorker(coordinator=EphemeralTaskCoordinator(ttl_seconds=30))

    first = await worker.submit_generate_preview(
        task_key="asset-1:list",
        source_path=str(source),
        target_path=str(target),
        max_width=320,
        quality=75,
    )
    duplicate = await worker.submit_generate_preview(
        task_key="asset-1:list",
        source_path=str(source),
        target_path=str(target),
        max_width=320,
        quality=75,
    )

    assert first["status"] == "queued"
    assert duplicate["status"] == "pending"
    assert len(submissions) == 1


@pytest.mark.asyncio
async def test_thumbnail_worker_releases_redis_guard_after_submit_failure(
    tmp_path: Path,
    monkeypatch,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    source = tmp_path / "source.png"
    target = tmp_path / "source__list_320.webp"
    source.write_bytes(b"source")
    attempts = 0

    class FakeWorker(AssetThumbnailWorkerServer):
        async def submit(self, payload, timeout=10):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("worker unavailable")
            return {"ok": True, "status": "queued"}

    worker = FakeWorker(coordinator=EphemeralTaskCoordinator(ttl_seconds=30))

    with pytest.raises(RuntimeError):
        await worker.submit_generate_preview(
            task_key="asset-1:list",
            source_path=str(source),
            target_path=str(target),
            max_width=320,
            quality=75,
        )

    retried = await worker.submit_generate_preview(
        task_key="asset-1:list",
        source_path=str(source),
        target_path=str(target),
        max_width=320,
        quality=75,
    )

    assert retried["status"] == "queued"
    assert attempts == 2


@pytest.mark.asyncio
async def test_thumbnail_worker_releases_redis_guard_after_queued_task_finishes(
    tmp_path: Path,
    monkeypatch,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    source = tmp_path / "source.png"
    target = tmp_path / "source__list_320.webp"
    source.write_bytes(b"source")
    deferred: list[callable] = []

    def fake_generate_list_preview(*, source_path, target_path, max_width, quality):
        Path(target_path).write_bytes(b"preview")

    class InlineWorker(AssetThumbnailWorkerServer):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.model = self._create_model({"max_width": 320, "quality": 75})
            self.model.registry = ThumbnailTaskRegistry(start_background_task=lambda fn: deferred.append(fn))

        async def submit(self, payload, timeout=10):
            return self._handle_request(self.model, payload)

    monkeypatch.setattr(
        "app.services.asset_thumbnail_worker.generate_list_preview",
        fake_generate_list_preview,
    )
    worker = InlineWorker(coordinator=EphemeralTaskCoordinator(ttl_seconds=30))

    first = await worker.submit_generate_preview(
        task_key="asset-1:list",
        source_path=str(source),
        target_path=str(target),
        max_width=320,
        quality=75,
    )
    duplicate = await worker.submit_generate_preview(
        task_key="asset-1:list",
        source_path=str(source),
        target_path=str(target),
        max_width=320,
        quality=75,
    )

    assert first["status"] == "queued"
    assert duplicate["status"] == "pending"

    deferred[0]()

    retried = await worker.submit_generate_preview(
        task_key="asset-1:list",
        source_path=str(source),
        target_path=str(target),
        max_width=320,
        quality=75,
    )

    assert retried["status"] == "ready"


@pytest.mark.asyncio
async def test_thumbnail_worker_uses_redis_guard_for_canvas_tile_submissions(
    tmp_path: Path,
    monkeypatch,
):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    source = tmp_path / "source.png"
    target = tmp_path / "source__tile_256_2_3_1.webp"
    source.write_bytes(b"source")
    submissions: list[dict] = []

    class FakeWorker(AssetThumbnailWorkerServer):
        async def submit(self, payload, timeout=10):
            submissions.append(dict(payload))
            return {"ok": True, "status": "queued"}

    worker = FakeWorker(coordinator=EphemeralTaskCoordinator(ttl_seconds=30))

    first = await worker.submit_generate_tile(
        task_key="project:1:tile:2:3:1:source",
        source_path=str(source),
        target_path=str(target),
        z=2,
        x=3,
        y=1,
        tile_size=256,
        quality=80,
    )
    duplicate = await worker.submit_generate_tile(
        task_key="project:1:tile:2:3:1:source",
        source_path=str(source),
        target_path=str(target),
        z=2,
        x=3,
        y=1,
        tile_size=256,
        quality=80,
    )

    assert first["status"] == "queued"
    assert duplicate["status"] == "pending"
    assert len(submissions) == 1
    assert submissions[0]["cmd"] == "generate_tile"
    assert submissions[0]["z"] == 2
    assert submissions[0]["x"] == 3
    assert submissions[0]["y"] == 1
    assert submissions[0]["tile_size"] == 256
