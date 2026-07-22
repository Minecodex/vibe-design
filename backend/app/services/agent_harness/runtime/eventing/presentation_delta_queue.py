from __future__ import annotations

import asyncio
import logging
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any

from app.core.config import (
    HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS,
    HARNESS_PRESENTATION_DELTA_PERSIST_MAX_BATCH_SIZE,
    HARNESS_PRESENTATION_DELTA_PERSIST_MAX_MERGED_CHARS,
    HARNESS_PRESENTATION_DELTA_PERSIST_QUEUE_MAX_SIZE,
    settings,
)
from app.services.agent_harness.runtime.conversation_events import append_conversation_event
from app.services.agent_harness.runtime.presentation_v2.projection_store import project_committed_event
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import publish_event_notification_sync

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class PendingPresentationDelta:
    user_id: int
    conversation_id: str
    run_id: str | None
    event_type: str
    lane: str
    payload: dict[str, Any]
    block_id: str | None
    tool_call_id: str | None
    parent_block_id: str | None
    idempotency_key: str | None
    created_at: float
    retry_count: int = 0


_PENDING: OrderedDict[tuple[Any, ...], PendingPresentationDelta] = OrderedDict()
_READY: deque[PendingPresentationDelta] = deque()
_LOCK = asyncio.Lock()
_WORKER_TASK: asyncio.Task | None = None
_WAKE_EVENT: asyncio.Event | None = None
_CLOSED = False


def should_async_persist_presentation_delta(*, event_type: str, lane: str) -> bool:
    return (
        bool(getattr(settings, "HARNESS_PRESENTATION_DELTA_ASYNC_PERSIST_ENABLED", True))
        and str(event_type or "") == "presentation.block.delta"
        and str(lane or "user").strip().lower() == "user"
    )


