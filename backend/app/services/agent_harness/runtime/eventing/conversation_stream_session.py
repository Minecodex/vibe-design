from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncGenerator, Callable
from functools import partial
from typing import Any

from app.api.v1.endpoints._agent_common import format_sse_data
from app.core.config import SSE_CONVERSATION_MARKER_QUEUE_MAX_SIZE
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import (
    subscribe_event_notifications,
    subscribe_runtime_notifications,
    subscribe_transient_event_notifications,
)
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    PROTOCOL_ERROR,
    TERMINAL_TURN_STATUSES,
    is_turn_completed_event,
)
from app.services.agent_harness.runtime.presentation_v2.protocol import presentation_event
from app.services.agent_harness.runtime.presentation_v2.reducer import reduce_event_to_ops
from app.services.sse_queue import bounded_queue, put_marker_nowait


_ACTIVE_STREAM_COUNT = 0
_MISSING_TURN_COMPLETED_RECONCILE_SECONDS = 2.0
_CONTROL_EVENT_TYPES = {
    "run_started",
    "turn_started",
    "turn_completed",
    "message_error",
    PROTOCOL_ERROR,
}


def active_conversation_sse_count() -> int:
    return _ACTIVE_STREAM_COUNT


def _should_emit_control_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or event.get("event_type") or "")
    return event_type in _CONTROL_EVENT_TYPES


