from __future__ import annotations

import json
import threading
import time
import uuid
from collections import OrderedDict
from hashlib import sha256
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from sqlalchemy.orm import Session

from app.core.config import (
    HARNESS_ACTIVE_RUN_STATE_CACHE_MAX_ENTRIES,
    HARNESS_ACTIVE_RUN_STATE_CACHE_TTL_SECONDS,
)
from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.message_visibility import (
    filter_transcript_messages,
    is_transcript_visible_message,
)
from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import (
    ConversationEvent,
    HarnessAgentRun,
    HarnessAgentStep,
    HarnessConversation,
    HarnessMessage,
    HarnessWorkspaceFile,
)
from app.services.agent_harness.runtime.presentation_v2.protocol import PROTOCOL_VERSION
from app.services.agent_harness.runtime.presentation_v2.projection_store import reconcile_projection
from app.services.agent_harness.runtime.presentation_v2.snapshot import build_session_detail_snapshot_payload
from app.services.llm_runtime.tool_calls import tool_call_name

TAIL_LIMIT = 80

_ACTIVE_RUN_STATE_CACHE: OrderedDict[tuple[str, str], tuple[float, dict[str, Any]]] = OrderedDict()
_ACTIVE_RUN_STATE_CACHE_LOCK = threading.Lock()

_CONVERSATION_COLUMN_FIELDS = {
    "created_at",
    "updated_at",
    "title",
    "runtime_profile",
    "project_id",
    "skill_id",
    "resolved_skill_id",
    "skill_resolution_source",
    "skill_selection_mode",
    "artifact_mode",
    "design_system_id",
    "last_skill_decision_reason",
    "last_skill_decision_confidence",
    "phase",
    "mode",
    "web_search_enabled",
    "status",
    "runtime_status",
    "display_status",
    "run_state",
    "stall_reason",
    "last_tool",
    "last_error_summary",
    "last_activity_at",
    "last_activity_source",
    "turn_status",
    "run_id",
    "active_run_id",
    "runtime_snapshot_json",
    "started_at",
    "finished_at",
    "engine_version",
    "model_preferences",
    "workspace_dir",
    "message_count",
    "last_message_preview",
    "parent_usage_log_id",
}

_RUNTIME_JSON_FIELDS = {
    "user_interaction",
    "planning_draft",
    "plan_state",
    "outline_runtime",
    "runtime_state",
    "failure",
    "recovery_summary",
    "recovery_history",
}

_RUNTIME_DIRECT_FIELD_MAP = {
    "updated_at": "updated_at",
}

_RUNTIME_STATE_MERGE_FIELDS = {
    "phase",
    "runtime_status",
    "run_state",
    "activity",
    "turn_route",
    "turn_status",
    "last_tool",
    "last_error_summary",
    "last_activity_at",
    "last_activity_source",
    "failure",
    "finished_at",
    "user_interaction",
    "runtime_contract",
    "cancel_requested",
}

