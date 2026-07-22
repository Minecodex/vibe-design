from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, TypedDict

PROTOCOL_VERSION = 2

PRESENTATION_EVENT_PREFIX = "presentation."

PresentationOpType = Literal[
    "presentation.conversation.patch",
    "presentation.message.upsert",
    "presentation.block.upsert",
    "presentation.block.delta",
    "presentation.block.patch",
    "presentation.block.complete",
    "presentation.block.remove",
]


class PresentationOp(TypedDict, total=False):
    protocol_version: int
    type: PresentationOpType
    conversation_id: str
    run_id: str | None
    turn_id: str | None
    lane: str
    created_at: str | None
    source_event_id: int | str | None
    source_sequence: int
    op_id: str
    message_key: str
    block_key: str
    parent_block_key: str | None
    placement: str
    order: int
    status: str
    revision: int
    role: str
    content: str | None
    payload: dict[str, Any]
    block: dict[str, Any]


def is_presentation_event_type(event_type: str | None) -> bool:
    return str(event_type or "").strip().startswith(PRESENTATION_EVENT_PREFIX)


def presentation_event(op: PresentationOp) -> dict[str, Any]:
    source_sequence = int(op.get("source_sequence") or 0)
    op_id = op.get("op_id")
    return {
        "type": op["type"],
        "event_type": op["type"],
        "lane": op.get("lane") or "user",
        "sequence": source_sequence,
        "seq": source_sequence,
        "run_id": op.get("run_id"),
        "conversation_id": op.get("conversation_id"),
        "protocol_version": PROTOCOL_VERSION,
        "source_sequence": source_sequence,
        "op_id": op_id,
        "data": deepcopy(dict(op)),
        "payload": {
            "protocol_version": PROTOCOL_VERSION,
            "source_sequence": source_sequence,
            "op_id": op_id,
            "message_key": op.get("message_key"),
            "block_key": op.get("block_key"),
            "parent_block_key": op.get("parent_block_key"),
            "status": op.get("status"),
        },
    }


def block_from_op(op: PresentationOp) -> dict[str, Any]:
    block = deepcopy(op.get("block") or {})
    payload = deepcopy(op.get("payload") or block.get("payload") or {})
    block_key = str(op.get("block_key") or block.get("block_key") or block.get("id") or "")
    ui_kind = str(block.get("ui_kind") or block.get("uiKind") or payload.get("ui_kind") or payload.get("uiKind") or "text")
    kind = str(block.get("kind") or ("text" if ui_kind == "text" else "content"))
    return {
        **block,
        "id": block.get("id") or block_key,
        "block_key": block_key,
        "parent_block_key": op.get("parent_block_key") or block.get("parent_block_key"),
        "kind": kind,
        "ui_kind": ui_kind,
        "uiKind": ui_kind,
        "order": int(op.get("order") or block.get("order") or 0),
        "status": str(op.get("status") or block.get("status") or "running"),
        "visible": bool(block.get("visible", True)),
        "content": op.get("content") if op.get("content") is not None else block.get("content"),
        "payload": payload,
        "children": deepcopy(block.get("children") or []),
        "revision": int(op.get("revision") or block.get("revision") or op.get("source_sequence") or 0),
        "source_sequence": int(op.get("source_sequence") or block.get("source_sequence") or 0),
    }
