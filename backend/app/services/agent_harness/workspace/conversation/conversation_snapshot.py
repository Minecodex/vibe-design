from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import conversation_meta_store as _meta
from app.services.agent_harness.authoring.planning.user_projection import build_user_progress


def _default_outline_runtime_state() -> dict[str, Any]:
    return {
        "current_outline": None,
        "execution_state": None,
        "projection_state": None,
        "execution_run": None,
        "last_revision": None,
        "updated_at": None,
    }


def _default_runtime_state() -> dict[str, Any]:
    return {
        "conversation_id": None,
        "parent_usage_log_id": None,
        "updated_at": None,
        "phase": "planning",
        "run_status": "idle",
        "current_item_id": None,
        "current_action": None,
        "item_progress": [],
        "artifacts": [],
        "failure": None,
        "runtime_status": "idle",
        "turn_status": "idle",
        "run_state": "idle",
        "run_id": None,
        "display_status": "空闲",
        "last_tool": None,
        "last_error_summary": None,
        "prepared_workspace": None,
        "workspace_runtime_session": None,
        "runtime_contract": None,
    }


def _resolve_design_system_id(
    conversation: dict[str, Any],
    runtime_state: dict[str, Any] | None,
) -> str | None:
    design_system_id = str(conversation.get("design_system_id") or "").strip()
    if design_system_id:
        return design_system_id

    runtime_contract = runtime_state.get("runtime_contract") if isinstance(runtime_state, dict) else None
    if isinstance(runtime_contract, dict):
        design_system_id = str(runtime_contract.get("design_system_id") or "").strip()
        if design_system_id:
            return design_system_id
    return None


def _current_user_plan(outline_runtime: dict[str, Any]) -> dict[str, Any] | None:
    current_outline = outline_runtime.get("current_outline")
    projection = outline_runtime.get("projection_state")
    execution = outline_runtime.get("execution_state")
    if isinstance(current_outline, dict):
        plan = deepcopy(current_outline)
        plan["projection_state"] = deepcopy(projection) if isinstance(projection, dict) else None
        plan["execution_state"] = deepcopy(execution) if isinstance(execution, dict) else None
        return plan
    return None


def _user_progress_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        blocks = message.get("blocks")
        if not isinstance(blocks, list):
            continue
        for raw_block in reversed(blocks):
            if not isinstance(raw_block, dict):
                continue
            if str(raw_block.get("ui_kind") or raw_block.get("uiKind") or "") != "user_progress_card":
                continue
            payload = raw_block.get("payload")
            if not isinstance(payload, dict):
                continue
            return {
                "message": payload.get("message"),
                "completed_message": payload.get("completed_message") or payload.get("completedMessage"),
                "status": payload.get("status"),
            }
    return None


def _user_progress_snapshot(
    conversation: dict[str, Any],
    outline_runtime: dict[str, Any],
    messages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    message_progress = _user_progress_from_messages(messages)
    if isinstance(message_progress, dict):
        return message_progress
    current_outline = outline_runtime.get("current_outline") if isinstance(outline_runtime.get("current_outline"), dict) else None
    execution_state = outline_runtime.get("execution_state") if isinstance(outline_runtime.get("execution_state"), dict) else None
    if not isinstance(current_outline, dict):
        return None
    mode = str((current_outline or {}).get("artifact_type") or "")
    progress = build_user_progress({
        "status": str((outline_runtime.get("projection_state") or {}).get("status") or (current_outline or {}).get("status") or ""),
        "outline_state": current_outline,
        "execution_state": execution_state,
    }, mode=mode or "other")
    return progress if isinstance(progress, dict) and progress.get("message") else None


def build_conversation_detail_snapshot(
    user_id: int,
    conversation_id: str,
    *,
    conversation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from app.services.agent_harness.workspace.session_v2.service import detail_snapshot as v2_detail_snapshot

    conv = deepcopy(conversation) if isinstance(conversation, dict) else _meta.get_conversation(user_id, conversation_id)
    if conv is None:
        return None
    snapshot = v2_detail_snapshot(user_id, conversation_id)
    if not snapshot:
        return None
    messages = snapshot.get("messages") if isinstance(snapshot.get("messages"), list) else []
    base = {**snapshot, **(conv or {})}
    outline_runtime = (
        deepcopy(base.get("outline_runtime"))
        if isinstance(base.get("outline_runtime"), dict)
        else _default_outline_runtime_state()
    )
    runtime_state = (
        deepcopy(base.get("runtime_state"))
        if isinstance(base.get("runtime_state"), dict)
        else _default_runtime_state()
    )

    return {
        **base,
        "design_system_id": _resolve_design_system_id(base, runtime_state),
        "outline_runtime": outline_runtime,
        "user_plan": _current_user_plan(outline_runtime),
        "user_progress": _user_progress_snapshot(base, outline_runtime, messages),
        "runtime_state": runtime_state,
        "messages": messages,
        "workspace_files": snapshot.get("workspace_files") or [],
    }
