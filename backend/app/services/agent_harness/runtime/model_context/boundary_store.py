from __future__ import annotations

import uuid
from copy import deepcopy
from typing import Any

from app.services.agent_harness.runtime.conversation_events import (
    append_conversation_event,
    load_conversation_events,
)
from app.services.agent_harness.runtime.state.store_core import utc_now

from .models import CompactionBoundaryV2

SCHEMA_VERSION = 2


def load_latest_boundary_v2(user_id: int, conversation_id: str) -> CompactionBoundaryV2 | None:
    for event in reversed(load_conversation_events(user_id, conversation_id)):
        if str(event.get("type") or "") != "compaction_boundary":
            continue
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        if int(payload.get("schema_version") or 0) != SCHEMA_VERSION:
            continue
        boundary = _boundary_from_event(event, payload)
        if boundary is not None:
            return boundary
    return None


def append_boundary_v2(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str | None,
    compact_type: str,
    covered: dict[str, Any],
    summary_message: dict[str, Any],
    restore_messages: list[dict[str, Any]] | None,
    token_counts: dict[str, Any],
    method: dict[str, Any],
) -> CompactionBoundaryV2:
    covered_payload = deepcopy(covered) if isinstance(covered, dict) else {}
    message_row_id_end = int(covered_payload.get("message_row_id_end") or 0)
    boundary_id = _deterministic_boundary_id(
        conversation_id,
        compact_type=str(compact_type or "auto_full"),
        message_row_id_end=message_row_id_end,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "boundary_id": boundary_id,
        "status": "completed",
        "compact_type": str(compact_type or "auto_full"),
        "created_at": utc_now(),
        "covered": covered_payload,
        "summary_message": _provider_message_payload(summary_message),
        "restore_messages": [
            _provider_message_payload(message)
            for message in (restore_messages or [])
            if isinstance(message, dict)
        ],
        "token_counts": deepcopy(token_counts) if isinstance(token_counts, dict) else {},
        "method": deepcopy(method) if isinstance(method, dict) else {},
    }
    record = append_conversation_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type="compaction_boundary",
        payload=payload,
        lane="system",
        idempotency_key=f"compaction-v2:{conversation_id}:{payload['compact_type']}:{message_row_id_end}",
    )
    boundary = _boundary_from_event(record, record.get("payload") if isinstance(record.get("payload"), dict) else payload)
    if boundary is None:
        raise RuntimeError("failed to append compaction boundary")
    return boundary


def _boundary_from_event(event: dict[str, Any], payload: dict[str, Any]) -> CompactionBoundaryV2 | None:
    covered = payload.get("covered") if isinstance(payload.get("covered"), dict) else {}
    summary_message = payload.get("summary_message") if isinstance(payload.get("summary_message"), dict) else {}
    if int(covered.get("message_row_id_end") or 0) < 0 or not summary_message:
        return None
    restore_messages = payload.get("restore_messages") if isinstance(payload.get("restore_messages"), list) else []
    compact_type = str(payload.get("compact_type") or "auto_full")
    if compact_type not in {"auto_full", "session_memory", "manual"}:
        compact_type = "auto_full"
    return CompactionBoundaryV2(
        boundary_id=str(payload.get("boundary_id") or ""),
        compact_type=compact_type,  # type: ignore[arg-type]
        covered=deepcopy(covered),
        summary_message=_provider_message_payload(summary_message),
        restore_messages=[
            _provider_message_payload(message)
            for message in restore_messages
            if isinstance(message, dict)
        ],
        token_counts=deepcopy(payload.get("token_counts") if isinstance(payload.get("token_counts"), dict) else {}),
        method=deepcopy(payload.get("method") if isinstance(payload.get("method"), dict) else {}),
        event_sequence=int(event.get("sequence") or event.get("seq") or 0),
        payload=deepcopy(payload),
    )


def _provider_message_payload(message: dict[str, Any]) -> dict[str, Any]:
    role = str(message.get("role") or "user").strip() or "user"
    payload: dict[str, Any] = {
        "role": role,
        "content": str(message.get("content") or ""),
    }
    if role == "assistant" and isinstance(message.get("tool_calls"), list):
        payload["tool_calls"] = deepcopy(message["tool_calls"])
    if role == "tool":
        payload["tool_call_id"] = str(message.get("tool_call_id") or "")
    return payload


def _deterministic_boundary_id(
    conversation_id: str,
    *,
    compact_type: str,
    message_row_id_end: int,
) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"harness-context-boundary-v2:{conversation_id}:{compact_type}:{message_row_id_end}",
    ).hex[:12]
