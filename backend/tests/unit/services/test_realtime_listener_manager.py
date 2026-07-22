from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.redis_coordination import InProcessRedisCoordinator
from app.services.realtime_bus import RealtimeBus, RealtimeScope, publish_invalidation
from app.services.realtime_listener_manager import RealtimeListenerManager


@pytest.mark.asyncio
async def test_listener_manager_accepts_legacy_provider_balance_invalidation():
    coordinator = InProcessRedisCoordinator(settings=Settings(REDIS_ENABLED=True, REDIS_REQUIRED=False))
    bus = RealtimeBus(coordinator, namespace="test-app")
    manager = RealtimeListenerManager(bus=bus)

    await manager.start()
    await publish_invalidation(
        "provider.balance.updated",
        scope=RealtimeScope(),
        reason="sync_success",
        bus=bus,
    )
    await manager.stop()
