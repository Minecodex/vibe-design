from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.services.agent_harness.runtime.presentation_v2.keys import (
    block_key_for_event,
    message_key_for_event,
    op_id_for_event,
    stable_hash,
    subagent_message_key,
    subagent_task_id_from_block_keys,
)
from app.services.agent_harness.runtime.presentation_v2.protocol import (
    PROTOCOL_VERSION,
    PresentationOp,
    is_presentation_event_type,
)


def reduce_event_to_ops(event: dict[str, Any]) -> list[PresentationOp]:
    event_type = str(event.get("type") or event.get("event_type") or "").strip()
    if not event_type or str(event.get("lane") or "user").strip().lower() != "user":
        return []
    if is_presentation_event_type(event_type):
        return [_normalize_presentation_op(event)]
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if event_type in {"selection_resolved", "design_system_selected", "workspace_runtime_session_updated"}:
        return [_conversation_patch(event, payload)]
    if event_type == "user_message":
        return [_message_upsert(event, role="user", content=_payload_text(payload), blocks=[])]
    if event_type == "interaction_submitted":
        return _interaction_submitted_ops(event, payload)
    if event_type in {
        "outline_projection_updated",
        "execution_projection_updated",
        "current_outline_created",
        "current_outline_updated",
        "execution_started",
        "plan_revision_applied",
    }:
        return _plan_card_ops(event, payload)
    if event_type == "planning_draft_updated":
        return _planning_draft_card_ops(event, payload)
    if event_type in {"execution_progress_updated", "user_progress_updated"}:
        return [_progress_card(event, payload)]
    if event_type == "turn_completed" and str(payload.get("status") or "").strip().lower() == "completed":
        return [_completed_progress_card(event, payload)]
    if event_type in {"tool_started", "tool_completed", "tool_result"}:
        if _has_dedicated_tool_card(payload):
            return []
        return [_tool_block(event, payload, event_type)]
    if event_type in {
        "critique.started",
        "critique.round_completed",
        "critique.protocol_rejected",
        "critique.shipped",
        "critique.below_threshold",
        "critique.degraded",
        "critique.failed",
    }:
        op = _subagent_design_jury_block(event, payload)
        if op is None:
            return []
        # On a terminal critique outcome, also patch the parent subagent card to a
        # terminal status. The subagent runner emits a block.complete for normal
        # completions, but the degraded/fail-open path can skip it (review_request
        # is None when the QualityReview subagent crashes mid-run), leaving the card
        # stuck at "running"/进行中 on reload. Mirror the frontend live reducer's
        # terminalSubagentStatusForCritique so persisted + live projections agree.
        parent_patch = _subagent_card_terminal_patch(event, payload)
        return [op, parent_patch] if parent_patch is not None else [op]
    if event_type in {"message_error", "protocol_error"}:
        return [_error_block(event, payload)]
    return []


def _base_op(
    event: dict[str, Any],
    *,
    op_type: str,
    message_key: str,
    block_key: str,
    role: str = "assistant",
    parent_block_key: str | None = None,
    order: int = 0,
    status: str = "running",
    content: str | None = None,
    payload: dict[str, Any] | None = None,
    block: dict[str, Any] | None = None,
    suffix: str = "",
) -> PresentationOp:
    source_sequence = int(event.get("sequence") or event.get("seq") or 0)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "type": op_type,  # type: ignore[typeddict-item]
        "conversation_id": str(event.get("conversation_id") or ""),
        "run_id": event.get("run_id"),
        "turn_id": _turn_id(event),
        "lane": str(event.get("lane") or "user"),
        "created_at": event.get("created_at") or event.get("ts"),
        "source_event_id": event.get("event_id") or event.get("id"),
        "source_sequence": source_sequence,
        "op_id": op_id_for_event(event, op_type, block_key, suffix=suffix),
        "message_key": message_key,
        "block_key": block_key,
        "parent_block_key": parent_block_key,
        "placement": "timeline",
        "order": int(order or 0),
        "status": status,
        "revision": source_sequence,
        "role": role,
        "content": content,
        "payload": deepcopy(payload or {}),
        "block": deepcopy(block or {}),
    }


