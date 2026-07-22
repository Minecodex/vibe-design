import asyncio

import pytest

from app.core.config import Settings
from app.core.redis_coordination import (
    RedisCoordinationDegradedError,
    RedisCoordinator,
    RedisKeyBuilder,
    create_redis_coordinator,
    reset_redis_coordinator_for_tests,
)
from app.services.license_service import LicenseService


async def test_disabled_redis_coordinator_reports_disabled_health():
    settings = Settings(REDIS_ENABLED=False, REDIS_REQUIRED=False)

    coordinator = create_redis_coordinator(settings)
    health = await coordinator.health()

    assert health["status"] == "disabled"
    assert health["enabled"] is False
    assert health["required"] is False
    assert health["degraded"] is False


def test_redis_key_builder_namespaces_and_hashes_resource_parts():
    key = RedisKeyBuilder(namespace="test-app").build(
        domain="conversation",
        purpose="stream",
        resource_parts=["conversation-123", "C:/secret/path/file.png"],
    )

    assert key.startswith("test-app:conversation:stream:")
    assert "conversation-123" not in key
    assert "secret" not in key
    assert "file.png" not in key


async def test_optional_enabled_redis_degrades_to_local_fallback_behaviors():
    settings = Settings(
        REDIS_ENABLED=True,
        REDIS_REQUIRED=False,
        REDIS_CONNECT_TIMEOUT_SECONDS=0.01,
        REDIS_OPERATION_TIMEOUT_SECONDS=0.01,
    )
    coordinator = create_redis_coordinator(settings)

    health = await coordinator.health()
    assert health["status"] == "degraded"
    assert health["enabled"] is True
    assert health["required"] is False
    assert health["degraded"] is True

    await coordinator.set_snapshot("snapshot-key", {"balance_cents": 1200}, ttl_seconds=30)
    assert await coordinator.get_snapshot("snapshot-key") == {"balance_cents": 1200}

    first_lease = await coordinator.try_acquire_lease("lease-key", owner="worker-a", ttl_seconds=30)
    second_lease = await coordinator.try_acquire_lease("lease-key", owner="worker-b", ttl_seconds=30)
    assert first_lease["acquired"] is True
    assert second_lease["acquired"] is False

    first_guard = await coordinator.duplicate_guard("dedupe-key", ttl_seconds=30)
    second_guard = await coordinator.duplicate_guard("dedupe-key", ttl_seconds=30)
    assert first_guard["acquired"] is True
    assert second_guard["acquired"] is False

    assert (await coordinator.rate_limit("bucket", limit=1, window_seconds=30))["allowed"] is True
    assert (await coordinator.rate_limit("bucket", limit=1, window_seconds=30))["allowed"] is False


async def test_in_process_blob_round_trips_bytes_and_enforces_limit():
    coordinator = create_redis_coordinator(
        Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_CONNECT_TIMEOUT_SECONDS=0.01,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.01,
        )
    )

    await coordinator.set_blob("blob-key", b"\x1f\x8bcompressed", ttl_seconds=30, max_bytes=64)

    assert await coordinator.get_blob("blob-key", max_bytes=64) == b"\x1f\x8bcompressed"
    with pytest.raises(ValueError):
        await coordinator.set_blob("blob-too-large", b"123456789", ttl_seconds=30, max_bytes=4)


async def test_redis_blob_uses_raw_bytes_payload():
    class _BlobClient:
        def __init__(self):
            self.values: dict[str, bytes] = {}

        async def set(self, key, value, **kwargs):
            del kwargs
            self.values[str(key)] = bytes(value)
            return True

        async def get(self, key):
            return self.values.get(str(key))

    client = _BlobClient()
    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=True),
        client=client,
    )

    await coordinator.set_blob("blob-key", b"\x1f\x8bcompressed", ttl_seconds=30, max_bytes=64)

    assert client.values["blob-key"] == b"\x1f\x8bcompressed"
    assert await coordinator.get_blob("blob-key", max_bytes=64) == b"\x1f\x8bcompressed"


