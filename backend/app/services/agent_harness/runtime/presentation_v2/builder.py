from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from app.services.agent_harness.runtime.presentation_v2.protocol import PROTOCOL_VERSION


PresentationEventType = Literal[
    "presentation.conversation.patch",
    "presentation.message.upsert",
    "presentation.block.upsert",
    "presentation.block.delta",
    "presentation.block.patch",
    "presentation.block.complete",
    "presentation.block.remove",
]


@dataclass(frozen=True)
class PresentationEventDraft:
    event_type: PresentationEventType
    payload: dict[str, Any]
    lane: str = "user"
    block_id: str | None = None
    tool_call_id: str | None = None
    artifact_id: str | None = None
    parent_block_id: str | None = None
    idempotency_key: str | None = None


def message_key_for_run(conversation_id: str, run_id: str, *, role: str = "assistant") -> str:
    return f"{conversation_id}:{run_id}:{role}"


def message_upsert(
    *,
    conversation_id: str,
    run_id: str,
    role: str,
    content: str | None = None,
    blocks: list[dict[str, Any]] | None = None,
    message_key: str | None = None,
) -> dict[str, Any]:
    resolved_message_key = message_key or message_key_for_run(conversation_id, run_id, role=role)
    return _op_payload(
        op_type="presentation.message.upsert",
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=resolved_message_key,
        block_key=f"message:{resolved_message_key}",
        role=role,
        status="completed",
        content=content,
        payload={"content": content, "blocks": deepcopy(blocks or [])},
        suffix="message",
    )


def text_block_start(
    *,
    conversation_id: str,
    run_id: str,
    block_key: str,
    message_key: str | None = None,
    parent_block_key: str | None = None,
    ui_kind: str = "text",
    order: int = 0,
    payload_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"text": "", **deepcopy(payload_extra or {})}
    block = _block(
        block_key=block_key,
        kind="text",
        ui_kind=ui_kind,
        order=order,
        status="running",
        content="",
        payload=payload,
    )
    return _op_payload(
        op_type="presentation.block.upsert",
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=message_key or message_key_for_run(conversation_id, run_id),
        block_key=block_key,
        parent_block_key=parent_block_key,
        order=order,
        status="running",
        content="",
        payload=payload,
        block=block,
    )


def block_delta(
    *,
    conversation_id: str,
    run_id: str,
    block_key: str,
    delta: str,
    message_key: str | None = None,
    parent_block_key: str | None = None,
    field: str = "text",
    order: int = 0,
) -> dict[str, Any]:
    return _op_payload(
        op_type="presentation.block.delta",
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=message_key or message_key_for_run(conversation_id, run_id),
        block_key=block_key,
        parent_block_key=parent_block_key,
        order=order,
        status="running",
        payload={"field": field, "delta": delta},
    )


def block_patch(
    *,
    conversation_id: str,
    run_id: str,
    block_key: str,
    patch: dict[str, Any],
    message_key: str | None = None,
    parent_block_key: str | None = None,
    status: str = "running",
    order: int = 0,
) -> dict[str, Any]:
    return _op_payload(
        op_type="presentation.block.patch",
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=message_key or message_key_for_run(conversation_id, run_id),
        block_key=block_key,
        parent_block_key=parent_block_key,
        order=order,
        status=status,
        payload=deepcopy(patch),
    )


