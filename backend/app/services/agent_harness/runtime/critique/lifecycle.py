from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.db.harness_session import harness_sync_session_scope

from .config import load_critique_config
from .quality_review import ensure_quality_review_authorized
from .repository import CritiqueRunState, finalize_run, get_run_for_harness_run


def critique_runtime_payload(*, harness_run_id: str) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        run = get_run_for_harness_run(session, harness_run_id)
        return _run_payload(run) if run is not None else None


def terminate_critique_run(*, harness_run_id: str, status: str) -> None:
    if not load_critique_config(settings).enabled:
        return
    terminal_status = "interrupted" if status == "cancelled" else "failed"
    with harness_sync_session_scope() as session:
        run = get_run_for_harness_run(session, harness_run_id)
        if run is None or run.status != "running":
            return
        finalize_run(
            session,
            critique_run_id=run.critique_run_id,
            status=terminal_status,
            best_round=run.best_round,
            score=run.score,
            selected_snapshot_relpath=run.selected_snapshot_relpath,
        )


def _run_payload(run: CritiqueRunState | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return {
        "critique_run_id": run.critique_run_id,
        "status": run.status,
        "round": run.best_round or 0,
        "max_rounds": run.max_rounds,
        "score_scale": run.score_scale,
        "score_threshold": run.score_threshold,
        "selected_round": run.best_round,
        "selected_score": run.score,
        "reason": run.reason,
        "warnings": run.warnings_json,
        "composite": run.score,
    }


__all__ = [
    "critique_runtime_payload",
    "ensure_quality_review_authorized",
    "terminate_critique_run",
]
