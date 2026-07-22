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
async def test_reconciler_settles_video_bill_with_task_adjustment(monkeypatch):
    log = SimpleNamespace(
        id=1,
        provider_request_id="oneapi-video-1",
        provider_trace_id="trace-video-1",
        provider_task_id="task-video-1",
        created_at=None,
        billing_lock_token="lock",
    )
    settled = []

    class FakeRepo:
        def __init__(self, db):
            pass

        async def list_due_provider_reconcile_logs(self, **kwargs):
            return [log]

        async def claim_provider_reconcile_logs(self, **kwargs):
            log.billing_lock_token = kwargs["lock_token"]
            return [log]

    class FakeBillingService:
        def __init__(self, db):
            pass

        async def apply_provider_reconcile_plan(self, plan, *, lock_token=None):
            assert len(plan.retries) == 0
            assert len(plan.blocks) == 0
            assert len(plan.settles) == 1
            settled.append((plan.settles[0].log_id, plan.settles[0].bill.quota, plan.settles[0].bill.amount_cents, lock_token))

    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    async def fake_fetch_recent_bill_rows():
        return [
            {"request_id": "oneapi-video-1", "quota": 1162500},
            {
                "request_id": "adjustment-row",
                "quota": 11681,
                "other": "{\"task_id\":\"task-video-1\"}",
            },
        ]

    provider.fetch_recent_bill_rows = fake_fetch_recent_bill_rows

    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", lambda: _AsyncSessionContext())
    monkeypatch.setattr(reconciler_mod, "UsageLogRepository", FakeRepo)
    monkeypatch.setattr(reconciler_mod, "BillingService", FakeBillingService)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider", lambda: provider)
    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", "test-key")

    processed = await reconciler_mod.LingyaAiBillingReconciler().run_once()

    assert processed == 1
    assert settled == [(1, 1174181, 235, log.billing_lock_token)]


@pytest.mark.asyncio
async def test_reconciler_retries_when_only_video_adjustment_row_exists(monkeypatch):
    log = SimpleNamespace(
        id=2,
        provider_request_id="oneapi-video-2",
        provider_trace_id=None,
        provider_task_id="task-video-2",
        created_at=None,
        billing_lock_token="lock",
    )
    retries = []

    class FakeRepo:
        def __init__(self, db):
            pass

        async def list_due_provider_reconcile_logs(self, **kwargs):
            return [log]

        async def claim_provider_reconcile_logs(self, **kwargs):
            log.billing_lock_token = kwargs["lock_token"]
            return [log]

    class FakeBillingService:
        def __init__(self, db):
            pass

        async def apply_provider_reconcile_plan(self, plan, *, lock_token=None):
            assert len(plan.settles) == 0
            assert len(plan.blocks) == 0
            assert len(plan.retries) == 1
            retries.append((plan.retries[0].log_id, lock_token, plan.retries[0].next_run_at))

    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    async def fake_fetch_recent_bill_rows():
        return [
            {
                "request_id": "adjustment-row",
                "quota": 11681,
                "other": "{\"task_id\":\"task-video-2\"}",
            },
        ]

    provider.fetch_recent_bill_rows = fake_fetch_recent_bill_rows

    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", lambda: _AsyncSessionContext())
    monkeypatch.setattr(reconciler_mod, "UsageLogRepository", FakeRepo)
    monkeypatch.setattr(reconciler_mod, "BillingService", FakeBillingService)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider", lambda: provider)
    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", "test-key")

    processed = await reconciler_mod.LingyaAiBillingReconciler().run_once()

    assert processed == 1
    assert retries and retries[0][0] == 2
    assert retries[0][1] == log.billing_lock_token


@pytest.mark.asyncio
async def test_reconciler_applies_one_batch_plan_for_mixed_outcomes(monkeypatch):
    logs = [
        SimpleNamespace(
            id=11,
            provider_request_id="req-settle",
            provider_trace_id=None,
            provider_task_id=None,
            created_at=None,
            billing_lock_token="lock",
        ),
        SimpleNamespace(
            id=12,
            provider_request_id="req-retry",
            provider_trace_id=None,
            provider_task_id=None,
            created_at=None,
            billing_lock_token="lock",
        ),
        SimpleNamespace(
            id=13,
            provider_request_id=None,
            provider_trace_id=None,
            provider_task_id=None,
            created_at=None,
            billing_lock_token="lock",
        ),
    ]
    applied = []

    class FakeRepo:
        def __init__(self, db):
            pass

        async def list_due_provider_reconcile_logs(self, **kwargs):
            return logs

        async def claim_provider_reconcile_logs(self, **kwargs):
            for log in logs:
                log.billing_lock_token = kwargs["lock_token"]
            return logs

    class FakeBillingService:
        def __init__(self, db):
            pass

        async def apply_provider_reconcile_plan(self, plan, *, lock_token=None):
            applied.append((plan, lock_token))

    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    async def fake_fetch_recent_bill_rows():
        return [
            {"request_id": "req-settle", "quota": 1011},
        ]

    provider.fetch_recent_bill_rows = fake_fetch_recent_bill_rows

    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", lambda: _AsyncSessionContext())
    monkeypatch.setattr(reconciler_mod, "UsageLogRepository", FakeRepo)
    monkeypatch.setattr(reconciler_mod, "BillingService", FakeBillingService)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider", lambda: provider)
    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", "test-key")

    reconciler = reconciler_mod.LingyaAiBillingReconciler()
    processed = await reconciler.run_once()

    assert processed == 3
    assert len(applied) == 1
    plan, lock_token = applied[0]
    assert len(plan.settles) == 1
    assert len(plan.retries) == 1
    assert len(plan.blocks) == 1
    assert lock_token == logs[0].billing_lock_token
    assert reconciler.metrics_snapshot() == {
        "leader_acquired": 0,
        "leader_denied": 0,
        "bill_fetch_allowed": 1,
        "bill_fetch_denied": 0,
        "claimed_logs": 3,
        "settled_logs": 1,
        "retried_logs": 1,
        "blocked_logs": 1,
        "failures": 0,
    }


