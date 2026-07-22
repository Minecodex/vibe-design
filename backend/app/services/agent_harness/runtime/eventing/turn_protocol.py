from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


TURN_STARTED = "turn_started"
ITEM_STARTED = "item_started"
ITEM_UPDATED = "item_updated"
ITEM_COMPLETED = "item_completed"
TURN_COMPLETED = "turn_completed"
PROTOCOL_ERROR = "protocol_error"

TERMINAL_TURN_STATUSES = {"completed", "failed", "blocked", "cancelled", "waiting_input"}
ACTIVE_TURN_STATUSES = {"running"}
TURN_STATUSES = ACTIVE_TURN_STATUSES | TERMINAL_TURN_STATUSES

_SUMMARY_LIMIT = 500


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalized_status(status: str, *, default: str = "running") -> str:
    value = str(status or "").strip().lower()
    return value if value in TURN_STATUSES else default


def _normalized_runtime_profile(value: str | None) -> str:
    return "canvas" if str(value or "").strip().lower() == "canvas" else "home"


def _plain_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return dict(payload or {})


def build_turn_error(
    error_type: str,
    summary: str,
    *,
    user_visible: bool = True,
    failure_signature: str | None = None,
) -> dict[str, Any]:
    return {
        "error_type": str(error_type or "WorkflowFailed"),
        "summary": str(summary or "")[:_SUMMARY_LIMIT],
        "user_visible": bool(user_visible),
        "failure_signature": failure_signature,
    }


def build_turn_started_payload(
    *,
    conversation_id: str,
    run_id: str,
    runtime_profile: str | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    return {
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "turn_id": str(run_id),
        "status": "running",
        "runtime_profile": _normalized_runtime_profile(runtime_profile),
        "started_at": str(started_at or _now_iso()),
    }


def build_item_started_payload(
    *,
    conversation_id: str,
    run_id: str,
    item_id: str,
    item_type: str,
    status: str = "running",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = str(status or "running").strip().lower()
    if normalized_status not in {"running", "pending"}:
        normalized_status = "running"
    return {
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "turn_id": str(run_id),
        "item_id": str(item_id),
        "item_type": str(item_type),
        "status": normalized_status,
        "payload": _plain_payload(payload),
    }


def build_item_updated_payload(
    *,
    conversation_id: str,
    run_id: str,
    item_id: str,
    item_type: str,
    status: str = "running",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_status = str(status or "running").strip().lower()
    if normalized_status not in {"running", "pending", "waiting_input"}:
        normalized_status = "running"
    return {
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "turn_id": str(run_id),
        "item_id": str(item_id),
        "item_type": str(item_type),
        "status": normalized_status,
        "payload": _plain_payload(payload),
    }


def build_item_completed_payload(
    *,
    conversation_id: str,
    run_id: str,
    item_id: str,
    item_type: str,
    status: str = "completed",
    payload: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    normalized_status = str(status or "completed").strip().lower()
    if normalized_status not in {"completed", "failed", "cancelled"}:
        normalized_status = "completed"
    return {
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "turn_id": str(run_id),
        "item_id": str(item_id),
        "item_type": str(item_type),
        "status": normalized_status,
        "payload": _plain_payload(payload),
        "error": error,
        "completed_at": str(completed_at or _now_iso()),
    }


def build_turn_completed_payload(
    *,
    conversation_id: str,
    run_id: str,
    status: str,
    runtime_snapshot: dict[str, Any] | None,
    error: dict[str, Any] | None = None,
    completed_at: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    return {
        "conversation_id": str(conversation_id),
        "run_id": str(run_id),
        "turn_id": str(run_id),
        "status": _normalized_status(status, default="completed"),
        "error": error,
        "runtime_snapshot": _plain_payload(runtime_snapshot),
        "completed_at": str(completed_at or _now_iso()),
        "duration_ms": int(duration_ms) if duration_ms is not None else None,
    }


def is_turn_completed_event(event: dict[str, Any] | None) -> bool:
    if not isinstance(event, dict):
        return False
    return str(event.get("event_type") or event.get("type") or "") == TURN_COMPLETED
