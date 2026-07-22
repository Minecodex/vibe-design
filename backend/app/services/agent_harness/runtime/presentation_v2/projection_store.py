from __future__ import annotations

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select, update

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import (
    ConversationEvent,
    HarnessConversation,
    HarnessMessage,
    HarnessPresentationProjectionState,
)
from app.services.agent_harness.runtime.presentation_v2.keys import message_key_for_event, stored_message_id
from app.services.agent_harness.runtime.presentation_v2.protocol import PROTOCOL_VERSION, PresentationOp, block_from_op
from app.services.agent_harness.runtime.presentation_v2.reducer import reduce_event_to_ops

logger = logging.getLogger(__name__)


def project_committed_event(user_id: int, conversation_id: str, event: dict[str, Any]) -> None:
    """Catch the durable presentation projection up to this committed event.

    The actual op reduction + apply happens inside ``reconcile_projection`` (which
    replays the committed log in sequence order). We intentionally do *not* call
    ``reduce_event_to_ops`` here: its result was previously discarded by every
    caller, so computing it was pure overhead.
    """
    if event.get("transient") or str(event.get("lane") or "user").strip().lower() != "user":
        return
    source_sequence = int(event.get("sequence") or event.get("seq") or 0)
    try:
        reconcile_projection(
            user_id,
            conversation_id,
            worker_id=f"presentation-v2:append:{conversation_id}:{source_sequence}",
        )
    except Exception:
        _mark_projection_failed(user_id, conversation_id, source_sequence, "projection_failed")
        logger.info("Presentation v2 projection failed for %s@%s", conversation_id, source_sequence, exc_info=True)