async def test_redis_set_blobs_uses_transaction_pipeline():
    class _Pipeline:
        def __init__(self, values):
            self.values = values
            self.transaction = None
            self.pending: list[tuple[str, bytes]] = []

        def set(self, key, value, **kwargs):
            del kwargs
            self.pending.append((str(key), bytes(value)))
            return self

        async def execute(self):
            for key, value in self.pending:
                self.values[key] = value
            return [True for _key, _value in self.pending]

    class _BlobClient:
        def __init__(self):
            self.values: dict[str, bytes] = {}
            self.pipeline_transaction_values: list[bool] = []

        def pipeline(self, *, transaction):
            self.pipeline_transaction_values.append(bool(transaction))
            return _Pipeline(self.values)

        async def get(self, key):
            return self.values.get(str(key))

    client = _BlobClient()
    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=True),
        client=client,
    )

    await coordinator.set_blobs(
        {"blob-a": b"a", "blob-b": b"b"},
        ttl_seconds=30,
        max_bytes=64,
    )

    assert client.pipeline_transaction_values == [True]
    assert await coordinator.get_blob("blob-a", max_bytes=64) == b"a"
    assert await coordinator.get_blob("blob-b", max_bytes=64) == b"b"


async def test_health_payload_includes_redis_status(monkeypatch):
    import app.services.license_service as license_service
    from app.core.config import settings

    monkeypatch.setattr(settings, "REDIS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "REDIS_REQUIRED", True, raising=False)
    monkeypatch.setattr(
        license_service,
        "agent_catalog_health",
        lambda: _async_value({"status": "ready"}),
        raising=False,
    )
    reset_redis_coordinator_for_tests()

    try:
        payload = await LicenseService(db=None).build_health_payload(
            app_name="test-app",
            app_env="development",
            deploy_type="saas",
        )
    finally:
        reset_redis_coordinator_for_tests()

    assert payload["redis"]["status"] == "required-unavailable"
    assert payload["redis"]["enabled"] is True
    assert payload["redis"]["required"] is True
    assert payload["status"] == "unhealthy"


async def test_health_payload_marks_unhealthy_when_agent_catalog_is_unavailable(monkeypatch):
    import app.services.license_service as license_service

    class FakeCoordinator:
        async def health(self):
            return {
                "status": "healthy",
                "enabled": True,
                "required": True,
                "degraded": False,
            }

    monkeypatch.setattr(license_service, "get_redis_coordinator", lambda: FakeCoordinator(), raising=False)
    monkeypatch.setattr(
        license_service,
        "agent_catalog_health",
        lambda: _async_value({"status": "unavailable", "reason": "agent catalog manifest missing"}),
        raising=False,
    )

    payload = await LicenseService(db=None).build_health_payload(
        app_name="test-app",
        app_env="development",
        deploy_type="saas",
    )

    assert payload["redis"]["status"] == "healthy"
    assert payload["agent_catalog"] == {
        "status": "unavailable",
        "reason": "agent catalog manifest missing",
    }
    assert payload["status"] == "unhealthy"


async def test_health_payload_uses_shared_redis_coordinator(monkeypatch):
    import app.services.license_service as license_service

    health_calls: list[str] = []

    class FakeCoordinator:
        async def health(self):
            health_calls.append("health")
            return {
                "status": "healthy",
                "enabled": True,
                "required": False,
                "degraded": False,
            }

    def create_should_not_run(*_args, **_kwargs):
        raise AssertionError("health payload should use the shared Redis coordinator")

    monkeypatch.setattr(license_service, "get_redis_coordinator", lambda: FakeCoordinator(), raising=False)
    monkeypatch.setattr(license_service, "create_redis_coordinator", create_should_not_run, raising=False)
    monkeypatch.setattr(
        license_service,
        "agent_catalog_health",
        lambda: _async_value({"status": "ready"}),
        raising=False,
    )

    payload = await LicenseService(db=None).build_health_payload(
        app_name="test-app",
        app_env="development",
        deploy_type="saas",
    )

    assert health_calls == ["health"]
    assert payload["redis"]["status"] == "healthy"


async def _async_value(value):
    return value


async def test_redis_operation_summary_records_degraded_domain_without_payloads():
    class FailingClient:
        async def get(self, _key):
            raise TimeoutError("redis timeout")

    settings = Settings(
        REDIS_ENABLED=True,
        REDIS_REQUIRED=False,
        REDIS_OPERATION_TIMEOUT_SECONDS=0.01,
    )
    coordinator = RedisCoordinator(settings=settings, client=FailingClient())
    key = coordinator.keys.build(
        domain="billing",
        purpose="snapshot",
        resource_parts=["conversation-123", "C:/secret/path/file.png"],
    )

    assert await coordinator.get_snapshot(key) is None

    health = await coordinator.health()
    summary = health["operation_summary"]
    recent = summary["recent_operations"]

    assert summary["fallback_count"] == 1
    assert recent[-1]["operation"] == "get_snapshot"
    assert recent[-1]["domain"] == "billing"
    assert recent[-1]["success"] is False
    assert recent[-1]["fallback"] is True
    assert recent[-1]["latency_ms"] >= 0
    rendered = repr(summary)
    assert "conversation-123" not in rendered
    assert "secret" not in rendered
    assert "file.png" not in rendered


async def test_in_process_pubsub_delivers_notifications_until_unsubscribed():
    coordinator = create_redis_coordinator(
        Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_CONNECT_TIMEOUT_SECONDS=0.01,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.01,
        )
    )
    received: list[dict] = []

    unsubscribe = await coordinator.subscribe("conversation-events", received.append)
    await coordinator.publish("conversation-events", {"conversation_id": "c1", "sequence": 2})
    unsubscribe()
    await coordinator.publish("conversation-events", {"conversation_id": "c1", "sequence": 3})

    assert received == [{"conversation_id": "c1", "sequence": 2}]


