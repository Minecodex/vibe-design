from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Any

from app.core.config import settings
from app.db.harness_session import run_harness_db
from app.services.agent_harness.runtime.context_projection import (
    claim_next_projection,
    complete_projection,
    fail_projection,
)
from app.services.agent_harness.runtime.context_projection_observability import (
    count_claimable_projection_states,
    emit_projection_perf_event,
)
from app.services.agent_harness.runtime import context_projection_wakeup
from app.services.agent_harness.runtime.recall_sidecar import rebuild_recall_sidecar
from app.services.ephemeral_task_coordinator import EphemeralTaskCoordinator, EphemeralTaskKey

logger = logging.getLogger(__name__)
_WORKER_TASK: asyncio.Task | None = None


def start_context_projection_worker() -> None:
    global _WORKER_TASK
    if not bool(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_ENABLED", False)):
        return
    if _WORKER_TASK is not None and not _WORKER_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _WORKER_TASK = loop.create_task(_run_worker_loop(), name="harness-context-projection-worker")


async def stop_context_projection_worker() -> None:
    global _WORKER_TASK
    task = _WORKER_TASK
    _WORKER_TASK = None
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


async def _run_worker_loop() -> None:
    interval = max(0.25, float(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_INTERVAL_SECONDS", 2.0) or 2.0))
    batch_size = _configured_batch_size()
    while True:
        try:
            processed = await run_harness_db(process_context_projection_batch, batch_size=batch_size)
            if processed is None:
                await context_projection_wakeup.wait_context_projection_wakeup(timeout_seconds=interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning("Context projection worker iteration failed", exc_info=True)
            await asyncio.sleep(interval)


def process_context_projection_batch(
    *,
    worker_id: str = "context-projection-worker",
    batch_size: int = 1,
) -> list[dict[str, Any]] | None:
    results: list[dict[str, Any]] = []
    capped_batch_size = min(max(1, int(batch_size or 1)), _configured_max_concurrency())
    for _ in range(capped_batch_size):
        item = process_next_context_projection(worker_id=worker_id)
        if item is None:
            break
        results.append(item)
    return results or None


def process_next_context_projection(*, worker_id: str = "context-projection-worker") -> dict[str, Any] | None:
    started = time.perf_counter()
    claim = claim_next_projection(
        worker_id=worker_id,
        lease_seconds=int(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_LEASE_SECONDS", 60) or 60),
    )
    if claim is None:
        emit_projection_perf_event(
            "context_projection.run",
            status="idle",
            worker_id=worker_id,
            claimable_conversations=count_claimable_projection_states(),
            elapsed_ms=_elapsed_ms(started),
        )
        return None
    result = _process_claim(claim)
    if result["failed_responsibilities"]:
        failed = fail_projection(
            str(claim["conversation_id"]),
            worker_id=worker_id,
            lease_token=str(claim["lease_token"]),
            error=RuntimeError(result["error_summary"]),
            completed_responsibilities=result["completed_responsibilities"],
            processed_sequence=int(claim["target_sequence"]),
            result=result["result"],
            timings=result["timings"],
        )
        payload = {
            "status": "failed",
            "conversation_id": claim["conversation_id"],
            "dirty_responsibilities": failed["dirty_responsibilities"],
            "completed_responsibilities": result["completed_responsibilities"],
            "failed_responsibilities": result["failed_responsibilities"],
            "last_error_type": failed["last_error_type"],
            "last_error_summary": failed["last_error_summary"],
        }
        emit_projection_perf_event(
            "context_projection.run",
            status="failed",
            worker_id=worker_id,
            conversation_id=claim["conversation_id"],
            elapsed_ms=_elapsed_ms(started),
            dirty_responsibilities=failed["dirty_responsibilities"],
            completed_responsibilities=result["completed_responsibilities"],
            failed_responsibilities=result["failed_responsibilities"],
        )
        return payload
    completed = complete_projection(
        str(claim["conversation_id"]),
        worker_id=worker_id,
        lease_token=str(claim["lease_token"]),
        processed_sequence=int(claim["target_sequence"]),
        completed_responsibilities=result["completed_responsibilities"],
        result=result["result"],
        timings=result["timings"],
    )
    payload = {
        "status": "completed",
        "conversation_id": claim["conversation_id"],
        "dirty_responsibilities": completed["dirty_responsibilities"],
        "latest_processed_sequence": completed["latest_processed_sequence"],
        "result": result["result"],
    }
    emit_projection_perf_event(
        "context_projection.run",
        status="completed",
        worker_id=worker_id,
        conversation_id=claim["conversation_id"],
        elapsed_ms=_elapsed_ms(started),
        dirty_responsibilities=completed["dirty_responsibilities"],
        completed_responsibilities=result["completed_responsibilities"],
    )
    return payload


def _process_claim(claim: dict[str, Any]) -> dict[str, Any]:
    user_id = int(claim["user_id"])
    conversation_id = str(claim["conversation_id"])
    responsibilities = set(claim.get("dirty_responsibilities") or [])
    result: dict[str, Any] = {
        "responsibilities": sorted(responsibilities),
        "target_sequence": int(claim.get("target_sequence") or 0),
    }
    timings: dict[str, Any] = {}
    completed: list[str] = []
    failed: list[str] = []
    errors: list[str] = []
    if "recall_sidecar_refresh" in responsibilities:
        _run_artifact(
            "recall_sidecar_refresh",
            lambda: rebuild_recall_sidecar(user_id, conversation_id),
            result=result,
            timings=timings,
            completed=completed,
            failed=failed,
            errors=errors,
            result_mapper=lambda recall: {
                "recall_path": recall.get("path"),
                "recall_chunks": recall.get("chunks"),
            },
            claim=claim,
        )
    return {
        "result": result,
        "timings": timings,
        "completed_responsibilities": sorted(set(completed)),
        "failed_responsibilities": sorted(set(failed)),
        "error_summary": "; ".join(errors)[:1000],
    }


def _run_artifact(
    responsibility: str,
    work,
    *,
    result: dict[str, Any],
    timings: dict[str, Any],
    completed: list[str],
    failed: list[str],
    errors: list[str],
    result_mapper,
    claim: dict[str, Any],
) -> None:
    started = time.perf_counter()
    guard = EphemeralTaskCoordinator(
        ttl_seconds=max(float(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_LEASE_SECONDS", 60) or 60), 1.0)
    )
    lease = guard.start_sync(
        EphemeralTaskKey.build(
            domain="context-projection",
            kind=responsibility,
            resource_parts=[claim.get("user_id"), claim.get("conversation_id"), responsibility],
            version=claim.get("target_sequence") or 0,
        ),
        owner_prefix="projection",
    )
    if not lease.acquired:
        failed.append(responsibility)
        errors.append(f"{responsibility}: EphemeralTaskAlreadyRunning")
        elapsed_ms = _elapsed_ms(started)
        timings[responsibility] = elapsed_ms
        emit_projection_perf_event(
            f"context_projection.artifact.{responsibility}",
            status="skipped_duplicate",
            elapsed_ms=elapsed_ms,
            conversation_id=claim.get("conversation_id"),
            user_id=claim.get("user_id"),
            worker_id=claim.get("lease_owner"),
            target_sequence=claim.get("target_sequence"),
            error_type="EphemeralTaskAlreadyRunning",
        )
        return
    try:
        mapped = result_mapper(work())
        result.update(mapped)
        completed.append(responsibility)
        guard.finish_sync(lease, status="done", result=_ephemeral_projection_result(mapped))
        status = "ok"
        error_type = None
    except Exception as exc:
        guard.fail_sync(lease, error_type=type(exc).__name__)
        failed.append(responsibility)
        errors.append(f"{responsibility}: {type(exc).__name__}: {exc}")
        status = "failed"
        error_type = type(exc).__name__
    elapsed_ms = _elapsed_ms(started)
    timings[responsibility] = elapsed_ms
    emit_projection_perf_event(
        f"context_projection.artifact.{responsibility}",
        status=status,
        elapsed_ms=elapsed_ms,
        conversation_id=claim.get("conversation_id"),
        user_id=claim.get("user_id"),
        worker_id=claim.get("lease_owner"),
        target_sequence=claim.get("target_sequence"),
        error_type=error_type,
    )


def _ephemeral_projection_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if not str(key).endswith("_path") and str(key) != "path"
    }


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _configured_batch_size() -> int:
    return min(
        max(1, int(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_BATCH_SIZE", 1) or 1)),
        _configured_max_concurrency(),
    )


def _configured_max_concurrency() -> int:
    return max(1, int(getattr(settings, "HARNESS_RECALL_SIDECAR_WORKER_MAX_CONCURRENCY", 1) or 1))
