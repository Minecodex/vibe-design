from __future__ import annotations

import uuid
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from sqlalchemy import or_, select, update

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.db.harness_session import harness_sync_session_scope, run_harness_db
from app.models.harness_session import (
    ConversationEvent,
    HarnessAgentActivity,
    HarnessAgentRun,
    HarnessAgentStep,
    HarnessConversation,
)
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    TURN_COMPLETED,
    build_turn_completed_payload,
    build_turn_error,
)
from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError

from .contracts import StepSpec
from .records import WorkflowRunRecord, WorkflowStepRecord, run_from_orm, step_from_orm
from .tool_gating import is_control_tool_breaker_failure
from .status import (
    RUN_ACTIVE_STATUSES,
    RUN_KINDS,
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING_INPUT,
    STEP_APPLY_USER_INPUT,
    STEP_CLAIMABLE_STATUSES,
    STEP_STATUS_CANCELLED,
    STEP_STATUS_CLAIMED,
    STEP_STATUS_FAILED,
    STEP_STATUS_QUEUED,
    STEP_STATUS_RUNNING,
    STEP_STATUS_SUCCEEDED,
    STEP_STATUS_WAITING_INPUT,
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _payload(value: dict[str, Any] | None) -> dict[str, Any]:
    return dict(sanitize_persistent_payload(value or {}))


def _merge_payload(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_payload(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged


def _repeat_idempotency_prefix(idempotency_key: str) -> str:
    digest = sha256(idempotency_key.encode("utf-8")).hexdigest()[:16]
    suffix = f":repeat:{digest}:"
    return f"{idempotency_key[: max(0, 255 - len(suffix) - 24)]}{suffix}"


def _repeat_idempotency_key(idempotency_key: str, run_id: str) -> str:
    return f"{_repeat_idempotency_prefix(idempotency_key)}{str(run_id)[:24]}"


def _bounded_identifier(value: str, *, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    digest = sha256(text.encode("utf-8")).hexdigest()[:20]
    suffix = f":sha:{digest}"
    return f"{text[: max(0, max_length - len(suffix))]}{suffix}"


def _activity_id(value: str) -> str:
    return _bounded_identifier(value, max_length=120)


def _step_id(run_id: str, step_type: str) -> str:
    return f"{str(run_id)[:32]}:{step_type}:{uuid.uuid4().hex[:12]}"


def _invalidate_active_run_cache(conversation_id: str | None) -> None:
    if not conversation_id:
        return
    try:
        from app.services.agent_harness.workspace.session_v2.db_store import invalidate_active_run_state_cache

        invalidate_active_run_state_cache(str(conversation_id))
    except Exception:
        pass


def _run_claimable_filter(now: datetime):
    return (
        or_(
            HarnessAgentStep.status == STEP_STATUS_QUEUED,
            HarnessAgentStep.status.in_([STEP_STATUS_CLAIMED, STEP_STATUS_RUNNING])
            & (HarnessAgentStep.claim_expires_at <= now),
        ),
        or_(HarnessAgentStep.next_run_at.is_(None), HarnessAgentStep.next_run_at <= now),
    )


def _has_active_conversation_step(
    session,
    *,
    conversation_id: str,
    now: datetime,
    exclude_step_pk: int,
) -> bool:
    active_step_id = session.scalars(
        select(HarnessAgentStep.id)
        .where(
            HarnessAgentStep.conversation_id == str(conversation_id),
            HarnessAgentStep.id != int(exclude_step_pk),
            HarnessAgentStep.status.in_([STEP_STATUS_CLAIMED, STEP_STATUS_RUNNING]),
            HarnessAgentStep.claim_expires_at.is_not(None),
            HarnessAgentStep.claim_expires_at > now,
        )
        .limit(1)
    ).first()
    return active_step_id is not None


def _max_attempts_summary(conversation: HarnessConversation | None) -> str:
    if str(getattr(conversation, "last_activity_source", "") or "") == "llm_call_started":
        return (
            "Agent run exceeded max attempts after model call started; "
            "the model call did not complete."
        )
    return "Agent run exceeded max attempts before the step could complete."


def _append_turn_completed_failed_event(
    session,
    *,
    run: HarnessAgentRun,
    step: HarnessAgentStep,
    message: str,
) -> None:
    key = f"run:{run.run_id}:turn-completed"
    existing = session.scalars(
        select(ConversationEvent.id).where(
            ConversationEvent.conversation_id == step.conversation_id,
            ConversationEvent.idempotency_key == key,
        )
    ).first()
    if existing is not None:
        return
    max_sequence = session.scalar(
        select(ConversationEvent.sequence)
        .where(ConversationEvent.conversation_id == step.conversation_id)
        .order_by(ConversationEvent.sequence.desc())
        .limit(1)
    )
    session.add(
        ConversationEvent(
            conversation_id=step.conversation_id,
            user_id=int(step.user_id),
            sequence=int(max_sequence or 0) + 1,
            run_id=str(run.run_id),
            event_type=TURN_COMPLETED,
            lane="user",
            idempotency_key=key,
            payload_json=build_turn_completed_payload(
                conversation_id=step.conversation_id,
                run_id=str(run.run_id),
                status="failed",
                runtime_snapshot={
                    "runtime_status": RUN_STATUS_FAILED,
                    "run_state": RUN_STATUS_FAILED,
                    "turn_status": RUN_STATUS_FAILED,
                    "last_error_summary": message,
                    "failure": {
                        "error_type": "MaxAttemptsExceeded",
                        "summary": message,
                        "failure_source": "queue_exhausted",
                        "step_type": step.step_type,
                    },
                },
                error=build_turn_error("MaxAttemptsExceeded", message),
            ),
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
    )


def _terminalize_exhausted_step(
    *,
    session,
    run: HarnessAgentRun,
    step: HarnessAgentStep,
    now: datetime,
) -> None:
    conversation = session.get(HarnessConversation, step.conversation_id)
    summary = _max_attempts_summary(conversation)
    step.status = STEP_STATUS_FAILED
    step.last_error_type = "MaxAttemptsExceeded"
    step.last_error_summary = summary
    step.claim_owner = None
    step.claim_token = None
    step.claim_expires_at = None
    step.finished_at = now
    step.updated_at = now
    run.status = RUN_STATUS_FAILED
    run.last_error_type = "MaxAttemptsExceeded"
    run.last_error_summary = summary
    run.finished_at = now
    run.updated_at = now
    if conversation is not None:
        snapshot = dict(conversation.runtime_snapshot_json or {})
        failure = {
            "error_type": "MaxAttemptsExceeded",
            "message": summary,
            "failure_source": "queue_exhausted",
        }
        snapshot.update(
            {
                "runtime_status": RUN_STATUS_FAILED,
                "run_state": RUN_STATUS_FAILED,
                "turn_status": RUN_STATUS_FAILED,
                "last_error_summary": summary,
                "failure": failure,
            }
        )
        conversation.runtime_snapshot_json = snapshot
        conversation.runtime_status = RUN_STATUS_FAILED
        conversation.run_state = RUN_STATUS_FAILED
        conversation.turn_status = RUN_STATUS_FAILED
        conversation.last_error_summary = summary
        conversation.active_run_id = None
        conversation.finished_at = now
        conversation.updated_at = now
    _append_turn_completed_failed_event(session, run=run, step=step, message=summary)


def create_run(
    *,
    user_id: int,
    conversation_id: str,
    kind: str,
    input: dict[str, Any],
    idempotency_key: str,
    run_id: str | None = None,
    first_step: StepSpec,
    parent_usage_log_id: int | None = None,
    reject_active_conflicts: bool = True,
) -> WorkflowRunRecord:
    if kind not in RUN_KINDS:
        raise ValueError(f"unsupported workflow run kind: {kind}")
    normalized_key = str(idempotency_key or "").strip()
    if not normalized_key:
        raise ValueError("idempotency_key is required")
    now = _utcnow()
    actual_run_id = run_id or uuid.uuid4().hex
    repeated_key_prefix = _repeat_idempotency_prefix(normalized_key)
    with harness_sync_session_scope() as session:
        conversation = session.scalars(
            select(HarnessConversation)
            .where(HarnessConversation.conversation_id == str(conversation_id))
            .with_for_update()
        ).first()
        existing_rows = session.scalars(
            select(HarnessAgentRun)
            .where(
                HarnessAgentRun.conversation_id == str(conversation_id),
                or_(
                    HarnessAgentRun.idempotency_key == normalized_key,
                    HarnessAgentRun.idempotency_key.startswith(repeated_key_prefix, autoescape=True),
                ),
            )
            .order_by(HarnessAgentRun.created_at.desc())
        ).all()
        for existing in existing_rows:
            if str(existing.status) in RUN_ACTIVE_STATUSES:
                return run_from_orm(existing)
        if reject_active_conflicts:
            active = session.scalars(
                select(HarnessAgentRun.id)
                .where(
                    HarnessAgentRun.conversation_id == str(conversation_id),
                    HarnessAgentRun.status.in_(sorted(RUN_ACTIVE_STATUSES)),
                )
                .limit(1)
            ).first()
            if active is not None:
                raise AgentRunAlreadyActiveError(f"conversation {conversation_id} already has active workflow run")
        effective_parent_usage_log_id = parent_usage_log_id
        if effective_parent_usage_log_id is None and conversation is not None:
            try:
                raw_parent_id = int(conversation.parent_usage_log_id or 0)
            except (TypeError, ValueError):
                raw_parent_id = 0
            effective_parent_usage_log_id = raw_parent_id or None
        storage_key = _repeat_idempotency_key(normalized_key, actual_run_id) if existing_rows else normalized_key
        row = HarnessAgentRun(
            run_id=actual_run_id,
            user_id=int(user_id),
            conversation_id=str(conversation_id),
            kind=str(kind),
            status=RUN_STATUS_QUEUED,
            current_step_type=first_step.step_type,
            input_json=_payload(input),
            idempotency_key=storage_key,
            parent_usage_log_id=effective_parent_usage_log_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        step_key = first_step.idempotency_key or f"run:{actual_run_id}:step:{first_step.step_type}:0"
        step = HarnessAgentStep(
            step_id=_step_id(actual_run_id, first_step.step_type),
            run_id=actual_run_id,
            conversation_id=str(conversation_id),
            user_id=int(user_id),
            step_type=first_step.step_type,
            status=STEP_STATUS_QUEUED,
            input_json=_payload(first_step.input),
            priority=int(first_step.priority or 0),
            max_attempts=max(int(first_step.max_attempts or 1), 1),
            idempotency_key=step_key,
            depends_on_step_id=first_step.depends_on_step_id,
            created_at=now,
            updated_at=now,
        )
        session.add(step)
        if conversation is not None:
            conversation.active_run_id = actual_run_id
            conversation.run_id = actual_run_id
            conversation.runtime_status = "running"
            conversation.run_state = "queued"
            conversation.turn_status = "queued"
            conversation.status = "active"
            conversation.finished_at = None
            snapshot = dict(conversation.runtime_snapshot_json or {})
            snapshot.update(
                {
                    "runtime_status": "running",
                    "run_state": "queued",
                    "turn_status": "queued",
                    "run_id": actual_run_id,
                }
            )
            conversation.runtime_snapshot_json = snapshot
            conversation.updated_at = now
        session.flush()
        return WorkflowRunRecord(**{**run_from_orm(row).__dict__, "created": True})


def get_active_run_for_conversation(conversation_id: str) -> WorkflowRunRecord | None:
    with harness_sync_session_scope() as session:
        row = session.scalars(
            select(HarnessAgentRun)
            .where(
                HarnessAgentRun.conversation_id == str(conversation_id),
                HarnessAgentRun.status.in_(sorted(RUN_ACTIVE_STATUSES)),
            )
            .order_by(HarnessAgentRun.created_at.desc())
            .limit(1)
        ).first()
        return run_from_orm(row) if row is not None else None


def complete_waiting_input_runs_for_conversation(conversation_id: str) -> int:
    now = _utcnow()
    completed = 0
    with harness_sync_session_scope() as session:
        rows = session.scalars(
            select(HarnessAgentRun)
            .where(
                HarnessAgentRun.conversation_id == str(conversation_id),
                HarnessAgentRun.status == RUN_STATUS_WAITING_INPUT,
            )
            .with_for_update()
        ).all()
        for run in rows:
            run.status = RUN_STATUS_COMPLETED
            run.finished_at = now
            run.updated_at = now
            completed += 1
            for step in session.scalars(
                select(HarnessAgentStep).where(
                    HarnessAgentStep.run_id == run.run_id,
                    HarnessAgentStep.status.in_([STEP_STATUS_QUEUED, STEP_STATUS_WAITING_INPUT]),
                )
            ).all():
                if step.status == STEP_STATUS_QUEUED:
                    step.status = STEP_STATUS_CANCELLED
                step.finished_at = step.finished_at or now
                step.updated_at = now
        if completed:
            conversation = session.get(HarnessConversation, str(conversation_id))
            if conversation is not None and any(conversation.active_run_id == row.run_id for row in rows):
                conversation.active_run_id = None
                conversation.updated_at = now
        session.flush()
    return completed


def get_run_parent_usage_log_id(run_id: str) -> int | None:
    with harness_sync_session_scope() as session:
        return session.scalars(
            select(HarnessAgentRun.parent_usage_log_id).where(HarnessAgentRun.run_id == str(run_id))
        ).first()


def set_run_parent_usage_log_id(run_id: str, parent_usage_log_id: int) -> None:
    with harness_sync_session_scope() as session:
        row = session.scalars(
            select(HarnessAgentRun).where(HarnessAgentRun.run_id == str(run_id))
        ).first()
        if row is None:
            return
        row.parent_usage_log_id = int(parent_usage_log_id)
        row.updated_at = _utcnow()


def get_run_runtime_snapshot(run_id: str) -> dict[str, Any]:
    with harness_sync_session_scope() as session:
        row = session.scalars(
            select(HarnessAgentRun.runtime_snapshot_json).where(HarnessAgentRun.run_id == str(run_id))
        ).first()
        return dict(row or {}) if isinstance(row, dict) else {}


def get_latest_step_checkpoint(
    *,
    run_id: str,
    step_type: str,
    status: str = STEP_STATUS_SUCCEEDED,
) -> dict[str, Any]:
    with harness_sync_session_scope() as session:
        row = session.scalars(
            select(HarnessAgentStep.checkpoint_json)
            .where(
                HarnessAgentStep.run_id == str(run_id),
                HarnessAgentStep.step_type == str(step_type),
                HarnessAgentStep.status == str(status),
            )
            .order_by(HarnessAgentStep.finished_at.desc(), HarnessAgentStep.id.desc())
            .limit(1)
        ).first()
        return dict(row or {}) if isinstance(row, dict) else {}


def count_consecutive_tool_validation_failures(
    *,
    run_id: str,
    before_step_pk: int,
    tool_name: str,
) -> int:
    count = 0
    normalized_tool = str(tool_name or "").strip()
    if not normalized_tool:
        return 0
    with harness_sync_session_scope() as session:
        rows = session.scalars(
            select(HarnessAgentStep)
            .where(
                HarnessAgentStep.run_id == str(run_id),
                HarnessAgentStep.id < int(before_step_pk),
                HarnessAgentStep.step_type == "persist_tool_result",
            )
            .order_by(HarnessAgentStep.id.desc())
            .limit(20)
        ).all()
        for row in rows:
            payload = row.input_json if isinstance(row.input_json, dict) else {}
            outcomes = payload.get("outcomes") if isinstance(payload.get("outcomes"), list) else []
            try:
                outcome_index = int(payload.get("outcome_index") or 0)
            except (TypeError, ValueError):
                outcome_index = 0
            outcome = dict(outcomes[outcome_index] or {}) if 0 <= outcome_index < len(outcomes) else {}
            result_payload = outcome.get("result_payload") if isinstance(outcome.get("result_payload"), dict) else {}
            row_tool = str(outcome.get("tool_name") or result_payload.get("tool") or "").strip()
            if row_tool != normalized_tool:
                break
            if not is_control_tool_breaker_failure(outcome):
                break
            count += 1
    return count


def claim_next_step(*, worker_id: str, lease_seconds: int, limit: int = 50) -> WorkflowStepRecord | None:
    now = _utcnow()
    expires_at = now + timedelta(seconds=max(int(lease_seconds or 60), 1))
    with harness_sync_session_scope() as session:
        candidate_ids = list(
            session.scalars(
                select(HarnessAgentStep.id)
                .where(
                    *_run_claimable_filter(now),
                )
                .order_by(HarnessAgentStep.priority.desc(), HarnessAgentStep.created_at.asc())
                .limit(max(int(limit or 1), 1))
            ).all()
        )
        for candidate_id in candidate_ids:
            step = session.scalars(
                select(HarnessAgentStep)
                .where(HarnessAgentStep.id == int(candidate_id))
                .with_for_update(skip_locked=True)
            ).first()
            if step is None:
                continue
            run = session.scalars(
                select(HarnessAgentRun)
                .where(HarnessAgentRun.run_id == step.run_id)
                .with_for_update()
            ).first()
            if run is None or str(run.status) not in RUN_ACTIVE_STATUSES:
                continue
            if str(run.status) == RUN_STATUS_WAITING_INPUT and str(step.step_type) != STEP_APPLY_USER_INPUT:
                continue
            if run.cancel_requested:
                step.status = STEP_STATUS_CANCELLED
                step.finished_at = now
                step.updated_at = now
                run.status = RUN_STATUS_CANCELLED
                run.finished_at = now
                run.updated_at = now
                continue
            if step.status == STEP_STATUS_QUEUED:
                claimable = True
            else:
                claimable = step.status in STEP_CLAIMABLE_STATUSES and step.claim_expires_at is not None and step.claim_expires_at <= now
            if not claimable:
                continue
            if _has_active_conversation_step(
                session,
                conversation_id=step.conversation_id,
                now=now,
                exclude_step_pk=int(step.id),
            ):
                continue
            if int(step.attempts or 0) >= int(step.max_attempts or 1):
                _terminalize_exhausted_step(session=session, run=run, step=step, now=now)
                continue
            token = uuid.uuid4().hex
            step.status = STEP_STATUS_CLAIMED
            step.claim_owner = str(worker_id)
            step.claim_token = token
            step.claim_expires_at = expires_at
            step.claimed_at = now
            step.last_renewed_at = now
            step.attempts = int(step.attempts or 0) + 1
            step.updated_at = now
            run.status = RUN_STATUS_RUNNING
            run.current_step_type = step.step_type
            run.started_at = run.started_at or now
            run.updated_at = now
            session.flush()
            return step_from_orm(step, cancel_requested=bool(run.cancel_requested))
    return None


def _stuck_run_artifact_published(user_id: int, conversation_id: str) -> bool:
    """True if the conversation's artifact manifest is in a published state.

    Used to decide whether a stuck (RUNNING, no-steps) run should be recovered as
    completed rather than failed. Best-effort: any read error is treated as
    not-published so the run still fails closed.
    """
    try:
        from app.services.agent_harness.runtime.artifacts.manifest import read_artifact_manifest

        manifest = read_artifact_manifest(int(user_id), str(conversation_id))
    except Exception:
        return False
    if not isinstance(manifest, dict):
        return False
    publication = manifest.get("publication") if isinstance(manifest.get("publication"), dict) else {}
    return str(publication.get("status") or "").strip().lower() == "published"


def recover_stuck_running_runs(*, grace_seconds: int = 120, limit: int = 50) -> int:
    now = _utcnow()
    cutoff = now - timedelta(seconds=max(int(grace_seconds or 0), 0))
    recovered = 0
    with harness_sync_session_scope() as session:
        run_ids = list(
            session.scalars(
                select(HarnessAgentRun.run_id)
                .where(
                    HarnessAgentRun.status == RUN_STATUS_RUNNING,
                    HarnessAgentRun.updated_at <= cutoff,
                )
                .order_by(HarnessAgentRun.updated_at.asc())
                .limit(max(int(limit or 1), 1))
            ).all()
        )
        for run_id in run_ids:
            run = session.scalars(
                select(HarnessAgentRun)
                .where(HarnessAgentRun.run_id == str(run_id))
                .with_for_update(skip_locked=True)
            ).first()
            if run is None or run.status != RUN_STATUS_RUNNING:
                continue
            active_step = session.scalars(
                select(HarnessAgentStep.id)
                .where(
                    HarnessAgentStep.run_id == run.run_id,
                    HarnessAgentStep.status.in_(
                        [
                            STEP_STATUS_QUEUED,
                            STEP_STATUS_CLAIMED,
                            STEP_STATUS_RUNNING,
                            STEP_STATUS_WAITING_INPUT,
                        ]
                    ),
                )
                .limit(1)
            ).first()
            if active_step is not None:
                continue
            # A stuck run whose artifact was actually published should not be marked
            # FAILED — the deliverable exists. This happens when the post-publish
            # finalize step is lost (e.g. a duplicate idempotency key) and the run is
            # left RUNNING with no steps. Recover it as COMPLETED instead of failing.
            published = _stuck_run_artifact_published(int(run.user_id), str(run.conversation_id))
            if published:
                summary = "Recovered a stuck run whose artifact was already published."
                terminal_status = RUN_STATUS_COMPLETED
                patch = {
                    "runtime_status": RUN_STATUS_COMPLETED,
                    "run_state": RUN_STATUS_COMPLETED,
                    "turn_status": RUN_STATUS_COMPLETED,
                    "failure": None,
                    "recovered_as_completed": True,
                }
            else:
                summary = "Agent run was running but had no remaining workflow steps."
                terminal_status = RUN_STATUS_FAILED
                patch = {
                    "runtime_status": RUN_STATUS_FAILED,
                    "run_state": RUN_STATUS_FAILED,
                    "turn_status": RUN_STATUS_FAILED,
                    "failure": {"error_type": "stuck_running_run", "summary": summary},
                }
            current_snapshot = dict(run.runtime_snapshot_json or {})
            current_snapshot.update(patch)
            run.runtime_snapshot_json = current_snapshot
            run.status = terminal_status
            run.finished_at = now
            run.last_error_type = None if published else "stuck_running_run"
            run.last_error_summary = None if published else summary
            run.updated_at = now
            conversation = session.get(HarnessConversation, run.conversation_id)
            if conversation is not None:
                snapshot = dict(conversation.runtime_snapshot_json or {})
                snapshot.update(patch)
                conversation.runtime_snapshot_json = snapshot
                conversation.active_run_id = None
                conversation.runtime_status = terminal_status
                conversation.run_state = terminal_status
                conversation.turn_status = terminal_status
                conversation.finished_at = now
                conversation.last_error_summary = None if published else summary
                conversation.updated_at = now
            recovered += 1
        session.flush()
    return recovered


async def recover_stuck_running_runs_async(**kwargs: Any) -> int:
    return await run_harness_db(recover_stuck_running_runs, **kwargs)


def mark_step_running(step_id: str, *, claim_token: str) -> WorkflowStepRecord | None:
    now = _utcnow()
    with harness_sync_session_scope() as session:
        step = session.scalars(select(HarnessAgentStep).where(HarnessAgentStep.step_id == str(step_id))).first()
        if step is None or step.claim_token != str(claim_token) or step.status != STEP_STATUS_CLAIMED:
            return None
        run = session.scalars(select(HarnessAgentRun).where(HarnessAgentRun.run_id == step.run_id)).first()
        step.status = STEP_STATUS_RUNNING
        step.started_at = step.started_at or now
        step.updated_at = now
        if run is not None:
            run.status = RUN_STATUS_RUNNING
            run.current_step_type = step.step_type
            run.updated_at = now
        session.flush()
        _invalidate_active_run_cache(step.conversation_id)
        return step_from_orm(step, cancel_requested=bool(getattr(run, "cancel_requested", False)))


def renew_step_claim(step_id: str, *, claim_token: str, lease_seconds: int) -> bool:
    now = _utcnow()
    with harness_sync_session_scope() as session:
        result = session.execute(
            update(HarnessAgentStep)
            .where(
                HarnessAgentStep.step_id == str(step_id),
                HarnessAgentStep.claim_token == str(claim_token),
                HarnessAgentStep.status.in_([STEP_STATUS_CLAIMED, STEP_STATUS_RUNNING]),
            )
            .values(
                claim_expires_at=now + timedelta(seconds=max(int(lease_seconds or 60), 1)),
                last_renewed_at=now,
                updated_at=now,
            )
        )
        ok = int(result.rowcount or 0) == 1
        if ok:
            conversation_id = session.scalars(
                select(HarnessAgentStep.conversation_id).where(HarnessAgentStep.step_id == str(step_id))
            ).first()
            _invalidate_active_run_cache(conversation_id)
        return ok


def update_step_checkpoint(
    step_id: str,
    *,
    claim_token: str,
    patch: dict[str, Any],
) -> WorkflowStepRecord | None:
    if not patch:
        with harness_sync_session_scope() as session:
            row = session.scalars(select(HarnessAgentStep).where(HarnessAgentStep.step_id == str(step_id))).first()
            return step_from_orm(row) if row is not None else None
    now = _utcnow()
    with harness_sync_session_scope() as session:
        step = session.scalars(select(HarnessAgentStep).where(HarnessAgentStep.step_id == str(step_id))).first()
        if (
            step is None
            or step.claim_token != str(claim_token)
            or str(step.status) not in {STEP_STATUS_CLAIMED, STEP_STATUS_RUNNING}
        ):
            return None
        checkpoint = _merge_payload(dict(step.checkpoint_json or {}), _payload(patch))
        step.checkpoint_json = checkpoint
        step.updated_at = now
        session.flush()
        run = session.scalars(select(HarnessAgentRun).where(HarnessAgentRun.run_id == step.run_id)).first()
        _invalidate_active_run_cache(step.conversation_id)
        return step_from_orm(step, cancel_requested=bool(getattr(run, "cancel_requested", False)))


def is_cancel_requested(run_id: str) -> bool:
    with harness_sync_session_scope() as session:
        row = session.scalars(select(HarnessAgentRun.cancel_requested).where(HarnessAgentRun.run_id == str(run_id))).first()
        return bool(row)


def request_cancel(conversation_id: str, *, reason: str = "user") -> bool:
    now = _utcnow()
    with harness_sync_session_scope() as session:
        rows = session.scalars(
            select(HarnessAgentRun)
            .where(
                HarnessAgentRun.conversation_id == str(conversation_id),
                HarnessAgentRun.status.in_(sorted(RUN_ACTIVE_STATUSES)),
            )
            .order_by(HarnessAgentRun.created_at.desc())
        ).all()
        if not rows:
            return False
        for run in rows:
            run.cancel_requested = True
            run.cancel_requested_at = now
            run.cancel_reason = str(reason or "user")
            run.updated_at = now
            if run.status in {RUN_STATUS_QUEUED, RUN_STATUS_WAITING_INPUT}:
                run.status = RUN_STATUS_CANCELLED
                run.finished_at = now
                for step in session.scalars(
                    select(HarnessAgentStep).where(
                        HarnessAgentStep.run_id == run.run_id,
                        HarnessAgentStep.status.in_([STEP_STATUS_QUEUED, STEP_STATUS_WAITING_INPUT]),
                    )
                ).all():
                    step.status = STEP_STATUS_CANCELLED
                    step.finished_at = now
                    step.updated_at = now
        conversation = session.get(HarnessConversation, str(conversation_id))
        if conversation is not None:
            snapshot = dict(conversation.runtime_snapshot_json or {})
            terminalized = all(str(run.status) == RUN_STATUS_CANCELLED for run in rows)
            snapshot.update(
                {
                    "runtime_status": RUN_STATUS_CANCELLED,
                    "run_state": RUN_STATUS_CANCELLED if terminalized else "cancelling",
                    "turn_status": RUN_STATUS_CANCELLED if terminalized else "cancelling",
                    "cancel_reason": str(reason or "user"),
                }
            )
            conversation.runtime_snapshot_json = snapshot
            if terminalized:
                conversation.active_run_id = None
                conversation.runtime_status = RUN_STATUS_CANCELLED
                conversation.run_state = RUN_STATUS_CANCELLED
                conversation.turn_status = RUN_STATUS_CANCELLED
                conversation.finished_at = now
            else:
                conversation.runtime_status = RUN_STATUS_CANCELLED
                conversation.run_state = "cancelling"
                conversation.turn_status = "cancelling"
            conversation.updated_at = now
        return True


def enqueue_step(*, run_id: str, user_id: int, conversation_id: str, spec: StepSpec) -> WorkflowStepRecord:
    now = _utcnow()
    with harness_sync_session_scope() as session:
        key = spec.idempotency_key or f"run:{run_id}:step:{spec.step_type}:{uuid.uuid4().hex[:8]}"
        existing = session.scalars(
            select(HarnessAgentStep).where(
                HarnessAgentStep.run_id == str(run_id),
                HarnessAgentStep.idempotency_key == key,
            )
        ).first()
        if existing is not None:
            return step_from_orm(existing)
        row = HarnessAgentStep(
            step_id=_step_id(run_id, spec.step_type),
            run_id=str(run_id),
            conversation_id=str(conversation_id),
            user_id=int(user_id),
            step_type=spec.step_type,
            status=STEP_STATUS_QUEUED,
            input_json=_payload(spec.input),
            priority=int(spec.priority or 0),
            max_attempts=max(int(spec.max_attempts or 1), 1),
            depends_on_step_id=spec.depends_on_step_id,
            idempotency_key=key,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        run = session.scalars(select(HarnessAgentRun).where(HarnessAgentRun.run_id == str(run_id))).first()
        if run is not None:
            run.current_step_type = spec.step_type
            run.status = RUN_STATUS_RUNNING
            run.updated_at = now
        session.flush()
        return step_from_orm(row)


def complete_step(
    step_id: str,
    *,
    claim_token: str,
    status: str,
    output: dict[str, Any] | None = None,
    runtime_patch: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_summary: str | None = None,
    terminal_run: bool = False,
) -> WorkflowStepRecord | None:
    now = _utcnow()
    with harness_sync_session_scope() as session:
        step = session.scalars(select(HarnessAgentStep).where(HarnessAgentStep.step_id == str(step_id))).first()
        if step is None or step.claim_token != str(claim_token):
            return None
        run = session.scalars(select(HarnessAgentRun).where(HarnessAgentRun.run_id == step.run_id)).first()
        conversation = session.get(HarnessConversation, step.conversation_id)
        step.status = status
        step.output_json = _payload(output)
        step.last_error_type = error_type
        step.last_error_summary = error_summary
        step.finished_at = now
        step.claim_owner = None
        step.claim_token = None
        step.claim_expires_at = None
        step.updated_at = now
        patch = _payload(runtime_patch)
        if run is not None:
            current_snapshot = dict(run.runtime_snapshot_json or {})
            current_snapshot.update(patch)
            run.runtime_snapshot_json = current_snapshot
            if status == STEP_STATUS_WAITING_INPUT:
                run.status = RUN_STATUS_WAITING_INPUT
            elif status == STEP_STATUS_FAILED:
                run.status = RUN_STATUS_FAILED
            elif status == STEP_STATUS_CANCELLED:
                run.status = RUN_STATUS_CANCELLED
            elif terminal_run:
                run.status = RUN_STATUS_COMPLETED if status == STEP_STATUS_SUCCEEDED else RUN_STATUS_FAILED
            else:
                run.status = RUN_STATUS_RUNNING
            run.last_error_type = error_type
            run.last_error_summary = error_summary
            if run.status in {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED, RUN_STATUS_WAITING_INPUT}:
                run.finished_at = now if run.status != RUN_STATUS_WAITING_INPUT else None
            run.updated_at = now
        if conversation is not None:
            snapshot = dict(conversation.runtime_snapshot_json or {})
            snapshot.update(patch)
            conversation.runtime_snapshot_json = snapshot
            if run is not None and run.status in {RUN_STATUS_COMPLETED, RUN_STATUS_FAILED, RUN_STATUS_CANCELLED}:
                conversation.active_run_id = None
                conversation.runtime_status = run.status
                conversation.run_state = run.status
                conversation.turn_status = run.status
                conversation.finished_at = now
            elif run is not None and run.status == RUN_STATUS_WAITING_INPUT:
                conversation.runtime_status = RUN_STATUS_WAITING_INPUT
                conversation.run_state = RUN_STATUS_WAITING_INPUT
                conversation.turn_status = RUN_STATUS_WAITING_INPUT
            conversation.updated_at = now
        session.flush()
        _invalidate_active_run_cache(step.conversation_id)
        return step_from_orm(step, cancel_requested=bool(getattr(run, "cancel_requested", False)))


def release_step_for_retry(
    step_id: str,
    *,
    claim_token: str,
    error_type: str,
    error_summary: str,
    retry_delay_seconds: float = 1.0,
) -> bool:
    now = _utcnow()
    next_run_at = now + timedelta(seconds=max(float(retry_delay_seconds or 0), 0.0))
    with harness_sync_session_scope() as session:
        step = session.scalars(select(HarnessAgentStep).where(HarnessAgentStep.step_id == str(step_id))).first()
        if step is None or step.claim_token != str(claim_token):
            return False
        if int(step.attempts or 0) >= int(step.max_attempts or 1):
            return False
        run = session.scalars(select(HarnessAgentRun).where(HarnessAgentRun.run_id == step.run_id)).first()
        step.status = STEP_STATUS_QUEUED
        step.claim_owner = None
        step.claim_token = None
        step.claim_expires_at = None
        step.next_run_at = next_run_at
        step.last_error_type = str(error_type or "")
        step.last_error_summary = str(error_summary or "")[:500]
        step.updated_at = now
        if run is not None:
            run.status = RUN_STATUS_QUEUED
            run.last_error_type = str(error_type or "")
            run.last_error_summary = str(error_summary or "")[:500]
            run.updated_at = now
        _invalidate_active_run_cache(step.conversation_id)
        return True


def record_activity(
    *,
    activity_id: str,
    run_id: str,
    step_id: str,
    conversation_id: str,
    activity_type: str,
    status: str,
    attempt: int,
    input_ref: str | None = None,
    output_ref: str | None = None,
    elapsed_ms: float | None = None,
    diagnostics: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_summary: str | None = None,
) -> None:
    now = _utcnow()
    stored_activity_id = _activity_id(activity_id)
    with harness_sync_session_scope() as session:
        existing = session.scalars(
            select(HarnessAgentActivity).where(HarnessAgentActivity.activity_id == stored_activity_id)
        ).first()
        if existing is not None:
            existing.status = str(status)
            existing.input_ref = input_ref
            existing.output_ref = output_ref
            existing.elapsed_ms = elapsed_ms
            existing.diagnostics_json = deepcopy(diagnostics)
            existing.error_type = error_type
            existing.error_summary = error_summary
            existing.finished_at = now
            existing.updated_at = now
            return
        session.add(
            HarnessAgentActivity(
                activity_id=stored_activity_id,
                run_id=str(run_id),
                step_id=str(step_id),
                conversation_id=str(conversation_id),
                activity_type=str(activity_type),
                status=str(status),
                attempt=max(int(attempt or 1), 1),
                input_ref=input_ref,
                output_ref=output_ref,
                diagnostics_json=deepcopy(diagnostics),
                elapsed_ms=elapsed_ms,
                started_at=now,
                finished_at=now,
                error_type=error_type,
                error_summary=error_summary,
                created_at=now,
                updated_at=now,
            )
        )


async def create_run_async(**kwargs: Any) -> WorkflowRunRecord:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.create_run, **kwargs)


async def get_active_run_for_conversation_async(conversation_id: str) -> WorkflowRunRecord | None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.get_active_run_for_conversation, conversation_id)


async def complete_waiting_input_runs_for_conversation_async(conversation_id: str) -> int:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.complete_waiting_input_runs_for_conversation, conversation_id)


async def get_run_parent_usage_log_id_async(run_id: str) -> int | None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.get_run_parent_usage_log_id, run_id)


async def set_run_parent_usage_log_id_async(run_id: str, parent_usage_log_id: int) -> None:
    from app.services.agent_harness.workflow import repositories as _self

    await run_harness_db(_self.set_run_parent_usage_log_id, run_id, parent_usage_log_id)


async def get_run_runtime_snapshot_async(run_id: str) -> dict[str, Any]:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.get_run_runtime_snapshot, run_id)


async def get_latest_step_checkpoint_async(**kwargs: Any) -> dict[str, Any]:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.get_latest_step_checkpoint, **kwargs)


async def count_consecutive_tool_validation_failures_async(**kwargs: Any) -> int:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.count_consecutive_tool_validation_failures, **kwargs)