def reconcile_projection(
    user_id: int,
    conversation_id: str,
    *,
    lease_seconds: int = 30,
    limit: int = 500,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Catch the presentation snapshot up to the durable event log.

    The projection cursor is only advanced after each event is successfully
    applied in sequence. If another worker already owns the lease, callers get
    the current state and can keep using the previous cursor.
    """
    from app.services.agent_harness.runtime.conversation_events import (
        latest_conversation_event_sequence,
        load_conversation_events,
    )

    latest_sequence = latest_conversation_event_sequence(user_id, conversation_id)
    owner = str(worker_id or f"presentation-v2:{uuid.uuid4().hex}").strip()
    claim = _claim_projection_lease(
        user_id,
        conversation_id,
        owner=owner,
        latest_sequence=latest_sequence,
        lease_seconds=lease_seconds,
    )
    if claim is None:
        return get_projection_state(user_id, conversation_id)
    applied_sequence = int(claim.get("applied_event_sequence") or 0)
    try:
        while applied_sequence < latest_sequence:
            events = load_conversation_events(
                user_id,
                conversation_id,
                after_sequence=applied_sequence,
                limit=limit,
            )
            if not events:
                break
            for event in events:
                source_sequence = int(event.get("sequence") or event.get("seq") or 0)
                if source_sequence <= applied_sequence:
                    continue
                _apply_committed_event(user_id, conversation_id, event, expected_sequence=source_sequence)
                applied_sequence = source_sequence
            if len(events) < max(1, int(limit or 1)):
                break
        _backfill_user_message_attachments(user_id, conversation_id, up_to_sequence=applied_sequence)
        _backfill_shipped_critique_cards(user_id, conversation_id, up_to_sequence=applied_sequence)
        _release_projection_lease(user_id, conversation_id, owner=owner, success=True)
    except Exception:
        _release_projection_lease(user_id, conversation_id, owner=owner, success=False, error_code="reconcile_failed")
        logger.info("Presentation v2 reconcile failed for %s", conversation_id, exc_info=True)
    return get_projection_state(user_id, conversation_id)


def _backfill_user_message_attachments(user_id: int, conversation_id: str, *, up_to_sequence: int) -> None:
    if int(up_to_sequence or 0) <= 0:
        return
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events

    events: list[dict[str, Any]] = []
    after_sequence = 0
    while after_sequence < int(up_to_sequence or 0):
        batch = load_conversation_events(
            user_id,
            conversation_id,
            after_sequence=after_sequence,
            limit=500,
        )
        if not batch:
            break
        for event in batch:
            sequence = int(event.get("sequence") or event.get("seq") or 0)
            if sequence > int(up_to_sequence or 0):
                break
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            attachments = payload.get("attachments")
            if (
                str(event.get("type") or event.get("event_type") or "").strip() == "user_message"
                and isinstance(attachments, list)
                and attachments
            ):
                events.append(event)
        next_after_sequence = int(batch[-1].get("sequence") or batch[-1].get("seq") or after_sequence)
        if next_after_sequence <= after_sequence:
            break
        after_sequence = next_after_sequence

    if not events:
        return

    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if conversation is None or int(conversation.user_id) != int(user_id):
            return
        changed = False
        for event in events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
            if not attachments:
                continue
            message_id = stored_message_id(message_key_for_event(event, role="user"))
            row = _find_message(session, conversation, message_id)
            if row is None or row.attachments_json:
                continue
            row.attachments_json = deepcopy(sanitize_persistent_payload(attachments))
            row.updated_at = _db_utcnow()
            changed = True
        if changed:
            session.flush()


def get_projection_state(user_id: int, conversation_id: str) -> dict[str, Any]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if conversation is None or int(conversation.user_id) != int(user_id):
            return {
                "protocol_version": PROTOCOL_VERSION,
                "applied_event_sequence": 0,
                "latest_observed_sequence": 0,
                "status": "idle",
            }
        state = session.get(HarnessPresentationProjectionState, conversation_id)
        if state is None:
            return {
                "protocol_version": PROTOCOL_VERSION,
                "applied_event_sequence": 0,
                "latest_observed_sequence": 0,
                "status": "idle",
            }
        return {
            "protocol_version": int(state.protocol_version or PROTOCOL_VERSION),
            "applied_event_sequence": int(state.applied_event_sequence or 0),
            "latest_observed_sequence": int(state.latest_observed_sequence or 0),
            "status": str(state.status or "idle"),
            "lease_owner": state.lease_owner,
            "lease_expires_at": _iso_datetime(state.lease_expires_at),
            "last_error_code": state.last_error_code,
        }


def _apply_committed_event(
    user_id: int,
    conversation_id: str,
    event: dict[str, Any],
    *,
    expected_sequence: int,
) -> None:
    source_sequence = int(event.get("sequence") or event.get("seq") or 0)
    if source_sequence != int(expected_sequence or 0):
        raise ValueError("event sequence mismatch")
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if conversation is None or int(conversation.user_id) != int(user_id):
            raise FileNotFoundError(conversation_id)
        state = _ensure_state(session, user_id, conversation_id)
        previous_applied = int(state.applied_event_sequence or 0)
        if source_sequence <= previous_applied:
            state.latest_observed_sequence = max(int(state.latest_observed_sequence or 0), source_sequence)
            state.updated_at = _db_utcnow()
            return
        if source_sequence != previous_applied + 1:
            # A hole in the sequence (e.g. a deleted/never-written sequence
            # number). Sequences are assigned as max(sequence)+1 under a unique
            # constraint with retry, so once sequence N is visible every sequence
            # < N is already committed — a hole is therefore *permanent* and will
            # never be filled. Skip forward over it (advancing the cursor to this
            # event) instead of stalling the projection indefinitely.
            logger.info(
                "Presentation v2 skipping sequence gap for %s: %s -> %s",
                conversation_id,
                previous_applied,
                source_sequence,
            )
        state.latest_observed_sequence = max(int(state.latest_observed_sequence or 0), source_sequence)
        state.status = "running"
        session.flush()
        if str(event.get("lane") or "user").strip().lower() == "user":
            for op in reduce_event_to_ops(event):
                _apply_op(session, conversation, op)
        state.applied_event_sequence = source_sequence
        state.status = "idle"
        state.last_error_code = None
        state.last_error_at = None
        state.updated_at = _db_utcnow()
        snapshot = dict(conversation.runtime_snapshot_json or {})
        snapshot["protocol_version"] = PROTOCOL_VERSION
        conversation.runtime_snapshot_json = snapshot
        session.flush()


def _backfill_shipped_critique_cards(user_id: int, conversation_id: str, *, up_to_sequence: int) -> None:
    """Materialize shipped critique cards for projections created before this event was rendered."""
    if int(up_to_sequence or 0) <= 0:
        return
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if conversation is None or int(conversation.user_id) != int(user_id):
            return
        rows = session.scalars(
            select(ConversationEvent)
            .where(
                ConversationEvent.conversation_id == conversation_id,
                ConversationEvent.user_id == int(user_id),
                ConversationEvent.lane == "user",
                ConversationEvent.event_type == "critique.shipped",
                ConversationEvent.sequence <= int(up_to_sequence),
            )
            .order_by(ConversationEvent.sequence.asc())
        ).all()
        for row in rows:
            event = {
                "id": int(row.id),
                "event_id": int(row.id),
                "conversation_id": row.conversation_id,
                "user_id": int(row.user_id),
                "sequence": int(row.sequence),
                "seq": int(row.sequence),
                "run_id": row.run_id,
                "type": row.event_type,
                "event_type": row.event_type,
                "lane": row.lane,
                "idempotency_key": row.idempotency_key,
                "payload": deepcopy(row.payload_json) if isinstance(row.payload_json, dict) else {},
                "block_id": row.block_id,
                "agent_id": row.agent_id,
                "tool_call_id": row.tool_call_id,
                "artifact_id": row.artifact_id,
                "parent_block_id": row.parent_block_id,
                "created_at": _iso_datetime(row.created_at),
                "ts": _iso_datetime(row.created_at),
            }
            for op in reduce_event_to_ops(event):
                _apply_op(session, conversation, op)
        session.flush()


def _claim_projection_lease(
    user_id: int,
    conversation_id: str,
    *,
    owner: str,
    latest_sequence: int,
    lease_seconds: int,
) -> dict[str, Any] | None:
    now = _db_utcnow()
    lease_expires_at = now + timedelta(seconds=max(1, int(lease_seconds or 30)))
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if conversation is None or int(conversation.user_id) != int(user_id):
            raise FileNotFoundError(conversation_id)
        state = _ensure_state(session, user_id, conversation_id)
        state.latest_observed_sequence = max(int(state.latest_observed_sequence or 0), int(latest_sequence or 0))
        session.flush()
        result = session.execute(
            update(HarnessPresentationProjectionState)
            .where(
                HarnessPresentationProjectionState.conversation_id == conversation_id,
                HarnessPresentationProjectionState.user_id == int(user_id),
                or_(
                    HarnessPresentationProjectionState.lease_owner.is_(None),
                    HarnessPresentationProjectionState.lease_expires_at.is_(None),
                    HarnessPresentationProjectionState.lease_expires_at <= now,
                    HarnessPresentationProjectionState.lease_owner == owner,
                ),
            )
            .execution_options(synchronize_session=False)
            .values(
                lease_owner=owner,
                lease_expires_at=lease_expires_at,
                status="running",
                latest_observed_sequence=max(int(state.latest_observed_sequence or 0), int(latest_sequence or 0)),
                updated_at=now,
            )
        )
        if int(result.rowcount or 0) != 1:
            return None
        state.lease_owner = owner
        state.lease_expires_at = lease_expires_at
        state.status = "running"
        state.updated_at = now
        session.flush()
        return {
            "applied_event_sequence": int(state.applied_event_sequence or 0),
            "latest_observed_sequence": int(state.latest_observed_sequence or 0),
        }


def _release_projection_lease(
    user_id: int,
    conversation_id: str,
    *,
    owner: str,
    success: bool,
    error_code: str | None = None,
) -> None:
    now = _db_utcnow()
    with harness_sync_session_scope() as session:
        state = session.get(HarnessPresentationProjectionState, conversation_id)
        if state is None or int(state.user_id) != int(user_id) or str(state.lease_owner or "") != owner:
            return
        state.lease_owner = None
        state.lease_expires_at = None
        state.status = "idle" if success else "failed"
        if success:
            state.last_error_code = None
            state.last_error_at = None
        else:
            state.last_error_code = error_code or "projection_failed"
            state.last_error_at = now
        state.updated_at = now


def _ensure_state(session, user_id: int, conversation_id: str) -> HarnessPresentationProjectionState:
    state = session.get(HarnessPresentationProjectionState, conversation_id)
    if state is not None:
        return state
    now = _db_utcnow()
    state = HarnessPresentationProjectionState(
        conversation_id=conversation_id,
        user_id=int(user_id),
        protocol_version=PROTOCOL_VERSION,
        applied_event_sequence=0,
        latest_observed_sequence=0,
        status="idle",
        created_at=now,
        updated_at=now,
    )
    session.add(state)
    session.flush()
    return state


def _mark_projection_failed(user_id: int, conversation_id: str, source_sequence: int, error_code: str) -> None:
    try:
        with harness_sync_session_scope() as session:
            state = _ensure_state(session, user_id, conversation_id)
            state.latest_observed_sequence = max(int(state.latest_observed_sequence or 0), int(source_sequence or 0))
            state.status = "failed"
            state.last_error_code = error_code
            state.last_error_at = _db_utcnow()
            state.updated_at = _db_utcnow()
    except Exception:
        logger.info("Failed to mark presentation projection failure", exc_info=True)


def _apply_op(session, conversation: HarnessConversation, op: PresentationOp) -> None:
    op_type = str(op.get("type") or "")
    if op_type == "presentation.conversation.patch":
        _apply_conversation_patch(conversation, op)
        return
    message_key = str(op.get("message_key") or "")
    message_id = stored_message_id(message_key)
    existing_row = _find_message(session, conversation, message_id) or _find_replace_current_plan_message(
        session,
        conversation,
        op,
    )
    if existing_row is None:
        if _requires_existing_progress(op) and not _has_outline_runtime(conversation):
            return
        if bool(op.get("requires_existing_message")):
            return
    pre_message_count = int(conversation.message_count or 0)
    row = existing_row or _create_message(session, conversation, message_id, message_key, str(op.get("role") or "assistant"), op)
    metadata = dict(row.metadata_json or {})
    op_id = str(op.get("op_id") or "").strip()
    applied_op_ids = [str(value) for value in list(metadata.get("applied_op_ids") or []) if value]
    if op_id and op_id in applied_op_ids:
        return
    metadata.update(
        {
            "protocol_version": PROTOCOL_VERSION,
            "message_key": message_key,
            "source_run_id": op.get("run_id"),
            "source_turn_id": op.get("turn_id"),
            "display_source_event_sequence": _display_source_event_sequence(metadata, op),
            "source_event_sequence": int(op.get("source_sequence") or 0),
            "render_kind": "presentation_v2",
        }
    )
    render_key = _render_key_from_op(op)
    if render_key:
        metadata["render_key"] = render_key
        metadata["render_only"] = True
    message_kind = _message_kind_from_op(op)
    if message_kind:
        metadata["message_kind"] = message_kind
    if op_id:
        metadata["applied_op_ids"] = [*applied_op_ids[-199:], op_id]
    if op_type == "presentation.message.upsert":
        payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
        payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        if payload_metadata:
            metadata.update(deepcopy(payload_metadata))
            metadata.update(
                {
                    "protocol_version": PROTOCOL_VERSION,
                    "message_key": message_key,
                    "source_run_id": op.get("run_id"),
                    "source_turn_id": op.get("turn_id"),
                    "display_source_event_sequence": _display_source_event_sequence(metadata, op),
                    "source_event_sequence": int(op.get("source_sequence") or 0),
                    "render_kind": "presentation_v2",
                }
            )
        blocks = payload.get("blocks") if isinstance(payload.get("blocks"), list) else None
        if "content" in payload or op.get("content") is not None:
            row.content = sanitize_persistent_payload(op.get("content") if op.get("content") is not None else payload.get("content"), field_name="content")
        if blocks is not None:
            row.blocks_json = [_normalize_stored_block(block) for block in blocks if isinstance(block, dict)]
        if "attachments" in payload:
            attachments = payload.get("attachments") if isinstance(payload.get("attachments"), list) else []
            row.attachments_json = deepcopy(sanitize_persistent_payload(attachments))
        row.streaming = str(op.get("status") or "") == "running"
        if str(op.get("role") or "") == "user":
            _maybe_promote_first_user_message_title(conversation, row, pre_message_count)
    elif op_type == "presentation.block.remove":
        row.blocks_json = _remove_block(row.blocks_json or [], str(op.get("block_key") or ""))
    elif _is_replace_current_plan_op(op):
        row.blocks_json = [block_from_op(op)]
        row.content = _extract_text(row.blocks_json)
        row.streaming = _has_running_blocks(row.blocks_json)
    else:
        row.blocks_json = _apply_block_op(row.blocks_json or [], op)
        row.content = _extract_text(row.blocks_json)
        row.streaming = _has_running_blocks(row.blocks_json)
    row.metadata_json = sanitize_persistent_payload(_normalize_projection_metadata(metadata))
    row.updated_at = _db_utcnow()
    conversation.last_message_preview = (row.content or "")[:160]
    conversation.updated_at = row.updated_at


def _maybe_promote_first_user_message_title(
    conversation: HarnessConversation,
    row: HarnessMessage,
    pre_message_count: int,
) -> None:
    """Promote a default conversation title from the first user message.

    In v2 the user message is created by the presentation projection rather than
    ``db_store.append_message_record``, so the title-promotion that used to live
    there must run here too. Reuses the db_store predicate/derivation as the single
    source of truth (local import avoids the projection_store<->db_store cycle).
    """
    if int(pre_message_count or 0) != 0 or str(row.role or "") != "user":
        return
    if not str(row.content or "").strip():
        return
    from app.services.agent_harness.workspace.session_v2.db_store import (
        DEFAULT_CONVERSATION_TITLES,
        _conversation_title_from_user_message,
    )

    if str(conversation.title or "").strip() not in DEFAULT_CONVERSATION_TITLES:
        return
    conversation.title = _conversation_title_from_user_message({"content": row.content})


def _apply_conversation_patch(conversation: HarnessConversation, op: PresentationOp) -> None:
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    patch = payload.get("patch") if isinstance(payload.get("patch"), dict) else payload
    allowed_fields = {
        "skill_id",
        "resolved_skill_id",
        "skill_selection_mode",
        "skill_resolution_source",
        "artifact_mode",
        "last_skill_decision_reason",
        "last_skill_decision_confidence",
        "design_system_id",
        "phase",
    }
    for key in allowed_fields:
        if key not in patch:
            continue
        if not hasattr(conversation, key):
            continue
        setattr(conversation, key, sanitize_persistent_payload(patch.get(key), field_name=key))
    snapshot = dict(conversation.runtime_snapshot_json or {})
    snapshot["protocol_version"] = PROTOCOL_VERSION
    conversation.runtime_snapshot_json = snapshot
    conversation.updated_at = _db_utcnow()


def _find_message(
    session,
    conversation: HarnessConversation,
    message_id: str,
) -> HarnessMessage | None:
    return session.scalar(
        select(HarnessMessage).where(
            HarnessMessage.conversation_id == conversation.conversation_id,
            HarnessMessage.message_id == message_id,
        )
    )


def _find_replace_current_plan_message(
    session,
    conversation: HarnessConversation,
    op: PresentationOp,
) -> HarnessMessage | None:
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    if not bool(payload.get("replace_current")):
        return None
    plan_instance_id = str(payload.get("plan_instance_id") or payload.get("planInstanceId") or "").strip()
    if not plan_instance_id:
        return None
    rows = session.scalars(
        select(HarnessMessage)
        .where(HarnessMessage.conversation_id == conversation.conversation_id)
        .order_by(HarnessMessage.created_at.desc())
    ).all()
    for row in rows:
        metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
        render_key = str(metadata.get("render_key") or "")
        if not render_key.startswith(f"home-user-plan:{plan_instance_id}:"):
            continue
        blocks = row.blocks_json if isinstance(row.blocks_json, list) else []
        first_block = next((block for block in blocks if isinstance(block, dict)), None)
        block_payload = first_block.get("payload") if isinstance(first_block, dict) and isinstance(first_block.get("payload"), dict) else {}
        snapshot_status = str(
            block_payload.get("snapshotStatus")
            or block_payload.get("snapshot_status")
            or block_payload.get("status")
            or ""
        ).strip().lower()
        if snapshot_status in {"", "active", "executing", "finalizing"}:
            return row
    return None


def _normalize_projection_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(metadata)
    if str(normalized.get("render_kind") or "").strip() == "presentation_v2":
        normalized.pop("ui_visible", None)
        normalized.pop("model_visible", None)
        if str(normalized.get("message_kind") or "").strip() == "agent_context":
            normalized.pop("message_kind", None)
    return normalized


def _is_replace_current_plan_op(op: PresentationOp) -> bool:
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    block = op.get("block") if isinstance(op.get("block"), dict) else {}
    ui_kind = str(block.get("ui_kind") or block.get("uiKind") or "")
    return bool(payload.get("replace_current")) and ui_kind == "user_plan_card"


def _create_message(
    session,
    conversation: HarnessConversation,
    message_id: str,
    message_key: str,
    role: str,
    op: PresentationOp,
) -> HarnessMessage:
    now = _db_utcnow()
    row = HarnessMessage(
        conversation_id=conversation.conversation_id,
        message_id=message_id,
        role=role,
        content=None,
        blocks_json=[],
        metadata_json={
            "protocol_version": PROTOCOL_VERSION,
            "message_key": message_key,
            "source_run_id": op.get("run_id"),
            "source_turn_id": op.get("turn_id"),
            "display_source_event_sequence": int(op.get("source_sequence") or 0),
            "source_event_sequence": int(op.get("source_sequence") or 0),
            "render_kind": "presentation_v2",
        },
        streaming=True,
        created_at=_parse_event_datetime(op.get("created_at")) or now,
        updated_at=now,
    )
    session.add(row)
    conversation.message_count = (int(conversation.message_count or 0) + 1)
    return row


def _display_source_event_sequence(metadata: dict[str, Any], op: PresentationOp) -> int:
    existing = _positive_int(metadata.get("display_source_event_sequence"))
    if existing is not None:
        return existing
    existing_source = _positive_int(metadata.get("source_event_sequence"))
    if existing_source is not None:
        return existing_source
    return int(op.get("source_sequence") or 0)


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _requires_existing_progress(op: PresentationOp) -> bool:
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    if not bool(payload.get("requires_existing_progress")):
        return False
    return str(op.get("block_key") or "") == "home-user-progress-card"


def _has_outline_runtime(conversation: HarnessConversation) -> bool:
    snapshot = conversation.runtime_snapshot_json if isinstance(conversation.runtime_snapshot_json, dict) else {}
    outline_runtime = snapshot.get("outline_runtime") if isinstance(snapshot.get("outline_runtime"), dict) else {}
    return isinstance(outline_runtime.get("current_outline"), dict)


def _render_key_from_op(op: PresentationOp) -> str | None:
    block = op.get("block") if isinstance(op.get("block"), dict) else {}
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    value = block.get("render_key") or payload.get("render_key")
    if value:
        return str(value)
    message_key = str(op.get("message_key") or "")
    if message_key in {"home-user-progress"} or message_key.startswith("interaction:"):
        return message_key
    # Per-subagent messages ({conv}:subagent:{task_id}) are render-only assistant
    # bubbles so the snapshot reconstruction emits each subagent card as its own
    # timeline message (see homeHarnessStoreSession subagent_card branch).
    if ":subagent:" in message_key:
        return message_key
    return None


def _message_kind_from_op(op: PresentationOp) -> str | None:
    ui_kind = str((op.get("block") or {}).get("ui_kind") or (op.get("block") or {}).get("uiKind") or "")
    if ui_kind in {
        "user_plan_card",
        "planning_draft_card",
        "user_progress_card",
        "interaction_form",
        "plan_card",
        "progress_card",
        "artifact_card",
        "subagent_card",
    }:
        return "render_only_assistant"
    return None


def _apply_block_op(blocks: list[dict[str, Any]], op: PresentationOp) -> list[dict[str, Any]]:
    block_key = str(op.get("block_key") or "")
    parent_key = op.get("parent_block_key")
    if parent_key:
        return _apply_child_block_op(blocks, str(parent_key), op)
    if str(op.get("type")) == "presentation.block.delta":
        return _upsert_block(blocks, _apply_delta(_find_block(blocks, block_key) or _placeholder_block(op), op))
    if str(op.get("type")) == "presentation.block.patch":
        return _upsert_block(blocks, _merge_block(_find_block(blocks, block_key) or block_from_op(op), op.get("payload") or {}, op))
    block = block_from_op(op)
    return _upsert_block(blocks, block)


def _apply_child_block_op(blocks: list[dict[str, Any]], parent_key: str, op: PresentationOp) -> list[dict[str, Any]]:
    blocks = _remove_block_outside_parent(blocks, str(op.get("block_key") or ""), parent_key)
    did_update = False
    next_blocks: list[dict[str, Any]] = []
    for block in blocks:
        if str(block.get("block_key") or block.get("id") or "") != parent_key:
            next_blocks.append(block)
            continue
        did_update = True
        children = _apply_block_op(list(block.get("children") or []), {**op, "parent_block_key": None})  # type: ignore[arg-type]
        next_blocks.append({**block, "children": children, "status": block.get("status") or "running"})
    if not did_update:
        parent = _placeholder_parent(parent_key, op)
        parent["children"] = _apply_block_op([], {**op, "parent_block_key": None})  # type: ignore[arg-type]
        next_blocks.append(parent)
    return _sort_blocks(next_blocks)


def _remove_block_outside_parent(blocks: list[dict[str, Any]], block_key: str, parent_key: str) -> list[dict[str, Any]]:
    if not block_key:
        return blocks
    next_blocks: list[dict[str, Any]] = []
    for block in blocks:
        current_key = str(block.get("block_key") or block.get("id") or "")
        if current_key == parent_key:
            next_blocks.append(block)
            continue
        if current_key == block_key:
            continue
        children = _remove_block(list(block.get("children") or []), block_key)
        if children != list(block.get("children") or []):
            next_blocks.append({**block, "children": children})
        else:
            next_blocks.append(block)
    return next_blocks


def _upsert_block(blocks: list[dict[str, Any]], block: dict[str, Any]) -> list[dict[str, Any]]:
    key = str(block.get("block_key") or block.get("id") or "")
    next_blocks = []
    replaced = False
    revision = int(block.get("revision") or block.get("source_sequence") or 0)
    for existing in blocks:
        existing_key = str(existing.get("block_key") or existing.get("id") or "")
        if existing_key != key:
            next_blocks.append(existing)
            continue
        existing_revision = int(existing.get("revision") or existing.get("source_sequence") or 0)
        if existing_revision > revision:
            next_blocks.append(existing)
        else:
            merged = {**existing, **block}
            # Mirror the frontend reducer (`mergeIncomingBlock`): a top-level card
            # upsert that carries no children must not clobber children that were
            # previously streamed under it via parent_block_key (e.g. subagent
            # nested tool/text blocks).
            if not block.get("children") and existing.get("children"):
                merged["children"] = existing.get("children")
            next_blocks.append(merged)
        replaced = True
    if not replaced:
        next_blocks.append(block)
    return _sort_blocks(next_blocks)


def _remove_block(blocks: list[dict[str, Any]], block_key: str) -> list[dict[str, Any]]:
    return [
        {
            **block,
            "children": _remove_block(list(block.get("children") or []), block_key),
        }
        for block in blocks
        if str(block.get("block_key") or block.get("id") or "") != block_key
    ]


def _find_block(blocks: list[dict[str, Any]], block_key: str) -> dict[str, Any] | None:
    for block in blocks:
        if str(block.get("block_key") or block.get("id") or "") == block_key:
            return deepcopy(block)
    return None


def _apply_delta(block: dict[str, Any], op: PresentationOp) -> dict[str, Any]:
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    field = str(payload.get("field") or "content")
    delta = str(payload.get("delta") or "")
    block = deepcopy(block)
    if field in {"content", "text"}:
        block["content"] = f"{block.get('content') or ''}{delta}"
        block.setdefault("payload", {})["text"] = f"{block.get('payload', {}).get('text') or ''}{delta}"
    else:
        block.setdefault("payload", {})[field] = f"{block.get('payload', {}).get(field) or ''}{delta}"
    block["status"] = "running"
    block["revision"] = int(op.get("revision") or op.get("source_sequence") or 0)
    block["source_sequence"] = int(op.get("source_sequence") or 0)
    return block


def _merge_block(block: dict[str, Any], patch: dict[str, Any], op: PresentationOp) -> dict[str, Any]:
    next_block = deepcopy(block)
    for key, value in patch.items():
        if key == "payload" and isinstance(value, dict):
            next_block["payload"] = {**dict(next_block.get("payload") or {}), **deepcopy(value)}
        else:
            next_block[key] = deepcopy(value)
    next_block["revision"] = int(op.get("revision") or op.get("source_sequence") or 0)
    next_block["source_sequence"] = int(op.get("source_sequence") or 0)
    return _normalize_stored_block(next_block)


def _placeholder_block(op: PresentationOp) -> dict[str, Any]:
    block_key = str(op.get("block_key") or "")
    return {
        "id": block_key,
        "block_key": block_key,
        "kind": "text",
        "ui_kind": "text",
        "uiKind": "text",
        "order": int(op.get("order") or 0),
        "status": str(op.get("status") or "running"),
        "visible": True,
        "content": "",
        "payload": {"text": ""},
        "children": [],
        "revision": int(op.get("revision") or op.get("source_sequence") or 0),
        "source_sequence": int(op.get("source_sequence") or 0),
    }


def _placeholder_parent(parent_key: str, op: PresentationOp) -> dict[str, Any]:
    return {
        "id": parent_key,
        "block_key": parent_key,
        "kind": "content",
        "ui_kind": "subagent_card" if parent_key.startswith("subagent:") else "content",
        "uiKind": "subagent_card" if parent_key.startswith("subagent:") else "content",
        "order": int(op.get("order") or 0),
        "status": "running",
        "visible": True,
        "payload": {"status": "running"},
        "children": [],
        "revision": int(op.get("revision") or op.get("source_sequence") or 0),
        "source_sequence": int(op.get("source_sequence") or 0),
    }


def _normalize_stored_block(block: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(block)
    block_key = str(normalized.get("block_key") or normalized.get("id") or "")
    normalized["id"] = str(normalized.get("id") or block_key)
    normalized["block_key"] = block_key or normalized["id"]
    ui_kind = str(normalized.get("ui_kind") or normalized.get("uiKind") or "content")
    normalized["ui_kind"] = ui_kind
    normalized["uiKind"] = ui_kind
    normalized["visible"] = bool(normalized.get("visible", True))
    normalized["payload"] = deepcopy(normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {})
    normalized["children"] = [_normalize_stored_block(child) for child in list(normalized.get("children") or []) if isinstance(child, dict)]
    return sanitize_persistent_payload(normalized)


def _sort_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((_normalize_stored_block(block) for block in blocks), key=lambda block: int(block.get("order") or 0))


def _extract_text(blocks: list[dict[str, Any]]) -> str | None:
    parts: list[str] = []
    for block in blocks:
        ui_kind = str(block.get("ui_kind") or block.get("uiKind") or "")
        payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
        if ui_kind in {"text", "assistant_text", "assistant_final_answer"} and not _block_has_tool_identity(block):
            text = block.get("content")
            if text is None:
                text = payload.get("text") or payload.get("content") or payload.get("message") or payload.get("summary")
            if text and str(block.get("visible", True)).lower() != "false":
                parts.append(str(text))
        if ui_kind == "content" and not _block_has_tool_identity(block):
            child_text = _extract_text(list(block.get("children") or []))
            if child_text:
                parts.append(child_text)
    return "".join(parts) or None


def _block_has_tool_identity(block: dict[str, Any]) -> bool:
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    for key in ("tool", "tool_name", "toolName", "call_id", "callId"):
        if str(block.get(key) or payload.get(key) or "").strip():
            return True
    return False


def _has_running_blocks(blocks: list[dict[str, Any]]) -> bool:
    for block in blocks:
        if str(block.get("status") or "") == "running":
            return True
        if _has_running_blocks(list(block.get("children") or [])):
            return True
    return False


def _parse_event_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        return None


def _db_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso_datetime(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value) if value is not None else None