async def enqueue_presentation_delta(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str | None,
    event_type: str,
    lane: str,
    payload: dict[str, Any],
    block_id: str | None = None,
    tool_call_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    if _CLOSED:
        return
    _ensure_worker()
    item = PendingPresentationDelta(
        user_id=int(user_id),
        conversation_id=str(conversation_id),
        run_id=run_id,
        event_type=str(event_type),
        lane=str(lane or "user"),
        payload=dict(payload or {}),
        block_id=block_id,
        tool_call_id=tool_call_id,
        parent_block_id=parent_block_id,
        idempotency_key=idempotency_key,
        created_at=time.monotonic(),
    )
    async with _LOCK:
        _enqueue_locked(item)
        _trim_locked()
        if _pending_count_locked() >= _max_batch_size():
            _move_pending_to_ready_locked(limit=_max_batch_size())
    _wake()


async def aclose(*, flush: bool = True, timeout: float = 5.0) -> None:
    global _CLOSED, _WORKER_TASK, _WAKE_EVENT
    _CLOSED = True
    if flush:
        try:
            await asyncio.wait_for(flush_pending(), timeout=max(float(timeout or 0), 0.1))
        except Exception:
            logger.warning("Presentation delta queue shutdown flush failed", exc_info=True)
    task = _WORKER_TASK
    _WORKER_TASK = None
    _WAKE_EVENT = None
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


async def flush_pending() -> None:
    async with _LOCK:
        _move_pending_to_ready_locked()
        batch = _drain_ready_locked(limit=_max_batch_size())
    while batch:
        await asyncio.to_thread(_persist_batch, batch)
        async with _LOCK:
            batch = _drain_ready_locked(limit=_max_batch_size())


def metrics_snapshot() -> dict[str, int]:
    return {
        "pending": len(_PENDING),
        "ready": len(_READY),
        "closed": int(_CLOSED),
    }


def reset_for_tests() -> None:
    global _CLOSED, _WORKER_TASK, _WAKE_EVENT
    _PENDING.clear()
    _READY.clear()
    _CLOSED = False
    _WORKER_TASK = None
    _WAKE_EVENT = None


def _ensure_worker() -> None:
    global _WORKER_TASK, _WAKE_EVENT
    if _WORKER_TASK is not None and not _WORKER_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _WAKE_EVENT = asyncio.Event()
    _WORKER_TASK = loop.create_task(_worker_loop(), name="presentation-delta-persist-queue")


async def _worker_loop() -> None:
    while True:
        interval = _flush_interval()
        wake = _WAKE_EVENT
        try:
            if wake is None:
                await asyncio.sleep(interval)
            else:
                try:
                    await asyncio.wait_for(wake.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
                wake.clear()
            async with _LOCK:
                _move_pending_to_ready_locked(limit=_max_batch_size())
                batch = _drain_ready_locked(limit=_max_batch_size())
            if batch:
                await asyncio.to_thread(_persist_batch, batch)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Presentation delta queue iteration failed", exc_info=True)
            await asyncio.sleep(interval)


def _enqueue_locked(item: PendingPresentationDelta) -> None:
    key = _merge_key(item)
    existing = _PENDING.get(key)
    if existing is None:
        _PENDING[key] = item
        return
    max_chars = _max_merged_chars()
    current_delta = str(existing.payload.get("delta") or "")
    incoming_delta = str(item.payload.get("delta") or "")
    if len(current_delta) + len(incoming_delta) > max_chars:
        _READY.append(existing)
        _PENDING[key] = item
        return
    merged_payload = dict(item.payload)
    merged_payload["delta"] = current_delta + incoming_delta
    existing.payload = merged_payload
    existing.idempotency_key = None
    _PENDING.move_to_end(key)


def _trim_locked() -> None:
    max_size = _queue_max_size()
    while _pending_count_locked() > max_size and _PENDING:
        _key, dropped = _PENDING.popitem(last=False)
        logger.warning(
            "Dropped presentation delta under queue pressure: conversation_id=%s block_id=%s",
            dropped.conversation_id,
            dropped.block_id,
        )


def _move_pending_to_ready_locked(*, limit: int | None = None) -> None:
    remaining = limit if limit is not None else len(_PENDING)
    while remaining is None or remaining > 0:
        if not _PENDING:
            break
        _key, item = _PENDING.popitem(last=False)
        _READY.append(item)
        if remaining is not None:
            remaining -= 1


def _drain_ready_locked(*, limit: int) -> list[PendingPresentationDelta]:
    batch: list[PendingPresentationDelta] = []
    capped = max(int(limit or 1), 1)
    while _READY and len(batch) < capped:
        batch.append(_READY.popleft())
    return batch


def _persist_batch(batch: list[PendingPresentationDelta]) -> None:
    failed: list[PendingPresentationDelta] = []
    for item in batch:
        persisted = False
        for attempt in range(int(item.retry_count or 0), 2):
            try:
                item.retry_count = attempt
                record = append_conversation_event(
                    item.user_id,
                    item.conversation_id,
                    run_id=item.run_id,
                    event_type=item.event_type,
                    payload=item.payload,
                    lane=item.lane,
                    block_id=item.block_id,
                    tool_call_id=item.tool_call_id,
                    parent_block_id=item.parent_block_id,
                    idempotency_key=item.idempotency_key,
                )
                if str(record.get("lane") or "user").strip().lower() == "user":
                    project_committed_event(item.user_id, item.conversation_id, record)
                try:
                    publish_event_notification_sync(record)
                except Exception:
                    logger.info("Conversation event fanout publish failed after delta queue append", exc_info=True)
                persisted = True
                break
            except Exception:
                logger.warning(
                    "Failed to persist presentation delta: conversation_id=%s block_id=%s attempt=%s",
                    item.conversation_id,
                    item.block_id,
                    attempt + 1,
                    exc_info=True,
                )
        if not persisted:
            failed.append(item)
    if failed:
        logger.warning("Dropped %s presentation delta events after retry failure", len(failed))


def _merge_key(item: PendingPresentationDelta) -> tuple[Any, ...]:
    return (
        item.user_id,
        item.conversation_id,
        item.run_id,
        item.block_id,
        item.parent_block_id,
        item.tool_call_id,
        str(item.payload.get("field") or ""),
    )


def _wake() -> None:
    if _WAKE_EVENT is not None:
        _WAKE_EVENT.set()


def _pending_count_locked() -> int:
    return len(_PENDING) + len(_READY)


def _flush_interval() -> float:
    return max(float(HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS), 0.05)


def _max_batch_size() -> int:
    return max(int(HARNESS_PRESENTATION_DELTA_PERSIST_MAX_BATCH_SIZE), 1)


def _queue_max_size() -> int:
    return max(int(HARNESS_PRESENTATION_DELTA_PERSIST_QUEUE_MAX_SIZE), 1)


def _max_merged_chars() -> int:
    return max(int(HARNESS_PRESENTATION_DELTA_PERSIST_MAX_MERGED_CHARS), 512)
