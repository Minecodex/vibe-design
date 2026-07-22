from __future__ import annotations

import asyncio
import logging
import time
import warnings
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


def diagnostics_enabled() -> bool:
    return bool(getattr(settings, "HARNESS_ASYNCIO_DIAGNOSTICS_ENABLED", False))


def enable_asyncio_diagnostics(*, component: str) -> None:
    if not diagnostics_enabled():
        return
    loop = asyncio.get_running_loop()
    slow_seconds = max(float(getattr(settings, "HARNESS_ASYNCIO_SLOW_CALLBACK_SECONDS", 5.0) or 5.0), 0.0)
    lag_threshold = max(float(getattr(settings, "HARNESS_ASYNCIO_LAG_THRESHOLD_SECONDS", 5.0) or 5.0), 0.01)
    lag_interval = max(float(getattr(settings, "HARNESS_ASYNCIO_LAG_INTERVAL_SECONDS", 0.5) or 0.5), 0.01)
    loop.set_debug(True)
    loop.slow_callback_duration = slow_seconds
    warnings.simplefilter("always", RuntimeWarning)
    logger.info(
        "Asyncio diagnostics enabled: component=%s slow_callback_seconds=%.3f lag_threshold_seconds=%.3f lag_interval_seconds=%.3f debug=%s",
        component,
        slow_seconds,
        lag_threshold,
        lag_interval,
        True,
    )


async def event_loop_lag_probe(
    *,
    component: str,
    stop_event: asyncio.Event,
    interval_seconds: float | None = None,
    threshold_seconds: float | None = None,
) -> None:
    if not diagnostics_enabled():
        return
    default_interval = float(getattr(settings, "HARNESS_ASYNCIO_LAG_INTERVAL_SECONDS", 0.5) or 0.5)
    default_threshold = float(getattr(settings, "HARNESS_ASYNCIO_LAG_THRESHOLD_SECONDS", 5.0) or 5.0)
    interval = max(float(interval_seconds if interval_seconds is not None else default_interval), 0.01)
    threshold = max(float(threshold_seconds if threshold_seconds is not None else default_threshold), 0.01)
    expected = time.perf_counter() + interval
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        now = time.perf_counter()
        lag = max(now - expected, 0.0)
        if lag >= threshold:
            logger.warning(
                "Event loop lag detected: component=%s lag_ms=%.3f threshold_ms=%.3f active_tasks=%s task_samples=%s",
                component,
                lag * 1000.0,
                threshold * 1000.0,
                len(asyncio.all_tasks()),
                _task_samples(),
            )
        expected = now + interval


def _task_samples(limit: int = 8) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for task in list(asyncio.all_tasks())[: max(int(limit or 8), 1)]:
        coro = task.get_coro()
        frame = getattr(coro, "cr_frame", None)
        sample: dict[str, Any] = {
            "name": task.get_name(),
            "coro": getattr(coro, "__qualname__", coro.__class__.__name__),
        }
        if frame is not None:
            sample["frame"] = {
                "file": frame.f_code.co_filename,
                "line": frame.f_lineno,
                "function": frame.f_code.co_name,
            }
        samples.append(sample)
    return samples
