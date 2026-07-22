from __future__ import annotations

from typing import Any


TRANSCRIPT_VISIBLE_KINDS = {
    "transcript_user",
    "transcript_assistant",
    "transcript_tool",
    "transcript_system",
    "final_answer",
}
INTERNAL_ONLY_KINDS = {
    "internal_model_prompt",
    "internal_recovery_prompt",
    "internal_audit_note",
}
MODEL_LEDGER_KINDS = {
    "agent_context",
}


def message_metadata(message: dict[str, Any]) -> dict[str, Any]:
    metadata = message.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _metadata_protocol_version(metadata: dict[str, Any]) -> int:
    try:
        return int(metadata.get("protocol_version") or 0)
    except (TypeError, ValueError):
        return 0


def resolve_message_kind(message: dict[str, Any]) -> str:
    metadata = message_metadata(message)
    explicit_kind = str(metadata.get("message_kind") or "").strip()
    if explicit_kind:
        return explicit_kind
    if is_internal_model_prompt_message(message):
        return "internal_model_prompt"
    role = str(message.get("role") or "").strip().lower()
    if role == "user":
        return "transcript_user"
    if role == "assistant":
        return "transcript_assistant"
    if role == "tool":
        return "transcript_tool"
    if role == "system":
        return "transcript_system"
    return "unknown"


def is_transcript_visible_message(message: dict[str, Any]) -> bool:
    metadata = message_metadata(message)
    if _metadata_protocol_version(metadata) == 2 and str(metadata.get("render_kind") or "") == "presentation_v2":
        return False
    if metadata.get("exclude_from_history"):
        return False
    if resolve_message_kind(message) in MODEL_LEDGER_KINDS:
        return bool(metadata.get("ui_visible"))
    return resolve_message_kind(message) in TRANSCRIPT_VISIBLE_KINDS


def is_latest_user_intent_message(message: dict[str, Any]) -> bool:
    return is_transcript_visible_message(message) and str(message.get("role") or "").strip().lower() == "user"


def is_model_session_message(message: dict[str, Any]) -> bool:
    metadata = message_metadata(message)
    if resolve_message_kind(message) in MODEL_LEDGER_KINDS:
        return metadata.get("model_visible") is not False
    if not is_transcript_visible_message(message):
        return False
    if metadata.get("model_visible") is False:
        return False
    return True


def filter_transcript_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [message for message in messages if isinstance(message, dict) and is_transcript_visible_message(message)]


def is_internal_model_prompt_message(message: dict[str, Any]) -> bool:
    metadata = message_metadata(message)
    explicit_kind = str(metadata.get("message_kind") or "").strip()
    return explicit_kind == "internal_model_prompt"


def assert_transcript_persistable_message(message: dict[str, Any]) -> None:
    if is_internal_model_prompt_message(message):
        raise ValueError("internal model prompt messages must not be persisted into the transcript")


def with_message_kind(message: dict[str, Any], *, message_kind: str | None) -> dict[str, Any]:
    if not str(message_kind or "").strip():
        return dict(message)
    normalized = dict(message)
    metadata = {
        **message_metadata(message),
        "message_kind": str(message_kind).strip(),
    }
    normalized["metadata"] = metadata
    return normalized