async def stream_conversation_events(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    transient_queue: asyncio.Queue[dict] | None = None,
    unsubscribe: Callable[[], None] | None = None,
    status_poll_seconds: float = 5.0,
    reconcile_interval_seconds: float = 60.0,
    missing_turn_completed_reconcile_seconds: float = _MISSING_TURN_COMPLETED_RECONCILE_SECONDS,
) -> AsyncGenerator[str, None]:
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_runtime_state
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events
    from app.services.agent_harness.runtime.eventing.event_log import subscribe_to_events

    global _ACTIVE_STREAM_COUNT

    redis_unsubscribe: Callable[[], Any] | None = None
    transient_redis_unsubscribe: Callable[[], Any] | None = None
    runtime_unsubscribe: Callable[[], Any] | None = None
    if transient_queue is None or unsubscribe is None:
        loop = asyncio.get_running_loop()
        transient_queue = bounded_queue(SSE_CONVERSATION_MARKER_QUEUE_MAX_SIZE)

        def _on_event(event: dict) -> None:
            if str(event.get("lane") or "user").strip().lower() != "user":
                return
            if event.get("transient"):
                enqueue_live_user_event(loop, transient_queue, {"kind": "transient_event", "event": event})
                return
            enqueue_live_user_event(loop, transient_queue, {"lane": "user"})

        def _on_redis_event_notification(notification: dict[str, Any]) -> None:
            if not isinstance(notification, dict):
                return
            metadata = notification.get("metadata")
            lane = metadata.get("lane") if isinstance(metadata, dict) else notification.get("lane")
            if str(lane or "").strip().lower() != "user":
                return
            enqueue_live_user_event(loop, transient_queue, {"lane": "user"})

        unsubscribe = subscribe_to_events(user_id, conversation_id, _on_event)
        redis_unsubscribe = await subscribe_event_notifications(
            user_id,
            conversation_id,
            _on_redis_event_notification,
        )
        transient_redis_unsubscribe = await subscribe_transient_event_notifications(
            user_id,
            conversation_id,
            lambda notification: enqueue_live_user_event(
                loop,
                transient_queue,
                {"kind": "transient_event", "event": (notification.get("metadata") or {}).get("event") or notification.get("event")},
            ),
        )
        runtime_unsubscribe = await subscribe_runtime_notifications(
            user_id,
            conversation_id,
            lambda _notification: enqueue_live_user_event(loop, transient_queue, {"kind": "runtime"}),
        )

    _ACTIVE_STREAM_COUNT += 1

    try:
        initial_runtime_state = get_runtime_state(user_id, conversation_id)
        initial_runtime_status = (
            str(initial_runtime_state.get("runtime_status") or "")
            if isinstance(initial_runtime_state, dict)
            else ""
        ) or "running"
        yield format_sse_data({
            "type": "run_preparing",
            "conversation_id": conversation_id,
            "lane": "user",
            "payload": {
                "conversation_id": conversation_id,
                "runtime_status": initial_runtime_status,
            },
        })

        last_sequence = max(0, int(after_sequence or 0))
        saw_turn_completed = False

        async def _emit_persisted_events() -> AsyncGenerator[str, None]:
            nonlocal last_sequence, saw_turn_completed
            for event in load_conversation_events(
                user_id,
                conversation_id,
                after_sequence=last_sequence,
            ):
                if str(event.get("lane") or "user").strip().lower() != "user":
                    continue
                sequence = event.get("sequence")
                if isinstance(sequence, int):
                    last_sequence = max(last_sequence, sequence)
                if is_turn_completed_event(event):
                    saw_turn_completed = True
                ops = reduce_event_to_ops(event)
                if ops:
                    for op in ops:
                        yield format_sse_data(presentation_event(op))
                if _should_emit_control_event(event):
                    yield format_sse_data(event)

        def _event_at_cursor() -> dict[str, Any] | None:
            if last_sequence <= 0:
                return None
            events = load_conversation_events(
                user_id,
                conversation_id,
                after_sequence=last_sequence - 1,
                limit=1,
            )
            if not events:
                return None
            event = events[0]
            if (
                int(event.get("sequence") or 0) == last_sequence
            ):
                return event
            return None

        async def _collect_queue_markers(first: dict | None = None) -> tuple[bool, bool, list[dict[str, Any]]]:
            has_event_notification = False
            has_runtime_notification = False
            transient_events: list[dict[str, Any]] = []
            pending = [first] if first is not None else []
            while True:
                try:
                    pending.append(transient_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            for item in pending:
                if not isinstance(item, dict):
                    continue
                if str(item.get("kind") or "") == "runtime":
                    has_runtime_notification = True
                    continue
                if str(item.get("kind") or "") == "transient_event":
                    event = item.get("event") if isinstance(item.get("event"), dict) else None
                    if event is not None:
                        transient_events.append(event)
                    continue
                if str(item.get("lane") or "user").strip().lower() == "user":
                    has_event_notification = True
            return has_event_notification, has_runtime_notification, transient_events

        async def _emit_transient_events(events: list[dict[str, Any]]) -> AsyncGenerator[str, None]:
            for event in events:
                if str(event.get("lane") or "user").strip().lower() != "user":
                    continue
                event = dict(event)
                event["transient"] = True
                for op in reduce_event_to_ops(event):
                    op = dict(op)
                    op["transient"] = True
                    yield format_sse_data(presentation_event(op))

        async def _refresh_runtime_state(current: dict[str, Any] | None) -> dict[str, Any] | None:
            refreshed = get_runtime_state(user_id, conversation_id)
            return refreshed if refreshed is not None else current

        runtime_state = initial_runtime_state
        loop = asyncio.get_running_loop()
        last_reconcile_at = loop.time()
        terminal_state_first_seen_at: float | None = None
        async for chunk in _emit_persisted_events():
            yield chunk
        if saw_turn_completed:
            return
        cursor_event = _event_at_cursor()
        if cursor_event is not None and str(cursor_event.get("lane") or "user").strip().lower() == "user":
            for op in reduce_event_to_ops(cursor_event):
                yield format_sse_data(presentation_event(op))
            if is_turn_completed_event(cursor_event):
                yield format_sse_data(cursor_event)
                return

        while True:
            if runtime_state is None:
                break

            runtime_status = str(runtime_state.get("runtime_status") or "").lower()
            if runtime_status in TERMINAL_TURN_STATUSES:
                if terminal_state_first_seen_at is None:
                    terminal_state_first_seen_at = loop.time()
                async for chunk in _emit_persisted_events():
                    yield chunk
                if saw_turn_completed:
                    break
                elapsed = loop.time() - terminal_state_first_seen_at
                if elapsed >= max(float(missing_turn_completed_reconcile_seconds), 0.0):
                    yield format_sse_data(
                        {
                            "type": PROTOCOL_ERROR,
                            "conversation_id": conversation_id,
                            "lane": "user",
                            "payload": {
                                "conversation_id": conversation_id,
                                "reason": "missing_turn_completed",
                                "runtime_status": runtime_status,
                            },
                        }
                    )
                    break
            else:
                terminal_state_first_seen_at = None

            try:
                marker = await asyncio.wait_for(transient_queue.get(), timeout=status_poll_seconds)
            except asyncio.TimeoutError:
                if loop.time() - last_reconcile_at >= max(float(reconcile_interval_seconds), 0.1):
                    runtime_state = await _refresh_runtime_state(runtime_state)
                    async for chunk in _emit_persisted_events():
                        yield chunk
                    if saw_turn_completed:
                        break
                    last_reconcile_at = loop.time()
                else:
                    yield ": keepalive\n\n"
                continue
            has_event, has_runtime, transient_events = await _collect_queue_markers(marker)
            async for chunk in _emit_transient_events(transient_events):
                yield chunk
            if has_runtime:
                runtime_state = await _refresh_runtime_state(runtime_state)
            if has_event:
                async for chunk in _emit_persisted_events():
                    yield chunk
                if saw_turn_completed:
                    break
                continue
    finally:
        _ACTIVE_STREAM_COUNT = max(_ACTIVE_STREAM_COUNT - 1, 0)
        unsubscribe()
        if redis_unsubscribe is not None:
            result = redis_unsubscribe()
            if inspect.isawaitable(result):
                await asyncio.gather(result, return_exceptions=True)
        if transient_redis_unsubscribe is not None:
            result = transient_redis_unsubscribe()
            if inspect.isawaitable(result):
                await asyncio.gather(result, return_exceptions=True)
        if runtime_unsubscribe is not None:
            result = runtime_unsubscribe()
            if inspect.isawaitable(result):
                await asyncio.gather(result, return_exceptions=True)


def enqueue_live_user_event(
    loop: asyncio.AbstractEventLoop,
    transient_queue: asyncio.Queue[dict],
    event: dict,
) -> None:
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    if current_loop is loop:
        put_marker_nowait(transient_queue, event, name="conversation.marker")
        return

    loop.call_soon_threadsafe(partial(put_marker_nowait, transient_queue, event, name="conversation.marker"))
