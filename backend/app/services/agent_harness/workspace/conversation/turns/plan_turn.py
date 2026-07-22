from __future__ import annotations

import uuid
from typing import Any

from .turn_payloads import (
    conversation_model_preferences,
    conversation_web_search_enabled,
    payload_versioned,
)


def prepare_start_plan_payload(
    *,
    conversation: dict[str, Any],
    language: str,
    turn_route: dict[str, Any] | None = None,
    user_message_event: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return payload_versioned(
        {
            "language": language,
            "web_search_enabled": conversation_web_search_enabled(conversation),
            "model_preferences": conversation_model_preferences(conversation),
            "turn_route": dict(turn_route or {}),
            "user_message_event": dict(user_message_event or {}),
        }
    )


def _approval_action_label(language: str) -> str:
    normalized = str(language or "").strip().lower()
    if normalized.startswith("zh"):
        return "执行计划"
    return "Start plan execution"


def _plan_execution_approval_message_id(
    *,
    conversation_id: str,
    outline: dict[str, Any] | None,
) -> str:
    outline = outline if isinstance(outline, dict) else {}
    plan_instance_id = str(outline.get("plan_instance_id") or "").strip()
    outline_id = str(outline.get("outline_id") or "").strip()
    version = str(outline.get("version") or outline.get("outline_version") or "1").strip()
    identity = plan_instance_id or outline_id or "current"
    return f"plan-execution-approved:{conversation_id}:{identity}:v{version}"


async def build_plan_execution_approval_user_event(
    *,
    conversation_id: str,
    conversation: dict[str, Any],
    language: str,
) -> dict[str, Any] | None:
    outline_runtime = conversation.get("outline_runtime") if isinstance(conversation.get("outline_runtime"), dict) else {}
    current_outline = outline_runtime.get("current_outline") if isinstance(outline_runtime, dict) else None
    if not isinstance(current_outline, dict):
        current_outline = None
    message_id = _plan_execution_approval_message_id(
        conversation_id=conversation_id,
        outline=current_outline,
    )
    metadata = {
        "kind": "plan_execution_approved",
        "source": "plan_start_action",
        "plan_instance_id": (current_outline or {}).get("plan_instance_id"),
        "outline_id": (current_outline or {}).get("outline_id"),
        "outline_version": (current_outline or {}).get("version") or (current_outline or {}).get("outline_version"),
    }
    return {
        "id": message_id,
        "role": "user",
        "content": _approval_action_label(language),
        "metadata": metadata,
        "attachments": [],
    }


def plan_execution_approval_user_event(message: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        content = ""
    event = {
        "id": str(message.get("id") or ""),
        "role": "user",
        "content": content,
        "attachments": list(message.get("attachments") or []),
        "created_at": str(message.get("created_at") or message.get("createdAt") or ""),
    }
    if isinstance(message.get("metadata"), dict):
        event["metadata"] = dict(message["metadata"])
    return event


def prepare_revise_plan_payload(
    *,
    conversation: dict[str, Any],
    instruction: str,
    language: str,
    turn_route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return payload_versioned(
        {
            "instruction": instruction,
            "language": language,
            "web_search_enabled": conversation_web_search_enabled(conversation),
            "model_preferences": conversation_model_preferences(conversation),
            "turn_route": dict(turn_route or {}),
        }
    )


def apply_manual_plan_patch(*, user_id: int, conversation: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    from app.services.agent_harness.authoring.planning.outline_runtime import OutlineCoordinator
    from app.services.agent_harness.authoring.planning.user_projection import emit_current_outline_updated
    from app.services.agent_harness.core.context import create_context
    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.runtime.state.store_core import read_outline_runtime_state
    from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state
    from app.services.agent_harness.workspace.conversation.conversation_service import get_conversation

    conversation_id = str(conversation["id"])
    run_id = str(conversation.get("run_id") or uuid.uuid4().hex[:12])
    ctx = create_context(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        language=str(conversation.get("language") or "zh"),
        conversation=conversation,
    )
    ctx.ensure_dirs()
    coordinator = OutlineCoordinator(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        ctx=ctx,
    )
    patched = coordinator.patch_current_outline(plan=plan, sync_runtime_state=False)
    current_outline = patched.get("current_outline") if isinstance(patched.get("current_outline"), dict) else None
    if current_outline:
        outline_event = {
            **current_outline,
            "execution_state": patched.get("execution_state"),
            "projection_state": patched.get("projection_state"),
        }
        emit_current_outline_updated(
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            current_outline=outline_event,
            created=False,
            change_source=str(patched.get("change_source") or "manual_patch"),
        )
        publish_user_event(
            user_id,
            conversation_id,
            run_id=run_id,
            event_type="plan_revision_applied",
            data={
                "outline": outline_event,
                "projection": outline_event.get("projection_state"),
                "execution_state": outline_event.get("execution_state"),
            },
            lane="user",
        )
    refreshed = patch_runtime_state(
        user_id,
        conversation_id,
        {
            "phase": "planning_ready",
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": None,
            "plan_state": patched.get("plan_state"),
        },
    )
    refreshed = refreshed or get_conversation(user_id, conversation_id) or conversation
    refreshed["outline_runtime"] = read_outline_runtime_state(user_id, conversation_id)
    return refreshed
