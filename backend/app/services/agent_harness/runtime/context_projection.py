from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, update

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import ContextProjectionRun, ContextProjectionState, HarnessConversation
from app.services.agent_harness.runtime import context_projection_wakeup
from app.services.agent_harness.runtime.context_projection_observability import emit_projection_perf_event


CONTEXT_PROJECTION_RESPONSIBILITIES = {
    "recall_sidecar_refresh",
}
CONTEXT_PROJECTION_FAILURE_RETRY_MIN_SECONDS = 2
CONTEXT_PROJECTION_FAILURE_RETRY_MAX_SECONDS = 60

STABLE_EVENT_RESPONSIBILITY_MAP: dict[str, tuple[str, ...]] = {
    "assistant_message_finalized": ("recall_sidecar_refresh",),
    "tool_result_recorded": ("recall_sidecar_refresh",),
    "generation_artifact_persisted": ("recall_sidecar_refresh",),
    "turn_completed": ("recall_sidecar_refresh",),
    "compaction_boundary": ("recall_sidecar_refresh",),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value) if value is not None else None


def _normalize_input_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.astimezone(timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_responsibilities(responsibilities: list[str] | tuple[str, ...] | set[str]) -> list[str]:
    normalized = sorted({str(item or "").strip() for item in responsibilities if str(item or "").strip()})
    unknown = [item for item in normalized if item not in CONTEXT_PROJECTION_RESPONSIBILITIES]
    if unknown:
        raise ValueError(f"Unknown context projection responsibility: {unknown[0]}")
    return normalized


def _encode_mask(responsibilities: list[str] | tuple[str, ...] | set[str]) -> str:
    return ",".join(_normalize_responsibilities(responsibilities))


def _decode_mask(mask: str | None) -> list[str]:
    return _normalize_responsibilities([item for item in str(mask or "").split(",") if item])


def _merge_mask(existing: str | None, incoming: list[str]) -> str:
    return _encode_mask([*_decode_mask(existing), *incoming])


def _serialize_state(row: ContextProjectionState) -> dict[str, Any]:
    return {
        "conversation_id": row.conversation_id,
        "user_id": int(row.user_id),
        "latest_observed_sequence": int(row.latest_observed_sequence or 0),
        "latest_processed_sequence": int(row.latest_processed_sequence or 0),
        "dirty_responsibilities": _decode_mask(row.dirty_mask),
        "last_dirty_reason": row.last_dirty_reason,
        "next_project_at": _iso(row.next_project_at),
        "lease_owner": row.lease_owner,
        "lease_token": row.lease_token,
        "lease_expires_at": _iso(row.lease_expires_at),
        "attempts": int(row.attempts or 0),
        "last_success_at": _iso(row.last_success_at),
        "last_failure_at": _iso(row.last_failure_at),
        "last_error_type": row.last_error_type,
        "last_error_summary": row.last_error_summary,
        "last_result": deepcopy(row.last_result_json) if isinstance(row.last_result_json, dict) else None,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _serialize_claim(row: ContextProjectionState, *, target_sequence: int) -> dict[str, Any]:
    payload = _serialize_state(row)
    payload["target_sequence"] = int(target_sequence)
    return payload


def get_projection_state(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        row = session.get(ContextProjectionState, conversation_id)
        if row is None or int(row.user_id) != int(user_id):
            return None
        return _serialize_state(row)


def mark_projection_dirty(
    user_id: int,
    conversation_id: str,
    *,
    responsibilities: list[str] | tuple[str, ...] | set[str],
    latest_event_sequence: int | None = None,
    reason: str = "unspecified",
    next_project_at: datetime | None = None,
) -> dict[str, Any]:
    incoming = _normalize_responsibilities(responsibilities)
    if not incoming:
        raise ValueError("at least one context projection responsibility is required")
    now = _now()
    requested_project_at = _normalize_input_datetime(next_project_at)
    emit_projection_perf_event(
        "context_projection.dirty_mark",
        status="attempt",
        user_id=int(user_id),
        conversation_id=conversation_id,
        dirty_responsibilities=incoming,
        latest_observed_sequence=int(latest_event_sequence or 0),
        reason=str(reason or "unspecified")[:120],
    )
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if conversation is None or int(conversation.user_id) != int(user_id):
            emit_projection_perf_event(
                "context_projection.dirty_mark",
                status="failed",
                user_id=int(user_id),
                conversation_id=conversation_id,
                error_type="FileNotFoundError",
            )
            raise FileNotFoundError(conversation_id)
        row = session.get(ContextProjectionState, conversation_id)
        if row is None:
            row = ContextProjectionState(
                conversation_id=conversation_id,
                user_id=int(user_id),
                latest_observed_sequence=max(0, int(latest_event_sequence or 0)),
                latest_processed_sequence=0,
                dirty_mask=_encode_mask(incoming),
                last_dirty_reason=str(reason or "unspecified")[:120],
                next_project_at=requested_project_at or now,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            previous_sequence = int(row.latest_observed_sequence or 0)
            row.dirty_mask = _merge_mask(row.dirty_mask, incoming)
            row.latest_observed_sequence = max(
                previous_sequence,
                int(latest_event_sequence or 0),
            )
            row.last_dirty_reason = str(reason or "unspecified")[:120]
            if requested_project_at is not None:
                row.next_project_at = requested_project_at
            elif row.next_project_at is None:
                row.next_project_at = now
            row.updated_at = now
        session.flush()
        state = _serialize_state(row)
        emit_projection_perf_event(
            "context_projection.dirty_mark",
            status="ok",
            user_id=int(user_id),
            conversation_id=conversation_id,
            dirty_responsibilities=state["dirty_responsibilities"],
            latest_observed_sequence=state["latest_observed_sequence"],
            latest_processed_sequence=state["latest_processed_sequence"],
            reason=state["last_dirty_reason"],
        )
    context_projection_wakeup.wake_context_projection_workers_sync(conversation_id)
    return state


def mark_projection_dirty_for_event(
    user_id: int,
    conversation_id: str,
    event: dict[str, Any],
) -> dict[str, Any] | None:
    event_type = str(event.get("event_type") or event.get("type") or "").strip()
    responsibilities = STABLE_EVENT_RESPONSIBILITY_MAP.get(event_type)
    if responsibilities is None:
        emit_projection_perf_event(
            "context_projection.dirty_mark",
            status="skipped",
            user_id=int(user_id),
            conversation_id=conversation_id,
            reason=event_type or "unknown_event",
        )
        return None
    return mark_projection_dirty(
        user_id,
        conversation_id,
        responsibilities=list(responsibilities),
        latest_event_sequence=int(event.get("sequence") or event.get("seq") or 0),
        reason=event_type,
    )


def claim_next_projection(*, worker_id: str, lease_seconds: int = 60) -> dict[str, Any] | None:
    owner = str(worker_id or "").strip()
    if not owner:
        raise ValueError("worker_id is required")
    now = _now()
    lease_expires_at = now + timedelta(seconds=max(1, int(lease_seconds or 60)))
    with harness_sync_session_scope() as session:
        while True:
            row = session.scalars(
                select(ContextProjectionState)
                .where(
                    ContextProjectionState.dirty_mask != "",
                    or_(ContextProjectionState.next_project_at.is_(None), ContextProjectionState.next_project_at <= now),
                    or_(
                        ContextProjectionState.lease_token.is_(None),
                        ContextProjectionState.lease_expires_at.is_(None),
                        ContextProjectionState.lease_expires_at <= now,
                    ),
                )
                .order_by(ContextProjectionState.next_project_at.asc(), ContextProjectionState.updated_at.asc())
                .limit(1)
            ).first()
            if row is None:
                return None
            lease_token = uuid.uuid4().hex
            target_sequence = int(row.latest_observed_sequence or 0)
            result = session.execute(
                update(ContextProjectionState)
                .where(
                    ContextProjectionState.conversation_id == row.conversation_id,
                    ContextProjectionState.dirty_mask != "",
                    or_(
                        ContextProjectionState.lease_token.is_(None),
                        ContextProjectionState.lease_expires_at.is_(None),
                        ContextProjectionState.lease_expires_at <= now,
                    ),
                )
                .execution_options(synchronize_session=False)
                .values(
                    lease_owner=owner,
                    lease_token=lease_token,
                    lease_expires_at=lease_expires_at,
                    attempts=int(row.attempts or 0) + 1,
                    updated_at=now,
                )
            )
            if int(result.rowcount or 0) != 1:
                continue
            row.lease_owner = owner
            row.lease_token = lease_token
            row.lease_expires_at = lease_expires_at
            row.attempts = int(row.attempts or 0) + 1
            row.updated_at = now
            session.add(
                ContextProjectionRun(
                    conversation_id=row.conversation_id,
                    user_id=int(row.user_id),
                    worker_id=owner,
                    lease_token=lease_token,
                    claimed_dirty_mask=row.dirty_mask,
                    starting_processed_sequence=int(row.latest_processed_sequence or 0),
                    target_sequence=target_sequence,
                    status="claimed",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.flush()
            claim = _serialize_claim(row, target_sequence=target_sequence)
            emit_projection_perf_event(
                "context_projection.claim",
                status="claimed",
                user_id=int(row.user_id),
                conversation_id=row.conversation_id,
                worker_id=owner,
                dirty_responsibilities=claim["dirty_responsibilities"],
                starting_processed_sequence=int(row.latest_processed_sequence or 0),
                target_sequence=target_sequence,
            )
            return claim


def complete_projection(
    conversation_id: str,
    *,
    worker_id: str,
    lease_token: str,
    processed_sequence: int,
    completed_responsibilities: list[str] | tuple[str, ...] | set[str],
    result: dict[str, Any] | None = None,
    timings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed = set(_normalize_responsibilities(completed_responsibilities))
    now = _now()
    with harness_sync_session_scope() as session:
        row = session.get(ContextProjectionState, conversation_id)
        if row is None:
            raise FileNotFoundError(conversation_id)
        _ensure_lease(row, worker_id=worker_id, lease_token=lease_token)
        current = set(_decode_mask(row.dirty_mask))
        if int(row.latest_observed_sequence or 0) <= int(processed_sequence):
            current -= completed
            row.latest_processed_sequence = max(int(row.latest_processed_sequence or 0), int(processed_sequence))
        row.dirty_mask = _encode_mask(current)
        row.lease_owner = None
        row.lease_token = None
        row.lease_expires_at = None
        row.last_success_at = now
        row.last_error_type = None
        row.last_error_summary = None
        row.attempts = 0
        row.last_result_json = deepcopy(result or {})
        row.updated_at = now
        _finish_projection_run(
            session,
            conversation_id=conversation_id,
            lease_token=lease_token,
            status="completed",
            ending_processed_sequence=int(row.latest_processed_sequence or 0),
            result=result or {},
            timings=timings or {},
        )
        session.flush()
        state = _serialize_state(row)
        emit_projection_perf_event(
            "context_projection.completion",
            status="completed",
            conversation_id=conversation_id,
            worker_id=worker_id,
            dirty_responsibilities=state["dirty_responsibilities"],
            latest_observed_sequence=state["latest_observed_sequence"],
            latest_processed_sequence=state["latest_processed_sequence"],
        )
        return state


def fail_projection(
    conversation_id: str,
    *,
    worker_id: str,
    lease_token: str,
    error: BaseException | str,
    completed_responsibilities: list[str] | tuple[str, ...] | set[str] = (),
    processed_sequence: int | None = None,
    result: dict[str, Any] | None = None,
    timings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = _now()
    error_type = type(error).__name__ if isinstance(error, BaseException) else "ProjectionError"
    error_summary = str(error)[:1000]
    completed = set(_normalize_responsibilities(completed_responsibilities))
    with harness_sync_session_scope() as session:
        row = session.get(ContextProjectionState, conversation_id)
        if row is None:
            raise FileNotFoundError(conversation_id)
        _ensure_lease(row, worker_id=worker_id, lease_token=lease_token)
        current = set(_decode_mask(row.dirty_mask))
        if processed_sequence is not None and int(row.latest_observed_sequence or 0) <= int(processed_sequence):
            current -= completed
        row.dirty_mask = _encode_mask(current)
        row.lease_owner = None
        row.lease_token = None
        row.lease_expires_at = None
        row.last_failure_at = now
        row.last_error_type = error_type
        row.last_error_summary = error_summary
        row.next_project_at = now + timedelta(seconds=_failure_retry_delay_seconds(int(row.attempts or 0)))
        row.last_result_json = deepcopy(result or {}) if result is not None else row.last_result_json
        row.updated_at = now
        _finish_projection_run(
            session,
            conversation_id=conversation_id,
            lease_token=lease_token,
            status="failed",
            ending_processed_sequence=int(row.latest_processed_sequence or 0),
            result=result or {},
            error_type=error_type,
            error_summary=error_summary,
            timings=timings or {},
        )
        session.flush()
        state = _serialize_state(row)
        emit_projection_perf_event(
            "context_projection.failure",
            status="failed",
            conversation_id=conversation_id,
            worker_id=worker_id,
            dirty_responsibilities=state["dirty_responsibilities"],
            completed_responsibilities=sorted(completed),
            error_type=error_type,
        )
        return state


def _ensure_lease(row: ContextProjectionState, *, worker_id: str, lease_token: str) -> None:
    if row.lease_owner != str(worker_id) or row.lease_token != str(lease_token):
        raise RuntimeError("context projection lease is owned by another worker")


def _failure_retry_delay_seconds(attempts: int) -> int:
    return min(
        CONTEXT_PROJECTION_FAILURE_RETRY_MAX_SECONDS,
        max(CONTEXT_PROJECTION_FAILURE_RETRY_MIN_SECONDS, int(attempts or 1) * 2),
    )


def _finish_projection_run(
    session,
    *,
    conversation_id: str,
    lease_token: str,
    status: str,
    ending_processed_sequence: int | None = None,
    result: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_summary: str | None = None,
    timings: dict[str, Any] | None = None,
) -> None:
    run = session.scalars(
        select(ContextProjectionRun)
        .where(
            ContextProjectionRun.conversation_id == conversation_id,
            ContextProjectionRun.lease_token == str(lease_token),
        )
        .order_by(ContextProjectionRun.id.desc())
        .limit(1)
    ).first()
    if run is None:
        return
    run.status = status
    run.ending_processed_sequence = ending_processed_sequence
    run.timings_json = deepcopy(timings or {}) if timings is not None else None
    run.result_json = deepcopy(result or {}) if result is not None else None
    run.error_type = error_type
    run.error_summary = error_summary
    run.updated_at = _now()