def text_block_complete(
    *,
    conversation_id: str,
    run_id: str,
    block_key: str,
    text: str,
    message_key: str | None = None,
    parent_block_key: str | None = None,
    ui_kind: str = "text",
    order: int = 0,
    status: str = "completed",
    payload_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {"text": text, **deepcopy(payload_extra or {})}
    block = _block(
        block_key=block_key,
        kind="text",
        ui_kind=ui_kind,
        order=order,
        status=status,
        content=text,
        payload=payload,
    )
    return _op_payload(
        op_type="presentation.block.complete",
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=message_key or message_key_for_run(conversation_id, run_id),
        block_key=block_key,
        parent_block_key=parent_block_key,
        order=order,
        status=status,
        content=text,
        payload=payload,
        block=block,
    )


def content_block_upsert(
    *,
    conversation_id: str,
    run_id: str,
    block_key: str,
    ui_kind: str,
    status: str,
    payload: dict[str, Any],
    message_key: str | None = None,
    parent_block_key: str | None = None,
    order: int = 0,
    kind: str = "content",
    content: str | None = None,
    complete: bool = False,
) -> dict[str, Any]:
    block = _block(
        block_key=block_key,
        kind=kind,
        ui_kind=ui_kind,
        order=order,
        status=status,
        content=content,
        payload=payload,
    )
    return _op_payload(
        op_type="presentation.block.complete" if complete else "presentation.block.upsert",
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=message_key or message_key_for_run(conversation_id, run_id),
        block_key=block_key,
        parent_block_key=parent_block_key,
        order=order,
        status=status,
        content=content,
        payload=payload,
        block=block,
    )


def interaction_form(
    *,
    conversation_id: str,
    run_id: str,
    interaction: dict[str, Any],
) -> dict[str, Any]:
    request_id = str(
        interaction.get("request_id")
        or interaction.get("tool_call_id")
        or interaction.get("id")
        or "interaction"
    ).strip() or "interaction"
    payload = {
        **deepcopy(interaction),
        "request_id": request_id,
        "requestId": request_id,
        "tool_call_id": request_id,
        "toolCallId": request_id,
        "status": str(interaction.get("status") or "pending"),
    }
    op_payload = content_block_upsert(
        conversation_id=conversation_id,
        run_id=run_id,
        message_key=f"interaction:{request_id}",
        block_key=f"interaction-form:{request_id}",
        ui_kind="interaction_form",
        status=str(payload.get("status") or "pending"),
        payload=payload,
        kind="interaction",
        content=interaction.get("content") or interaction.get("question"),
    )
    op_payload["block"]["render_key"] = f"interaction:{request_id}"
    return op_payload


def progress_card(
    *,
    conversation_id: str,
    run_id: str,
    progress: dict[str, Any],
    complete: bool = False,
) -> dict[str, Any]:
    message = str(progress.get("message") or "").strip() or None
    completed_message = progress.get("completed_message") or progress.get("completedMessage")
    status = str(progress.get("status") or ("completed" if complete else "in_progress"))
    payload = {
        **deepcopy(progress),
        "message": message,
        "completedMessage": completed_message,
        "completed_message": completed_message,
        "status": status,
    }
    op_payload = content_block_upsert(
        conversation_id=conversation_id,
        run_id=run_id,
        message_key="home-user-progress",
        block_key="home-user-progress-card",
        ui_kind="progress_card",
        status=status,
        payload=payload,
        order=1,
        content=message,
        complete=complete,
    )
    op_payload["block"]["user_visible"] = True
    op_payload["block"]["debug_only"] = False
    return op_payload


def subagent_card(
    *,
    conversation_id: str,
    run_id: str,
    payload: dict[str, Any],
    status: str,
    complete: bool = False,
) -> dict[str, Any]:
    task_id = str(
        payload.get("task_id")
        or payload.get("taskId")
        or payload.get("agent_run_id")
        or payload.get("id")
        or "subagent"
    ).strip() or "subagent"
    label = str(payload.get("label") or payload.get("purpose") or payload.get("description") or task_id)
    block_payload = {
        **deepcopy(payload),
        "task_id": task_id,
        "taskId": task_id,
        "label": label,
        "status": status,
    }
    op_payload = content_block_upsert(
        conversation_id=conversation_id,
        run_id=run_id,
        block_key=f"subagent:{task_id}",
        ui_kind="subagent_card",
        status=status,
        payload=block_payload,
        content=payload.get("summary"),
        complete=complete,
    )
    op_payload["block"]["task_id"] = task_id
    op_payload["block"]["taskId"] = task_id
    op_payload["block"]["label"] = label
    return op_payload


def event_draft(
    payload: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    block_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    lane: str = "user",
) -> PresentationEventDraft:
    payload = _strip_unassigned_sequence_fields(payload)
    event_type = str(payload.get("type") or "")
    if not event_type.startswith("presentation."):
        raise ValueError("presentation event payload must include a presentation.* type")
    block_key = str(payload.get("block_key") or payload.get("blockKey") or "").strip()
    return PresentationEventDraft(
        event_type=event_type,  # type: ignore[arg-type]
        payload=deepcopy(payload),
        lane=lane,
        block_id=block_id or block_key or None,
        tool_call_id=tool_call_id,
        artifact_id=artifact_id,
        parent_block_id=parent_block_id or payload.get("parent_block_key") or None,
        idempotency_key=idempotency_key,
    )


def _strip_unassigned_sequence_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove placeholder sequence fields before the event log assigns one."""
    cleaned = deepcopy(payload)
    source_sequence = _positive_int(cleaned.get("source_sequence") or cleaned.get("sourceSequence"))
    if source_sequence is None:
        cleaned.pop("source_sequence", None)
        cleaned.pop("sourceSequence", None)
        cleaned.pop("op_id", None)
        cleaned.pop("opId", None)
    if _positive_int(cleaned.get("revision")) is None:
        cleaned.pop("revision", None)
    block = cleaned.get("block")
    if isinstance(block, dict):
        if _positive_int(block.get("source_sequence") or block.get("sourceSequence")) is None:
            block.pop("source_sequence", None)
            block.pop("sourceSequence", None)
        if _positive_int(block.get("revision")) is None:
            block.pop("revision", None)
    return cleaned


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _op_payload(
    *,
    op_type: PresentationEventType,
    conversation_id: str,
    run_id: str,
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
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "type": op_type,
        "conversation_id": conversation_id,
        "run_id": run_id,
        "turn_id": None,
        "lane": "user",
        "created_at": None,
        "source_event_id": None,
        "source_sequence": 0,
        "op_id": "",
        "message_key": message_key,
        "block_key": block_key,
        "parent_block_key": parent_block_key,
        "placement": "timeline",
        "order": int(order or 0),
        "status": status,
        "revision": 0,
        "role": role,
        "content": content,
        "payload": deepcopy(payload or {}),
        "block": deepcopy(block or {}),
        "producer_suffix": suffix,
    }


def _block(
    *,
    block_key: str,
    kind: str,
    ui_kind: str,
    order: int,
    status: str,
    payload: dict[str, Any],
    content: str | None = None,
) -> dict[str, Any]:
    return {
        "id": block_key,
        "block_key": block_key,
        "parent_block_key": None,
        "kind": kind,
        "ui_kind": ui_kind,
        "uiKind": ui_kind,
        "order": int(order or 0),
        "status": status,
        "visible": True,
        "content": content,
        "payload": deepcopy(payload),
        "children": [],
        "revision": 0,
        "source_sequence": 0,
    }
