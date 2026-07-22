from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any

from app.services.agent_harness.workspace.conversation.conversation_service import (
    get_conversation,
    update_conversation,
)
from app.services.agent_harness.runtime.state.runtime_snapshot import build_runtime_state_snapshot
from app.services.agent_harness.runtime.state.model_session.recovery_events import append_recovery_event

from .store_core import (
    _default_outline_runtime_state,
    _default_runtime_state,
    utc_now,
)

logger = logging.getLogger(__name__)


def _patch_v2_runtime_state(
    user_id: int,
    conversation_id: str,
    updates: dict[str, Any],
) -> None:
    try:
        from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

        patch_runtime_state(user_id, conversation_id, updates, touch_updated_at=False)
    except Exception:
        logger.debug(
            "Failed to mirror harness runtime projection into session snapshot",
            exc_info=True,
            extra={"user_id": user_id, "conversation_id": conversation_id},
        )


def persist_outline_runtime_state(
    user_id: int,
    conversation_id: str,
    *,
    current_outline: dict[str, Any] | None | object = Ellipsis,
    execution_state: dict[str, Any] | None | object = Ellipsis,
    projection_state: dict[str, Any] | None | object = Ellipsis,
    execution_run: dict[str, Any] | None | object = Ellipsis,
    last_revision: dict[str, Any] | None | object = Ellipsis,
    render_mode: str = "replace_current",
    sync_runtime_state: bool = True,
) -> dict[str, Any]:
    conversation = get_conversation(user_id, conversation_id) or {}
    state = dict(conversation.get("outline_runtime") or _default_outline_runtime_state())
    if current_outline is not Ellipsis:
        state["current_outline"] = current_outline
    if execution_state is not Ellipsis:
        state["execution_state"] = execution_state
    if projection_state is not Ellipsis:
        state["projection_state"] = projection_state
    if execution_run is not Ellipsis:
        state["execution_run"] = execution_run
    if last_revision is not Ellipsis:
        state["last_revision"] = last_revision
    state["updated_at"] = utc_now()
    _patch_v2_runtime_state(user_id, conversation_id, {"outline_runtime": state})
    if sync_runtime_state:
        persist_runtime_state(user_id, conversation_id)
    return state


def persist_runtime_state(
    user_id: int,
    conversation_id: str,
    *,
    conversation: dict[str, Any] | None = None,
) -> None:
    source = conversation or get_conversation(user_id, conversation_id) or {}
    outline_runtime = dict(source.get("outline_runtime") or _default_outline_runtime_state())
    existing_runtime_state = dict(source.get("runtime_state") or _default_runtime_state())
    snapshot = build_runtime_state_snapshot(
        conversation_id=conversation_id,
        conversation=source,
        outline_runtime_state=outline_runtime,
        runtime_state=existing_runtime_state,
    )
    snapshot["updated_at"] = utc_now()
    _patch_v2_runtime_state(
        user_id,
        conversation_id,
        {
            "outline_runtime": outline_runtime,
            "runtime_state": snapshot,
        },
    )


def persist_runtime_session(
    user_id: int,
    conversation_id: str,
    *,
    prepared_workspace: dict[str, Any] | None | object = Ellipsis,
    workspace_runtime_session: dict[str, Any] | None | object = Ellipsis,
    runtime_contract: dict[str, Any] | None | object = Ellipsis,
    discovery_status: str | None | object = Ellipsis,
    discovery_started_at: str | None | object = Ellipsis,
    discovery_completed_at: str | None | object = Ellipsis,
    discovery_payload: dict[str, Any] | None | object = Ellipsis,
    discovery_schema: list[dict[str, Any]] | None | object = Ellipsis,
) -> dict[str, Any]:
    conversation = get_conversation(user_id, conversation_id) or {}
    runtime_state = dict(conversation.get("runtime_state") or _default_runtime_state())
    if prepared_workspace is not Ellipsis:
        runtime_state["prepared_workspace"] = prepared_workspace
    if workspace_runtime_session is not Ellipsis:
        runtime_state["workspace_runtime_session"] = workspace_runtime_session
    if runtime_contract is not Ellipsis:
        runtime_state["runtime_contract"] = runtime_contract
    if discovery_status is not Ellipsis:
        runtime_state["discovery_status"] = discovery_status
    if discovery_started_at is not Ellipsis:
        runtime_state["discovery_started_at"] = discovery_started_at
    if discovery_completed_at is not Ellipsis:
        runtime_state["discovery_completed_at"] = discovery_completed_at
    if discovery_payload is not Ellipsis:
        runtime_state["discovery_payload"] = discovery_payload
    if discovery_schema is not Ellipsis:
        runtime_state["discovery_schema"] = discovery_schema
    runtime_state["updated_at"] = utc_now()
    _patch_v2_runtime_state(user_id, conversation_id, {"runtime_state": runtime_state})
    return runtime_state


