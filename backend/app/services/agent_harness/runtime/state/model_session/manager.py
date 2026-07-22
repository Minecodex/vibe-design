"""Thin shim over the transcript store.

Historically this module mirrored every persisted message into a
runtime-state ``active_history`` projection. That projection is no longer
consumed anywhere — ``model_context.assembler.build_model_context``
rebuilds the LLM message list directly from transcripted ``harness_messages``
rows on every turn — so the mirror has been removed.

What remains is the public ``record_transcript_message`` / ``record_tool_result``
entry points still used by compatibility message APIs and non-workflow tools.
They simply forward to the canonical transcript persistence (with the
blob-promotion step preserved for large tool results).
"""

from __future__ import annotations

from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.workspace.conversation import transcript_store


def record_transcript_message(
    user_id: int,
    conversation_id: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    return transcript_store.save_message(user_id, conversation_id, message)


def record_user_message(
    user_id: int,
    conversation_id: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    return record_transcript_message(user_id, conversation_id, message)


def record_tool_result(
    user_id: int,
    conversation_id: str,
    *,
    tool_call_id: str,
    tool_name: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.services.agent_harness.runtime.blob_artifacts import promote_large_tool_result

    content = sanitize_persistent_payload(content, field_name="content")
    metadata = sanitize_persistent_payload(metadata or {})
    promoted = promote_large_tool_result(
        user_id,
        conversation_id,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        content=content,
    )
    normalized_metadata = dict(metadata or {})
    if promoted.get("promoted") and isinstance(promoted.get("artifact"), dict):
        normalized_metadata["blob_artifact"] = promoted["artifact"]
        normalized_metadata["result_ref"] = promoted["artifact"]["ref"]
    message: dict[str, Any] = {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "content": promoted.get("content", content),
    }
    if normalized_metadata:
        message["metadata"] = normalized_metadata
    return record_transcript_message(
        user_id,
        conversation_id,
        message,
    )
