from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.core.redis_coordination import get_redis_coordinator
from app.services.agent_harness.runtime.eventing.conversation_event_subscription_pool import (
    ConversationEventSubscriptionPool,
)

logger = logging.getLogger(__name__)


def _cancel_topic(user_id: int, conversation_id: str) -> str:
    coordinator = get_redis_coordinator()
    return coordinator.keys.build(
        domain="agent-run",
        purpose="cancel",
        resource_parts=[str(int(user_id)), str(conversation_id)],
    )


async def _subscribe_cancel_topic(
    user_id: int,
    conversation_id: str,
    callback: Callable[[dict[str, Any]], Any],
) -> Callable[[], Any]:
    topic = _cancel_topic(int(user_id), str(conversation_id))
    return await get_redis_coordinator().subscribe(topic, callback)


_CANCEL_POOL: ConversationEventSubscriptionPool | None = None


def _get_cancel_pool() -> ConversationEventSubscriptionPool:
    global _CANCEL_POOL
    if _CANCEL_POOL is None:
        _CANCEL_POOL = ConversationEventSubscriptionPool(
            log_label="agent run cancel signal",
            subscribe_fn=_subscribe_cancel_topic,
        )
    return _CANCEL_POOL


def reset_cancel_signal_pool_for_tests() -> None:
    global _CANCEL_POOL
    _CANCEL_POOL = None


async def publish_cancel_signal(user_id: int, conversation_id: str) -> dict[str, Any]:
    return await get_redis_coordinator().publish(
        _cancel_topic(user_id, conversation_id),
        {
            "type": "cancel_requested",
            "user_id": int(user_id),
            "conversation_id": str(conversation_id),
        },
    )


def publish_cancel_signal_sync(user_id: int, conversation_id: str) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Threadpool callers must not create throwaway event loops or Redis pools.
        return None

    task = loop.create_task(publish_cancel_signal(user_id, conversation_id))

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Agent run cancel signal publish failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


async def wait_cancel_signal(user_id: int, conversation_id: str, *, timeout_seconds: float) -> dict[str, Any]:
    event = asyncio.Event()
    payload: dict[str, Any] = {}

    async def _on_signal(envelope: dict[str, Any]) -> None:
        payload.update(envelope)
        event.set()

    unsubscribe = await _get_cancel_pool().subscribe(int(user_id), str(conversation_id), _on_signal)
    try:
        try:
            await asyncio.wait_for(event.wait(), timeout=max(float(timeout_seconds), 0.0))
        except asyncio.TimeoutError:
            return {"woken": False}
        return {"woken": True, "payload": dict(payload)}
    finally:
        await unsubscribe()
