from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.agent_harness.runtime.conversation_events import query_conversation_events
from app.services.agent_harness.workspace.conversation.conversation_service import get_conversation, get_conversation_dir
from app.services.agent_harness.workspace.conversation.conversation_store_support import is_within_path
from app.services.agent_harness.workspace.session_v2.service import detail_snapshot
from app.services.agent_harness.runtime.sidechain.diagnostics import build_sidechain_trace_diagnostic

TRACE_PROFILE_DIAGNOSTIC = "diagnostic"
TRACE_PROFILE_FULL = "full"
TRACE_PROFILES = {TRACE_PROFILE_DIAGNOSTIC, TRACE_PROFILE_FULL}

_REDACTED = "[REDACTED]"
_REDACTED_BEARER = "Bearer [REDACTED]"
_MAX_STRING_BY_PROFILE = {
    TRACE_PROFILE_DIAGNOSTIC: 2_000,
    TRACE_PROFILE_FULL: 12_000,
}
_MAX_LIST_BY_PROFILE = {
    TRACE_PROFILE_DIAGNOSTIC: 40,
    TRACE_PROFILE_FULL: 120,
}
_MAX_DICT_KEYS_BY_PROFILE = {
    TRACE_PROFILE_DIAGNOSTIC: 60,
    TRACE_PROFILE_FULL: 180,
}

_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(authorization|cookie|set-cookie|api[-_]?key|access[-_]?token|refresh[-_]?token|secret|password|license|signature|sig)"
)
_BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]+")
_SECRET_TOKEN_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:access_token|api_key|apikey|signature|sig|x-amz-signature|token)=)([^&\s]+)"
)


def export_trace_log(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str | None = None,
    profile: str = TRACE_PROFILE_DIAGNOSTIC,
    seq_from: int | None = None,
    seq_to: int | None = None,
    output_path: str | Path | None = None,
) -> Path:
    normalized_profile = str(profile or TRACE_PROFILE_DIAGNOSTIC).strip().lower()
    if normalized_profile not in TRACE_PROFILES:
        raise ValueError(f"Unsupported trace profile: {profile}")

    conversation = get_conversation(user_id, conversation_id)
    if conversation is None:
        raise FileNotFoundError(conversation_id)

    resolved_output = _resolve_output_path(
        conversation,
        output_path=output_path,
    )
    snapshot = detail_snapshot(user_id, conversation_id)
    events = query_conversation_events(
        user_id,
        conversation_id,
        run_id=run_id,
        seq_from=seq_from,
        seq_to=seq_to,
    )

    header = _build_trace_header(
        conversation=conversation,
        snapshot=snapshot,
        run_id=run_id,
        profile=normalized_profile,
        seq_from=seq_from,
        seq_to=seq_to,
        output_path=resolved_output,
        event_count=len(events),
    )

    lines = [json.dumps(header, ensure_ascii=False)]
    for event in events:
        lines.append(
            json.dumps(
                _build_trace_event(event, profile=normalized_profile),
                ensure_ascii=False,
            )
        )

    resolved_output.parent.mkdir(parents=True, exist_ok=True)
    resolved_output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return resolved_output


def default_trace_export_path(user_id: int, conversation_id: str) -> Path:
    conversation = get_conversation(user_id, conversation_id)
    if conversation is None:
        raise FileNotFoundError(conversation_id)
    conversation_dir = _conversation_dir_from_meta(conversation)
    return conversation_dir / "trace.log"


def _resolve_output_path(
    conversation: dict[str, Any],
    *,
    output_path: str | Path | None,
) -> Path:
    default_path = _conversation_dir_from_meta(conversation) / "trace.log"
    conversation_dir = default_path.parent.resolve()
    if output_path is None:
        return default_path

    raw = Path(output_path)
    candidate = (conversation_dir / raw).resolve() if not raw.is_absolute() else raw.resolve()
    if not is_within_path(candidate, conversation_dir):
        raise ValueError("Trace export output_path must stay within the conversation directory")
    return candidate


def _conversation_dir_from_meta(conversation: dict[str, Any]) -> Path:
    user_id = int(conversation["user_id"])
    conversation_id = str(conversation.get("id") or conversation.get("conversation_id") or "")
    runtime_profile = str(conversation.get("runtime_profile") or "home")
    project_id = conversation.get("project_id")
    return get_conversation_dir(
        user_id,
        conversation_id,
        runtime_profile=runtime_profile,
        project_id=project_id,
    )


def _build_trace_header(
    *,
    conversation: dict[str, Any],
    snapshot: dict[str, Any] | None,
    run_id: str | None,
    profile: str,
    seq_from: int | None,
    seq_to: int | None,
    output_path: Path,
    event_count: int,
) -> dict[str, Any]:
    payload = {
        "type": "trace_header",
        "profile": profile,
        "conversation_id": str(conversation.get("id") or conversation.get("conversation_id") or ""),
        "run_id": run_id,
        "seq_from": seq_from,
        "seq_to": seq_to,
        "output_path": output_path.name,
        "event_count": event_count,
        "conversation": _sanitize_value(conversation, profile=profile),
    }
    if snapshot is not None:
        payload["snapshot"] = _sanitize_value(snapshot, profile=profile)
        context_diagnostic = _context_runtime_diagnostic(snapshot)
        if context_diagnostic:
            payload["agent_context"] = context_diagnostic
    return payload


