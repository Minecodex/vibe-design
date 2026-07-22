from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.blob_artifacts import promote_large_tool_result
from app.services.agent_harness.runtime.eventing.event_log import append_event

from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta, utc_now, write_json
from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir


def trace_path(user_id: int, conversation_id: str) -> Path:
    return get_conversation_dir(user_id, conversation_id) / "trace.log"

def append_trace(
    user_id: int,
    conversation_id: str,
    *,
    trace_type: str,
    phase: str | None = None,
    run_status: str | None = None,
    current_item_id: str | None = None,
    summary: str | None = None,
    duration_ms: int | None = None,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> None:
    return
def record_internal_runtime_prompt(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    prompt_type: str,
    summary: str,
    prompt: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> None:
    metadata = prompt.get("metadata") if isinstance(prompt.get("metadata"), dict) else {}
    append_trace(
        user_id,
        conversation_id,
        trace_type=prompt_type,
        summary=summary,
        payload={
            "prompt": str(prompt.get("content") or ""),
            **({"prompt_bundle_trace": metadata.get("prompt_bundle_trace")} if metadata.get("prompt_bundle_trace") else {}),
            **(payload or {}),
        },
        run_id=run_id,
    )
def record_internal_recovery_prompt(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    decision: str,
    prompt: dict[str, Any],
    review: dict[str, Any],
    hint: str | None,
) -> None:
    record_internal_runtime_prompt(
        user_id,
        conversation_id,
        run_id=run_id,
        prompt_type="internal_recovery_prompt_generated",
        summary=f"Generated internal recovery prompt ({decision})",
        prompt=prompt,
        payload={
            "decision": decision,
            "hint": hint,
            "root_cause_hint": review.get("root_cause_hint"),
            "output_excerpt": review.get("output_excerpt"),
            "review": review,
        },
    )
def persist_tool_result(
    user_id: int,
    conversation_id: str,
    *,
    tool_call_id: str,
    payload: dict[str, Any],
) -> str:
    sanitized_payload = sanitize_persistent_payload(payload)
    text = json.dumps(sanitized_payload, ensure_ascii=False, sort_keys=True)
    promoted = promote_large_tool_result(
        user_id,
        conversation_id,
        tool_call_id=tool_call_id,
        tool_name=str(payload.get("tool") or "tool_result"),
        content=text,
    )
    result_ref = (
        str(promoted["artifact"]["ref"])
        if promoted.get("promoted") and isinstance(promoted.get("artifact"), dict)
        else f"event://tool-result/{uuid.uuid4().hex[:12]}"
    )
    event_payload = {
        "tool": sanitized_payload.get("tool"),
        "tool_call_id": tool_call_id,
        "result_ref": result_ref,
        "preview": promoted.get("preview"),
        "inline_payload": None if promoted.get("promoted") else sanitized_payload,
        "blob_artifact": promoted.get("artifact"),
        "size_chars": len(text),
        "mime_kind": "application/json",
    }
    append_event(
        user_id,
        conversation_id,
        run_id="tool-result",
        event_type="tool_result_recorded",
        payload=event_payload,
        lane="internal",
        tool_call_id=tool_call_id,
    )
    return result_ref
