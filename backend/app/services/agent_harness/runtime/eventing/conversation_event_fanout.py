from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.core.config import EVENT_NOTIFICATION_COALESCE_TYPES, settings
from app.core.redis_coordination import get_redis_coordinator
from app.services.agent_harness.runtime.eventing import notification_coalescer
from app.services.agent_harness.runtime.eventing.conversation_event_subscription_pool import (
    get_conversation_event_subscription_pool,
    get_conversation_runtime_subscription_pool,
    get_conversation_transient_subscription_pool,
)
from app.services.realtime_bus import (
    RealtimeBus,
    RealtimeResource,
    RealtimeScope,
    publish_notification,
)

logger = logging.getLogger(__name__)


def _event_lane(record: dict[str, Any]) -> str:
    return str(record.get("lane") or "user").strip().lower() or "user"


def build_event_notification(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_id": str(record.get("conversation_id") or ""),
        "user_id": int(record.get("user_id") or 0),
        "sequence": int(record.get("sequence") or record.get("seq") or 0),
        "event_type": str(record.get("event_type") or record.get("type") or ""),
        "run_id": record.get("run_id"),
        "lane": _event_lane(record),
    }


async def _publish_envelope(envelope: dict[str, Any]) -> None:
    user_id = int(envelope.get("user_id") or 0)
    conversation_id = str(envelope.get("conversation_id") or "")
    sequence = int(envelope.get("sequence") or 0)
    if not user_id or not conversation_id or not sequence:
        return
    await publish_notification(
        "conversation.event.appended",
        scope=RealtimeScope(user_id=user_id, conversation_id=conversation_id),
        resource=RealtimeResource(
            type="conversation_event",
            id=conversation_id,
            version=str(sequence),
        ),
        reason=str(envelope.get("event_type") or "event_appended"),
        worker="harness",
        metadata={"lane": _event_lane(envelope)},
        bus=RealtimeBus(get_redis_coordinator()),
    )


async def publish_event_notification(record: dict[str, Any]) -> None:
    await _publish_envelope(build_event_notification(record))


def build_transient_event_notification(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "conversation_id": str(record.get("conversation_id") or ""),
        "user_id": int(record.get("user_id") or 0),
        "event": dict(record or {}),
    }


async def publish_transient_event(record: dict[str, Any], *, bus: RealtimeBus | None = None) -> None:
    envelope = build_transient_event_notification(record)
    user_id = int(envelope.get("user_id") or 0)
    conversation_id = str(envelope.get("conversation_id") or "")
    if not user_id or not conversation_id:
        return
    await publish_notification(
        "conversation.event.transient",
        scope=RealtimeScope(user_id=user_id, conversation_id=conversation_id),
        resource=RealtimeResource(
            type="conversation_transient_event",
            id=conversation_id,
        ),
        reason=str((envelope.get("event") or {}).get("event_type") or "transient_event"),
        worker="harness",
        metadata={"event_type": str((envelope.get("event") or {}).get("event_type") or "transient_event")},
        extra_payload={"event": envelope["event"]},
        bus=bus or RealtimeBus(get_redis_coordinator()),
    )


async def publish_runtime_notification(
    user_id: int,
    conversation_id: str,
    *,
    reason: str = "runtime_updated",
) -> None:
    await publish_notification(
        "conversation.runtime.updated",
        scope=RealtimeScope(user_id=int(user_id), conversation_id=str(conversation_id)),
        resource=RealtimeResource(
            type="conversation_runtime",
            id=str(conversation_id),
        ),
        reason=reason,
        worker="harness",
        bus=RealtimeBus(get_redis_coordinator()),
    )


def publish_event_notification_sync(record: dict[str, Any]) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # DB/threadpool paths must not create throwaway event loops or Redis
        # pools. Async callers publish after the durable write returns.
        return None

    if settings.EVENT_NOTIFICATION_COALESCE_ENABLED:
        coalescer = notification_coalescer.get_or_create_for_running_loop(
            publish=_publish_envelope,
            window_seconds=max(int(settings.EVENT_NOTIFICATION_COALESCE_WINDOW_MS), 0) / 1000.0,
            coalesce_types=EVENT_NOTIFICATION_COALESCE_TYPES,
        )
        if coalescer is not None:
            try:
                coalescer.submit(build_event_notification(record))
            except Exception:
                logger.info("Conversation event coalescer submit failed", exc_info=True)
            return None

    task = loop.create_task(publish_event_notification(record))

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Conversation event fanout publish failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


def publish_transient_event_sync(record: dict[str, Any]) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None

    task = loop.create_task(publish_transient_event(record))

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Conversation transient event publish failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


def publish_runtime_notification_sync(
    user_id: int,
    conversation_id: str,
    *,
    reason: str = "runtime_updated",
) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # DB/threadpool paths must not create throwaway event loops or Redis
        # pools. Async callers publish after the durable write returns.
        return None

    task = loop.create_task(
        publish_runtime_notification(
            user_id,
            conversation_id,
            reason=reason,
        )
    )

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Conversation runtime fanout publish failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


async def subscribe_event_notifications(
    user_id: int,
    conversation_id: str,
    callback: Callable[[dict[str, Any]], Any],
) -> Callable[[], Any]:
    # All conversation event subscribers within this process share a single
    # Redis pubsub subscription per (user_id, conversation_id) via the pool.
    return await get_conversation_event_subscription_pool().subscribe(
        int(user_id),
        str(conversation_id),
        callback,
    )


async def subscribe_transient_event_notifications(
    user_id: int,
    conversation_id: str,
    callback: Callable[[dict[str, Any]], Any],
) -> Callable[[], Any]:
    return await get_conversation_transient_subscription_pool().subscribe(
        int(user_id),
        str(conversation_id),
        callback=callback,
    )


async def subscribe_runtime_notifications(
    user_id: int,
    conversation_id: str,
    callback: Callable[[dict[str, Any]], Any],
) -> Callable[[], Any]:
    # Runtime state subscribers share a single Redis pubsub subscription per
    # (user_id, conversation_id), matching event-log notification fanout.
    return await get_conversation_runtime_subscription_pool().subscribe(
        int(user_id),
        str(conversation_id),
        callback=callback,
    )