@pytest.mark.asyncio
async def test_reconciler_rate_limits_bill_row_fetches_within_one_minute(monkeypatch):
    log = SimpleNamespace(
        id=21,
        provider_request_id="req-rate-limit",
        provider_trace_id=None,
        provider_task_id=None,
        created_at=None,
        billing_lock_token="lock",
    )
    fetch_calls = 0
    claim_calls = 0

    class FakeRepo:
        def __init__(self, db):
            pass

        async def list_due_provider_reconcile_logs(self, **kwargs):
            return [log]

        async def claim_provider_reconcile_logs(self, **kwargs):
            nonlocal claim_calls
            claim_calls += 1
            log.billing_lock_token = kwargs["lock_token"]
            return [log]

    class FakeBillingService:
        def __init__(self, db):
            pass

        async def apply_provider_reconcile_plan(self, plan, *, lock_token=None):
            return None

    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    async def fake_fetch_recent_bill_rows():
        nonlocal fetch_calls
        fetch_calls += 1
        return [{"request_id": "req-rate-limit", "quota": 1011}]

    provider.fetch_recent_bill_rows = fake_fetch_recent_bill_rows

    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", lambda: _AsyncSessionContext())
    monkeypatch.setattr(reconciler_mod, "UsageLogRepository", FakeRepo)
    monkeypatch.setattr(reconciler_mod, "BillingService", FakeBillingService)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider", lambda: provider)
    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(reconciler_mod.settings, "PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS", 60)
    monkeypatch.setattr(reconciler_mod.settings, "PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT", 9)

    reconciler = reconciler_mod.LingyaAiBillingReconciler()

    first_processed = await reconciler.run_once()
    second_processed = await reconciler.run_once()
    reconciler._last_bill_rows_fetch_at = datetime.now(UTC) - timedelta(seconds=6)
    third_processed = await reconciler.run_once()
    reconciler._last_bill_rows_fetch_at = datetime.now(UTC) - timedelta(seconds=7)
    fourth_processed = await reconciler.run_once()

    assert first_processed == 1
    assert second_processed == 0
    assert third_processed == 0
    assert fourth_processed == 1
    assert fetch_calls == 2
    assert claim_calls == 2


@pytest.mark.asyncio
async def test_reconciler_uses_distributed_provider_request_policy_before_claiming(monkeypatch):
    log = SimpleNamespace(
        id=31,
        provider_request_id="req-distributed-limit",
        provider_trace_id=None,
        provider_task_id=None,
        created_at=None,
        billing_lock_token="lock",
    )
    policy_calls: list[dict] = []
    claim_calls = 0
    fetch_calls = 0

    class FakeDecision:
        allowed = False
        retry_after_seconds = 12
        reason = "rate_limited"

    class FakePolicy:
        def __init__(self, *, namespace):
            self.namespace = namespace

        async def allow(self, **kwargs):
            policy_calls.append({"namespace": self.namespace, **kwargs})
            return FakeDecision()

    class FakeRepo:
        def __init__(self, db):
            pass

        async def list_due_provider_reconcile_logs(self, **kwargs):
            return [log]

        async def claim_provider_reconcile_logs(self, **kwargs):
            nonlocal claim_calls
            claim_calls += 1
            return [log]

    provider = LingyaAiBuiltinProvider("test-key", billing_unit_per_yuan=500000)

    async def fake_fetch_recent_bill_rows():
        nonlocal fetch_calls
        fetch_calls += 1
        return [{"request_id": "req-distributed-limit", "quota": 1011}]

    provider.fetch_recent_bill_rows = fake_fetch_recent_bill_rows

    monkeypatch.setattr(reconciler_mod, "AsyncSessionLocal", lambda: _AsyncSessionContext())
    monkeypatch.setattr(reconciler_mod, "UsageLogRepository", FakeRepo)
    monkeypatch.setattr(reconciler_mod, "ProviderRequestPolicy", FakePolicy)
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider_code", lambda: "lingyaai")
    monkeypatch.setattr(reconciler_mod, "get_active_builtin_provider", lambda: provider)
    monkeypatch.setattr(reconciler_mod.settings, "BUILTIN_PROVIDER_API_KEY", "test-key")
    monkeypatch.setattr(reconciler_mod.settings, "PROVIDER_RATE_LIMIT_BILLING_FETCH_WINDOW_SECONDS", 60)
    monkeypatch.setattr(reconciler_mod.settings, "PROVIDER_RATE_LIMIT_BILLING_FETCH_LIMIT", 9)

    reconciler = reconciler_mod.LingyaAiBillingReconciler()
    processed = await reconciler.run_once()

    assert processed == 0
    assert reconciler.metrics_snapshot()["bill_fetch_denied"] == 1
    assert claim_calls == 0
    assert fetch_calls == 0
    assert policy_calls == [
        {
            "namespace": "lingyaai-billing",
            "provider": "lingyaai",
            "operation": "billing_fetch",
            "priority": "background",
            "limit": 9,
            "window_seconds": 60.0,
        }
    ]


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
