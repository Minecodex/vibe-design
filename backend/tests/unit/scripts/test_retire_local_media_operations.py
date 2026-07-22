from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from scripts import retire_local_media_operations as cleanup


@pytest.mark.asyncio
async def test_cleanup_removes_only_media_operation_keys(monkeypatch):
    coordinator = InProcessRedisCoordinator(settings=Settings(_env_file=None))
    media_key = coordinator.keys.build(domain="media-operation", purpose="queue", resource_parts=["global"])
    other_key = coordinator.keys.build(domain="generation", purpose="queue", resource_parts=["global"])
    await coordinator.set_snapshot(media_key, {"status": "queued"}, ttl_seconds=60)
    await coordinator.set_snapshot(other_key, {"status": "queued"}, ttl_seconds=60)
    monkeypatch.setattr(cleanup, "get_redis_coordinator", lambda: coordinator)

    assert await cleanup.retire_local_media_operations() == 1
    assert await cleanup.retire_local_media_operations() == 0
    assert await coordinator.get_snapshot(other_key) == {"status": "queued"}