_TERMINAL_RUNTIME_STATUSES = {"completed", "failed", "blocked", "cancelled"}
_ACTIVE_STEP_STATUSES = ("claimed", "running")
_ACTIVE_RUN_STATUSES = ("queued", "running", "waiting_input")
_RUNTIME_NOTIFICATION_FIELDS = (
    set(_RUNTIME_STATE_MERGE_FIELDS)
    | set(_RUNTIME_JSON_FIELDS)
    | (set(_RUNTIME_DIRECT_FIELD_MAP) - {"updated_at"})
    | {"status", "display_status", "stall_reason"}
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_id() -> str:
    return uuid.uuid4().hex[:8]


def normalize_message_id(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return _message_id()
    if len(text) <= 40:
        return text
    digest = sha256(text.encode("utf-8")).hexdigest()[:20]
    suffix = f":sha:{digest}"
    return f"{text[: max(0, 40 - len(suffix))]}{suffix}"


def _db_utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _db_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _db_datetime(value)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return _db_datetime(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.isoformat()
    return str(value)


def _has_runtime_notification_update(updates: dict[str, Any]) -> bool:
    return any(key in _RUNTIME_NOTIFICATION_FIELDS for key in updates)


def _publish_runtime_updated(user_id: int, conversation_id: str, updates: dict[str, Any]) -> None:
    if not _has_runtime_notification_update(updates):
        return
    from app.services.agent_harness.runtime.eventing.conversation_event_fanout import (
        publish_runtime_notification_sync,
    )

    publish_runtime_notification_sync(
        int(user_id),
        str(conversation_id),
        reason="runtime_updated",
    )


def _is_deleted_conversation(conversation: HarnessConversation | None) -> bool:
    return str(getattr(conversation, "status", "") or "").strip().lower() == "deleted"


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_inaccessible_conversation(
    conversation: HarnessConversation | None,
    user_id: int,
    *,
    include_deleted: bool = False,
) -> bool:
    if conversation is None or int(conversation.user_id) != int(user_id):
        return True
    return not include_deleted and _is_deleted_conversation(conversation)


def _empty_active_run_state(*, checkpoint: int | None = None) -> dict[str, Any]:
    return {
        "cancel_requested": False,
        "heartbeat_at": None,
        "run_owner": None,
        "run_owner_token": None,
        "run_claimed_at": None,
        "run_last_renewed_at": None,
        "run_lease_expires_at": None,
        "run_checkpoint": checkpoint,
    }


def _active_step_projection():
    return select(
        HarnessAgentStep.id.label("id"),
        HarnessAgentStep.run_id.label("run_id"),
        HarnessAgentStep.claim_owner.label("claim_owner"),
        HarnessAgentStep.claim_token.label("claim_token"),
        HarnessAgentStep.claimed_at.label("claimed_at"),
        HarnessAgentStep.last_renewed_at.label("last_renewed_at"),
        HarnessAgentStep.claim_expires_at.label("claim_expires_at"),
        HarnessAgentStep.attempts.label("attempts"),
        HarnessAgentStep.updated_at.label("updated_at"),
    )


def _active_step_sort_key(row: Any) -> tuple[float, int]:
    updated_at = row.get("updated_at") if hasattr(row, "get") else None
    if isinstance(updated_at, datetime):
        comparable = updated_at
        if comparable.tzinfo is None:
            comparable = comparable.replace(tzinfo=timezone.utc)
        updated_ts = comparable.timestamp()
    else:
        updated_ts = 0.0
    return updated_ts, int(row.get("id") or 0)


def _latest_active_step(session: Session, *filters: Any) -> Any | None:
    rows = []
    for status in _ACTIVE_STEP_STATUSES:
        row = (
            session.execute(
                _active_step_projection()
                .where(
                    *filters,
                    HarnessAgentStep.status == status,
                )
                .order_by(HarnessAgentStep.updated_at.desc(), HarnessAgentStep.id.desc())
                .limit(1)
            )
            .mappings()
            .first()
        )
        if row is not None:
            rows.append(row)
    if not rows:
        return None
    return max(rows, key=_active_step_sort_key)


def _run_cancel_requested(session: Session, run_id: str) -> bool:
    value = session.scalar(
        select(HarnessAgentRun.cancel_requested)
        .where(HarnessAgentRun.run_id == str(run_id))
        .limit(1)
    )
    return bool(value)


def _active_run_cache_ttl() -> float:
    return max(float(HARNESS_ACTIVE_RUN_STATE_CACHE_TTL_SECONDS), 0.0)


def _active_run_cache_max_entries() -> int:
    return max(int(HARNESS_ACTIVE_RUN_STATE_CACHE_MAX_ENTRIES), 1)


def _active_run_cache_key(conversation_id: str, active_run_id: str | None) -> tuple[str, str]:
    return str(conversation_id), str(active_run_id or "").strip()


def _get_cached_active_run_state(conversation_id: str, active_run_id: str | None) -> dict[str, Any] | None:
    ttl = _active_run_cache_ttl()
    if ttl <= 0:
        return None
    key = _active_run_cache_key(conversation_id, active_run_id)
    now = time.monotonic()
    with _ACTIVE_RUN_STATE_CACHE_LOCK:
        cached = _ACTIVE_RUN_STATE_CACHE.get(key)
        if cached is None:
            return None
        cached_at, state = cached
        if now - cached_at > ttl:
            _ACTIVE_RUN_STATE_CACHE.pop(key, None)
            return None
        _ACTIVE_RUN_STATE_CACHE.move_to_end(key)
        return deepcopy(state)


def _set_cached_active_run_state(conversation_id: str, active_run_id: str | None, state: dict[str, Any]) -> None:
    ttl = _active_run_cache_ttl()
    if ttl <= 0:
        return
    key = _active_run_cache_key(conversation_id, active_run_id)
    with _ACTIVE_RUN_STATE_CACHE_LOCK:
        _ACTIVE_RUN_STATE_CACHE[key] = (time.monotonic(), deepcopy(state))
        _ACTIVE_RUN_STATE_CACHE.move_to_end(key)
        max_entries = _active_run_cache_max_entries()
        while len(_ACTIVE_RUN_STATE_CACHE) > max_entries:
            _ACTIVE_RUN_STATE_CACHE.popitem(last=False)


def invalidate_active_run_state_cache(conversation_id: str, active_run_id: str | None = None) -> None:
    prefix = str(conversation_id)
    key = _active_run_cache_key(conversation_id, active_run_id)
    with _ACTIVE_RUN_STATE_CACHE_LOCK:
        if active_run_id is not None:
            _ACTIVE_RUN_STATE_CACHE.pop(key, None)
            return
        for candidate in list(_ACTIVE_RUN_STATE_CACHE):
            if candidate[0] == prefix:
                _ACTIVE_RUN_STATE_CACHE.pop(candidate, None)


def _is_active_run_state_timeout(exc: Exception) -> bool:
    if isinstance(exc, SQLAlchemyTimeoutError):
        return True
    if isinstance(exc, OperationalError):
        text = str(exc).lower()
        return "queuepool" in text or "timeout" in text or "timed out" in text
    return False


def _active_run_state_from_db(conversation_id: str, *, active_run_id: str | None = None) -> dict[str, Any]:
    with harness_sync_session_scope() as session:
        active_run_key = str(active_run_id or "").strip()
        active_step = None
        active_run_pending_state: dict[str, Any] | None = None
        if active_run_key:
            active_step = _latest_active_step(session, HarnessAgentStep.run_id == active_run_key)
            if active_step is None:
                workflow_cancel_requested = session.scalar(
                    select(HarnessAgentRun.cancel_requested)
                    .where(
                        HarnessAgentRun.run_id == active_run_key,
                        HarnessAgentRun.status.in_(_ACTIVE_RUN_STATUSES),
                    )
                    .limit(1)
                )
                if workflow_cancel_requested is not None:
                    active_run_pending_state = _empty_active_run_state(checkpoint=0)
                    active_run_pending_state["cancel_requested"] = bool(workflow_cancel_requested)
        if active_step is None:
            active_step = _latest_active_step(
                session,
                HarnessAgentStep.conversation_id == str(conversation_id),
            )
        if active_step is not None:
            return {
                "cancel_requested": _run_cancel_requested(session, str(active_step["run_id"])),
                "heartbeat_at": _iso(active_step["last_renewed_at"]),
                "run_owner": active_step["claim_owner"],
                "run_owner_token": active_step["claim_token"],
                "run_claimed_at": _iso(active_step["claimed_at"]),
                "run_last_renewed_at": _iso(active_step["last_renewed_at"]),
                "run_lease_expires_at": _iso(active_step["claim_expires_at"]),
                "run_checkpoint": int(active_step["attempts"] or 0),
            }
        workflow_row = session.execute(
            select(HarnessAgentRun.cancel_requested)
            .where(
                HarnessAgentRun.conversation_id == str(conversation_id),
                HarnessAgentRun.status.in_(_ACTIVE_RUN_STATUSES),
            )
            .order_by(HarnessAgentRun.created_at.desc())
            .limit(1)
        ).first()
        if workflow_row is not None:
            state = _empty_active_run_state(checkpoint=0)
            state["cancel_requested"] = bool(workflow_row[0])
            return state
        if active_run_pending_state is not None:
            return active_run_pending_state
    return _empty_active_run_state()


def _active_run_state(conversation_id: str, *, active_run_id: str | None = None) -> dict[str, Any]:
    try:
        state = _active_run_state_from_db(conversation_id, active_run_id=active_run_id)
        _set_cached_active_run_state(conversation_id, active_run_id, state)
        return state
    except Exception as exc:
        if not _is_active_run_state_timeout(exc):
            raise
        cached = _get_cached_active_run_state(conversation_id, active_run_id)
        if cached is not None:
            cached["_active_run_state_degraded"] = True
            cached["_active_run_state_source"] = "cache"
            return cached
        state = _empty_active_run_state()
        state["_active_run_state_degraded"] = True
        state["_active_run_state_source"] = "empty_timeout"
        return state


def _runtime_snapshot(row: HarnessConversation) -> dict[str, Any]:
    return dict(row.runtime_snapshot_json or {}) if isinstance(row.runtime_snapshot_json, dict) else {}


def _serialize_conversation(
    row: HarnessConversation,
    runtime: object | None = None,
    *,
    include_active_run_state: bool = True,
) -> dict[str, Any]:
    del runtime
    snapshot = _runtime_snapshot(row)
    payload = {
        "id": row.conversation_id,
        "conversation_id": row.conversation_id,
        "user_id": row.user_id,
        "title": row.title,
        "runtime_profile": row.runtime_profile,
        "project_id": row.project_id,
        "skill_id": row.skill_id,
        "resolved_skill_id": row.resolved_skill_id,
        "skill_resolution_source": row.skill_resolution_source,
        "skill_selection_mode": row.skill_selection_mode,
        "artifact_mode": row.artifact_mode,
        "design_system_id": row.design_system_id,
        "last_skill_decision_reason": row.last_skill_decision_reason,
        "last_skill_decision_confidence": row.last_skill_decision_confidence,
        "phase": row.phase,
        "mode": row.mode,
        "web_search_enabled": bool(row.web_search_enabled),
        "status": row.status,
        "runtime_status": row.runtime_status,
        "display_status": row.display_status,
        "run_state": row.run_state,
        "stall_reason": row.stall_reason,
        "last_tool": row.last_tool,
        "last_error_summary": row.last_error_summary,
        "last_activity_at": _iso(row.last_activity_at),
        "last_activity_source": row.last_activity_source,
        "turn_status": row.turn_status,
        "run_id": row.run_id,
        "protocol_version": PROTOCOL_VERSION,
        "active_run_id": row.active_run_id,
        "runtime_snapshot": deepcopy(snapshot) or None,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "engine_version": row.engine_version,
        "model_preferences": deepcopy(row.model_preferences),
        "created_at": _iso(row.created_at) or "",
        "updated_at": _iso(row.updated_at) or "",
        "message_count": int(row.message_count or 0),
        "last_message_preview": row.last_message_preview,
        "workspace_dir": row.workspace_dir,
        "activity": None,
        "turn_route": None,
    }
    if include_active_run_state:
        payload.update(_active_run_state(row.conversation_id, active_run_id=row.active_run_id))
    else:
        payload.update(_empty_active_run_state())
    payload["user_interaction"] = deepcopy(snapshot.get("user_interaction"))
    payload["planning_draft"] = deepcopy(snapshot.get("planning_draft"))
    payload["plan_state"] = deepcopy(snapshot.get("plan_state"))
    payload["outline_runtime"] = deepcopy(snapshot.get("outline_runtime"))
    payload["runtime_state"] = deepcopy(snapshot.get("runtime_state"))
    payload["runtime_updated_at"] = snapshot.get("runtime_updated_at") or _iso(row.updated_at)
    payload["failure"] = deepcopy(snapshot.get("failure"))
    payload["recovery_summary"] = deepcopy(snapshot.get("recovery_summary"))
    payload["recovery_history"] = deepcopy(snapshot.get("recovery_history")) or []
    payload["parent_usage_log_id"] = row.parent_usage_log_id
    runtime_state = payload.get("runtime_state")
    if isinstance(runtime_state, dict):
        for key in ("turn_route", "activity"):
            if payload.get(key) is None and key in runtime_state:
                payload[key] = deepcopy(runtime_state.get(key))
    return payload


def _serialize_message(row: HarnessMessage) -> dict[str, Any]:
    metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
    tool_call_id = row.tool_call_id or str(metadata.get("tool_call_id") or "").strip() or None
    tool_name = row.tool_name or str(metadata.get("tool_name") or "").strip() or None
    payload: dict[str, Any] = {
        "id": row.message_id,
        "role": row.role,
        "content": row.content,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "streaming": bool(row.streaming),
        "_seq": int(row.id),
    }
    if tool_call_id:
        payload["tool_call_id"] = tool_call_id
    if tool_name:
        payload["tool_name"] = tool_name
    if row.blocks_json is not None:
        payload["blocks"] = deepcopy(row.blocks_json)
    if row.attachments_json is not None:
        payload["attachments"] = deepcopy(row.attachments_json)
    if row.tool_calls_json is not None:
        payload["tool_calls"] = deepcopy(row.tool_calls_json)
    if row.metadata_json is not None:
        payload["metadata"] = deepcopy(row.metadata_json)
    return payload


def _preview_from_message(message: dict[str, Any] | None) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()[:160]
    blocks = message.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            payload = block.get("payload") if isinstance(block, dict) else None
            text = payload.get("text") if isinstance(payload, dict) else None
            if isinstance(text, str) and text.strip():
                return text.strip()[:160]
    return ""


def _apply_conversation_updates(
    conversation: HarnessConversation,
    runtime: object | None,
    updates: dict[str, Any],
) -> None:
    del runtime
    runtime_state_updates: dict[str, Any] = {}
    snapshot = _runtime_snapshot(conversation)
    for key, value in updates.items():
        if key == "runtime_snapshot_json":
            snapshot = deepcopy(sanitize_persistent_payload(value)) if isinstance(value, dict) else {}
            continue
        if key in _CONVERSATION_COLUMN_FIELDS:
            if key in {"created_at", "updated_at", "last_activity_at", "started_at", "finished_at"}:
                setattr(conversation, key, _parse_datetime(value))
            else:
                setattr(conversation, key, deepcopy(value))
            if key in _RUNTIME_STATE_MERGE_FIELDS:
                runtime_state_updates[key] = _iso(getattr(conversation, key)) if key in {"last_activity_at", "finished_at"} else deepcopy(value)
            continue
        if key in _RUNTIME_JSON_FIELDS:
            snapshot[key] = deepcopy(sanitize_persistent_payload(value))
            if key in _RUNTIME_STATE_MERGE_FIELDS:
                runtime_state_updates[key] = deepcopy(value)
            continue
        runtime_direct_field = _RUNTIME_DIRECT_FIELD_MAP.get(key)
        if runtime_direct_field is not None:
            snapshot[key] = _iso(_parse_datetime(value)) if key == "updated_at" else deepcopy(value)
            if key in _RUNTIME_STATE_MERGE_FIELDS:
                runtime_state_updates[key] = deepcopy(value)
            continue
        if key in _RUNTIME_STATE_MERGE_FIELDS:
            runtime_state_updates[key] = deepcopy(value)
    runtime_status_update = str(runtime_state_updates.get("runtime_status") or "").strip().lower()
    if runtime_status_update in _TERMINAL_RUNTIME_STATUSES:
        runtime_state_updates["run_status"] = runtime_status_update
        runtime_state_updates["current_action"] = None

    if runtime_state_updates:
        current_state = dict(snapshot.get("runtime_state") or {}) if isinstance(snapshot.get("runtime_state"), dict) else {}
        current_state.update(sanitize_persistent_payload(runtime_state_updates))
        snapshot["runtime_state"] = current_state
    if "updated_at" in updates:
        snapshot["runtime_updated_at"] = _iso(_parse_datetime(updates.get("updated_at"))) or str(updates.get("updated_at") or "")
    conversation.runtime_snapshot_json = snapshot or None


def create_conversation_record(user_id: int, metadata: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    payload = sanitize_persistent_payload(dict(metadata))
    payload["workspace_dir"] = str(workspace_dir)
    with harness_sync_session_scope() as session:
        conversation = HarnessConversation(
            conversation_id=str(payload["id"]),
            user_id=int(user_id),
            runtime_profile=str(payload.get("runtime_profile") or "home"),
            project_id=payload.get("project_id"),
            title=str(payload.get("title") or ""),
            skill_id=payload.get("skill_id"),
            resolved_skill_id=payload.get("resolved_skill_id"),
            skill_resolution_source=payload.get("skill_resolution_source"),
            skill_selection_mode=str(payload.get("skill_selection_mode") or "auto"),
            artifact_mode=str(payload.get("artifact_mode") or "web"),
            design_system_id=payload.get("design_system_id"),
            last_skill_decision_reason=payload.get("last_skill_decision_reason"),
            last_skill_decision_confidence=payload.get("last_skill_decision_confidence"),
            phase=str(payload.get("phase") or "executing"),
            mode=str(payload.get("mode") or "fast"),
            web_search_enabled=bool(payload.get("web_search_enabled", True)),
            status=str(payload.get("status") or "active"),
            runtime_status=str(payload.get("runtime_status") or "idle"),
            display_status=str(payload.get("display_status") or "空闲"),
            run_state=str(payload.get("run_state") or "idle"),
            stall_reason=payload.get("stall_reason"),
            last_tool=payload.get("last_tool"),
            last_error_summary=payload.get("last_error_summary"),
            last_activity_at=_parse_datetime(payload.get("last_activity_at")),
            last_activity_source=payload.get("last_activity_source"),
            turn_status=payload.get("turn_status"),
            run_id=payload.get("run_id"),
            started_at=_parse_datetime(payload.get("started_at")),
            finished_at=_parse_datetime(payload.get("finished_at")),
            engine_version=str(payload.get("engine_version") or "harness"),
            model_preferences=deepcopy(payload.get("model_preferences")),
            workspace_dir=str(workspace_dir),
            message_count=int(payload.get("message_count") or 0),
            last_message_preview=payload.get("last_message_preview"),
            parent_usage_log_id=payload.get("parent_usage_log_id"),
            active_run_id=payload.get("active_run_id"),
            runtime_snapshot_json=deepcopy(payload.get("runtime_snapshot_json") or payload.get("runtime_snapshot")),
            created_at=_parse_datetime(payload.get("created_at")) or _db_utcnow(),
            updated_at=_parse_datetime(payload.get("updated_at")) or _db_utcnow(),
        )
        snapshot = dict(conversation.runtime_snapshot_json or {})
        for key in _RUNTIME_JSON_FIELDS:
            if key in payload:
                snapshot[key] = deepcopy(payload.get(key))
        snapshot["protocol_version"] = PROTOCOL_VERSION
        snapshot["runtime_updated_at"] = _iso(conversation.updated_at)
        conversation.runtime_snapshot_json = snapshot or None
        session.add(conversation)
    return get_conversation_record(user_id, str(payload["id"])) or payload


def get_conversation_record(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        return _serialize_conversation(conversation)


def update_conversation_record(user_id: int, conversation_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    result: dict[str, Any] | None = None
    merged_updates = dict(updates)
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        if "updated_at" not in merged_updates:
            merged_updates["updated_at"] = utc_now()
        _apply_conversation_updates(conversation, None, merged_updates)
        session.flush()
        result = _serialize_conversation(conversation)
    _publish_runtime_updated(user_id, conversation_id, merged_updates)
    return result


def compare_and_swap_runtime_state_payload(
    user_id: int,
    conversation_id: str,
    *,
    expected_updated_at: str | datetime | None,
    runtime_state: dict[str, Any],
) -> dict[str, Any] | None:
    next_updated_at = _db_utcnow()
    result: dict[str, Any] | None = None
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        snapshot = _runtime_snapshot(conversation)
        expected_dt = _parse_datetime(expected_updated_at)
        current_runtime_updated_at = _parse_datetime(snapshot.get("runtime_updated_at")) or conversation.updated_at
        if expected_updated_at not in {None, ""}:
            if expected_dt is None or current_runtime_updated_at != expected_dt:
                return None
        snapshot["runtime_state"] = deepcopy(sanitize_persistent_payload(runtime_state))
        snapshot["runtime_updated_at"] = _iso(next_updated_at)
        conversation.runtime_snapshot_json = snapshot
        conversation.updated_at = next_updated_at
        session.flush()
        result = _serialize_conversation(conversation)
    if result is not None:
        _publish_runtime_updated(user_id, conversation_id, {"runtime_state": runtime_state})
    return result


def delete_conversation_record(user_id: int, conversation_id: str) -> bool:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id, include_deleted=True):
            return False
        if _is_deleted_conversation(conversation):
            return True
        deleted_at = _db_utcnow()
        conversation.status = "deleted"
        conversation.runtime_status = "cancelled"
        conversation.run_state = "cancelled"
        conversation.display_status = "已删除"
        conversation.finished_at = conversation.finished_at or deleted_at
        conversation.updated_at = deleted_at
        return True


def list_conversation_records(
    user_id: int,
    *,
    runtime_profile: str,
    project_id: int | None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    with harness_sync_session_scope() as session:
        query = select(HarnessConversation).where(
            HarnessConversation.user_id == int(user_id),
            HarnessConversation.runtime_profile == str(runtime_profile or "home"),
            HarnessConversation.status != "deleted",
        )
        if project_id is None:
            query = query.where(HarnessConversation.project_id.is_(None))
        else:
            query = query.where(HarnessConversation.project_id == int(project_id))
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.order_by(HarnessConversation.updated_at.desc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
        ).all()
        items = [_serialize_conversation(row, include_active_run_state=False) for row in rows]
        return items, int(total)


def iter_running_conversation_refs() -> list[tuple[int, str]]:
    with harness_sync_session_scope() as session:
        rows = session.scalars(
            select(HarnessConversation).where(
                HarnessConversation.runtime_status == "running",
                HarnessConversation.status != "deleted",
            )
        ).all()
        return [(int(row.user_id), row.conversation_id) for row in rows]


DEFAULT_CONVERSATION_TITLES = frozenset(("", "新会话", "New Chat", "New Session", "Untitled"))


def _should_promote_first_user_message_to_title(
    conversation: HarnessConversation,
    message: dict[str, Any],
) -> bool:
    if int(conversation.message_count or 0) != 0:
        return False
    if str(message.get("role") or "") != "user":
        return False
    if str(conversation.title or "").strip() not in DEFAULT_CONVERSATION_TITLES:
        return False
    return bool(str(message.get("content") or "").strip())


def _conversation_title_from_user_message(message: dict[str, Any]) -> str:
    return " ".join(str(message.get("content") or "").split())[:80]


def append_message_record(user_id: int, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
    sanitized_message = sanitize_persistent_payload(message)
    metadata = sanitized_message.get("metadata") if isinstance(sanitized_message.get("metadata"), dict) else {}
    tool_call_id = (
        str(sanitized_message.get("tool_call_id") or "").strip()
        or str(metadata.get("tool_call_id") or "").strip()
        or None
    )
    tool_name = (
        str(sanitized_message.get("tool_name") or "").strip()
        or str(metadata.get("tool_name") or "").strip()
        or None
    )
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            raise FileNotFoundError(conversation_id)
        stored_message_id = normalize_message_id(str(sanitized_message.get("id") or "").strip())
        row = HarnessMessage(
            conversation_id=conversation_id,
            message_id=stored_message_id,
            role=str(sanitized_message.get("role") or "assistant"),
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            content=sanitized_message.get("content"),
            blocks_json=deepcopy(sanitized_message.get("blocks")),
            attachments_json=deepcopy(sanitized_message.get("attachments")),
            tool_calls_json=deepcopy(sanitized_message.get("tool_calls")),
            metadata_json=deepcopy(sanitized_message.get("metadata")),
            streaming=bool(sanitized_message.get("streaming") or False),
            created_at=_parse_datetime(sanitized_message.get("created_at")) or _db_utcnow(),
            updated_at=_parse_datetime(sanitized_message.get("updated_at") or sanitized_message.get("created_at")) or _db_utcnow(),
        )
        session.add(row)
        session.flush()
        payload = _serialize_message(row)
        # Append is the only single-insert path; increment atomically at the DB
        # (message_count = message_count + 1) instead of an O(n) COUNT(*) per append.
        # The column expression avoids lost updates under concurrent appends.
        if _should_promote_first_user_message_to_title(conversation, payload):
            conversation.title = _conversation_title_from_user_message(payload)
        conversation.message_count = func.coalesce(HarnessConversation.message_count, 0) + 1
        conversation.last_message_preview = _preview_from_message(payload)
        conversation.updated_at = row.created_at
        session.flush()
        return payload


def load_message_records(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return []
        rows = session.scalars(
            select(HarnessMessage)
            .where(HarnessMessage.conversation_id == conversation_id)
            .order_by(HarnessMessage.id.asc())
        ).all()
        return [_serialize_message(row) for row in rows]


def get_message_record(user_id: int, conversation_id: str, message_id: str) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        row = _get_message_row(session, conversation_id, message_id)
        return _serialize_message(row) if row is not None else None


def get_latest_assistant_message_record(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        row = session.scalars(
            select(HarnessMessage)
            .where(
                HarnessMessage.conversation_id == conversation_id,
                HarnessMessage.role == "assistant",
            )
            .order_by(HarnessMessage.id.desc())
            .limit(1)
        ).first()
        return _serialize_message(row) if row is not None else None


def load_message_records_after_seq(user_id: int, conversation_id: str, *, after_seq: int) -> list[dict[str, Any]]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return []
        rows = session.scalars(
            select(HarnessMessage)
            .where(
                HarnessMessage.conversation_id == conversation_id,
                HarnessMessage.id > int(after_seq or 0),
            )
            .order_by(HarnessMessage.id.asc())
        ).all()
        return filter_transcript_messages([_serialize_message(row) for row in rows])


def message_count(user_id: int, conversation_id: str) -> int | None:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        return int(conversation.message_count or 0)


def count_assistant_tool_calls_by_name(user_id: int, conversation_id: str, tool_name: str) -> int:
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        return 0
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return 0
        rows = session.scalars(
            select(HarnessMessage.tool_calls_json).where(
                HarnessMessage.conversation_id == conversation_id,
                HarnessMessage.role == "assistant",
                HarnessMessage.tool_calls_json.is_not(None),
            )
        ).all()
        count = 0
        for tool_calls in rows:
            if not isinstance(tool_calls, list):
                continue
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                if tool_call_name(tool_call) == normalized_tool_name:
                    count += 1
        return count


def count_successful_tool_messages_by_name(user_id: int, conversation_id: str, tool_name: str) -> int:
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        return 0
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return 0
        rows = session.scalars(
            select(HarnessMessage).where(
                HarnessMessage.conversation_id == conversation_id,
                HarnessMessage.role == "tool",
                HarnessMessage.tool_name == normalized_tool_name,
            )
        ).all()
        count = 0
        for row in rows:
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            content = row.content
            if isinstance(content, str) and content.strip().startswith("{"):
                try:
                    payload = json.loads(content)
                except Exception:
                    payload = {}
                if isinstance(payload, dict) and str(payload.get("status") or "").strip().lower() == "failed":
                    continue
            failure_kind = str(metadata.get("failure_kind") or "").strip()
            if failure_kind:
                continue
            count += 1
        return count


def count_tool_messages_by_name(user_id: int, conversation_id: str, tool_name: str) -> int:
    normalized_tool_name = str(tool_name or "").strip()
    if not normalized_tool_name:
        return 0
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return 0
        return int(
            session.scalar(
                select(func.count())
                .select_from(HarnessMessage)
                .where(
                    HarnessMessage.conversation_id == conversation_id,
                    HarnessMessage.role == "tool",
                    HarnessMessage.tool_name == normalized_tool_name,
                )
            )
            or 0
        )


def _read_filtered_messages_page(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
    is_visible: Callable[[dict[str, Any]], bool],
    display_sort_key: Callable[[dict[str, Any]], tuple[int, int]] | None = None,
) -> dict[str, Any]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return {"messages": [], "messages_page": {"has_more": False, "oldest_seq": None, "limit": limit}}
        page_limit = max(1, int(limit))
        batch_limit = max(page_limit * 3, 50)
        cursor = int(before_seq) if before_seq is not None else None
        visible_desc: list[dict[str, Any]] = []
        raw_rows_exhausted = False

        while len(visible_desc) <= page_limit:
            query = select(HarnessMessage).where(HarnessMessage.conversation_id == conversation_id)
            if cursor is not None:
                query = query.where(HarnessMessage.id < cursor)
            rows_desc = session.scalars(query.order_by(HarnessMessage.id.desc()).limit(batch_limit)).all()
            if not rows_desc:
                raw_rows_exhausted = True
                break
            cursor = int(rows_desc[-1].id)
            visible_desc.extend(
                message
                for message in (_serialize_message(row) for row in rows_desc)
                if is_visible(message)
            )
            if len(rows_desc) < batch_limit:
                raw_rows_exhausted = True
                break

        selected_desc = visible_desc[:page_limit]
        messages_with_seq = sorted(selected_desc, key=display_sort_key) if display_sort_key else list(reversed(selected_desc))
        messages = [{key: deepcopy(value) for key, value in item.items() if not key.startswith("_")} for item in messages_with_seq]
        oldest_seq = min((item["_seq"] for item in messages_with_seq), default=None)
        has_more = len(visible_desc) > page_limit or (oldest_seq is not None and not raw_rows_exhausted)
        return {
            "messages": messages,
            "messages_page": {
                "has_more": has_more,
                "oldest_seq": oldest_seq,
                "limit": limit,
            },
        }


def read_messages_page(user_id: int, conversation_id: str, *, before_seq: int | None, limit: int) -> dict[str, Any]:
    return _read_filtered_messages_page(
        user_id,
        conversation_id,
        before_seq=before_seq,
        limit=limit,
        is_visible=is_transcript_visible_message,
    )


def _is_presentation_v2_snapshot_message(message: dict[str, Any]) -> bool:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    return int(metadata.get("protocol_version") or 0) == PROTOCOL_VERSION and str(
        metadata.get("render_kind") or ""
    ).strip() == "presentation_v2"


def _presentation_snapshot_display_sort_key(message: dict[str, Any]) -> tuple[int, int]:
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    row_seq = _coerce_int(message.get("_seq"))
    source_seq = _coerce_int(
        metadata.get("display_source_event_sequence", metadata.get("source_event_sequence")),
        row_seq,
    )
    if source_seq <= 0:
        source_seq = row_seq
    return (source_seq, row_seq)


def read_presentation_snapshot_messages_page(
    user_id: int,
    conversation_id: str,
    *,
    before_seq: int | None,
    limit: int,
) -> dict[str, Any]:
    return _read_filtered_messages_page(
        user_id,
        conversation_id,
        before_seq=before_seq,
        limit=limit,
        is_visible=_is_presentation_v2_snapshot_message,
        display_sort_key=_presentation_snapshot_display_sort_key,
    )


def _get_message_row(session, conversation_id: str, message_id: str) -> HarnessMessage | None:
    stored_message_id = normalize_message_id(message_id)
    return session.scalar(
        select(HarnessMessage).where(
            HarnessMessage.conversation_id == conversation_id,
            HarnessMessage.message_id == stored_message_id,
        )
    )


def update_message_record(
    user_id: int,
    conversation_id: str,
    *,
    message_id: str,
    content: Any = None,
    blocks: Any = None,
    metadata: Any = None,
    streaming: Any = None,
    attachments: Any = Ellipsis,
    tool_calls: Any = Ellipsis,
    has_content: bool = False,
    has_blocks: bool = False,
    has_metadata: bool = False,
    has_streaming: bool = False,
) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        row = _get_message_row(session, conversation_id, message_id)
        if row is None:
            return None
        if has_content:
            row.content = sanitize_persistent_payload(content, field_name="content")
        if has_blocks:
            row.blocks_json = deepcopy(sanitize_persistent_payload(blocks))
        if has_metadata:
            row.metadata_json = deepcopy(sanitize_persistent_payload(metadata))
        if has_streaming:
            row.streaming = bool(streaming)
        if attachments is not Ellipsis:
            row.attachments_json = deepcopy(sanitize_persistent_payload(attachments))
        if tool_calls is not Ellipsis:
            row.tool_calls_json = deepcopy(sanitize_persistent_payload(tool_calls))
        row.updated_at = _db_utcnow()
        session.flush()
        payload = _serialize_message(row)
        conversation.last_message_preview = _preview_from_message(payload)
        conversation.updated_at = row.updated_at
        session.flush()
        return payload


def append_message_delta_record(user_id: int, conversation_id: str, *, message_id: str, delta: str) -> dict[str, Any] | None:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return None
        row = _get_message_row(session, conversation_id, message_id)
        if row is None:
            return None
        row.content = sanitize_persistent_payload(f"{row.content or ''}{delta}", field_name="content")
        row.streaming = True
        row.updated_at = _db_utcnow()
        session.flush()
        payload = _serialize_message(row)
        conversation.last_message_preview = _preview_from_message(payload)
        conversation.updated_at = row.updated_at
        session.flush()
        return payload


def read_runtime_state_payload(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    conversation = get_conversation_record(user_id, conversation_id)
    if conversation is None:
        return None
    payload = {
        key: deepcopy(conversation.get(key))
        for key in (
            "id",
            "conversation_id",
            "user_id",
            "status",
            "phase",
            "runtime_status",
            "display_status",
            "run_state",
            "stall_reason",
            "last_tool",
            "last_error_summary",
            "last_activity_at",
            "last_activity_source",
            "turn_status",
            "run_id",
            "active_run_id",
            "started_at",
            "finished_at",
            "updated_at",
            "cancel_requested",
            "heartbeat_at",
            "run_owner",
            "run_owner_token",
            "run_claimed_at",
            "run_last_renewed_at",
            "run_lease_expires_at",
            "run_checkpoint",
            "user_interaction",
            "planning_draft",
            "plan_state",
            "outline_runtime",
            "runtime_state",
            "runtime_updated_at",
            "failure",
            "recovery_summary",
            "recovery_history",
            "parent_usage_log_id",
        )
    }
    runtime_state = payload.get("runtime_state")
    if isinstance(runtime_state, dict):
        for key in ("turn_route", "activity", "cancel_requested"):
            if key in runtime_state:
                payload[key] = deepcopy(runtime_state.get(key))
    return payload


def patch_workspace_file(user_id: int, conversation_id: str, payload: dict[str, Any]) -> None:
    payload = sanitize_persistent_payload(payload)
    external_id = str(payload.get("file_id") or payload.get("asset_id") or payload.get("path") or "").strip()
    if not external_id:
        return
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return
        row = session.scalar(
            select(HarnessWorkspaceFile).where(
                HarnessWorkspaceFile.conversation_id == conversation_id,
                HarnessWorkspaceFile.external_id == external_id,
            )
        )
        now = _db_utcnow()
        if row is None:
            row = HarnessWorkspaceFile(
                conversation_id=conversation_id,
                external_id=external_id,
                kind=str(payload.get("source") or payload.get("kind") or "file"),
                path=payload.get("path"),
                name=str(payload.get("name") or external_id),
                file_type=str(payload.get("type") or "file"),
                size=int(payload.get("size") or 0),
                source=payload.get("source"),
                current_version_id=payload.get("current_version_id"),
                metadata_json=deepcopy(payload),
                created_at=_parse_datetime(payload.get("created_at")) or now,
                updated_at=_parse_datetime(payload.get("updated_at") or payload.get("created_at")) or now,
            )
            session.add(row)
        else:
            row.kind = str(payload.get("source") or payload.get("kind") or row.kind)
            row.path = payload.get("path")
            row.name = str(payload.get("name") or row.name)
            row.file_type = str(payload.get("type") or row.file_type)
            row.size = int(payload.get("size") or 0)
            row.source = payload.get("source")
            row.current_version_id = payload.get("current_version_id")
            row.metadata_json = deepcopy(payload)
            row.updated_at = _parse_datetime(payload.get("updated_at") or payload.get("created_at")) or now


def list_workspace_file_payloads(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return []
        rows = session.scalars(
            select(HarnessWorkspaceFile)
            .where(HarnessWorkspaceFile.conversation_id == conversation_id)
            .order_by(HarnessWorkspaceFile.created_at.asc(), HarnessWorkspaceFile.name.asc())
        ).all()
        return [deepcopy(row.metadata_json) for row in rows]


def load_recent_message_records(
    user_id: int,
    conversation_id: str,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        if _is_inaccessible_conversation(conversation, user_id):
            return []
        rows = session.scalars(
            select(HarnessMessage)
            .where(HarnessMessage.conversation_id == conversation_id)
            .order_by(HarnessMessage.id.desc())
            .limit(max(1, int(limit)))
        ).all()
        return [_serialize_message(row) for row in reversed(rows)]


def _latest_event_sequence(conversation_id: str) -> int:
    with harness_sync_session_scope() as session:
        latest = session.scalar(
            select(func.max(ConversationEvent.sequence)).where(
                ConversationEvent.conversation_id == conversation_id
            )
        )
        return int(latest or 0)


def _db_store_self():
    from app.services.agent_harness.workspace.session_v2 import db_store as _self
    return _self


def _async_runner():
    from app.db.harness_session import run_harness_db
    return run_harness_db


async def create_conversation_record_async(user_id: int, metadata: dict[str, Any], workspace_dir: Path) -> dict[str, Any]:
    return await _async_runner()(_db_store_self().create_conversation_record, user_id, metadata, workspace_dir)


async def get_conversation_record_async(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    return await _async_runner()(_db_store_self().get_conversation_record, user_id, conversation_id)


async def update_conversation_record_async(user_id: int, conversation_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    result = await _async_runner()(_db_store_self().update_conversation_record, user_id, conversation_id, updates)
    if result is not None and _has_runtime_notification_update(dict(updates or {})):
        try:
            from app.services.agent_harness.runtime.eventing.conversation_event_fanout import (
                publish_runtime_notification,
            )

            await publish_runtime_notification(
                int(user_id),
                str(conversation_id),
                reason="runtime_updated",
            )
        except Exception:
            pass
    return result


async def compare_and_swap_runtime_state_payload_async(
    user_id: int,
    conversation_id: str,
    *,
    expected_updated_at: str | datetime | None,
    runtime_state: dict[str, Any],
) -> dict[str, Any] | None:
    return await _async_runner()(
        _db_store_self().compare_and_swap_runtime_state_payload,
        user_id,
        conversation_id,
        expected_updated_at=expected_updated_at,
        runtime_state=runtime_state,
    )


async def delete_conversation_record_async(user_id: int, conversation_id: str) -> bool:
    return await _async_runner()(_db_store_self().delete_conversation_record, user_id, conversation_id)


async def list_conversation_records_async(
    user_id: int,
    *,
    runtime_profile: str = "home",
    project_id: int | None = None,
    page: int,
    page_size: int,
) -> tuple[list[dict[str, Any]], int]:
    return await _async_runner()(
        _db_store_self().list_conversation_records,
        user_id,
        runtime_profile=runtime_profile,
        project_id=project_id,
        page=page,
        page_size=page_size,
    )


async def iter_running_conversation_refs_async() -> list[tuple[int, str]]:
    return await _async_runner()(_db_store_self().iter_running_conversation_refs)


async def append_message_record_async(user_id: int, conversation_id: str, message: dict[str, Any]) -> dict[str, Any]:
    return await _async_runner()(_db_store_self().append_message_record, user_id, conversation_id, message)


async def load_message_records_async(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    return await _async_runner()(_db_store_self().load_message_records, user_id, conversation_id)


async def get_message_record_async(
    user_id: int, conversation_id: str, message_id: str
) -> dict[str, Any] | None:
    return await _async_runner()(
        _db_store_self().get_message_record, user_id, conversation_id, message_id
    )


async def get_latest_assistant_message_record_async(
    user_id: int, conversation_id: str
) -> dict[str, Any] | None:
    return await _async_runner()(
        _db_store_self().get_latest_assistant_message_record, user_id, conversation_id
    )


async def message_count_async(user_id: int, conversation_id: str) -> int | None:
    return await _async_runner()(_db_store_self().message_count, user_id, conversation_id)


async def count_assistant_tool_calls_by_name_async(user_id: int, conversation_id: str, tool_name: str) -> int:
    return await _async_runner()(
        _db_store_self().count_assistant_tool_calls_by_name, user_id, conversation_id, tool_name
    )


async def count_tool_messages_by_name_async(user_id: int, conversation_id: str, tool_name: str) -> int:
    return await _async_runner()(
        _db_store_self().count_tool_messages_by_name, user_id, conversation_id, tool_name
    )


async def read_messages_page_async(
    user_id: int, conversation_id: str, *, before_seq: int | None, limit: int
) -> dict[str, Any]:
    return await _async_runner()(
        _db_store_self().read_messages_page,
        user_id,
        conversation_id,
        before_seq=before_seq,
        limit=limit,
    )


async def update_message_record_async(*args: Any, **kwargs: Any) -> Any:
    return await _async_runner()(_db_store_self().update_message_record, *args, **kwargs)


async def append_message_delta_record_async(
    user_id: int, conversation_id: str, *, message_id: str, delta: str
) -> dict[str, Any] | None:
    return await _async_runner()(
        _db_store_self().append_message_delta_record,
        user_id,
        conversation_id,
        message_id=message_id,
        delta=delta,
    )


async def read_runtime_state_payload_async(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    return await _async_runner()(_db_store_self().read_runtime_state_payload, user_id, conversation_id)


async def patch_workspace_file_async(user_id: int, conversation_id: str, payload: dict[str, Any]) -> None:
    return await _async_runner()(_db_store_self().patch_workspace_file, user_id, conversation_id, payload)


async def list_workspace_file_payloads_async(user_id: int, conversation_id: str) -> list[dict[str, Any]]:
    return await _async_runner()(_db_store_self().list_workspace_file_payloads, user_id, conversation_id)


async def load_recent_message_records_async(*args: Any, **kwargs: Any) -> Any:
    return await _async_runner()(_db_store_self().load_recent_message_records, *args, **kwargs)


async def build_detail_snapshot_async(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    return await _async_runner()(_db_store_self().build_detail_snapshot, user_id, conversation_id)


def build_detail_snapshot(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    conversation = get_conversation_record(user_id, conversation_id)
    if conversation is None:
        return None
    projection_state = reconcile_projection(user_id, conversation_id)
    page = read_presentation_snapshot_messages_page(user_id, conversation_id, before_seq=None, limit=TAIL_LIMIT)
    latest_event_sequence = _latest_event_sequence(conversation_id)
    return build_session_detail_snapshot_payload(
        conversation=conversation,
        messages_page=page,
        workspace_files=list_workspace_file_payloads(user_id, conversation_id),
        projection_state=projection_state,
        latest_event_sequence=latest_event_sequence,
        tail_limit=TAIL_LIMIT,
    )