async def test_in_process_wakeup_releases_waiters():
    coordinator = create_redis_coordinator(
        Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_CONNECT_TIMEOUT_SECONDS=0.01,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.01,
        )
    )

    await coordinator.wakeup("projection:c1")
    result = await coordinator.wait_wakeup("projection:c1", timeout_seconds=0.01)
    timeout_result = await coordinator.wait_wakeup("projection:c1", timeout_seconds=0.01)

    assert result["woken"] is True
    assert timeout_result["woken"] is False


async def test_redis_wait_wakeup_idle_timeout_is_successful_non_fallback_operation():
    class FakePubSub:
        def __init__(self):
            self.subscribed: list[str] = []
            self.closed = False

        async def subscribe(self, *channels):
            self.subscribed.extend(channels)

        async def get_message(self, *, ignore_subscribe_messages=False, timeout=None):
            if timeout is not None:
                await asyncio.sleep(float(timeout))
            return None

        async def close(self):
            self.closed = True

    class IdleWakeupClient:
        def __init__(self):
            self.eval_calls = 0
            self.last_pubsub: FakePubSub | None = None

        async def ping(self):
            return True

        async def eval(self, *_args):
            self.eval_calls += 1
            return 0

        def pubsub(self):
            self.last_pubsub = FakePubSub()
            return self.last_pubsub

    client = IdleWakeupClient()
    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=True,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.05,
        ),
        client=client,
    )

    result = await coordinator.wait_wakeup("generation:scheduler", timeout_seconds=0.03)

    assert result == {"woken": False}
    # wait_wakeup now uses a long-lived shared pubsub subscriber: subscribe
    # happens once per (loop, channel), and the entry consume eval still
    # runs on every call.
    assert client.eval_calls >= 1
    assert client.last_pubsub is not None
    assert client.last_pubsub.subscribed and client.last_pubsub.subscribed[0].startswith("wakeup:")
    # The shared subscriber stays open across calls — close happens at
    # coordinator shutdown, not on every wait_wakeup return.
    assert client.last_pubsub.closed is False
    # A second wait should reuse the same pubsub instance (no churn).
    second_pubsub_before = client.last_pubsub
    await coordinator.wait_wakeup("generation:scheduler", timeout_seconds=0.01)
    assert client.last_pubsub is second_pubsub_before
    health = await coordinator.health()
    summary = health["operation_summary"]
    assert summary["success_count"] == 2
    assert summary["failure_count"] == 0
    assert summary["fallback_count"] == 0
    assert summary["recent_operations"][-1]["operation"] == "wait_wakeup"
    await coordinator.shutdown_wakeup_subscribers()
    assert second_pubsub_before.closed is True


