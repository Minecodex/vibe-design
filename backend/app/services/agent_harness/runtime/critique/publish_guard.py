from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.harness_session import harness_sync_session_scope

from .repository import get_run_for_harness_run
from .workspace_snapshots import restore_round_snapshot


@dataclass(frozen=True, slots=True)
class PublishGuardFailure:
    reason_code: str
    message: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CritiquePublishSelection:
    restored_snapshot: bool = False
    selected_round: int | None = None
    selected_score: float | None = None
    selected_snapshot_relpath: str | None = None
    status: str | None = None


def check_critique_publish_guard(
    session: Session,
    *,
    harness_run_id: str,
    manifest_entry: str,
) -> PublishGuardFailure | None:
    run = get_run_for_harness_run(session, harness_run_id)
    if run is None:
        return None
    if run.status == "running":
        return PublishGuardFailure(
            reason_code="critique_in_progress",
            message="Design Jury is still running. Complete the current review round before publish_output.",
        )
    if run.status not in {"shipped", "below_threshold", "degraded", "failed"}:
        return PublishGuardFailure(
            reason_code="critique_not_authorized",
            message="Design Jury did not authorize publication.",
        )
    if run.status == "failed" and run.best_round is None and not run.selected_snapshot_relpath:
        return None
    if run.status == "degraded" and run.best_round is None and not run.selected_snapshot_relpath:
        return None
    if run.best_round is None:
        return PublishGuardFailure(
            reason_code="critique_selected_round_missing",
            message="Design Jury selected round is missing.",
        )
    selected_round = next(
        (
            item
            for item in run_rounds(session, run.critique_run_id)
            if item.round_number == run.best_round
        ),
        None,
    )
    if selected_round is None:
        return PublishGuardFailure(
            reason_code="critique_round_snapshot_missing",
            message="Design Jury selected round snapshot is missing.",
        )
    if selected_round.active_entry != manifest_entry:
        return PublishGuardFailure(
            reason_code="critique_manifest_mismatch",
            message="Registered artifact does not match the Design Jury selected snapshot.",
        )
    return None


def prepare_critique_publish_selection(
    ctx: Any,
    *,
    manifest_entry: str,
) -> PublishGuardFailure | CritiquePublishSelection | None:
    with harness_sync_session_scope() as session:
        failure = check_critique_publish_guard(
            session,
            harness_run_id=str(ctx.run_id),
            manifest_entry=manifest_entry,
        )
        if failure is not None:
            return failure
        run = get_run_for_harness_run(session, str(ctx.run_id))
        if run is None or run.best_round is None or not run.selected_snapshot_relpath:
            return None
        rounds = run_rounds(session, run.critique_run_id)
        selected_round = next((item for item in rounds if item.round_number == run.best_round), None)
        if selected_round is None:
            return PublishGuardFailure(
                reason_code="critique_round_snapshot_missing",
                message="Design Jury selected round snapshot is missing.",
            )
        selected_snapshot_relpath = run.selected_snapshot_relpath
        selected_score = run.score
        status = run.status

    conversation_dir = Path(ctx.conversation_dir).resolve()
    snapshot_dir = _inside_conversation(conversation_dir / selected_snapshot_relpath, conversation_dir)
    snapshot_entry = _inside_conversation(
        _snapshot_entry_path(
            snapshot_dir=snapshot_dir,
            artifact_work_root=str(getattr(ctx, "artifact_work_root", "") or ""),
            manifest_entry=manifest_entry,
        ),
        conversation_dir,
    )
    project_entry = _inside_conversation(Path(ctx.project_dir) / manifest_entry, conversation_dir)
    if not snapshot_entry.is_file():
        return PublishGuardFailure(
            reason_code="critique_selected_snapshot_entry_missing",
            message="Design Jury selected round entry is missing.",
        )

    restored = False
    if not project_entry.is_file() or _sha256(project_entry) != _sha256(snapshot_entry):
        restore_round_snapshot(
            ctx,
            snapshot_dir=snapshot_dir,
            artifact_work_root=str(getattr(ctx, "artifact_work_root", "") or ""),
        )
        restored = True
        project_entry = _inside_conversation(Path(ctx.project_dir) / manifest_entry, conversation_dir)
        if not project_entry.is_file() or _sha256(project_entry) != _sha256(snapshot_entry):
            return PublishGuardFailure(
                reason_code="critique_selected_snapshot_restore_failed",
                message="Could not restore the Design Jury selected round before publishing.",
            )

    return CritiquePublishSelection(
        restored_snapshot=restored,
        selected_round=run.best_round,
        selected_score=selected_score,
        selected_snapshot_relpath=selected_snapshot_relpath,
        status=status,
    )


def run_rounds(session: Session, critique_run_id: str):
    from .repository import list_rounds

    return list_rounds(session, critique_run_id)


def _snapshot_entry_path(*, snapshot_dir: Path, artifact_work_root: str, manifest_entry: str) -> Path:
    normalized_entry = str(manifest_entry or "").replace("\\", "/").strip().strip("/")
    normalized_root = str(artifact_work_root or "").replace("\\", "/").strip().strip("/")
    entry_inside_root = normalized_entry
    if normalized_root and normalized_entry.startswith(f"{normalized_root}/"):
        entry_inside_root = normalized_entry[len(normalized_root) + 1 :]
    return (snapshot_dir / "artifact-work-root" / entry_inside_root).resolve()


def _inside_conversation(path: Path, conversation_dir: Path) -> Path:
    resolved = Path(path).resolve()
    resolved.relative_to(conversation_dir.resolve())
    return resolved


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
