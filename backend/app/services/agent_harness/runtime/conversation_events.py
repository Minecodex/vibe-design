from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import ConversationEvent, HarnessConversation

logger = logging.getLogger(__name__)


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value) if value is not None else None


def _serialize_event(row: ConversationEvent) -> dict[str, Any]:
    return {
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
        "created_at": _iso(row.created_at),
        "ts": _iso(row.created_at),
    }


def _is_inaccessible_conversation(conversation: HarnessConversation | None, user_id: int) -> bool:
    if conversation is None or int(conversation.user_id) != int(user_id):
        return True
    return str(conversation.status or "").strip().lower() == "deleted"


def append_conversation_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    lane: str = "user",
    block_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    normalized_idempotency_key = str(idempotency_key or "").strip() or None
    sanitized_payload = sanitize_persistent_payload(payload or {})
    record: dict[str, Any] | None = None
    for attempt in range(8):
        try:
            with harness_sync_session_scope() as session:
                conversation = session.get(HarnessConversation, conversation_id)
                if _is_inaccessible_conversation(conversation, user_id):
                    raise FileNotFoundError(conversation_id)
                max_sequence = session.scalar(
                    select(func.max(ConversationEvent.sequence)).where(
                        ConversationEvent.conversation_id == conversation_id
                    )
                )
                row = ConversationEvent(
                    conversation_id=conversation_id,
                    user_id=int(user_id),
                    sequence=int(max_sequence or 0) + 1,
                    run_id=run_id,
                    event_type=str(event_type),
                    lane=str(lane or "user"),
                    idempotency_key=normalized_idempotency_key,
                    payload_json=deepcopy(sanitized_payload),
                    block_id=block_id,
                    agent_id=agent_id,
                    tool_call_id=tool_call_id,
                    artifact_id=artifact_id,
                    parent_block_id=parent_block_id,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(row)
                session.flush()
                record = _serialize_event(row)
            _mark_context_projection_dirty_for_event(record)
            return record
        except IntegrityError:
            if normalized_idempotency_key:
                with harness_sync_session_scope() as session:
                    existing = session.scalar(
                        select(ConversationEvent).where(
                            ConversationEvent.conversation_id == conversation_id,
                            ConversationEvent.idempotency_key == normalized_idempotency_key,
                        )
                    )
                    if existing is not None:
                        record = _serialize_event(existing)
                if record is not None:
                    _mark_context_projection_dirty_for_event(record)
                    return record
            if attempt == 7:
                raise
            continue
    raise RuntimeError("unreachable")


def _mark_context_projection_dirty_for_event(record: dict[str, Any]) -> None:
    try:
        from app.services.agent_harness.runtime.context_projection import mark_projection_dirty_for_event

        mark_projection_dirty_for_event(
            int(record.get("user_id") or 0),
            str(record.get("conversation_id") or ""),
            record,
        )
    except Exception:
        logger.info("Context projection dirty mark failed after conversation event append", exc_info=True)


def load_conversation_events(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    return query_conversation_events(
        user_id,
        conversation_id,
        after_sequence=after_sequence,
        limit=limit,
    )


def latest_conversation_event_sequence(user_id: int, conversation_id: str) -> int:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return 0
        return int(
            session.scalar(
                select(func.max(ConversationEvent.sequence)).where(
                    ConversationEvent.conversation_id == conversation_id
                )
            )
            or 0
        )


def query_conversation_events(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    seq_from: int | None = None,
    seq_to: int | None = None,
    run_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return []
        query = select(ConversationEvent).where(ConversationEvent.conversation_id == conversation_id)
        if after_sequence is not None:
            query = query.where(ConversationEvent.sequence > int(after_sequence))
        if seq_from is not None:
            query = query.where(ConversationEvent.sequence >= int(seq_from))
        if seq_to is not None:
            query = query.where(ConversationEvent.sequence <= int(seq_to))
        if run_id is not None:
            query = query.where(ConversationEvent.run_id == str(run_id))
        query = query.order_by(ConversationEvent.sequence.asc())
        if limit is not None:
            query = query.limit(max(1, int(limit)))
        rows = session.scalars(query).all()
        return [_serialize_event(row) for row in rows]


async def append_conversation_event_async(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str | None,
    event_type: str,
    payload: dict[str, Any] | None = None,
    lane: str = "user",
    block_id: str | None = None,
    agent_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    from app.db.harness_session import run_harness_db
    from app.services.agent_harness.runtime import conversation_events as _self
    return await run_harness_db(
        _self.append_conversation_event,
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=event_type,
        payload=payload,
        lane=lane,
        block_id=block_id,
        agent_id=agent_id,
        tool_call_id=tool_call_id,
        artifact_id=artifact_id,
        parent_block_id=parent_block_id,
        idempotency_key=idempotency_key,
    )


async def load_conversation_events_async(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from app.db.harness_session import run_harness_db
    from app.services.agent_harness.runtime import conversation_events as _self
    return await run_harness_db(
        _self.load_conversation_events,
        user_id,
        conversation_id,
        after_sequence=after_sequence,
        limit=limit,
    )


async def query_conversation_events_async(
    user_id: int,
    conversation_id: str,
    *,
    after_sequence: int | None = None,
    seq_from: int | None = None,
    seq_to: int | None = None,
    run_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    from app.db.harness_session import run_harness_db
    from app.services.agent_harness.runtime import conversation_events as _self
    return await run_harness_db(
        _self.query_conversation_events,
        user_id,
        conversation_id,
        after_sequence=after_sequence,
        seq_from=seq_from,
        seq_to=seq_to,
        run_id=run_id,
        limit=limit,
    )
