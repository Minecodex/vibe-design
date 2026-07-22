from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.redis_coordination import DisabledRedisCoordinator, InProcessRedisCoordinator
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey


@pytest.mark.asyncio
async def test_ephemeral_task_coordinator_blocks_duplicate_running_task(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator(ttl_seconds=30)
    task = EphemeralTaskKey.build(
        domain="artifact-export",
        kind="html_bundle",
        resource_parts=["conversation-1", "C:/secret/path/index.html"],
        version="v1",
    )

    first = await guard.start(task, owner_prefix="test")
    duplicate = await guard.start(task, owner_prefix="test")

    assert first.acquired is True
    assert duplicate.acquired is False
    assert duplicate.snapshot is not None
    assert duplicate.snapshot.status == "running"


@pytest.mark.asyncio
async def test_ephemeral_task_coordinator_records_done_snapshot_and_reuses_within_ttl(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator(ttl_seconds=30)
    task = EphemeralTaskKey.build(domain="preview", kind="render", resource_parts=["asset-1"], version="v1")

    lease = await guard.start(task, owner_prefix="test")
    await guard.finish(lease, result={"file_id": "f_1", "version_id": "v0001"})
    snapshot = await guard.read(task)
    duplicate_done = await guard.start(task, owner_prefix="test")

    assert snapshot is not None
    assert snapshot.status == "done"
    assert snapshot.result == {"file_id": "f_1", "version_id": "v0001"}
    assert duplicate_done.acquired is False
    assert duplicate_done.snapshot is not None
    assert duplicate_done.snapshot.status == "done"


@pytest.mark.asyncio
async def test_ephemeral_task_coordinator_fail_releases_guard(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator(ttl_seconds=30)
    task = EphemeralTaskKey.build(domain="model-worker", kind="warmup", resource_parts=["sam2"], version="cfg")

    lease = await guard.start(task, owner_prefix="test")
    await guard.fail(lease, error_type="WarmupFailed")
    retry = await guard.start(task, owner_prefix="test")

    assert retry.acquired is True


def test_ephemeral_task_keys_hash_resource_parts_without_leaking_sensitive_values(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator()
    task = EphemeralTaskKey.build(
        domain="artifact-export",
        kind="file",
        resource_parts=["conversation-123", "C:/secret/path/file.png", "sk-real-token"],
        version="123:456",
    )

    lease_key, status_key = guard.keys_for(task)
    rendered = f"{lease_key} {status_key}"

    assert "conversation-123" not in rendered
    assert "secret" not in rendered
    assert "file.png" not in rendered
    assert "sk-real-token" not in rendered


@pytest.mark.asyncio
async def test_ephemeral_task_coordinator_disabled_redis_does_not_block(monkeypatch):
    coordinator = DisabledRedisCoordinator(settings=Settings(REDIS_ENABLED=False, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator()
    task = EphemeralTaskKey.build(domain="preview", kind="render", resource_parts=["asset-1"], version="v1")

    first = await guard.start(task, owner_prefix="test")
    duplicate = await guard.start(task, owner_prefix="test")

    assert first.acquired is True
    assert duplicate.acquired is True


@pytest.mark.asyncio
async def test_ephemeral_task_coordinator_redacts_sensitive_snapshot_payload(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator(ttl_seconds=30)
    task = EphemeralTaskKey.build(domain="artifact-export", kind="file", resource_parts=["asset-1"], version="v1")

    lease = await guard.start(
        task,
        owner_prefix="test",
        status_payload={
            "source": "https://storage.test/file.png?X-Amz-Signature=secret",
            "artifact_ref": "artifact_ref:image_1",
        },
    )
    await guard.finish(
        lease,
        result={
            "file_id": "f_1",
            "absolute_path": "C:/Users/example/secret/file.png",
            "nested": {
                "token": "sk-secret-token",
                "relative_path": "published/f_1/v0001/source.png",
                "signed_url": "https://storage.test/file.png?token=secret",
            },
        },
    )
    snapshot = await guard.read(task)

    assert snapshot is not None
    rendered = str(snapshot.raw)
    assert "sk-secret-token" not in rendered
    assert "X-Amz-Signature" not in rendered
    assert "C:/Users/example" not in rendered
    assert snapshot.result is not None
    assert snapshot.result["file_id"] == "f_1"
    assert snapshot.result["absolute_path"] == "[REDACTED_PATH]"
    assert snapshot.result["nested"]["relative_path"] == "published/f_1/v0001/source.png"
    assert "token" not in snapshot.result["nested"]
    assert "signed_url" not in snapshot.result["nested"]


@pytest.mark.asyncio
async def test_ephemeral_task_start_sync_rejects_async_context():
    """Fix 3: calling *_sync from an async context would block the running
    event loop via a thread-trampoline. The wrapper should refuse instead."""
    guard = EphemeralTaskCoordinator(ttl_seconds=30)
    task = EphemeralTaskKey.build(domain="d", kind="k")

    with pytest.raises(RuntimeError, match="async context"):
        guard.start_sync(task, owner_prefix="test")


@pytest.mark.asyncio
async def test_ephemeral_task_strict_lease_failure_propagates_when_redis_required(monkeypatch):
    """Fix 5: with REDIS_REQUIRED=True, EphemeralTaskCoordinator.start surfaces
    RedisCoordinationDegradedError rather than silently returning acquired=True."""
    from app.core.redis_coordination import (
        RedisCoordinationDegradedError,
        RedisCoordinator,
    )

    coordinator = RedisCoordinator(
        settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=True),
    )
    coordinator._create_client = staticmethod(lambda settings: None)  # type: ignore[assignment]
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    guard = EphemeralTaskCoordinator(ttl_seconds=30)
    task = EphemeralTaskKey.build(domain="dedupe", kind="job", resource_parts=["x"])

    with pytest.raises(RedisCoordinationDegradedError):
        await guard.start(task, owner_prefix="test")
