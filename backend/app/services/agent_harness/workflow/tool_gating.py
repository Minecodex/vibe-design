from __future__ import annotations

from typing import Any

from app.services.agent_harness.runtime.eventing.presentation import (
    build_media_card_for_tool,
    build_web_search_card_for_tool,
)
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2

from .contracts import EventSpec
from .presentation_events import event_spec_from_presentation_draft


# Deliverable tools that must wait for plan approval. Blocked while the run is in
# a plan-gate phase (planning_ready / awaiting_plan_review).
PLAN_GATE_BLOCKED_TOOLS = {
    "edit_file",
    "exec_command",
    "generate_image",
    "generate_video",
    "publish_output",
    "register_artifact",
    "Agent",
    "write_file",
}

# Tools that render a user-facing media card. analyze_image streams its text into a
# child block whose parent is this media card, so the card must exist before the tool
# runs. generate_image/generate_video only emit an "end" card (status=processing acts
# as the in-progress placeholder); the generation-task poller later updates the same
# block_id to completed.
_MEDIA_CARD_TOOLS = {"generate_image", "generate_video", "analyze_image"}
# Tools that get a card published *before* execution (a running placeholder).
_TOOL_CARD_START_TOOLS = {"analyze_image", "web_search"}

# Control tools whose repeated deterministic failures trip the workflow breaker.
# These tools do no external IO, so any is_error / failed outcome is an input or
# precondition rejection that will fail identically on retry.
CONTROL_TOOL_FAILURE_BREAKER_TOOLS = {
    "update_planning_draft",
    "request_plan_approval",
    "update_execution_progress",
    "ask_user",
}

_TOOL_NAME_ALIASES = {
    "Bash": "exec_command",
    "bash": "exec_command",
    "EditFile": "edit_file",
    "edit_file": "edit_file",
    "file_edit": "edit_file",
}


def normalized_tool_name(tool_name: str) -> str:
    return _TOOL_NAME_ALIASES.get(str(tool_name or "").strip(), str(tool_name or "").strip())


def blocks_plan_gate_tool(*, conversation: dict[str, Any], tool_name: str) -> bool:
    phase = str((conversation or {}).get("phase") or "").strip().lower()
    if phase not in {"planning_ready", "awaiting_plan_review"}:
        return False
    return normalized_tool_name(tool_name) in PLAN_GATE_BLOCKED_TOOLS


def normalized_card_tool_name(tool_name: str) -> str:
    return str(tool_name or "").replace("lc_", "")


def interaction_response_message_key(*, conversation_id: str, request_id: str, turn: int | str | None = None) -> str:
    safe_request_id = str(request_id or "").strip() or "interaction"
    safe_turn = str(turn if turn is not None else "").strip()
    suffix = f":{safe_turn}" if safe_turn else ""
    return f"interaction-response:{conversation_id}:{safe_request_id}{suffix}"


def presentation_scope_for_interaction_response(
    *,
    conversation_id: str,
    request_id: str,
    turn: int | str | None = None,
) -> dict[str, str | None]:
    return {
        "message_key": interaction_response_message_key(
            conversation_id=conversation_id,
            request_id=request_id,
            turn=turn,
        ),
        "parent_block_key": None,
    }


def normalize_presentation_scope(value: Any) -> dict[str, str | None]:
    if not isinstance(value, dict):
        return {}
    message_key = str(value.get("message_key") or value.get("messageKey") or "").strip()
    parent_block_key = str(value.get("parent_block_key") or value.get("parentBlockKey") or "").strip()
    if not message_key and not parent_block_key:
        return {}
    return {
        "message_key": message_key or None,
        "parent_block_key": parent_block_key or None,
    }


def build_tool_card_event(
    *,
    conversation_id: str,
    run_id: str,
    step_id: str,
    phase: str,
    tool_name: str,
    call_id: str,
    result_payload: dict[str, Any],
    status: str,
    message_key: str | None = None,
    parent_block_key: str | None = None,
    order: int = 0,
) -> EventSpec | None:
    """Build the user-facing media / web-search card event for a tool call.

    Media tools render a media card and web_search renders a search card, with a
    block on submit (running/processing) that is updated on completion.
    """
    normalized = normalized_card_tool_name(tool_name)
    if phase == "start" and normalized not in _TOOL_CARD_START_TOOLS:
        return None
    if normalized in _MEDIA_CARD_TOOLS:
        block = build_media_card_for_tool(
            tool_name=tool_name,
            call_id=call_id,
            result_payload=result_payload,
            status=status,
        )
    elif normalized == "web_search":
        block = build_web_search_card_for_tool(
            call_id=call_id,
            result_payload=result_payload,
            status=status,
        )
    else:
        return None
    block_key = str(block.get("block_key") or block.get("id") or f"tool-card:{call_id}")
    ui_kind = str(block.get("ui_kind") or block.get("uiKind") or "artifact_card")
    payload = block.get("payload") if isinstance(block.get("payload"), dict) else {}
    op_payload = presentation_v2.content_block_upsert(
        conversation_id=conversation_id,
        run_id=run_id,
        block_key=block_key,
        ui_kind=ui_kind,
        status=status,
        payload=payload,
        message_key=message_key,
        parent_block_key=parent_block_key,
        order=int(order or block.get("order") or 0),
        kind=str(block.get("kind") or "content"),
        complete=phase != "start",
    )
    op_payload["block"] = {**block, **op_payload["block"], "payload": payload}
    return event_spec_from_presentation_draft(
        presentation_v2.event_draft(
            op_payload,
            block_id=block_key,
            tool_call_id=call_id,
            idempotency_key=f"run:{run_id}:step:{step_id}:tool-card:{phase}:{call_id}",
        )
    )


def is_control_tool_breaker_failure(outcome: dict[str, Any]) -> bool:
    """Whether a control-tool outcome counts toward the failure breaker.

    Control tools (see CONTROL_TOOL_FAILURE_BREAKER_TOOLS) perform no external IO,
    so any error / failed outcome is a deterministic input or precondition
    rejection that will fail identically on retry. Callers gate on the tool name
    being a control tool before calling this, so this only answers "did it fail".
    """
    return bool(outcome.get("is_error")) or str(outcome.get("status") or "") == "failed"
