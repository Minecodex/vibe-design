from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.redis_coordination import get_redis_coordinator
from app.services.realtime_bus import RealtimeBus, RealtimeScope, wait_realtime_wakeup, wakeup_realtime

logger = logging.getLogger(__name__)


def _wakeup_key() -> str:
    return RealtimeBus(get_redis_coordinator()).wakeup_key(
        name="context.projection.wakeup",
        scope=RealtimeScope(),
    )


async def wake_context_projection_workers(conversation_id: str | None = None) -> dict[str, Any]:
    # Wakeup is intentionally global (the projection worker pool drains all dirty
    # rows on each tick), so we keep a single shared wakeup key but surface the
    # triggering conversation in `reason` for tracing.
    reason = "projection_dirty"
    if conversation_id:
        safe_id = str(conversation_id).strip()[:64]
        if safe_id:
            reason = f"projection_dirty:{safe_id}"
    return await wakeup_realtime(
        "context.projection.wakeup",
        scope=RealtimeScope(),
        reason=reason,
        worker="context-projection",
        bus=RealtimeBus(get_redis_coordinator()),
    )


def wake_context_projection_workers_sync(conversation_id: str | None = None) -> asyncio.Task | None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Threadpool callers must not create throwaway event loops or Redis pools.
        return None

    task = loop.create_task(wake_context_projection_workers(conversation_id))

    def _log_failure(done: asyncio.Task) -> None:
        try:
            done.result()
        except Exception:
            logger.info("Context projection Redis wakeup failed", exc_info=True)

    task.add_done_callback(_log_failure)
    return task


async def wait_context_projection_wakeup(*, timeout_seconds: float) -> dict[str, Any]:
    return await wait_realtime_wakeup(
        "context.projection.wakeup",
        scope=RealtimeScope(),
        timeout_seconds=max(float(timeout_seconds), 0.0),
        bus=RealtimeBus(get_redis_coordinator()),
    )