async def test_wait_wakeup_concurrent_ensure_creates_single_subscriber():
    # Concurrent first-time waiters on the same channel must share one
    # subscriber instance; the per-(loop, channel) lock prevents duplicate
    # background tasks from being spawned.
    class FakePubSub:
        def __init__(self):
            self.subscribed: list[str] = []
            self.closed = False

        async def subscribe(self, *channels):
            self.subscribed.extend(channels)

        async def get_message(self, *, ignore_subscribe_messages=False, timeout=None):
            if timeout is not None:
                await asyncio.sleep(float(timeout))
            return None

        async def close(self):
            self.closed = True

    class CountingClient:
        def __init__(self):
            self.pubsub_count = 0
            self.created: list[FakePubSub] = []

        async def ping(self):
            return True

        async def eval(self, *_args):
            return 0

        def pubsub(self):
            self.pubsub_count += 1
            ps = FakePubSub()
            self.created.append(ps)
            return ps

    client = CountingClient()
    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=True,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.1,
        ),
        client=client,
    )

    # Fire 8 wait_wakeup calls in parallel before any subscriber is ready.
    results = await asyncio.gather(
        *[coordinator.wait_wakeup("ch:concurrent", timeout_seconds=0.02) for _ in range(8)]
    )

    assert all(r == {"woken": False} for r in results)
    # Exactly one pubsub connection should have been created despite 8
    # racing callers — the lock collapses them.
    assert client.pubsub_count == 1
    await coordinator.shutdown_wakeup_subscribers()


async def test_health_surfaces_wakeup_subscriber_stats():
    class FakePubSub:
        def __init__(self):
            self.closed = False

        async def subscribe(self, *_channels):
            return None

        async def get_message(self, *, ignore_subscribe_messages=False, timeout=None):
            if timeout is not None:
                await asyncio.sleep(float(timeout))
            return None

        async def close(self):
            self.closed = True

    class HealthyClient:
        def __init__(self):
            self.pubsub_count = 0

        async def ping(self):
            return True

        async def eval(self, *_args):
            return 0

        def pubsub(self):
            self.pubsub_count += 1
            return FakePubSub()

    client = HealthyClient()
    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=True,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.1,
        ),
        client=client,
    )

    await coordinator.wait_wakeup("ch:obs", timeout_seconds=0.01)
    health = await coordinator.health()

    summary = health.get("wakeup_subscribers")
    assert summary is not None
    assert summary["channel_count"] == 1
    channel_info = summary["channels"]["wakeup:ch:obs"]
    assert channel_info["state"] == "running"
    assert channel_info["rebuild_count"] == 0
    assert channel_info["last_failure_reason"] is None
    await coordinator.shutdown_wakeup_subscribers()


async def test_wakeup_subscriber_rebuilds_after_failure_and_reports_stats():
    class FlakyPubSub:
        def __init__(self, *, fail: bool):
            self._fail = fail
            self.closed = False

        async def subscribe(self, *_channels):
            if self._fail:
                raise ConnectionError("simulated pubsub failure")

        async def get_message(self, *, ignore_subscribe_messages=False, timeout=None):
            if timeout is not None:
                await asyncio.sleep(float(timeout))
            return None

        async def close(self):
            self.closed = True

    class FlakyClient:
        def __init__(self):
            self.pubsub_count = 0
            self._next_fails = True  # first attempt fails, subsequent ok

        async def ping(self):
            return True

        async def eval(self, *_args):
            return 0

        def pubsub(self):
            self.pubsub_count += 1
            ps = FlakyPubSub(fail=self._next_fails)
            self._next_fails = False
            return ps

    client = FlakyClient()
    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=True,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.1,
        ),
        client=client,
    )

    # First call: subscriber subscribe() raises → wait_wakeup falls back to
    # a single eval and returns woken=False without hanging.
    first = await coordinator.wait_wakeup("ch:flaky", timeout_seconds=0.02)
    assert first == {"woken": False}

    # Second call: ensure_wakeup_subscriber detects the failed state, stops
    # the failed subscriber, and creates a healthy one. Stats should record
    # the rebuild.
    second = await coordinator.wait_wakeup("ch:flaky", timeout_seconds=0.02)
    assert second == {"woken": False}

    health = await coordinator.health()
    channel_info = health["wakeup_subscribers"]["channels"]["wakeup:ch:flaky"]
    assert channel_info["rebuild_count"] >= 1
    assert channel_info["last_failure_reason"] == "ConnectionError"
    assert channel_info["last_failure_at"] is not None
    assert channel_info["state"] == "running"
    await coordinator.shutdown_wakeup_subscribers()


