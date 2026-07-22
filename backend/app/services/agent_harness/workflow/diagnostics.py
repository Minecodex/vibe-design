from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

from app.core.config import settings

logger = logging.getLogger(__name__)


def workflow_diagnostics_enabled() -> bool:
    return bool(getattr(settings, "HARNESS_WORKFLOW_DIAGNOSTICS_ENABLED", False))


def activity_diagnostics_enabled() -> bool:
    return bool(getattr(settings, "HARNESS_ACTIVITY_DIAGNOSTICS_ENABLED", False))


def tool_loop_diagnostics_enabled() -> bool:
    return bool(getattr(settings, "HARNESS_TOOL_LOOP_DIAGNOSTICS_ENABLED", False))


def perf_warning_seconds() -> float:
    return max(float(getattr(settings, "HARNESS_PERF_SEGMENT_WARNING_SECONDS", 0.1) or 0.1), 0.0)


def workflow_step_warning_seconds() -> float:
    fallback = perf_warning_seconds()
    return max(float(getattr(settings, "HARNESS_WORKFLOW_STEP_WARNING_SECONDS", fallback) or fallback), 0.0)


def activity_warning_seconds() -> float:
    fallback = perf_warning_seconds()
    return max(float(getattr(settings, "HARNESS_ACTIVITY_WARNING_SECONDS", fallback) or fallback), 0.0)


def _safe_summary(value: object, *, limit: int = 240) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    if len(text) > limit:
        return text[:limit] + "..."
    return text


@contextmanager
def workflow_step_timer(*, step_type: str, step_id: str, run_id: str, attempt: int) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if workflow_diagnostics_enabled() and elapsed_ms >= workflow_step_warning_seconds() * 1000.0:
            logger.warning(
                "Workflow step slow: step_type=%s step_id=%s run_id=%s elapsed_ms=%.3f attempt=%s",
                _safe_summary(step_type),
                _safe_summary(step_id),
                _safe_summary(run_id),
                elapsed_ms,
                int(attempt or 0),
            )


def log_step_retry(*, step_id: str, attempt: int, error_type: str) -> None:
    if workflow_diagnostics_enabled():
        logger.warning(
            "Step retry: step_id=%s attempt=%s error_type=%s",
            _safe_summary(step_id),
            int(attempt or 0),
            _safe_summary(error_type),
        )


def log_step_terminalized(*, run_id: str, step_id: str, status: str) -> None:
    if not workflow_diagnostics_enabled():
        return
    normalized_status = str(status or "").strip().lower()
    log = logger.info if normalized_status == "succeeded" else logger.warning
    log(
        "Step terminalized: run_id=%s step_id=%s status=%s",
        _safe_summary(run_id),
        _safe_summary(step_id),
        _safe_summary(status),
    )


def log_lease_safety(*, step_id: str, lease_remaining_ms: float, heartbeat_late_ms: float, renew_elapsed_ms: float) -> None:
    if not workflow_diagnostics_enabled():
        return
    threshold_ms = max(float(getattr(settings, "HARNESS_LEASE_SAFETY_WARNING_SECONDS", 30.0) or 30.0), 0.0) * 1000.0
    if lease_remaining_ms <= threshold_ms or heartbeat_late_ms > threshold_ms:
        logger.warning(
            "Lease safety: step_id=%s lease_remaining_ms=%.3f heartbeat_late_ms=%.3f renew_elapsed_ms=%.3f",
            _safe_summary(step_id),
            lease_remaining_ms,
            heartbeat_late_ms,
            renew_elapsed_ms,
        )


def log_activity_slow(*, activity_type: str, activity_id: str, step_id: str, elapsed_ms: float | None) -> None:
    if not activity_diagnostics_enabled() or elapsed_ms is None:
        return
    if float(elapsed_ms) >= activity_warning_seconds() * 1000.0:
        logger.warning(
            "Activity slow: activity_type=%s activity_id=%s step_id=%s elapsed_ms=%.3f",
            _safe_summary(activity_type),
            _safe_summary(activity_id),
            _safe_summary(step_id),
            float(elapsed_ms),
        )


def log_event_fanout_slow(*, event_type: str, sequence: object | None, publish_elapsed_ms: float) -> None:
    if not workflow_diagnostics_enabled():
        return
    if float(publish_elapsed_ms) >= perf_warning_seconds() * 1000.0:
        logger.warning(
            "Event fanout slow: event_type=%s sequence=%s publish_elapsed_ms=%.3f",
            _safe_summary(event_type),
            _safe_summary(sequence),
            float(publish_elapsed_ms),
        )


def log_workflow_phase_timing(
    *,
    phase: str,
    step_type: str,
    step_id: str,
    run_id: str,
    elapsed_ms: float,
    metadata: dict[str, object] | None = None,
) -> None:
    if not workflow_diagnostics_enabled():
        return
    metadata_parts = []
    for key, value in sorted((metadata or {}).items()):
        metadata_parts.append(f"{_safe_summary(key, limit=80)}={_safe_summary(value, limit=160)}")
    metadata_text = " ".join(metadata_parts)
    logger.info(
        "Workflow phase timing: phase=%s step_type=%s step_id=%s run_id=%s elapsed_ms=%.3f%s%s",
        _safe_summary(phase),
        _safe_summary(step_type),
        _safe_summary(step_id),
        _safe_summary(run_id),
        float(elapsed_ms),
        " " if metadata_text else "",
        metadata_text,
    )


def log_step_schedule_timing(
    *,
    step_type: str,
    step_id: str,
    run_id: str,
    queue_ms: float | None,
    run_ms: float,
    wake_source: str,
    next_step_count: int,
    status: str,
) -> None:
    if not workflow_diagnostics_enabled():
        return
    logger.info(
        "Workflow step schedule timing: step_type=%s step_id=%s run_id=%s queue_ms=%s run_ms=%.3f wake_source=%s next_step_count=%s status=%s",
        _safe_summary(step_type),
        _safe_summary(step_id),
        _safe_summary(run_id),
        f"{float(queue_ms):.3f}" if queue_ms is not None else "unknown",
        float(run_ms),
        _safe_summary(wake_source, limit=40),
        int(next_step_count or 0),
        _safe_summary(status, limit=60),
    )


def log_tool_extra_field_ignored(*, tool_name: str, field: str) -> None:
    if not tool_loop_diagnostics_enabled():
        return
    logger.warning(
        "Tool extra field ignored: tool_name=%s field=%s",
        _safe_summary(tool_name),
        _safe_summary(field),
    )


def log_tool_failure_loop_detected(
    *,
    run_id: str,
    tool_name: str,
    failure_count: int,
    latest_step_id: str,
    error_type: str,
    breaker_threshold: int,
) -> None:
    if not tool_loop_diagnostics_enabled():
        return
    logger.warning(
        "Tool failure loop detected: run_id=%s tool_name=%s failure_count=%s latest_step_id=%s error_type=%s breaker_threshold=%s",
        _safe_summary(run_id),
        _safe_summary(tool_name),
        int(failure_count or 0),
        _safe_summary(latest_step_id),
        _safe_summary(error_type),
        int(breaker_threshold or 0),
    )


def log_tool_failure_breaker_terminalized(*, run_id: str, tool_name: str, status: str) -> None:
    if not tool_loop_diagnostics_enabled():
        return
    logger.warning(
        "Tool failure breaker terminalized run: run_id=%s tool_name=%s status=%s",
        _safe_summary(run_id),
        _safe_summary(tool_name),
        _safe_summary(status),
    )