def _turn_id(event: dict[str, Any]) -> str | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    value = payload.get("turn_id") or payload.get("turnId") or event.get("turn_id")
    return str(value) if value else None


def _payload_text(payload: dict[str, Any]) -> str | None:
    message = payload.get("message")
    value = payload.get("content") or payload.get("text")
    if value is None and isinstance(message, dict):
        value = message.get("content")
    if value is None and not isinstance(message, dict):
        value = message
    return str(value) if value is not None else None


def _normalize_presentation_op(event: dict[str, Any]) -> PresentationOp:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    source = payload or data
    message_key = str(source.get("message_key") or message_key_for_event(event)).strip()
    block_key = str(source.get("block_key") or block_key_for_event(event)).strip()
    parent_block_key = source.get("parent_block_key")
    # Route subagent cards (and every block nested under them) to a stable
    # per-subagent message instead of the producer-supplied run-level message,
    # so each subagent renders at its own time on the home timeline.
    subagent_task_id = subagent_task_id_from_block_keys(block_key, parent_block_key)
    if subagent_task_id:
        message_key = subagent_message_key(str(event.get("conversation_id") or ""), subagent_task_id)
    return _base_op(
        event,
        op_type=str(event.get("type") or event.get("event_type")),
        message_key=message_key,
        block_key=block_key,
        role=str(source.get("role") or "assistant"),
        parent_block_key=source.get("parent_block_key"),
        order=int(source.get("order") or 0),
        status=str(source.get("status") or "running"),
        content=source.get("content"),
        payload=source.get("payload") if isinstance(source.get("payload"), dict) else source,
        block=source.get("block") if isinstance(source.get("block"), dict) else {},
    )


def _message_upsert(
    event: dict[str, Any],
    *,
    role: str,
    content: str | None,
    blocks: list[dict[str, Any]],
) -> PresentationOp:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    metadata = _user_visible_message_metadata(payload.get("metadata"))
    message_key = message_key_for_event(event, role=role)
    return _base_op(
        event,
        op_type="presentation.message.upsert",
        message_key=message_key,
        block_key=f"message:{message_key}",
        role=role,
        status="completed",
        content=content,
        payload={
            "content": content,
            "blocks": deepcopy(blocks),
            "attachments": deepcopy(payload.get("attachments") if isinstance(payload.get("attachments"), list) else []),
            "base_file_versions": deepcopy(
                payload.get("base_file_versions") if isinstance(payload.get("base_file_versions"), list) else []
            ),
            "metadata": deepcopy(metadata),
        },
        suffix="message",
    )


def _interaction_submitted_ops(event: dict[str, Any], payload: dict[str, Any]) -> list[PresentationOp]:
    ops: list[PresentationOp] = []
    form_patch = _interaction_form_submitted_patch(event, payload)
    if form_patch is not None:
        ops.append(form_patch)
    ops.append(_interaction_submission_message(event, payload))
    return ops


