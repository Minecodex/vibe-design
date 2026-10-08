import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.services.lingyaai_billing_reconciler as reconciler_mod
from app.core.redis_coordination import reset_redis_coordinator_for_tests
from app.services.builtin_provider import LingyaAiBuiltinProvider


class _AsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture(autouse=True)
def isolate_reconciler_runtime(monkeypatch):
    monkeypatch.setattr(reconciler_mod, "is_provider_balance_sync_enabled", lambda: False)
    monkeypatch.setattr(reconciler_mod.settings, "REDIS_ENABLED", False, raising=False)
    monkeypatch.setattr(reconciler_mod.settings, "REDIS_REQUIRED", False, raising=False)
    reset_redis_coordinator_for_tests()
    yield
    reset_redis_coordinator_for_tests()


@pytest.mark.asyncio
async def test_reconciler_is_disabled_in_provider_balance_sync_mode(monkeypatch):
    def fail_session():
        raise AssertionError("reconciler should not open a DB session in Provider Balance Sync Mode")

    monkeypatch.setattr(reconciler_mod, "is_provider_balance_sync_enabled", lambda: True)
    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", fail_session)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", "test-key")

    processed = await reconciler_mod.LingyaAiBillingReconciler().run_once()

    assert processed == 0


@pytest.mark.asyncio
async def test_reconciler_uses_redis_leader_lease_before_file_lock(monkeypatch, tmp_path):
    lease_calls: list[tuple[str, str, float]] = []

    class FakeKeys:
        def build(self, *, domain, purpose, resource_parts=()):
            return ":".join([domain, purpose, *resource_parts])

    class FakeCoordinator:
        keys = FakeKeys()

        async def try_acquire_lease(self, key, *, owner, ttl_seconds):
            lease_calls.append((key, owner, ttl_seconds))
            return {"acquired": True, "owner": owner}

        async def release_lease(self, key, *, owner):
            return True

    monkeypatch.setattr(reconciler_mod, "get_redis_coordinator", lambda: FakeCoordinator())

    reconciler = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "must-not-be-used.lock"))

    assert await reconciler._try_acquire_leader_lock_async() is True
    metrics = reconciler.metrics_snapshot()
    assert lease_calls
    assert lease_calls[0][0] == "lingyaai-billing:leader:active"
    assert reconciler._lock_fd is None
    assert reconciler.is_leader is True
    assert metrics["leader_acquired"] == 1
    assert metrics["leader_denied"] == 0


@pytest.mark.asyncio
async def test_reconciler_start_inside_event_loop_uses_redis_leader_lease_before_fallback(monkeypatch, tmp_path):
    lease_calls: list[tuple[str, str, float]] = []
    started: list[str] = []

    class FakeKeys:
        def build(self, *, domain, purpose, resource_parts=()):
            return ":".join([domain, purpose, *resource_parts])

    class FakeCoordinator:
        keys = FakeKeys()

        async def try_acquire_lease(self, key, *, owner, ttl_seconds):
            lease_calls.append((key, owner, ttl_seconds))
            return {"acquired": True, "owner": owner}

        async def release_lease(self, key, *, owner):
            return True

    async def fake_run_loop(self):
        started.append(self._redis_leader_owner or "")
        await self._shutdown_event.wait()

    monkeypatch.setattr(reconciler_mod, "get_redis_coordinator", lambda: FakeCoordinator())
    monkeypatch.setattr(reconciler_mod.LingyaAiBillingReconciler, "_run_loop", fake_run_loop)

    reconciler = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "must-not-be-used.lock"))

    reconciler.start()
    await asyncio.sleep(0)

    assert lease_calls
    assert lease_calls[0][0] == "lingyaai-billing:leader:active"
    assert reconciler._lock_fd is None
    assert reconciler.is_leader is True
    assert started == [reconciler._redis_leader_owner]

    await reconciler.shutdown()


@pytest.mark.asyncio
async def test_reconciler_keeps_retrying_when_started_as_follower(monkeypatch, tmp_path):
    attempts = 0
    run_calls = 0

    async def fake_try_acquire():
        nonlocal attempts
        attempts += 1
        return attempts >= 2

    async def fake_run_loop():
        nonlocal run_calls
        run_calls += 1
        reconciler._shutdown_event.set()

    monkeypatch.setattr(reconciler_mod.settings, "LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS", 0.1)

    reconciler = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))
    monkeypatch.setattr(reconciler, "_try_acquire_leader_lock_async", fake_try_acquire)
    monkeypatch.setattr(reconciler, "_run_loop", fake_run_loop)

    await reconciler._start_and_run_loop()

    assert attempts == 2
    assert run_calls == 1


