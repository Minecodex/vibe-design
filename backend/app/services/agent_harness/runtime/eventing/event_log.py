from __future__ import annotations

import asyncio
import logging
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable

from app.core.config import CONVERSATION_EVENT_SEQUENCE_CACHE_MAX_ENTRIES
from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.conversation_events import (
    append_conversation_event,
    append_conversation_event_async,
)
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import publish_event_notification_sync
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import publish_transient_event_sync
from app.services.agent_harness.runtime.eventing.presentation_delta_queue import (
    enqueue_presentation_delta,
    should_async_persist_presentation_delta,
)
from app.services.agent_harness.runtime.presentation_v2.projection_store import project_committed_event

_SEQUENCE_CACHE: OrderedDict[tuple[int, str], int] = OrderedDict()
_SUBSCRIBERS: dict[tuple[int, str], list[Callable[[dict[str, Any]], None]]] = {}
_CACHE_LOCK = threading.Lock()
logger = logging.getLogger(__name__)


def _log_background_task_failure(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception:
        logger.warning("Background presentation delta enqueue failed", exc_info=True)


def _reserve_next_sequence(user_id: int, conversation_id: str) -> int:
    key = (user_id, conversation_id)
    with _CACHE_LOCK:
        current = _SEQUENCE_CACHE.get(key, 0) + 1
        _SEQUENCE_CACHE[key] = current
        _SEQUENCE_CACHE.move_to_end(key)
        max_entries = max(1, int(CONVERSATION_EVENT_SEQUENCE_CACHE_MAX_ENTRIES or 0))
        while len(_SEQUENCE_CACHE) > max_entries:
            _SEQUENCE_CACHE.popitem(last=False)
        return current


def clear_conversation_event_caches(user_id: int, conversation_id: str) -> None:
    with _CACHE_LOCK:
        key = (user_id, conversation_id)
        _SEQUENCE_CACHE.pop(key, None)
        _SUBSCRIBERS.pop(key, None)


def _snapshot_subscribers(
    user_id: int,
    conversation_id: str,
) -> tuple[Callable[[dict[str, Any]], None], ...]:
    with _CACHE_LOCK:
        return tuple(_SUBSCRIBERS.get((user_id, conversation_id), ()))


def _notify_subscribers(
    user_id: int,
    conversation_id: str,
    record: dict[str, Any],
) -> None:
    for callback in _snapshot_subscribers(user_id, conversation_id):
        try:
            callback(record)
        except Exception:
            logger.warning(
                "Event subscriber failed for conversation %s",
                conversation_id,
                exc_info=True,
            )


def _build_transient_record(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    event_type: str,
    payload: dict[str, Any],
    lane: str,
    block_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    sequence = _reserve_next_sequence(user_id, conversation_id)
    sanitized_payload = sanitize_persistent_payload(payload or {})
    record = {
        "seq": sequence,
        "sequence": sequence,
        "ts": datetime.now(timezone.utc).isoformat(),
        "conversation_id": conversation_id,
        "run_id": run_id,
        "type": event_type,
        "event_type": event_type,
        "lane": lane,
        "payload": sanitized_payload,
        "transient": True,
    }
    for field, value in (
        ("block_id", block_id),
        ("agent_id", agent_id),
        ("tool_call_id", tool_call_id),
        ("artifact_id", artifact_id),
        ("parent_block_id", parent_block_id),
    ):
        if value is not None:
            record[field] = value
    if idempotency_key is not None:
        record["idempotency_key"] = idempotency_key
    return record


def append_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    lane: str = "user",
    block_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    sanitized_payload = sanitize_persistent_payload(payload if payload is not None else (data or {}))
    if should_async_persist_presentation_delta(event_type=event_type, lane=lane):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            record = _build_transient_record(
                user_id,
                conversation_id,
                run_id=run_id,
                event_type=event_type,
                payload=sanitized_payload,
                lane=lane,
                block_id=block_id,
                agent_id=agent_id,
                tool_call_id=tool_call_id,
                artifact_id=artifact_id,
                parent_block_id=parent_block_id,
                idempotency_key=idempotency_key,
            )
            _notify_subscribers(user_id, conversation_id, record)
            try:
                publish_transient_event_sync(record)
            except Exception:
                logger.info("Conversation transient event fanout publish failed", exc_info=True)
            task = loop.create_task(
                enqueue_presentation_delta(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    event_type=event_type,
                    lane=lane,
                    payload=sanitized_payload,
                    block_id=block_id,
                    tool_call_id=tool_call_id,
                    parent_block_id=parent_block_id,
                    idempotency_key=idempotency_key,
                )
            )
            task.add_done_callback(_log_background_task_failure)
            return record
    try:
        record = append_conversation_event(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
    except FileNotFoundError:
        if str(lane or "user") == "user":
            logger.warning(
                "Failed to persist user-visible conversation event",
                exc_info=True,
            )
            raise
        logger.info(
            "Dropped non-user conversation event for unavailable conversation %s",
            conversation_id,
        )
        return _build_transient_record(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        if str(lane or "user") == "user":
            logger.warning(
                "Failed to persist user-visible conversation event",
                exc_info=True,
            )
            raise
        logger.warning(
            "Failed to persist conversation event; falling back to transient event",
            exc_info=True,
        )
        record = _build_transient_record(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
    if not record.get("transient"):
        if str(record.get("lane") or "user").strip().lower() == "user":
            project_committed_event(user_id, conversation_id, record)
        try:
            publish_event_notification_sync(record)
        except Exception:
            logger.info("Conversation event fanout publish failed after durable append", exc_info=True)
    _notify_subscribers(user_id, conversation_id, record)
    return record


async def append_event_async(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    lane: str = "user",
    block_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    sanitized_payload = sanitize_persistent_payload(payload if payload is not None else (data or {}))
    if should_async_persist_presentation_delta(event_type=event_type, lane=lane):
        record = _build_transient_record(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
        _notify_subscribers(user_id, conversation_id, record)
        try:
            publish_transient_event_sync(record)
        except Exception:
            logger.info("Conversation transient event fanout publish failed", exc_info=True)
        try:
            await enqueue_presentation_delta(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_id,
                event_type=event_type,
                lane=lane,
                payload=sanitized_payload,
                block_id=block_id,
                tool_call_id=tool_call_id,
                parent_block_id=parent_block_id,
                idempotency_key=idempotency_key,
            )
        except Exception:
            logger.warning("Failed to enqueue presentation delta for async persistence", exc_info=True)
        return record
    try:
        record = await append_conversation_event_async(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
    except FileNotFoundError:
        if str(lane or "user") == "user":
            logger.warning(
                "Failed to persist user-visible conversation event",
                exc_info=True,
            )
            raise
        logger.info(
            "Dropped non-user conversation event for unavailable conversation %s",
            conversation_id,
        )
        return _build_transient_record(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
    except Exception:
        if str(lane or "user") == "user":
            logger.warning(
                "Failed to persist user-visible conversation event",
                exc_info=True,
            )
            raise
        logger.warning(
            "Failed to persist conversation event; falling back to transient event",
            exc_info=True,
        )
        record = _build_transient_record(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type=event_type,
            payload=sanitized_payload,
            lane=lane,
            block_id=block_id,
            agent_id=agent_id,
            tool_call_id=tool_call_id,
            artifact_id=artifact_id,
            parent_block_id=parent_block_id,
            idempotency_key=idempotency_key,
        )
    if not record.get("transient"):
        if str(record.get("lane") or "user").strip().lower() == "user":
            project_committed_event(user_id, conversation_id, record)
        try:
            publish_event_notification_sync(record)
        except Exception:
            logger.info("Conversation event fanout publish failed after durable append", exc_info=True)
    _notify_subscribers(user_id, conversation_id, record)
    return record


def publish_transient_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    lane: str = "user",
    block_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    record = _build_transient_record(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=event_type,
        payload=payload if payload is not None else (data or {}),
        lane=lane,
        block_id=block_id,
        agent_id=agent_id,
        tool_call_id=tool_call_id,
        artifact_id=artifact_id,
        parent_block_id=parent_block_id,
        idempotency_key=idempotency_key,
    )
    _notify_subscribers(user_id, conversation_id, record)
    return record


def subscribe_to_events(
    user_id: int,
    conversation_id: str,
    callback: Callable[[dict[str, Any]], None],
) -> Callable[[], None]:
    key = (user_id, conversation_id)
    with _CACHE_LOCK:
        _SUBSCRIBERS.setdefault(key, []).append(callback)

    def unsubscribe() -> None:
        with _CACHE_LOCK:
            subscribers = _SUBSCRIBERS.get(key)
            if not subscribers:
                return
            try:
                subscribers.remove(callback)
            except ValueError:
                return
            if not subscribers:
                _SUBSCRIBERS.pop(key, None)

    return unsubscribe