def _interaction_form_submitted_patch(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp | None:
    """Mark the pending interaction form as submitted on the durable projection.

    This makes ``submitted`` a server-owned single source of truth instead of
    relying purely on the frontend optimistic op and the reload-time
    submission-bubble reconciliation. Mirrors ``optimisticInteractionSubmissionOps``
    on the client so both paths converge on the same block state.
    """
    request_id = str(payload.get("request_id") or payload.get("requestId") or "").strip()
    if not request_id:
        return None
    answers = deepcopy(payload.get("answers")) if isinstance(payload.get("answers"), dict) else None
    submitted_label = str(payload.get("display_label") or payload.get("answer") or "").strip() or None
    submitted_answer = payload.get("answer")
    submitted_payload = {
        "status": "submitted",
        "answers": answers,
        "submitted_label": submitted_label,
        "submittedLabel": submitted_label,
        "submitted_answer": submitted_answer,
        "submittedAnswer": submitted_answer,
        "approved": payload.get("approved"),
    }
    op = _base_op(
        event,
        op_type="presentation.block.patch",
        message_key=f"interaction:{request_id}",
        block_key=f"interaction-form:{request_id}",
        status="submitted",
        payload={"status": "submitted", "payload": submitted_payload},
        suffix="interaction-form-submitted",
    )
    # Submission only marks an *existing* form submitted; it must never
    # materialize a stray form message when the form was never projected.
    op["requires_existing_message"] = True  # type: ignore[typeddict-unknown-key]
    return op


def _interaction_submission_message(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp:
    kind = str(payload.get("kind") or "").strip()
    answer = str(payload.get("answer") or "").strip()
    display_label = str(payload.get("display_label") or "").strip()
    content = display_label or answer
    request_id = str(payload.get("request_id") or payload.get("requestId") or "").strip()
    conversation_id = str(event.get("conversation_id") or "").strip()
    digest = stable_hash(
        json.dumps(
            {
                "request_id": request_id,
                "answer": payload.get("answer"),
                "display_label": payload.get("display_label"),
                "answers": payload.get("answers") if isinstance(payload.get("answers"), dict) else {},
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ),
        length=16,
    )
    message_key = str(payload.get("message_key") or payload.get("message_id") or "").strip()
    if not message_key:
        message_key = f"interaction-submission:{conversation_id}:{request_id or 'interaction'}:{digest}"
    op = _message_upsert(
        event,
        role="user",
        content=content,
        blocks=[],
    )
    op["message_key"] = message_key
    op["block_key"] = f"message:{message_key}"
    op["op_id"] = op_id_for_event(event, str(op.get("type") or "presentation.message.upsert"), str(op["block_key"]), suffix="message")
    op["payload"] = {
        **dict(op.get("payload") or {}),
        "content": content,
        "metadata": {
            **dict((op.get("payload") or {}).get("metadata") or {}),
            "request_id": request_id or None,
            "kind": payload.get("kind"),
            "answer": payload.get("answer"),
            "display_label": payload.get("display_label"),
            "approved": payload.get("approved"),
            "answers": deepcopy(payload.get("answers") if isinstance(payload.get("answers"), dict) else {}),
            "source": "interaction_submitted",
        },
    }
    return op


def _conversation_patch(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp:
    patch: dict[str, Any] = {}
    for key in (
        "skill_id",
        "resolved_skill_id",
        "skill_selection_mode",
        "skill_resolution_source",
        "artifact_mode",
        "last_skill_decision_reason",
        "last_skill_decision_confidence",
        "design_system_id",
        "phase",
    ):
        if key in payload:
            patch[key] = deepcopy(payload.get(key))
    workspace_runtime_session = payload.get("workspace_runtime_session")
    if isinstance(workspace_runtime_session, dict):
        selected_design_system = workspace_runtime_session.get("selected_design_system")
        if selected_design_system is not None and "design_system_id" not in patch:
            patch["design_system_id"] = deepcopy(selected_design_system)
    return _base_op(
        event,
        op_type="presentation.conversation.patch",
        message_key="conversation:meta",
        block_key="conversation:meta",
        role="assistant",
        status="completed",
        payload={
            "patch": patch,
            "source_event_type": str(event.get("type") or event.get("event_type") or ""),
        },
        block={},
        suffix="conversation-patch",
    )


def _user_visible_message_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    visible_keys = {
        "base_file_versions",
        "references",
        "reference_diagnostics",
        "skill_id",
    }
    return {key: deepcopy(value[key]) for key in visible_keys if key in value}


def _progress_card(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp:
    message = str(payload.get("message") or "").strip() or None
    completed_message = payload.get("completed_message")
    status = str(payload.get("status") or "in_progress")
    block_key = "home-user-progress-card"
    block_payload = {
        "message": message,
        "completedMessage": completed_message,
        "completed_message": completed_message,
        "status": status,
    }
    block = _content_block(
        block_key=block_key,
        ui_kind="user_progress_card",
        status=status,
        order=1,
        payload=block_payload,
        event=event,
    )
    block["user_visible"] = True
    block["debug_only"] = False
    return _base_op(
        event,
        op_type="presentation.block.upsert",
        message_key="home-user-progress",
        block_key=block_key,
        order=1,
        status=status,
        content=message,
        payload=block_payload,
        block=block,
        suffix="progress",
    )


def _completed_progress_card(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp:
    message = str(payload.get("message") or "").strip() or "已完成"
    block_key = "home-user-progress-card"
    block_payload = {
        "message": message,
        "completedMessage": None,
        "completed_message": None,
        "status": "completed",
        "requires_existing_progress": True,
    }
    patch_payload = {**block_payload, "payload": block_payload}
    block = _content_block(
        block_key=block_key,
        ui_kind="user_progress_card",
        status="completed",
        order=1,
        payload=block_payload,
        event=event,
    )
    block["user_visible"] = True
    block["debug_only"] = False
    return _base_op(
        event,
        op_type="presentation.block.patch",
        message_key="home-user-progress",
        block_key=block_key,
        order=1,
        status="completed",
        content=message,
        payload=patch_payload,
        block=block,
        suffix="progress-complete",
    )


def _plan_card_ops(event: dict[str, Any], payload: dict[str, Any]) -> list[PresentationOp]:
    op = _plan_card(event, payload)
    if op is None:
        return []
    previous = _previous_plan_supersede_patch(event, op)
    phase_patch = _plan_phase_patch(event)
    ops = [candidate for candidate in (phase_patch, previous, op) if candidate is not None]
    return ops


def _planning_draft_card_ops(event: dict[str, Any], payload: dict[str, Any]) -> list[PresentationOp]:
    op = _planning_draft_card(event, payload)
    return [op] if op is not None else []


def _plan_phase_patch(event: dict[str, Any]) -> PresentationOp | None:
    event_type = str(event.get("type") or event.get("event_type") or "").strip()
    if event_type in {"current_outline_created", "current_outline_updated", "plan_revision_applied"}:
        return _conversation_patch(event, {"phase": "planning_ready"})
    if event_type == "execution_started":
        return _conversation_patch(event, {"phase": "executing"})
    return None


def _planning_draft_card(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp | None:
    draft = payload.get("planning_draft")
    if not isinstance(draft, dict):
        draft = payload.get("planningDraft")
    if not isinstance(draft, dict):
        draft = payload
    if not isinstance(draft, dict):
        return None

    draft_outline = [item for item in list(draft.get("draft_outline") or draft.get("draftOutline") or []) if isinstance(item, dict)]
    summary = str(draft.get("summary") or "").strip()
    if not summary and not draft_outline:
        return None

    confirmed_inputs = draft.get("confirmed_inputs")
    if not isinstance(confirmed_inputs, dict):
        confirmed_inputs = draft.get("confirmedInputs") if isinstance(draft.get("confirmedInputs"), dict) else {}
    assumptions = list(draft.get("assumptions") or []) if isinstance(draft.get("assumptions"), list) else []
    open_questions = draft.get("open_questions")
    if not isinstance(open_questions, list):
        open_questions = draft.get("openQuestions") if isinstance(draft.get("openQuestions"), list) else []
    updated_at = draft.get("updated_at") or draft.get("updatedAt")
    render_key = "home-planning-draft"
    block_key = "home-planning-draft-card"
    payload_value = {
        "summary": summary,
        "confirmedInputs": deepcopy(confirmed_inputs),
        "confirmed_inputs": deepcopy(confirmed_inputs),
        "assumptions": deepcopy(assumptions),
        "draftOutline": deepcopy(draft_outline),
        "draft_outline": deepcopy(draft_outline),
        "openQuestions": deepcopy(open_questions),
        "open_questions": deepcopy(open_questions),
        "updatedAt": updated_at,
        "updated_at": updated_at,
        "readonly": True,
        "render_key": render_key,
    }
    block = _content_block(
        block_key=block_key,
        ui_kind="planning_draft_card",
        status="draft",
        order=int(payload.get("order") or 0),
        payload=payload_value,
        event=event,
    )
    block["render_key"] = render_key
    block["user_visible"] = True
    block["debug_only"] = False
    return _base_op(
        event,
        op_type="presentation.block.upsert",
        message_key=render_key,
        block_key=block_key,
        order=block["order"],
        status="draft",
        payload=payload_value,
        block=block,
        suffix="planning-draft",
    )


def _plan_card(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp | None:
    plan = payload.get("outline") if isinstance(payload.get("outline"), dict) else payload.get("plan") if isinstance(payload.get("plan"), dict) else None
    if not isinstance(plan, dict):
        return None
    projection = payload.get("projection") if isinstance(payload.get("projection"), dict) else payload.get("projection_state")
    projection = projection if isinstance(projection, dict) else plan.get("projection_state") if isinstance(plan.get("projection_state"), dict) else None
    execution_state = payload.get("execution_state") if isinstance(payload.get("execution_state"), dict) else plan.get("execution_state")
    execution_state = execution_state if isinstance(execution_state, dict) else None
    render_source = projection if isinstance(projection, dict) else plan
    plan_instance_id = str(plan.get("plan_instance_id") or render_source.get("plan_instance_id") or "").strip() or "plan-unknown"
    outline_version = _safe_int(plan.get("version") or plan.get("outline_version") or render_source.get("version") or render_source.get("outline_version")) or 1
    snapshot_status = _normalize_plan_snapshot_status(plan.get("snapshot_status"), plan.get("status"))
    status = str(plan.get("status") or render_source.get("status") or "").strip() or "planning_ready"
    display_status = snapshot_status if snapshot_status not in {"active", ""} else status
    artifact_type = render_source.get("artifact_type") or plan.get("artifact_type")
    title = render_source.get("title") or plan.get("title")
    summary = render_source.get("summary") or plan.get("summary")
    progress_message = render_source.get("progress_message") or plan.get("progress_message")
    render_items = list(render_source.get("items") or []) or list(plan.get("items") or [])
    render_key = f"home-user-plan:{plan_instance_id}:v{outline_version}"
    block_key = f"home-user-plan-card:{plan_instance_id}:v{outline_version}"
    payload_value = {
        "artifactType": artifact_type,
        "artifact_type": artifact_type,
        "title": title,
        "summary": summary,
        "status": display_status,
        "planInstanceId": plan_instance_id,
        "plan_instance_id": plan_instance_id,
        "outlineVersion": outline_version,
        "outline_version": outline_version,
        "snapshotStatus": snapshot_status,
        "snapshot_status": snapshot_status,
        "isCurrent": snapshot_status in {"active", "executing", "finalizing"},
        "isHistorical": snapshot_status not in {"active", "executing", "finalizing"},
        "progressMessage": progress_message,
        "progress_message": progress_message,
        "items": deepcopy(render_items),
        "constraints": deepcopy(list(plan.get("constraints") or [])),
        "styleNotes": deepcopy(list(plan.get("style_notes") or [])),
        "style_notes": deepcopy(list(plan.get("style_notes") or [])),
        "outline": _outline_payload(render_source),
        "outlineState": deepcopy(plan),
        "outline_state": deepcopy(plan),
        "projectionState": deepcopy(projection),
        "projection_state": deepcopy(projection),
        "executionState": deepcopy(execution_state),
        "execution_state": deepcopy(execution_state),
        "readonly": bool((projection or {}).get("readonly"))
        or str(plan.get("status") or "").strip().lower() in {"approved", "executing", "finalizing", "completed", "abandoned"},
        "render_key": render_key,
        "change_source": payload.get("change_source"),
        "replace_current": str(payload.get("change_source") or "").strip().lower() == "manual_patch",
    }
    block = _content_block(
        block_key=block_key,
        ui_kind="user_plan_card",
        status=display_status,
        order=int(payload.get("order") or 0),
        payload=payload_value,
        event=event,
    )
    block["render_key"] = render_key
    block["user_visible"] = True
    block["debug_only"] = False
    return _base_op(
        event,
        op_type="presentation.block.upsert",
        message_key=render_key,
        block_key=block_key,
        order=block["order"],
        status=display_status,
        payload=payload_value,
        block=block,
        suffix="plan",
    )


def _previous_plan_supersede_patch(event: dict[str, Any], op: PresentationOp) -> PresentationOp | None:
    payload = op.get("payload") if isinstance(op.get("payload"), dict) else {}
    plan_instance_id = str(payload.get("plan_instance_id") or "").strip()
    outline_version = _safe_int(payload.get("outline_version"))
    if not plan_instance_id or outline_version is None or outline_version <= 1:
        return None
    change_source = str(payload.get("change_source") or "").strip().lower()
    if change_source != "ai_revision":
        return None
    previous_version = outline_version - 1
    previous_render_key = f"home-user-plan:{plan_instance_id}:v{previous_version}"
    previous_block_key = f"home-user-plan-card:{plan_instance_id}:v{previous_version}"
    patch_payload = {
        "status": "superseded",
        "snapshotStatus": "superseded",
        "snapshot_status": "superseded",
        "isCurrent": False,
        "isHistorical": True,
        "payload": {
            "status": "superseded",
            "snapshotStatus": "superseded",
            "snapshot_status": "superseded",
            "isCurrent": False,
            "isHistorical": True,
        },
    }
    block = _content_block(
        block_key=previous_block_key,
        ui_kind="user_plan_card",
        status="superseded",
        order=int(op.get("order") or 0),
        payload=patch_payload["payload"],
        event=event,
    )
    block["render_key"] = previous_render_key
    block["user_visible"] = True
    block["debug_only"] = False
    return _base_op(
        event,
        op_type="presentation.block.patch",
        message_key=previous_render_key,
        block_key=previous_block_key,
        order=block["order"],
        status="superseded",
        payload=patch_payload,
        block=block,
        suffix="plan-supersede",
    )


def _tool_block(event: dict[str, Any], payload: dict[str, Any], event_type: str) -> PresentationOp:
    call_id = str(payload.get("call_id") or payload.get("tool_call_id") or event.get("tool_call_id") or block_key_for_event(event, fallback_kind="tool"))
    tool_name = str(payload.get("tool") or payload.get("tool_name") or payload.get("toolName") or "")
    ui_kind = "tool_result" if event_type == "tool_result" else "tool_call"
    status = "completed" if event_type in {"tool_completed", "tool_result"} else "running"
    if payload.get("error") or payload.get("is_error") or payload.get("isError"):
        status = "failed"
    block_key = f"tool:{call_id}"
    block = _content_block(
        block_key=block_key,
        ui_kind=ui_kind,
        status=status,
        order=int(payload.get("order") or 0),
        payload={
            **deepcopy(payload),
            "call_id": call_id,
            "callId": call_id,
            "tool": tool_name,
            "tool_name": tool_name,
            "toolName": tool_name,
            "status": status,
        },
        event=event,
    )
    return _base_op(
        event,
        op_type="presentation.block.complete" if status in {"completed", "failed"} else "presentation.block.upsert",
        message_key=message_key_for_event(event),
        block_key=block_key,
        order=block["order"],
        status=status,
        payload=block["payload"],
        block=block,
    )


def _has_dedicated_tool_card(payload: dict[str, Any]) -> bool:
    tool_name = str(payload.get("tool") or payload.get("tool_name") or payload.get("toolName") or payload.get("kind") or "").replace("lc_", "")
    return tool_name in {"analyze_image", "generate_image", "generate_video", "web_search"}


def _subagent_design_jury_block(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp | None:
    subagent_task_id = str(payload.get("subagent_task_id") or payload.get("subagentTaskId") or "").strip()
    if not subagent_task_id:
        return None
    critique_run_id = str(payload.get("critique_run_id") or payload.get("critiqueRunId") or "active").strip() or "active"
    event_type = str(event.get("type") or "")
    block_payload = deepcopy(payload)
    status = str(block_payload.get("display_status") or block_payload.get("displayStatus") or block_payload.get("status") or "running").strip() or "running"
    if event_type == "critique.round_completed":
        status = "completed"
        block_payload["status"] = "completed"
        block_payload.setdefault("display_status", "round_completed")
        block_payload.setdefault("displayStatus", "round_completed")
    elif status == "round_completed":
        status = "completed"
        block_payload["status"] = "completed"
    block_key = f"subagent-{subagent_task_id}-design-jury-{critique_run_id}"
    block = _content_block(
        block_key=block_key,
        ui_kind="design_jury_card",
        status=status,
        order=int(block_payload.get("order") or 0),
        payload=block_payload,
        event=event,
    )
    block["render_key"] = f"subagent:{subagent_task_id}:design-jury:{critique_run_id}"
    return _base_op(
        event,
        op_type="presentation.block.complete" if status in {"completed", "shipped", "below_threshold", "degraded", "failed"} else "presentation.block.upsert",
        message_key=subagent_message_key(str(event.get("conversation_id") or ""), subagent_task_id),
        block_key=block_key,
        parent_block_key=f"subagent:{subagent_task_id}",
        order=block["order"],
        status=status,
        payload=block["payload"],
        block=block,
    )


def _subagent_card_terminal_patch(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp | None:
    """Patch the parent subagent card to a terminal status on a terminal critique.

    Mirrors the frontend ``terminalSubagentStatusForCritique`` so a reloaded
    snapshot shows the same terminal state the live stream did — in particular it
    rescues the degraded first-attempt Design Jury card, whose runner-side
    block.complete is skipped when the QualityReview subagent crashes mid-run.
    """
    subagent_task_id = str(payload.get("subagent_task_id") or payload.get("subagentTaskId") or "").strip()
    if not subagent_task_id:
        return None
    event_type = str(event.get("type") or event.get("event_type") or "")
    terminal_status = {
        "critique.shipped": "completed",
        "critique.below_threshold": "completed",
        "critique.degraded": "degraded",
        "critique.failed": "failed",
        "critique.protocol_rejected": "failed",
    }.get(event_type)
    if terminal_status is None:
        return None
    block_key = f"subagent:{subagent_task_id}"
    patch_payload = {"status": terminal_status, "payload": {"status": terminal_status}}
    block = _content_block(
        block_key=block_key,
        ui_kind="subagent_card",
        status=terminal_status,
        order=0,
        payload={"status": terminal_status},
        event=event,
    )
    block["render_key"] = f"subagent:{subagent_task_id}"
    return _base_op(
        event,
        op_type="presentation.block.patch",
        message_key=subagent_message_key(str(event.get("conversation_id") or ""), subagent_task_id),
        block_key=block_key,
        order=0,
        status=terminal_status,
        payload=patch_payload,
        block=block,
        suffix="subagent-card-terminal",
    )


def _error_block(event: dict[str, Any], payload: dict[str, Any]) -> PresentationOp:
    block_key = block_key_for_event(event, fallback_kind="error")
    text = str(payload.get("summary") or payload.get("message") or payload.get("error") or "Agent message failed.")
    block = _content_block(
        block_key=block_key,
        ui_kind="error_card",
        status="failed",
        order=int(payload.get("order") or 0),
        payload={**deepcopy(payload), "message": text},
        event=event,
    )
    return _base_op(
        event,
        op_type="presentation.block.complete",
        message_key=message_key_for_event(event),
        block_key=block_key,
        order=block["order"],
        status="failed",
        content=text,
        payload=block["payload"],
        block=block,
    )


def _content_block(
    *,
    block_key: str,
    ui_kind: str,
    status: str,
    order: int,
    payload: dict[str, Any],
    event: dict[str, Any],
    kind: str = "content",
    content: str | None = None,
) -> dict[str, Any]:
    sequence = int(event.get("sequence") or event.get("seq") or 0)
    return {
        "id": block_key,
        "block_key": block_key,
        "kind": kind,
        "ui_kind": ui_kind,
        "uiKind": ui_kind,
        "order": order,
        "status": status,
        "visible": True,
        "content": content,
        "payload": deepcopy(payload),
        "children": [],
        "revision": sequence,
        "source_sequence": sequence,
    }


def _outline_payload(plan: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in list(plan.get("items") or []) if isinstance(item, dict)]
    artifact_type = str(plan.get("artifact_type") or "other")
    outline_key = "items"
    if artifact_type == "ppt":
        outline_key = "slides"
    elif artifact_type in {"word", "html"}:
        outline_key = "sections"
    elif artifact_type == "excel":
        outline_key = "sheets"
    return {outline_key: deepcopy(items)}


def _normalize_plan_snapshot_status(snapshot_status: Any, plan_status: Any) -> str:
    explicit = str(snapshot_status or "").strip().lower()
    if explicit:
        return explicit
    normalized_status = str(plan_status or "").strip().lower()
    if normalized_status in {"executing", "in_progress"}:
        return "executing"
    if normalized_status in {"finalizing", "completed", "failed", "abandoned", "superseded"}:
        return normalized_status
    return "active"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