@pytest.mark.asyncio
async def test_reconciler_retries_after_leader_run_loop_exits(monkeypatch, tmp_path):
    attempts = 0
    run_calls = 0
    releases = 0

    async def fake_try_acquire():
        nonlocal attempts
        attempts += 1
        return True

    async def fake_run_loop():
        nonlocal run_calls
        run_calls += 1
        if run_calls >= 2:
            reconciler._shutdown_event.set()

    def fake_release():
        nonlocal releases
        releases += 1

    monkeypatch.setattr(reconciler_mod.settings, "LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS", 0.1)

    reconciler = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))
    monkeypatch.setattr(reconciler, "_try_acquire_leader_lock_async", fake_try_acquire)
    monkeypatch.setattr(reconciler, "_run_loop", fake_run_loop)
    monkeypatch.setattr(reconciler, "_release_leader_lock", fake_release)

    await reconciler._start_and_run_loop()

    assert attempts == 2
    assert run_calls == 2
    assert releases == 2


@pytest.mark.asyncio
async def test_reconciler_renews_redis_leader_lease_while_running(monkeypatch, tmp_path):
    renew_calls: list[tuple[str, str, float]] = []

    class FakeKeys:
        def build(self, *, domain, purpose, resource_parts=()):
            return ":".join([domain, purpose, *resource_parts])

    class FakeCoordinator:
        keys = FakeKeys()

        async def renew_lease(self, key, *, owner, ttl_seconds):
            renew_calls.append((key, owner, ttl_seconds))
            return {"renewed": True, "owner": owner}

    monkeypatch.setattr(reconciler_mod, "get_redis_coordinator", lambda: FakeCoordinator())
    monkeypatch.setattr(reconciler_mod.settings, "LINGYAAI_BILLING_RECONCILE_INTERVAL_SECONDS", 0.1)

    reconciler = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))
    reconciler._redis_leader_owner = "lingyaai-billing-reconciler:test"

    async def run_once():
        reconciler._shutdown_event.set()
        return 0

    monkeypatch.setattr(reconciler, "run_once", run_once)

    await reconciler._run_loop()

    assert renew_calls
    assert renew_calls[0][0] == "lingyaai-billing:leader:active"
    assert renew_calls[0][1] == "lingyaai-billing-reconciler:test"


@pytest.mark.asyncio
@pytest.mark.skipif(reconciler_mod.fcntl is None, reason="fcntl unavailable")
async def test_reconciler_file_lock_allows_only_one_leader(tmp_path, monkeypatch):
    started: list[str] = []

    async def fake_run_loop(self):
        started.append(self._lock_path)
        await self._shutdown_event.wait()

    monkeypatch.setattr(reconciler_mod.LingyaAiBillingReconciler, "_run_loop", fake_run_loop)

    leader = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))
    follower = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))

    leader.start()
    await asyncio.sleep(0)
    follower.start()
    await asyncio.sleep(0)

    assert leader.is_leader is True
    assert leader.is_running is True
    assert follower.is_leader is False
    assert follower.is_running is False
    assert started == [str(tmp_path / "billing.lock")]

    await leader.shutdown()


@pytest.mark.asyncio
@pytest.mark.skipif(reconciler_mod.fcntl is None, reason="fcntl unavailable")
async def test_reconciler_reacquires_lock_after_leader_shutdown(tmp_path, monkeypatch):
    async def fake_run_loop(self):
        await self._shutdown_event.wait()

    monkeypatch.setattr(reconciler_mod.LingyaAiBillingReconciler, "_run_loop", fake_run_loop)

    first = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))
    second = reconciler_mod.LingyaAiBillingReconciler(lock_path=str(tmp_path / "billing.lock"))

    first.start()
    await asyncio.sleep(0)
    await first.shutdown()

    second.start()
    await asyncio.sleep(0)

    assert second.is_leader is True
    assert second.is_running is True

    await second.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("global_key", ["", "test-legacy-global-key"])
@pytest.mark.parametrize("balance_sync", [False, True])
async def test_retired_reconciler_cannot_claim_or_charge_legacy_work(
    monkeypatch, global_key, balance_sync,
):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("retired reconciliation must perform no external work")

    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", global_key)
    monkeypatch.setattr(reconciler_mod, "is_provider_balance_sync_enabled", lambda: balance_sync)
    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", forbidden)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider", forbidden)

    assert await reconciler_mod.LingyaAiBillingReconciler().run_once() == 0
