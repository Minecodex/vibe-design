from __future__ import annotations

import asyncio
import inspect
from functools import partial
from collections.abc import AsyncGenerator, Callable
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.api.v1.endpoints._agent_common import format_sse_data
from app.services.project_access_service import ProjectAccessService
from app.services.realtime_bus import REALTIME_KIND_NOTIFY, RealtimeBus, RealtimeScope
from app.core.config import SSE_REALTIME_QUEUE_MAX_SIZE
from app.services.sse_queue import bounded_queue, put_coalesced_nowait

router = APIRouter(prefix="/realtime", tags=["realtime"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


@router.get("/events")
async def stream_realtime_events(
    request: Request,
    db: DbSession,
    user: CurrentUser,
    project_id: int | None = None,
) -> StreamingResponse:
    if project_id is not None:
        await ProjectAccessService(db).ensure_can_read_project(
            project_id=project_id,
            user_id=user.id,
            is_admin=(user.role == "admin"),
        )
    return StreamingResponse(
        _event_stream(request, user_id=user.id, project_id=project_id),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


async def _event_stream(
    request: Request,
    *,
    user_id: int,
    project_id: int | None,
) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[dict] = bounded_queue(SSE_REALTIME_QUEUE_MAX_SIZE)
    loop = asyncio.get_running_loop()
    unsubscribers: list[Callable[[], Any]] = []
    bus = RealtimeBus()

    def _enqueue(envelope: dict) -> None:
        if envelope.get("name") != "asset.preview.updated":
            return
        loop.call_soon_threadsafe(
            partial(put_coalesced_nowait, queue, dict(envelope), name="realtime.asset.preview.updated")
        )

    unsubscribers.append(
        await bus.subscribe(
            kind=REALTIME_KIND_NOTIFY,
            name="asset.preview.updated",
            scope=RealtimeScope(user_id=int(user_id)),
            callback=_enqueue,
        )
    )
    if project_id is not None:
        unsubscribers.append(
            await bus.subscribe(
                kind=REALTIME_KIND_NOTIFY,
                name="asset.preview.updated",
                scope=RealtimeScope(project_id=int(project_id)),
                callback=_enqueue,
            )
        )

    try:
        yield format_sse_data({"type": "realtime_ready"})
        while True:
            if await request.is_disconnected():
                break
            try:
                envelope = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            yield format_sse_data({"type": "realtime_notification", "data": envelope})
    finally:
        pending: list[Any] = []
        for unsubscribe in unsubscribers:
            result = unsubscribe()
            if inspect.isawaitable(result):
                pending.append(result)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
