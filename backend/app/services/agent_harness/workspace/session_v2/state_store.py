from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from . import db_store

STATE_FIELDS = frozenset({
    "runtime_status",
    "run_state",
    "run_id",
    "heartbeat_at",
    "cancel_requested",
    "run_owner",
    "run_owner_token",
    "run_claimed_at",
    "run_last_renewed_at",
    "run_lease_expires_at",
    "run_checkpoint",
    "model_preferences",
    "skill",
    "skill_id",
    "resolved_skill_id",
    "skill_resolution_source",
    "skill_selection_mode",
    "artifact_mode",
    "design_system_id",
    "billing_preflight",
    "generation_tasks",
    "generation_artifacts",
    "phase",
    "status",
    "display_status",
    "stall_reason",
    "last_tool",
    "last_error_summary",
    "last_activity_at",
    "last_activity_source",
    "turn_status",
    "started_at",
    "finished_at",
    "parent_usage_log_id",
    "user_interaction",
    "plan_state",
    "outline_runtime",
    "runtime_state",
    "recovery_summary",
    "recovery_history",
    "failure",
})


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_state(conversation: dict[str, Any] | None = None) -> dict[str, Any]:
    source = conversation or {}
    return {
        "runtime_status": source.get("runtime_status") or "idle",
        "run_state": source.get("run_state") or "idle",
        "run_id": source.get("run_id"),
        "heartbeat_at": source.get("heartbeat_at"),
        "cancel_requested": bool(source.get("cancel_requested") or False),
        "run_owner": source.get("run_owner"),
        "run_owner_token": source.get("run_owner_token"),
        "run_claimed_at": source.get("run_claimed_at"),
        "run_last_renewed_at": source.get("run_last_renewed_at"),
        "run_lease_expires_at": source.get("run_lease_expires_at"),
        "run_checkpoint": source.get("run_checkpoint"),
        "model_preferences": deepcopy(source.get("model_preferences") or {}),
        "skill": deepcopy(source.get("skill") or {}),
        "skill_id": source.get("skill_id"),
        "resolved_skill_id": source.get("resolved_skill_id"),
        "skill_resolution_source": source.get("skill_resolution_source"),
        "skill_selection_mode": source.get("skill_selection_mode") or "auto",
        "artifact_mode": source.get("artifact_mode") or "web",
        "design_system_id": source.get("design_system_id"),
        "billing_preflight": deepcopy(source.get("billing_preflight") or {}),
        "generation_tasks": deepcopy(source.get("generation_tasks") or {}),
        "generation_artifacts": deepcopy(source.get("generation_artifacts") or {}),
        "phase": source.get("phase") or "executing",
        "status": source.get("status") or "active",
        "display_status": source.get("display_status") or "空闲",
        "stall_reason": source.get("stall_reason"),
        "last_tool": source.get("last_tool"),
        "last_error_summary": source.get("last_error_summary"),
        "last_activity_at": source.get("last_activity_at"),
        "last_activity_source": source.get("last_activity_source"),
        "turn_status": source.get("turn_status") or source.get("runtime_status") or "idle",
        "started_at": source.get("started_at"),
        "finished_at": source.get("finished_at"),
        "parent_usage_log_id": source.get("parent_usage_log_id"),
        "user_interaction": deepcopy(source.get("user_interaction")),
        "plan_state": deepcopy(source.get("plan_state")),
        "outline_runtime": deepcopy(source.get("outline_runtime")),
        "runtime_state": deepcopy(source.get("runtime_state")),
        "recovery_summary": deepcopy(source.get("recovery_summary")),
        "recovery_history": deepcopy(source.get("recovery_history") or []),
        "failure": deepcopy(source.get("failure")),
        "updated_at": source.get("updated_at") or utc_now(),
    }


def read_state(user_id: int, conversation_id: str) -> dict[str, Any]:
    payload = db_store.read_runtime_state_payload(user_id, conversation_id)
    return default_state(payload)


def write_state(user_id: int, conversation_id: str, state: dict[str, Any]) -> dict[str, Any]:
    payload = default_state(state)
    payload.update({key: deepcopy(value) for key, value in state.items()})
    payload["updated_at"] = payload.get("updated_at") or utc_now()
    db_store.update_conversation_record(user_id, conversation_id, payload)
    return payload


def patch_state(
    user_id: int,
    conversation_id: str,
    updates: dict[str, Any],
    *,
    touch_updated_at: bool = True,
) -> dict[str, Any]:
    state = read_state(user_id, conversation_id)
    state.update({key: deepcopy(value) for key, value in updates.items()})
    if touch_updated_at:
        state["updated_at"] = utc_now()
    return write_state(user_id, conversation_id, state)


def split_state_updates(conversation: dict[str, Any]) -> dict[str, Any]:
    return {
        key: deepcopy(value)
        for key, value in conversation.items()
        if key in STATE_FIELDS or key == "updated_at"
    }
