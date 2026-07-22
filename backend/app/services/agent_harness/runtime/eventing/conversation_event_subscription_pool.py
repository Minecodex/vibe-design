from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from app.services.realtime_bus import (
    REALTIME_KIND_NOTIFY,
    RealtimeBus,
    RealtimeScope,
)

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], Any]
SubscribeFn = Callable[[int, str, EventCallback], Awaitable[Callable[[], Any]]]


@dataclass
class _PerConversationSubscription:
    callbacks: list[EventCallback] = field(default_factory=list)
    redis_unsubscribe: Callable[[], Any] | None = None


class ConversationEventSubscriptionPool:
    """Process-level fanout layer for per-conversation realtime notifications.

    Multiple SSE connections to the same (user_id, conversation_id) share a
    single Redis pubsub subscription. The first subscriber opens the Redis
    channel; the last one closes it. Internal lock serialises subscribe /
    unsubscribe so the open / close transitions are not racy.
    """

    def __init__(
        self,
        *,
        bus: RealtimeBus | None = None,
        notification_name: str = "conversation.event.appended",
        log_label: str = "conversation event",
        subscribe_fn: SubscribeFn | None = None,
    ) -> None:
        self._explicit_bus = bus
        self._notification_name = str(notification_name)
        self._log_label = str(log_label)
        self._subscribe_fn = subscribe_fn
        self._entries: dict[tuple[int, str], _PerConversationSubscription] = {}
        self._lock = asyncio.Lock()

    def _resolve_bus(self) -> RealtimeBus:
        return self._explicit_bus if self._explicit_bus is not None else RealtimeBus()

    async def subscribe(
        self,
        user_id: int,
        conversation_id: str,
        callback: EventCallback,
    ) -> Callable[[], Awaitable[None]]:
        key = (int(user_id), str(conversation_id))

        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                entry = _PerConversationSubscription()
                self._entries[key] = entry

                async def _fanout(envelope: dict[str, Any]) -> None:
                    # Snapshot callbacks to tolerate concurrent subscribe /
                    # unsubscribe while dispatching. The list mutation only
                    # happens under the pool lock, so a shallow copy is safe.
                    for cb in list(entry.callbacks):
                        try:
                            result = cb(envelope)
                            if inspect.isawaitable(result):
                                await result
                        except Exception:
                            logger.info(
                                "%s fanout callback failed",
                                self._log_label,
                                exc_info=True,
                            )

                if self._subscribe_fn is not None:
                    entry.redis_unsubscribe = await self._subscribe_fn(
                        int(user_id),
                        str(conversation_id),
                        _fanout,
                    )
                else:
                    entry.redis_unsubscribe = await self._resolve_bus().subscribe(
                        kind=REALTIME_KIND_NOTIFY,
                        name=self._notification_name,
                        scope=RealtimeScope(
                            user_id=int(user_id),
                            conversation_id=str(conversation_id),
                        ),
                        callback=_fanout,
                    )
            entry.callbacks.append(callback)

        async def unsubscribe() -> None:
            await self._detach(key, callback)

        return unsubscribe

    async def _detach(
        self,
        key: tuple[int, str],
        callback: EventCallback,
    ) -> None:
        redis_unsubscribe: Callable[[], Any] | None = None
        async with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return
            try:
                entry.callbacks.remove(callback)
            except ValueError:
                return
            if entry.callbacks:
                return
            # Last callback gone: tear down the shared Redis subscription.
            self._entries.pop(key, None)
            redis_unsubscribe = entry.redis_unsubscribe
        if redis_unsubscribe is None:
            return
        try:
            result = redis_unsubscribe()
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.info(
                "%s Redis unsubscribe failed",
                self._log_label,
                exc_info=True,
            )

    def active_conversation_count(self) -> int:
        return len(self._entries)


_POOL: ConversationEventSubscriptionPool | None = None
_RUNTIME_POOL: ConversationEventSubscriptionPool | None = None
_TRANSIENT_POOL: ConversationEventSubscriptionPool | None = None


def get_conversation_event_subscription_pool() -> ConversationEventSubscriptionPool:
    global _POOL
    if _POOL is None:
        _POOL = ConversationEventSubscriptionPool()
    return _POOL


def get_conversation_runtime_subscription_pool() -> ConversationEventSubscriptionPool:
    global _RUNTIME_POOL
    if _RUNTIME_POOL is None:
        _RUNTIME_POOL = ConversationEventSubscriptionPool(
            notification_name="conversation.runtime.updated",
            log_label="conversation runtime",
        )
    return _RUNTIME_POOL


def get_conversation_transient_subscription_pool() -> ConversationEventSubscriptionPool:
    global _TRANSIENT_POOL
    if _TRANSIENT_POOL is None:
        _TRANSIENT_POOL = ConversationEventSubscriptionPool(
            notification_name="conversation.event.transient",
            log_label="conversation transient event",
        )
    return _TRANSIENT_POOL


def reset_conversation_event_subscription_pool_for_tests() -> None:
    global _POOL, _RUNTIME_POOL, _TRANSIENT_POOL
    _POOL = None
    _RUNTIME_POOL = None
    _TRANSIENT_POOL = None
