from __future__ import annotations

from collections.abc import Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.harness_session import HarnessAgentRun


@dataclass(slots=True)
class CritiqueRunState:
    critique_run_id: str
    harness_run_id: str
    conversation_id: str
    user_id: int
    artifact_mode: str
    artifact_work_root: str
    status: str = "running"
    protocol_version: int = 1
    max_rounds: int = 3
    score_scale: int = 10
    score_threshold: float = 8.0
    fallback_policy: str = "ship_best"
    best_round: int | None = None
    score: float | None = None
    selected_snapshot_relpath: str | None = None
    reason: str | None = None
    artifact_fingerprint: str | None = None
    packet_hash: str | None = None
    subagent_task_id: str | None = None
    warnings_json: list[dict[str, Any]] = field(default_factory=list)
    review_started_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class CritiqueRoundState:
    round_number: int
    active_entry: str
    snapshot_relpath: str
    composite: float
    must_fix_count: int
    findings_json: list[dict[str, Any]] = field(default_factory=list)
    warnings_json: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


def get_run(session: Session, critique_run_id: str) -> CritiqueRunState | None:
    for row in session.scalars(select(HarnessAgentRun)).all():
        state = _state_from_agent_run(row)
        if state is not None and state.critique_run_id == str(critique_run_id):
            return state
    return None


def get_run_for_harness_run(session: Session, harness_run_id: str) -> CritiqueRunState | None:
    row = _agent_run_for_update(session, harness_run_id)
    return _state_from_agent_run(row) if row is not None else None


def create_run(
    session: Session,
    *,
    critique_run_id: str,
    harness_run_id: str,
    conversation_id: str,
    user_id: int,
    artifact_mode: str,
    artifact_work_root: str,
    protocol_version: int = 1,
    max_rounds: int = 3,
    score_scale: int = 10,
    score_threshold: float = 8.0,
    fallback_policy: str = "ship_best",
) -> CritiqueRunState:
    row = _agent_run_for_update(session, harness_run_id)
    if row is None:
        raise ValueError("harness agent run not found")
    existing = _state_from_agent_run(row)
    if existing is not None:
        return existing
    now = _utcnow()
    state = CritiqueRunState(
        critique_run_id=str(critique_run_id),
        harness_run_id=str(harness_run_id),
        conversation_id=str(conversation_id),
        user_id=int(user_id),
        artifact_mode=str(artifact_mode),
        artifact_work_root=str(artifact_work_root),
        status="running",
        protocol_version=int(protocol_version),
        max_rounds=int(max_rounds),
        score_scale=int(score_scale),
        score_threshold=float(score_threshold),
        fallback_policy=str(fallback_policy),
        created_at=now,
        updated_at=now,
    )
    snapshot = _snapshot(row)
    snapshot["critique"] = {**_state_to_json(state), "rounds": []}
    _write_snapshot(row, snapshot)
    session.flush()
    return state


def get_round(
    session: Session,
    *,
    critique_run_id: str,
    round_number: int,
) -> CritiqueRoundState | None:
    for item in list_rounds(session, critique_run_id):
        if item.round_number == int(round_number):
            return item
    return None


def list_rounds(session: Session, critique_run_id: str) -> list[CritiqueRoundState]:
    row = _agent_run_for_critique(session, critique_run_id)
    if row is None:
        return []
    critique = _critique_snapshot(row)
    rows = critique.get("rounds") if isinstance(critique.get("rounds"), list) else []
    return sorted(
        (_round_from_json(item) for item in rows if isinstance(item, dict)),
        key=lambda item: item.round_number,
    )


def insert_round(
    session: Session,
    *,
    critique_run_id: str,
    round_number: int,
    active_entry: str,
    snapshot_relpath: str,
    composite: float,
    must_fix_count: int,
    findings: Sequence[dict],
    warnings: Sequence[dict] = (),
) -> CritiqueRoundState:
    row = _agent_run_for_critique(session, critique_run_id)
    if row is None:
        raise ValueError("critique run not found")
    critique = _critique_snapshot(row)
    existing_rounds = critique.get("rounds") if isinstance(critique.get("rounds"), list) else []
    for item in existing_rounds:
        if isinstance(item, dict) and int(item.get("round_number") or 0) == int(round_number):
            return _round_from_json(item)
    now = _utcnow()
    round_state = CritiqueRoundState(
        round_number=int(round_number),
        active_entry=str(active_entry),
        snapshot_relpath=str(snapshot_relpath),
        composite=float(composite),
        must_fix_count=int(must_fix_count),
        findings_json=[dict(item) for item in findings],
        warnings_json=[dict(item) for item in warnings],
        created_at=now,
        updated_at=now,
    )
    critique["rounds"] = [*existing_rounds, _round_to_json(round_state)]
    snapshot = _snapshot(row)
    snapshot["critique"] = critique
    _write_snapshot(row, snapshot)
    session.flush()
    return round_state


