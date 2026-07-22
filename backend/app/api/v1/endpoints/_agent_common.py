"""Shared SSE helpers for harness API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.db.session import AsyncSessionLocal
from app.services.agent_common.events import AgentEvent

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Background helpers
# ------------------------------------------------------------------

async def mark_usage_log_cancelled(parent_log_id: int | None) -> None:
    """Mark an interrupted agent usage log as cancelled using a fresh DB session."""
    if not parent_log_id:
        return
    try:
        from app.repositories.billing_repository import UsageLogRepository
        async with AsyncSessionLocal() as fresh_db:
            repo = UsageLogRepository(fresh_db)
            log = await repo.get(parent_log_id)
            if log and log.status == "pending":
                await repo.update(log, {"status": "cancelled"})
                for child in await repo.get_children(parent_log_id):
                    if child.status == "pending":
                        await repo.update(child, {"status": "cancelled"})
                logger.info("Marked interrupted usage log %s as cancelled", parent_log_id)
    except Exception:
        logger.warning("Failed to mark usage log %s as cancelled", parent_log_id, exc_info=True)


# ------------------------------------------------------------------
# Request helpers
# ------------------------------------------------------------------

def get_request_language(request: Request) -> str:
    """Infer agent language from the current request headers."""
    accept_lang = request.headers.get("accept-language", "zh-CN")
    return "en" if "en" in accept_lang.lower() else "zh"


def get_agent_session_factory(request: Request | object):
    app = getattr(request, "app", None)
    state = getattr(app, "state", None)
    session_factory = getattr(state, "db_session_factory", None)
    return session_factory or AsyncSessionLocal


def format_sse_data(payload: object) -> str:
    """Serialize an SSE data frame without changing the payload shape."""
    if isinstance(payload, str):
        data = payload
    else:
        data = json.dumps(payload, ensure_ascii=False)
    return f"data: {data}\n\n"


# ------------------------------------------------------------------
# SSE streaming via MessageBus
# ------------------------------------------------------------------

def stream_agent_events_via_bus(
    *,
    engine,
    conversation_id: int | str,
    producer_factory,
    on_error,
) -> StreamingResponse:
    """Generic SSE streamer for legacy agent engines and durable harness events.

    Requirements on *engine*:
      - engine.bus: MessageBus (optional — falls back to direct iteration)
      - engine.stream_completed: bool
      - engine.current_parent_usage_log_id: int | None
    """
    if not hasattr(engine, "bus"):
        async def event_stream_fallback():
            try:
                async for event in producer_factory():
                    yield format_sse_data(event.to_json())
                engine.stream_completed = True
            except Exception as e:
                engine.stream_completed = True
                logger.exception("Agent stream error")
                await on_error(e)
                error_event = json.dumps(
                    {"type": "error", "data": {"message": str(e)}},
                    ensure_ascii=False,
                )
                yield format_sse_data(error_event)

        async def on_stream_end_fallback():
            if not getattr(engine, "stream_completed", False):
                await mark_usage_log_cancelled(
                    getattr(engine, "current_parent_usage_log_id", None)
                )

        return StreamingResponse(
            event_stream_fallback(),
            media_type="text/event-stream",
            headers=_SSE_HEADERS,
            background=BackgroundTask(on_stream_end_fallback),
        )

    async def event_stream():
        async def _produce() -> None:
            try:
                async for event in producer_factory():
                    await engine.bus.publish_event(conversation_id, event)
            finally:
                with suppress(Exception):
                    await engine.bus.publish_event(conversation_id, AgentEvent("done", {}))

        producer_task = asyncio.create_task(_produce())

        try:
            async for event in engine.bus.subscribe_outbound(conversation_id):
                if event.type == "done":
                    break
                yield format_sse_data(event.to_json())
            await producer_task
            engine.stream_completed = True
        except Exception as e:
            engine.stream_completed = True
            logger.exception("Agent stream error")
            await on_error(e)
            error_event = json.dumps(
                {"type": "error", "data": {"message": str(e)}},
                ensure_ascii=False,
            )
            yield format_sse_data(error_event)
        finally:
            if not producer_task.done():
                producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
            engine.bus.unsubscribe(conversation_id)

    async def on_stream_end():
        if not engine.stream_completed:
            await mark_usage_log_cancelled(engine.current_parent_usage_log_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
        background=BackgroundTask(on_stream_end),
    )


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}