async def test_redis_required_strict_lease_raises_on_unavailable_client():
    """Fix 5: when REDIS_REQUIRED=True and the redis client cannot be created,
    distributed-correctness operations must raise rather than silently fall back."""
    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=True),
    )
    # Simulate "redis dependency unavailable" by forcing _create_client to None.
    coordinator._create_client = staticmethod(lambda settings: None)  # type: ignore[assignment]

    with pytest.raises(RedisCoordinationDegradedError) as excinfo:
        await coordinator.try_acquire_lease("k", owner="o", ttl_seconds=1.0)
    assert excinfo.value.operation == "try_acquire_lease"

    # Non-strict operations (get_snapshot) still degrade transparently.
    snapshot = await coordinator.get_snapshot("absent")
    assert snapshot is None


async def test_redis_strict_falls_back_when_required_disabled():
    """Fix 5: with REDIS_REQUIRED=False, strict ops still fall back transparently."""
    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False),
    )
    coordinator._create_client = staticmethod(lambda settings: None)  # type: ignore[assignment]

    result = await coordinator.try_acquire_lease("k", owner="o", ttl_seconds=1.0)
    assert result.get("acquired") is True


async def test_redis_required_strict_raises_when_redis_operation_fails():
    """Fix 5: strict mode raises when an existing client raises during the op."""

    class _FailingClient:
        async def ping(self):
            return True

        async def set(self, *args, **kwargs):
            raise ConnectionError("redis network down")

        async def get(self, *args, **kwargs):
            return None

    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=True,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.05,
        ),
        client=_FailingClient(),
    )

    with pytest.raises(RedisCoordinationDegradedError):
        await coordinator.try_acquire_lease("k", owner="o", ttl_seconds=1.0)


async def test_redis_call_value_error_propagates_without_falling_back():
    """Fix 6: ValueError (e.g. oversized payload) must propagate, never degrade."""

    class _OkClient:
        async def ping(self):
            return True

        async def set(self, *args, **kwargs):
            return True

    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_MAX_PAYLOAD_BYTES=8,
        ),
        client=_OkClient(),
    )

    with pytest.raises(ValueError):
        await coordinator.set_snapshot("k", {"oversized": "x" * 1024}, ttl_seconds=5)


async def test_create_client_passes_pool_config(monkeypatch):
    """_create_client must forward max_connections / health_check_interval to redis."""
    captured: dict = {}

    def fake_from_url(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return object()

    import app.core.redis_coordination as rc

    monkeypatch.setattr(rc.redis_asyncio, "from_url", fake_from_url, raising=False)
    client = RedisCoordinator._create_client(
        Settings(
            REDIS_URL="redis://example:6379/2",
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_CONNECT_TIMEOUT_SECONDS=2.5,
            REDIS_MAX_CONNECTIONS=128,
            REDIS_HEALTH_CHECK_INTERVAL_SECONDS=45,
        )
    )

    assert client is not None
    assert captured["url"] == "redis://example:6379/2"
    assert captured["max_connections"] == 128
    assert captured["health_check_interval"] == 45
    assert captured["socket_connect_timeout"] == pytest.approx(2.5)
    assert captured["socket_timeout"] == pytest.approx(10.0)
    assert captured["decode_responses"] is True


async def test_pubsub_client_disables_socket_read_timeout(monkeypatch):
    """Pub/Sub listeners must not inherit command socket_timeout.

    A finite socket_timeout makes idle pubsub.listen() raise TimeoutError and
    permanently drops SSE wakeup subscriptions before the agent emits events.
    """

    class _FakeClient:
        pass

    calls: list[dict] = []

    def fake_from_url(_url, **kwargs):
        calls.append(dict(kwargs))
        return _FakeClient()

    import app.core.redis_coordination as rc

    monkeypatch.setattr(rc.redis_asyncio, "from_url", fake_from_url, raising=False)
    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_SOCKET_TIMEOUT_SECONDS=10.0,
        )
    )

    assert coordinator._client is not None
    assert coordinator._pubsub_client is not None

    assert calls[0]["socket_timeout"] == pytest.approx(10.0)
    assert calls[1]["socket_timeout"] is None


