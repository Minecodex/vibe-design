from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

from app.services.provider_balance_sync import ProviderBalanceSyncService, provider_balance_sync_service
from app.services.realtime_bus import (
    REALTIME_KIND_INVALIDATE,
    RealtimeBus,
    RealtimeScope,
)

logger = logging.getLogger(__name__)


class RealtimeListenerManager:
    def __init__(
        self,
        *,
        bus: RealtimeBus | None = None,
        provider_balance_service: ProviderBalanceSyncService = provider_balance_sync_service,
    ) -> None:
        self.bus = bus or RealtimeBus()
        self.provider_balance_service = provider_balance_service
        self._unsubscribers: list[Callable[[], Any]] = []

    async def start(self) -> None:
        if self._unsubscribers:
            return
        await self._subscribe_provider_balance()

    async def stop(self) -> None:
        unsubscribers = list(self._unsubscribers)
        self._unsubscribers.clear()
        pending: list[Any] = []
        for unsubscribe in unsubscribers:
            try:
                result = unsubscribe()
                if inspect.isawaitable(result):
                    pending.append(result)
            except Exception:
                logger.info("Realtime listener unsubscribe failed", exc_info=True)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _subscribe_provider_balance(self) -> None:
        async def _on_invalidation(envelope: dict) -> None:
            if envelope.get("name") != "provider.balance.updated":
                return
            self.provider_balance_service.invalidate_local_snapshot()

        unsubscribe = await self.bus.subscribe(
            kind=REALTIME_KIND_INVALIDATE,
            name="provider.balance.updated",
            scope=RealtimeScope(),
            callback=_on_invalidation,
        )
        self._unsubscribers.append(unsubscribe)