def _build_trace_event(event: dict[str, Any], *, profile: str) -> dict[str, Any]:
    payload = _sanitize_value(event.get("payload") or {}, profile=profile)
    trace_event = {
        "type": "event",
        "seq": event.get("seq"),
        "event_id": event.get("event_id") or event.get("id"),
        "ts": event.get("ts") or event.get("created_at"),
        "run_id": event.get("run_id"),
        "event_type": event.get("event_type") or event.get("type"),
        "lane": event.get("lane"),
        "block_id": event.get("block_id"),
        "parent_block_id": event.get("parent_block_id"),
        "tool_call_id": event.get("tool_call_id"),
        "agent_id": event.get("agent_id"),
        "artifact_id": event.get("artifact_id"),
        "payload": payload,
    }
    event_type = str(event.get("event_type") or event.get("type") or "")
    if event_type.startswith("subagent_") and isinstance(event.get("payload"), dict):
        trace_event["sidechain"] = _sanitize_value(
            build_sidechain_trace_diagnostic(event.get("payload") or {}),
            profile=profile,
        )
    return trace_event


def _sanitize_value(value: Any, *, profile: str, key: str | None = None) -> Any:
    if isinstance(value, dict):
        if key == "context_session":
            return _sanitize_context_session(value)
        if key == "render_context":
            return _sanitize_render_context(value)
        keys = list(value.keys())
        max_keys = _MAX_DICT_KEYS_BY_PROFILE[profile]
        payload: dict[str, Any] = {}
        for idx, raw_key in enumerate(keys):
            if idx >= max_keys:
                payload["_truncated_keys"] = {
                    "omitted": len(keys) - max_keys,
                }
                break
            text_key = str(raw_key)
            child = value.get(raw_key)
            if _SENSITIVE_KEY_PATTERN.search(text_key):
                payload[text_key] = _REDACTED if child not in (None, "") else child
                continue
            if text_key in {"system_prompt", "messages", "tool_schemas"}:
                payload[text_key] = _summarize_prompt_like_value(child)
                continue
            payload[text_key] = _sanitize_value(child, profile=profile, key=text_key)
        return payload

    if isinstance(value, list):
        max_items = _MAX_LIST_BY_PROFILE[profile]
        items = [
            _sanitize_value(item, profile=profile, key=key)
            for item in value[:max_items]
        ]
        if len(value) > max_items:
            items.append({"_truncated_items": len(value) - max_items})
        return items

    if isinstance(value, tuple):
        return _sanitize_value(list(value), profile=profile, key=key)

    if isinstance(value, str):
        return _sanitize_string(value, profile=profile, key=key)

    return deepcopy(value)


def _context_runtime_diagnostic(snapshot: dict[str, Any]) -> dict[str, Any]:
    runtime_snapshot = snapshot.get("runtime_snapshot_json")
    if not isinstance(runtime_snapshot, dict):
        runtime_snapshot = snapshot.get("runtime_snapshot")
    if not isinstance(runtime_snapshot, dict):
        runtime_snapshot = snapshot.get("runtime_state")
    if not isinstance(runtime_snapshot, dict):
        return {}
    payload: dict[str, Any] = {}
    session = runtime_snapshot.get("context_session")
    if isinstance(session, dict):
        payload["context_session"] = _sanitize_context_session(session)
    render_context = runtime_snapshot.get("render_context")
    if isinstance(render_context, dict):
        payload["render_context"] = _sanitize_render_context(render_context)
    return payload


def _sanitize_context_session(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": session.get("version"),
        "fingerprint": session.get("fingerprint"),
        "runtime_preparation_fingerprint": session.get("runtime_preparation_fingerprint"),
        "static_context_hash": session.get("static_context_hash"),
        "language": session.get("language"),
        "model": session.get("model"),
        "skill_id": session.get("skill_id"),
        "artifact_mode": session.get("artifact_mode"),
        "created_at": session.get("created_at"),
        "tool_schema_count": len(session.get("tool_schemas") or []) if isinstance(session.get("tool_schemas"), list) else 0,
        "has_runtime_contract": isinstance(session.get("runtime_contract"), dict),
        "has_workspace_runtime_session": isinstance(session.get("workspace_runtime_session"), dict),
        "has_prepared_workspace": isinstance(session.get("prepared_workspace"), dict),
    }


def _sanitize_render_context(render_context: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "turn",
        "message_seq_end",
        "event_seq_end",
        "dynamic_context_digest",
        "history_source",
        "static_context_hash",
    }
    return {key: deepcopy(render_context.get(key)) for key in allowed if key in render_context}


def _summarize_prompt_like_value(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return {"redacted": True, "chars": len(value)}
    if isinstance(value, list):
        return {"redacted": True, "items": len(value)}
    if isinstance(value, dict):
        return {"redacted": True, "keys": len(value)}
    return {"redacted": True}


def _sanitize_string(value: str, *, profile: str, key: str | None = None) -> str:
    if key and _SENSITIVE_KEY_PATTERN.search(key):
        return _REDACTED if value.strip() else value

    sanitized = value
    sanitized = _BEARER_PATTERN.sub(_REDACTED_BEARER, sanitized)
    sanitized = _SECRET_TOKEN_PATTERN.sub(_REDACTED, sanitized)
    sanitized = _QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", sanitized)

    max_len = _MAX_STRING_BY_PROFILE[profile]
    if len(sanitized) <= max_len:
        return sanitized
    omitted = len(sanitized) - max_len
    return f"{sanitized[:max_len]}\n...[TRUNCATED {omitted} chars]"