async def claim_next_step_async(**kwargs: Any) -> WorkflowStepRecord | None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.claim_next_step, **kwargs)


async def mark_step_running_async(step_id: str, **kwargs: Any) -> WorkflowStepRecord | None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.mark_step_running, step_id, **kwargs)


async def renew_step_claim_async(step_id: str, **kwargs: Any) -> bool:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.renew_step_claim, step_id, **kwargs)


async def update_step_checkpoint_async(step_id: str, **kwargs: Any) -> WorkflowStepRecord | None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.update_step_checkpoint, step_id, **kwargs)


async def complete_step_async(step_id: str, **kwargs: Any) -> WorkflowStepRecord | None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.complete_step, step_id, **kwargs)


async def release_step_for_retry_async(step_id: str, **kwargs: Any) -> bool:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.release_step_for_retry, step_id, **kwargs)


async def request_cancel_async(conversation_id: str, **kwargs: Any) -> bool:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.request_cancel, conversation_id, **kwargs)


async def enqueue_step_async(**kwargs: Any) -> WorkflowStepRecord:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.enqueue_step, **kwargs)


async def record_activity_async(**kwargs: Any) -> None:
    from app.services.agent_harness.workflow import repositories as _self

    return await run_harness_db(_self.record_activity, **kwargs)