def merge_runtime_artifact(
    user_id: int,
    conversation_id: str,
    *,
    artifact: dict[str, Any],
) -> None:
    artifact_path = str(artifact.get("file_path") or artifact.get("path") or "").strip()
    if not artifact_path:
        return
    conversation = get_conversation(user_id, conversation_id) or {}
    state = dict(conversation.get("runtime_state") or _default_runtime_state())
    artifacts = list(state.get("artifacts") or [])
    existing_index = next(
        (index for index, item in enumerate(artifacts) if str(item.get("file_path") or item.get("path") or "") == artifact_path),
        None,
    )
    if existing_index is None:
        artifacts.append(artifact)
    else:
        artifacts[existing_index] = artifact
    state["artifacts"] = artifacts
    state["updated_at"] = utc_now()
    _patch_v2_runtime_state(user_id, conversation_id, {"runtime_state": state})


def set_runtime_projection(
    user_id: int,
    conversation_id: str,
    sync_runtime_state: bool = True,
    **updates: Any,
) -> dict[str, Any] | None:
    updates.setdefault("last_activity_at", utc_now())
    conversation = update_conversation(user_id, conversation_id, **updates)
    if conversation is not None and sync_runtime_state:
        persist_runtime_state(user_id, conversation_id, conversation=conversation)
    return conversation


def append_recovery_history(
    user_id: int,
    conversation_id: str,
    *,
    decision: str,
    review: dict[str, Any],
    related_tool_call_id: str | None = None,
) -> dict[str, Any] | None:
    conversation = get_conversation(user_id, conversation_id) or {}
    event_source = "post_tool_timeout" if review.get("post_tool_silence") else str(review.get("source") or "tool_failure")
    resolved_tool_call_id = related_tool_call_id or str(review.get("tool_call_id") or "").strip() or None
    append_recovery_event(
        user_id,
        conversation_id,
        run_id=str(conversation.get("run_id") or "") or None,
        stage=str(conversation.get("phase") or review.get("failure_stage") or "") or None,
        source=event_source,
        decision=decision,
        review=review,
        attempt_count=1,
        related_tool_call_id=resolved_tool_call_id,
    )
    history = conversation.get("recovery_history")
    if not isinstance(history, list):
        history = []
    history_item = {
        "decision": decision,
        "review": review,
        "created_at": utc_now(),
    }
    if resolved_tool_call_id:
        history_item["related_tool_call_id"] = resolved_tool_call_id
    history.append(history_item)
    return update_conversation(
        user_id,
        conversation_id,
        recovery_history=history[-20:],
        recovery_summary={"decision": decision, "review": review},
    )


def persist_plan_review_state(
    user_id: int,
    conversation_id: str,
    *,
    draft_plan: dict[str, Any] | None = None,
    draft_outline: dict[str, Any] | None = None,
    approved_outline: dict[str, Any] | None = None,
    review_status: str = "idle",
    revision_session: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_outline = approved_outline or draft_outline or draft_plan
    execution_state = {
        "status": review_status,
        "steps": list((active_outline or {}).get("steps") or []),
    }
    projection_state = dict(active_outline or {}) if isinstance(active_outline, dict) else None
    state = persist_outline_runtime_state(
        user_id,
        conversation_id,
        current_outline=dict(active_outline or {}) if isinstance(active_outline, dict) else None,
        execution_state=execution_state,
        projection_state=projection_state,
        last_revision=revision_session,
    )
    state["review_status"] = review_status
    _patch_v2_runtime_state(user_id, conversation_id, {"outline_runtime": state})
    persist_runtime_state(user_id, conversation_id)
    return state

