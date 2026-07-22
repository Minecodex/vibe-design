from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.agent_harness.generation_artifact_retry_coordinator import (
    GenerationArtifactRetryCoordinator,
)


@pytest.mark.asyncio
async def test_generation_artifact_retry_guard_expires_after_worker_crash(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    retry_guard = GenerationArtifactRetryCoordinator(ttl_seconds=0.01)

    first = await retry_guard.start(
        conversation_id="conv-1",
        artifact_ref="artifact_ref:image_1",
        current_task_id="task-1",
        source="manual",
    )
    duplicate = await retry_guard.start(
        conversation_id="conv-1",
        artifact_ref="artifact_ref:image_1",
        current_task_id="task-1",
        source="manual",
    )
    await asyncio.sleep(0.05)
    recovered = await retry_guard.start(
        conversation_id="conv-1",
        artifact_ref="artifact_ref:image_1",
        current_task_id="task-1",
        source="manual",
    )

    assert first.acquired is True
    assert duplicate.acquired is False
    assert recovered.acquired is True


@pytest.mark.asyncio
async def test_generation_artifact_retry_guard_preserves_version_through_finish(monkeypatch):
    """Fix 1: finish() must store the original current_task_id as version,
    not the default placeholder that _lease_from_handle previously fell back to."""
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    retry_guard = GenerationArtifactRetryCoordinator(ttl_seconds=60)

    handle = await retry_guard.start(
        conversation_id="conv-a",
        artifact_ref="artifact_ref:image_77",
        current_task_id="task-77",
        source="manual",
    )
    assert handle.acquired
    assert handle.version == "task-77"

    await retry_guard.finish(
        handle,
        artifact_ref="artifact_ref:image_77",
        task_id="task-77",
        status="processing",
    )

    status_payload = await coordinator.get_snapshot(handle.status_key)
    assert status_payload is not None
    assert status_payload.get("version") == "task-77"
