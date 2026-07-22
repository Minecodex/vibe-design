from __future__ import annotations

from hashlib import sha256
from typing import Any


def stable_hash(value: str, *, length: int = 16) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[: max(1, int(length))]


def message_key_for_event(event: dict[str, Any], *, role: str = "assistant") -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    explicit = str(payload.get("message_key") or payload.get("message_id") or payload.get("messageId") or "").strip()
    if explicit:
        return explicit
    run_id = str(event.get("run_id") or "run")
    conversation_id = str(event.get("conversation_id") or "conversation")
    return f"{conversation_id}:{run_id}:{role}"


def subagent_message_key(conversation_id: str, task_id: str) -> str:
    """Stable per-subagent message key.

    Subagent cards (and every block nested under them via
    ``parent_block_key=subagent:<task_id>`` — design-jury cards, analyze-image
    narration, nested tool calls) are grouped into one message *per subagent*
    rather than collapsed into the single run-level ``{conv}:{run}:assistant``
    message. That keeps each subagent card at its own creation time on the home
    timeline so it interleaves chronologically with the per-tool-batch messages
    instead of clustering together.
    """
    return f"{str(conversation_id or 'conversation')}:subagent:{str(task_id or 'subagent')}"


def subagent_task_id_from_block_keys(block_key: str | None, parent_block_key: str | None) -> str:
    """Extract the subagent task id from a block/parent key, if any.

    Matches the ``subagent:<task_id>`` form (colon separator) used by the
    subagent card block key and by children's ``parent_block_key``. The
    design-jury child's own ``subagent-<task>-design-jury-<run>`` block key uses
    hyphens and intentionally does not match here — its ``parent_block_key`` does.
    """
    for key in (parent_block_key, block_key):
        text = str(key or "")
        if text.startswith("subagent:"):
            return text[len("subagent:"):]
    return ""


def stored_message_id(message_key: str) -> str:
    text = str(message_key or "").strip()
    if len(text) <= 40:
        return text
    return f"msg:v2:{stable_hash(text, length=32)}"


def block_key_for_event(event: dict[str, Any], *, fallback_kind: str = "text") -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    for key in ("block_key", "block_id", "blockId", "id"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    value = str(event.get("block_id") or "").strip()
    if value:
        return value
    sequence = int(event.get("sequence") or event.get("seq") or 0)
    return f"{fallback_kind}:{sequence}"


def op_id_for_event(event: dict[str, Any], op_type: str, block_key: str, *, suffix: str = "") -> str:
    sequence = int(event.get("sequence") or event.get("seq") or 0)
    raw = f"{event.get('conversation_id')}:{sequence}:{op_type}:{block_key}:{suffix}"
    return f"op:v2:{stable_hash(raw, length=24)}"