async def test_create_client_clamps_invalid_pool_config(monkeypatch):
    """REDIS_MAX_CONNECTIONS=0 must clamp to 1; negative health_check_interval to 0."""
    captured: dict = {}

    def fake_from_url(url, **kwargs):
        captured.update(kwargs)
        return object()

    import app.core.redis_coordination as rc

    monkeypatch.setattr(rc.redis_asyncio, "from_url", fake_from_url, raising=False)
    RedisCoordinator._create_client(
        Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_MAX_CONNECTIONS=0,
            REDIS_HEALTH_CHECK_INTERVAL_SECONDS=-5,
        )
    )

    assert captured["max_connections"] == 1
    assert captured["health_check_interval"] == 0


async def test_health_includes_connection_pool_summary():
    """health() output must include connection_pool stats derived from client.connection_pool."""

    class _FakePool:
        def __init__(self):
            self.max_connections = 50
            self._in_use_connections = {object(), object(), object()}
            self._available_connections = [object(), object()]

    class _OkClient:
        def __init__(self):
            self.connection_pool = _FakePool()

        async def ping(self):
            return True

    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False),
        client=_OkClient(),
    )

    health = await coordinator.health()
    pool = health["connection_pool"]
    assert pool["available"] is True
    assert pool["max_connections"] == 50
    assert pool["in_use"] == 3
    assert pool["idle"] == 2
    assert pool["created"] == 5
    assert pool["saturation"] == pytest.approx(0.1)


async def test_health_connection_pool_summary_degrades_when_pool_attrs_missing():
    """If the redis-py internal attributes are missing or shaped differently,
    the summary must report unavailable rather than raise."""

    class _ClientWithoutPool:
        async def ping(self):
            return True

    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False),
        client=_ClientWithoutPool(),
    )
    health = await coordinator.health()
    assert health["connection_pool"] == {"available": False}


async def test_health_failure_path_includes_connection_pool():
    """Even when the ping fails, connection_pool stats are still surfaced."""

    class _FakePool:
        def __init__(self):
            self.max_connections = 10
            self._in_use_connections = set()
            self._available_connections = []

    class _PingFailingClient:
        def __init__(self):
            self.connection_pool = _FakePool()

        async def ping(self):
            raise ConnectionError("redis down")

    coordinator = RedisCoordinator(
        settings=Settings(
            REDIS_ENABLED=True,
            REDIS_REQUIRED=False,
            REDIS_OPERATION_TIMEOUT_SECONDS=0.05,
        ),
        client=_PingFailingClient(),
    )
    health = await coordinator.health()
    assert health["degraded"] is True
    assert health["connection_pool"]["available"] is True
    assert health["connection_pool"]["max_connections"] == 10

    # The in-process fallback must NOT have been written either — otherwise
    # the payload-size limit would be silently bypassed.
    assert coordinator._fallback._snapshots.get("k") is None


def test_sweep_dead_loop_clients_tolerates_cache_mutation_during_iteration():
    class _DeadLoopRef:
        def __call__(self):
            return None

    class _MutatingItemsDict(dict):
        def items(self):
            items = super().items()
            self[999] = (_DeadLoopRef(), object())
            return items

    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False),
    )
    coordinator._loop_clients = _MutatingItemsDict({
        1: (_DeadLoopRef(), object()),
    })
    coordinator._pubsub_loop_clients = _MutatingItemsDict({
        2: (_DeadLoopRef(), object()),
    })
    coordinator._binary_loop_clients = {1: (_DeadLoopRef(), object())}

    coordinator._sweep_dead_loop_clients()

    assert 1 not in coordinator._loop_clients
    assert 1 not in coordinator._binary_loop_clients
    assert 2 not in coordinator._pubsub_loop_clients