def mark_review_started(session: Session, critique_run_id: str) -> CritiqueRunState | None:
    row = _agent_run_for_critique(session, critique_run_id)
    if row is None:
        return None
    critique = _critique_snapshot(row)
    if not critique:
        return None
    if not critique.get("review_started_at"):
        now = _utcnow()
        critique["review_started_at"] = now.isoformat()
        critique["updated_at"] = now.isoformat()
        snapshot = _snapshot(row)
        snapshot["critique"] = critique
        _write_snapshot(row, snapshot)
        session.flush()
    return _state_from_agent_run(row)


def update_run_payload(
    session: Session,
    *,
    critique_run_id: str,
    values: dict[str, Any],
) -> CritiqueRunState | None:
    row = _agent_run_for_critique(session, critique_run_id)
    if row is None:
        return None
    critique = _critique_snapshot(row)
    if not critique:
        return None
    critique.update(deepcopy(values))
    critique["updated_at"] = _utcnow().isoformat()
    snapshot = _snapshot(row)
    snapshot["critique"] = critique
    _write_snapshot(row, snapshot)
    session.flush()
    return _state_from_agent_run(row)


def reopen_run_for_review(
    session: Session,
    *,
    critique_run_id: str,
    reason: str = "artifact_review_stale",
) -> CritiqueRunState | None:
    row = _agent_run_for_critique(session, critique_run_id)
    if row is None:
        return None
    critique = _critique_snapshot(row)
    if not critique:
        return None
    critique.update(
        {
            "status": "running",
            "best_round": None,
            "score": None,
            "selected_snapshot_relpath": None,
            "reason": reason,
            "updated_at": _utcnow().isoformat(),
        }
    )
    snapshot = _snapshot(row)
    snapshot["critique"] = critique
    _write_snapshot(row, snapshot)
    session.flush()
    return _state_from_agent_run(row)


def finalize_run(
    session: Session,
    *,
    critique_run_id: str,
    status: str,
    best_round: int | None,
    score: float | None,
    selected_snapshot_relpath: str | None,
    reason: str | None = None,
    warnings: Sequence[dict] = (),
) -> bool:
    if status == "running":
        return False
    row = _agent_run_for_critique(session, critique_run_id)
    if row is None:
        return False
    critique = _critique_snapshot(row)
    if str(critique.get("status") or "") != "running":
        return False
    critique.update(
        {
            "status": str(status),
            "best_round": int(best_round) if best_round is not None else None,
            "score": float(score) if score is not None else None,
            "selected_snapshot_relpath": str(selected_snapshot_relpath) if selected_snapshot_relpath else None,
            "reason": str(reason) if reason else critique.get("reason"),
            "warnings": [dict(item) for item in warnings] if warnings else list(critique.get("warnings") or []),
            "updated_at": _utcnow().isoformat(),
        }
    )
    snapshot = _snapshot(row)
    snapshot["critique"] = critique
    _write_snapshot(row, snapshot)
    session.flush()
    return True


def _agent_run_for_update(session: Session, harness_run_id: str) -> HarnessAgentRun | None:
    return session.scalars(
        select(HarnessAgentRun)
        .where(HarnessAgentRun.run_id == str(harness_run_id))
        .with_for_update()
    ).first()


def _agent_run_for_critique(session: Session, critique_run_id: str) -> HarnessAgentRun | None:
    for row in session.scalars(select(HarnessAgentRun).with_for_update()).all():
        critique = _critique_snapshot(row)
        if str(critique.get("critique_run_id") or "") == str(critique_run_id):
            return row
    return None


