from __future__ import annotations

import asyncio
import logging

from app.core.config import SSE_QUEUE_OVERFLOW_LOG_INTERVAL_SECONDS

logger = logging.getLogger(__name__)
_LAST_OVERFLOW_LOG_AT: dict[str, float] = {}


def bounded_queue(max_size: int) -> asyncio.Queue[dict]:
    return asyncio.Queue(maxsize=max(1, int(max_size or 1)))


def _queue_max_size(queue: asyncio.Queue[dict]) -> int:
    return int(getattr(queue, "maxsize", 0) or 0)


def _marker_kind(marker: dict) -> str:
    if not isinstance(marker, dict):
        return "marker"
    kind = str(marker.get("kind") or "").strip().lower()
    if kind:
        return kind
    lane = str(marker.get("lane") or "").strip().lower()
    if lane == "user":
        return "user"
    if lane:
        return f"lane:{lane}"
    return "marker"


def _log_overflow_once(
    name: str,
    loop: asyncio.AbstractEventLoop,
    *,
    kind: str | None = None,
    queue_size: int | None = None,
    max_size: int | None = None,
) -> None:
    interval = max(1.0, float(SSE_QUEUE_OVERFLOW_LOG_INTERVAL_SECONDS or 30))
    now = loop.time()
    last = _LAST_OVERFLOW_LOG_AT.get(name, 0.0)
    if now - last >= interval:
        _LAST_OVERFLOW_LOG_AT[name] = now
        logger.warning(
            "SSE queue overflow; coalescing pending events name=%s kind=%s queue_size=%s max_size=%s",
            name,
            kind,
            queue_size,
            max_size,
        )


def put_coalesced_nowait(queue: asyncio.Queue[dict], item: dict, *, name: str) -> None:
    try:
        queue.put_nowait(item)
        return
    except asyncio.QueueFull:
        loop = asyncio.get_running_loop()
        _log_overflow_once(
            name,
            loop,
            kind="coalesced",
            queue_size=queue.qsize(),
            max_size=_queue_max_size(queue),
        )
    while True:
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        try:
            queue.put_nowait(item)
            return
        except asyncio.QueueFull:
            continue


def put_marker_nowait(queue: asyncio.Queue[dict], marker: dict, *, name: str) -> None:
    marker_kind = _marker_kind(marker)
    pending: list[dict] = []
    while True:
        try:
            existing = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if _marker_kind(existing) != marker_kind:
            pending.append(existing)
    pending.append(marker)

    max_size = _queue_max_size(queue)
    if max_size > 0 and len(pending) > max_size:
        loop = asyncio.get_running_loop()
        _log_overflow_once(
            name,
            loop,
            kind=marker_kind,
            queue_size=len(pending),
            max_size=max_size,
        )
        pending = pending[-max_size:]

    for item in pending:
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            break