def _state_from_agent_run(row: HarnessAgentRun | None) -> CritiqueRunState | None:
    if row is None:
        return None
    critique = _critique_snapshot(row)
    if not critique:
        return None
    return CritiqueRunState(
        critique_run_id=str(critique.get("critique_run_id") or ""),
        harness_run_id=str(critique.get("harness_run_id") or row.run_id),
        conversation_id=str(critique.get("conversation_id") or row.conversation_id),
        user_id=int(critique.get("user_id") or row.user_id),
        artifact_mode=str(critique.get("artifact_mode") or ""),
        artifact_work_root=str(critique.get("artifact_work_root") or ""),
        status=str(critique.get("status") or "running"),
        protocol_version=int(critique.get("protocol_version") or 1),
        max_rounds=int(critique.get("max_rounds") or 3),
        score_scale=int(critique.get("score_scale") or 10),
        score_threshold=float(critique.get("score_threshold") or 8.0),
        fallback_policy=str(critique.get("fallback_policy") or "ship_best"),
        best_round=int(critique["best_round"]) if critique.get("best_round") is not None else None,
        score=float(critique["score"]) if critique.get("score") is not None else None,
        selected_snapshot_relpath=(
            str(critique.get("selected_snapshot_relpath"))
            if critique.get("selected_snapshot_relpath")
            else None
        ),
        reason=str(critique.get("reason")) if critique.get("reason") else None,
        artifact_fingerprint=(
            str(critique.get("artifact_fingerprint"))
            if critique.get("artifact_fingerprint")
            else None
        ),
        packet_hash=str(critique.get("packet_hash")) if critique.get("packet_hash") else None,
        subagent_task_id=str(critique.get("subagent_task_id")) if critique.get("subagent_task_id") else None,
        warnings_json=[dict(item) for item in list(critique.get("warnings") or []) if isinstance(item, dict)],
        review_started_at=_parse_datetime(critique.get("review_started_at")),
        created_at=_parse_datetime(critique.get("created_at")) or _parse_datetime(row.created_at),
        updated_at=_parse_datetime(critique.get("updated_at")) or _parse_datetime(row.updated_at),
    )


def _state_to_json(state: CritiqueRunState) -> dict[str, Any]:
    return {
        "critique_run_id": state.critique_run_id,
        "harness_run_id": state.harness_run_id,
        "conversation_id": state.conversation_id,
        "user_id": state.user_id,
        "artifact_mode": state.artifact_mode,
        "artifact_work_root": state.artifact_work_root,
        "status": state.status,
        "protocol_version": state.protocol_version,
        "max_rounds": state.max_rounds,
        "score_scale": state.score_scale,
        "score_threshold": state.score_threshold,
        "fallback_policy": state.fallback_policy,
        "best_round": state.best_round,
        "score": state.score,
        "selected_snapshot_relpath": state.selected_snapshot_relpath,
        "reason": state.reason,
        "artifact_fingerprint": state.artifact_fingerprint,
        "packet_hash": state.packet_hash,
        "subagent_task_id": state.subagent_task_id,
        "warnings": [dict(item) for item in state.warnings_json],
        "review_started_at": state.review_started_at.isoformat() if state.review_started_at else None,
        "created_at": state.created_at.isoformat() if state.created_at else None,
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _round_from_json(data: dict[str, Any]) -> CritiqueRoundState:
    return CritiqueRoundState(
        round_number=int(data.get("round_number") or 0),
        active_entry=str(data.get("active_entry") or ""),
        snapshot_relpath=str(data.get("snapshot_relpath") or ""),
        composite=float(data.get("composite") or 0.0),
        must_fix_count=int(data.get("must_fix_count") or 0),
        findings_json=[dict(item) for item in list(data.get("findings") or []) if isinstance(item, dict)],
        warnings_json=[dict(item) for item in list(data.get("warnings") or []) if isinstance(item, dict)],
        created_at=_parse_datetime(data.get("created_at")),
        updated_at=_parse_datetime(data.get("updated_at")),
    )


def _round_to_json(round_state: CritiqueRoundState) -> dict[str, Any]:
    return {
        "round_number": round_state.round_number,
        "active_entry": round_state.active_entry,
        "snapshot_relpath": round_state.snapshot_relpath,
        "composite": round_state.composite,
        "must_fix_count": round_state.must_fix_count,
        "findings": [dict(item) for item in round_state.findings_json],
        "warnings": [dict(item) for item in round_state.warnings_json],
        "created_at": round_state.created_at.isoformat() if round_state.created_at else None,
        "updated_at": round_state.updated_at.isoformat() if round_state.updated_at else None,
    }


def _snapshot(row: HarnessAgentRun) -> dict[str, Any]:
    return deepcopy(row.runtime_snapshot_json) if isinstance(row.runtime_snapshot_json, dict) else {}


def _critique_snapshot(row: HarnessAgentRun) -> dict[str, Any]:
    snapshot = _snapshot(row)
    critique = snapshot.get("critique")
    return deepcopy(critique) if isinstance(critique, dict) else {}


def _write_snapshot(row: HarnessAgentRun, snapshot: dict[str, Any]) -> None:
    row.runtime_snapshot_json = deepcopy(snapshot)
    row.updated_at = _utcnow()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
