from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import replace
from typing import Any

from app.core.config import settings
from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.authoring.prompt.runtime_time import runtime_time_block
from app.services.agent_harness.capabilities.skill_protocols.base import prepared_workspace_from_payload
from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.core.utils.token_counter import estimate_messages_tokens, estimate_tokens
from app.services.agent_harness.prompt_runtime import Phase, PolicyEngine, PromptMode, TurnSpec
from app.services.agent_harness.runtime.critique.lifecycle import critique_runtime_payload
from app.services.agent_harness.runtime.model_context import build_model_context, compact_if_needed
from app.services.agent_harness.runtime.model_context.budget_policy import (
    build_model_context_budget,
    calculate_token_state,
)
from app.services.agent_harness.runtime.model_context.microcompact import microcompact_messages
from app.services.agent_harness.runtime.model_context.models import ModelContextLimitExceeded
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta, utc_now, write_json
from app.services.agent_harness.runtime.system_write_lease import system_write_lease
from app.services.multimodal_service import get_multimodal_model_config, resolve_multimodal_provider

from .runtime_preparation import create_workflow_context, prepare_execution_runtime_context

CONTEXT_SESSION_VERSION = 1
RENDER_CONTEXT_CHECKPOINT_VERSION = 1
DEFAULT_RENDER_CONTEXT_TOKEN_BUDGET = 100_000
CONTEXT_SAFETY_MARGIN_TOKENS = 4_096
AGENT_CONTEXT_VERSION = 2
_POLICY_ENGINE = PolicyEngine()
HOME_INFORMATIONAL_TOOL_NAMES: tuple[str, ...] = (
    "ask_user",
    "search_harness_history",
    "workspace_map",
    "list_files",
    "glob_files",
    "grep_files",
    "read_file",
    "web_search",
    "fetch_webpage",
    "analyze_image",
    "generate_image",
    "generate_video",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_payload(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _tool_schema_name(schema: dict[str, Any]) -> str:
    function = schema.get("function") if isinstance(schema.get("function"), dict) else {}
    return str(function.get("name") or schema.get("name") or "")


def _stable_tool_schemas(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        json.loads(_canonical_json(schema))
        for schema in sorted((dict(item) for item in schemas if isinstance(item, dict)), key=_tool_schema_name)
    ]


def _context_session_phase(conversation: dict[str, Any]) -> str:
    phase = str(conversation.get("phase") or "").strip().lower()
    if phase in {"planning", "planning_ready", "awaiting_plan_review"}:
        return Phase.PLANNING.value
    if phase == Phase.REVISING_PLAN.value:
        return Phase.REVISING_PLAN.value
    if phase == Phase.FINALIZING.value:
        return Phase.FINALIZING.value
    if phase == Phase.RECOVERY.value:
        return Phase.RECOVERY.value
    return Phase.EXECUTING.value


def _is_plan_execution_in_progress(conversation: dict[str, Any]) -> bool:
    if str(conversation.get("phase") or "").strip().lower() != Phase.EXECUTING.value:
        return False
    plan_state = conversation.get("plan_state")
    if not isinstance(plan_state, dict):
        return False
    if str(plan_state.get("status") or "").strip().lower() == "in_progress":
        return True
    outline = plan_state.get("outline_state") if isinstance(plan_state.get("outline_state"), dict) else {}
    execution = plan_state.get("execution_state") if isinstance(plan_state.get("execution_state"), dict) else {}
    return (
        str(outline.get("status") or "").strip().lower() == "executing"
        or str(execution.get("status") or "").strip().lower() == "in_progress"
    )


def _allows_no_skill_context(conversation: dict[str, Any]) -> bool:
    if str(conversation.get("runtime_profile") or "home").strip().lower() != "home":
        return False
    turn_route = conversation.get("turn_route") if isinstance(conversation.get("turn_route"), dict) else {}
    return (
        str(turn_route.get("route_kind") or "").strip() == "informational_turn"
        and str(turn_route.get("activity") or "").strip() == "answering"
        and not bool(turn_route.get("requires_skill_selection"))
        and not conversation.get("skill_id")
        and not conversation.get("resolved_skill_id")
    )


def tool_schemas_for_phase(
    registry: Any,
    *,
    phase: str,
    language: str,
    skill_tool_names: list[str] | None = None,
    disabled_tool_names: list[str] | None = None,
    repair_required: bool = False,
    web_search_call_count: int = 0,
    hide_ask_user: bool = False,
) -> list[dict[str, Any]]:
    decision = _POLICY_ENGINE.resolve(
        TurnSpec(
            mode=PromptMode.MAIN_TURN,
            phase=phase if phase in {member.value for member in Phase} else Phase.EXECUTING,
            language=language,
            conversation={"user_plan_repair_required": repair_required},
            web_search_call_count=web_search_call_count,
        )
    )
    if phase in {"planning", "revising_plan"}:
        tools = registry.get_tools_for_skill(None)
        allowed_names = set(decision.allowed_tools)
        tools = [tool for tool in tools if tool.name in allowed_names]
    else:
        tools = registry.get_tools_for_skill(skill_tool_names)
    if disabled_tool_names:
        disabled_names = {str(name or "").strip() for name in disabled_tool_names if str(name or "").strip()}
        tools = [tool for tool in tools if tool.name not in disabled_names]
    if hide_ask_user:
        tools = [tool for tool in tools if tool.name != "ask_user"]
    return registry.to_api_schemas(tools=tools, fmt="openai", language=language)


def home_informational_tool_schemas(registry: Any, *, language: str) -> list[dict[str, Any]]:
    tools = registry.get_tools_by_names(HOME_INFORMATIONAL_TOOL_NAMES)
    return registry.to_api_schemas(tools=tools, fmt="openai", language=language)


def _context_session_static_payload(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": int(session.get("version") or CONTEXT_SESSION_VERSION),
        "phase": str(session.get("phase") or ""),
        "language": str(session.get("language") or ""),
        "model": str(session.get("model") or ""),
        "multimodal_provider": str(session.get("multimodal_provider") or ""),
        "skill_id": str(session.get("skill_id") or ""),
        "artifact_mode": str(session.get("artifact_mode") or ""),
        "system_prompt": str(session.get("system_prompt") or ""),
        "context_snapshot_blocks": list(session.get("context_snapshot_blocks") or []),
        "turn_append_blocks": list(session.get("turn_append_blocks") or []),
        "tool_schemas": _stable_tool_schemas(list(session.get("tool_schemas") or [])),
        "runtime_contract": dict(session.get("runtime_contract") or {}),
        "workspace_runtime_session": dict(session.get("workspace_runtime_session") or {}),
        "prepared_workspace": dict(session.get("prepared_workspace") or {}),
    }


def _context_session_fingerprint(static_payload: dict[str, Any]) -> str:
    runtime_contract = static_payload.get("runtime_contract") if isinstance(static_payload.get("runtime_contract"), dict) else {}
    return _sha256_payload(
        {
            "version": CONTEXT_SESSION_VERSION,
            "phase": static_payload.get("phase"),
            "language": static_payload.get("language"),
            "model": static_payload.get("model"),
            "multimodal_provider": static_payload.get("multimodal_provider"),
            "skill_id": static_payload.get("skill_id"),
            "artifact_mode": static_payload.get("artifact_mode"),
            "skill_source_digest": (runtime_contract.get("active_skill_context") or {}).get("source_digest"),
            "context_snapshot_hash": _sha256_payload(static_payload.get("context_snapshot_blocks") or []),
            "tool_schema_hash": _sha256_payload(static_payload.get("tool_schemas") or []),
        }
    )


def _stable_system_hash(system: str) -> str:
    return hashlib.sha256(str(system or "").encode("utf-8")).hexdigest()


def _context_block_entries(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("id") or "").strip()
        content = str(block.get("content") or "").strip()
        if not block_id or not content:
            continue
        entries.append(
            {
                "id": block_id,
                "content": content,
                "hash": _sha256_payload({"id": block_id, "content": content}),
                "cache_policy": "snapshot",
            }
        )
    return entries


def _agent_prompt_context_snapshot(*, stable_system: str, context_entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": AGENT_CONTEXT_VERSION,
        "stable_system_hash": _stable_system_hash(stable_system),
        "context_blocks": {
            str(entry.get("id")): str(entry.get("hash"))
            for entry in context_entries
            if str(entry.get("id") or "").strip() and str(entry.get("hash") or "").strip()
        },
    }


def _previous_agent_prompt_context(conversation: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(conversation, dict):
        return None
    candidates = [
        conversation.get("agent_prompt_context_v2"),
        (conversation.get("runtime_snapshot") or {}).get("agent_prompt_context_v2")
        if isinstance(conversation.get("runtime_snapshot"), dict)
        else None,
        (conversation.get("runtime_snapshot_json") or {}).get("agent_prompt_context_v2")
        if isinstance(conversation.get("runtime_snapshot_json"), dict)
        else None,
    ]
    runtime_state = conversation.get("runtime_state")
    if isinstance(runtime_state, dict):
        candidates.append(runtime_state.get("agent_prompt_context_v2"))
    for candidate in candidates:
        if isinstance(candidate, dict) and int(candidate.get("version") or 0) == AGENT_CONTEXT_VERSION:
            return candidate
    return None


def _render_agent_context_content(*, kind: str, entries: list[dict[str, Any]]) -> str:
    lines = [f'<agent_context kind="{kind}" version="{AGENT_CONTEXT_VERSION}">']
    for entry in entries:
        block_id = str(entry.get("id") or "").strip()
        content = str(entry.get("content") or "").strip()
        if not block_id or not content:
            continue
        lines.extend([f'<context_block id="{block_id}">', content, "</context_block>"])
    lines.append("</agent_context>")
    return "\n".join(lines)


def _agent_context_message(
    *,
    kind: str,
    content: str,
    context_hash: str,
    idempotency_key: str,
    cache_policy: str = "snapshot",
    ledger_turn_key: str | None = None,
    render_step_id: str | None = None,
    turn: int | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "message_kind": "agent_context",
        "model_visible": True,
        "ui_visible": False,
        "agent_context_kind": kind,
        "agent_context_version": AGENT_CONTEXT_VERSION,
        "context_hash": context_hash,
        "cache_policy": cache_policy,
        "idempotency_key": idempotency_key,
    }
    if ledger_turn_key:
        metadata["ledger_turn_key"] = ledger_turn_key
    if render_step_id:
        metadata["render_step_id"] = render_step_id
    if turn is not None:
        metadata["turn"] = int(turn)
    return {
        "role": "system",
        "content": content,
        "metadata": metadata,
    }


def _user_intent_ledger_message(
    *,
    current_user_message: dict[str, Any] | None,
    run_id: str,
    ledger_turn_key: str,
    render_step_id: str,
    turn: int,
) -> dict[str, Any] | None:
    if not isinstance(current_user_message, dict):
        return None
    content = str(current_user_message.get("content") or "")
    attachments = (
        list(current_user_message.get("attachments") or [])
        if isinstance(current_user_message.get("attachments"), list)
        else []
    )
    metadata = (
        dict(current_user_message.get("metadata") or {})
        if isinstance(current_user_message.get("metadata"), dict)
        else {}
    )
    if not content and not attachments and not metadata:
        return None

    original_key = str(metadata.get("idempotency_key") or "").strip() or f"run:{run_id}:user-message"
    context_hash = _sha256_payload(
        {
            "content": content,
            "attachments": attachments,
            "references": metadata.get("references"),
        }
    )
    ledger_metadata = {
        **metadata,
        "message_kind": "agent_context",
        "model_visible": True,
        "ui_visible": False,
        "agent_context_kind": "user_intent",
        "agent_context_version": AGENT_CONTEXT_VERSION,
        "context_hash": context_hash,
        "cache_policy": "run_input",
        "idempotency_key": f"{original_key}:agent-context:user-intent",
        "source_message_id": original_key,
        "ledger_turn_key": ledger_turn_key,
        "render_step_id": render_step_id,
        "turn": int(turn),
    }
    return {
        "role": "user",
        "content": content,
        "attachments": attachments,
        "created_at": current_user_message.get("created_at"),
        "metadata": ledger_metadata,
    }


def _context_ledger_messages(
    *,
    run_id: str,
    context_session: dict[str, Any],
    conversation: dict[str, Any] | None,
    ledger_turn_key: str,
    render_step_id: str,
    turn: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    stable_system = str(context_session.get("system_prompt") or "")
    entries = _context_block_entries(list(context_session.get("context_snapshot_blocks") or []))
    snapshot = _agent_prompt_context_snapshot(stable_system=stable_system, context_entries=entries)
    previous = _previous_agent_prompt_context(conversation)
    previous_hashes = previous.get("context_blocks") if isinstance(previous, dict) else None
    stable_changed = not isinstance(previous, dict) or previous.get("stable_system_hash") != snapshot["stable_system_hash"]
    if stable_changed or not isinstance(previous_hashes, dict):
        changed_entries = entries
        kind = "context_init"
    else:
        changed_entries = [
            entry
            for entry in entries
            if str(previous_hashes.get(str(entry.get("id") or "")) or "") != str(entry.get("hash") or "")
        ]
        kind = "context_update"
    if not changed_entries:
        return [], snapshot
    content = _render_agent_context_content(kind=kind, entries=changed_entries)
    context_hash = _sha256_payload({"kind": kind, "entries": changed_entries})
    return [
        _agent_context_message(
            kind=kind,
            content=content,
            context_hash=context_hash,
            idempotency_key=f"run:{run_id}:agent-context:{kind}:{context_hash[:16]}",
            ledger_turn_key=ledger_turn_key,
            render_step_id=render_step_id,
            turn=turn,
        )
    ], snapshot


def _runtime_time_ledger_message(
    *,
    ledger_turn_key: str,
    render_step_id: str,
    turn: int,
    language: str,
) -> dict[str, Any]:
    content = (
        f'<agent_context kind="runtime_time" version="{AGENT_CONTEXT_VERSION}">\n'
        f"{runtime_time_block(language)}\n"
        "</agent_context>"
    )
    context_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return _agent_context_message(
        kind="runtime_time",
        content=content,
        context_hash=context_hash,
        idempotency_key=f"{ledger_turn_key}:agent-context:runtime-time:{context_hash[:16]}",
        cache_policy="append_each_turn",
        ledger_turn_key=ledger_turn_key,
        render_step_id=render_step_id,
        turn=turn,
    )


def _turn_append_ledger_message(
    *,
    ledger_turn_key: str,
    render_step_id: str,
    turn: int,
    context_session: dict[str, Any],
) -> dict[str, Any] | None:
    entries = _context_block_entries(list(context_session.get("turn_append_blocks") or []))
    if not entries:
        return None
    content = _render_agent_context_content(kind="turn_append", entries=entries)
    context_hash = _sha256_payload({"kind": "turn_append", "entries": entries})
    return _agent_context_message(
        kind="turn_append",
        content=content,
        context_hash=context_hash,
        idempotency_key=f"{ledger_turn_key}:agent-context:turn-append:{context_hash[:16]}",
        cache_policy="append_each_turn",
        ledger_turn_key=ledger_turn_key,
        render_step_id=render_step_id,
        turn=turn,
    )


def _resolve_multimodal_provider_for_budget(model: str, provider_code: str | None) -> str:
    explicit = str(provider_code or "").strip()
    if explicit:
        return explicit
    return resolve_multimodal_provider(str(model or ""))


def _model_message_budget_details(
    *,
    system: str,
    model: str,
    provider_code: str | None,
    tool_schemas: list[dict[str, Any]],
) -> dict[str, Any]:
    resolved_provider = _resolve_multimodal_provider_for_budget(model, provider_code)
    config = get_multimodal_model_config(str(model or ""), resolved_provider)
    configured_limit = int((config or {}).get("max_input_tokens") or 0) if isinstance(config, dict) else 0
    fallback_budget_used = configured_limit <= 0
    if configured_limit <= 0:
        configured_limit = DEFAULT_RENDER_CONTEXT_TOKEN_BUDGET
    system_tokens = estimate_tokens(system)
    tools_tokens = estimate_tokens(json.dumps(tool_schemas or [], ensure_ascii=False, separators=(",", ":")))
    budget = max(4_096, configured_limit - system_tokens - tools_tokens - CONTEXT_SAFETY_MARGIN_TOKENS)
    return {
        "message_token_budget": budget,
        "model_provider": resolved_provider,
        "configured_max_input_tokens": configured_limit,
        "fallback_budget_used": fallback_budget_used,
        "system_token_estimate": system_tokens,
        "tool_schema_token_estimate": tools_tokens,
        "safety_margin_tokens": CONTEXT_SAFETY_MARGIN_TOKENS,
    }


def _model_message_token_budget(
    *,
    system: str,
    model: str,
    provider_code: str | None,
    tool_schemas: list[dict[str, Any]],
) -> int:
    return int(
        _model_message_budget_details(
            system=system,
            model=model,
            provider_code=provider_code,
            tool_schemas=tool_schemas,
        )["message_token_budget"]
    )


def _prompt_debug_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _prompt_debug_text_hash(text: Any) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _prompt_debug_optional_hash(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _prompt_debug_text_hash(text)


def _prompt_debug_message_fingerprint(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    return {
        "role": str(message.get("role") or ""),
        "content_hash": _prompt_debug_hash(content),
        "content_chars": len(str(content or "")),
        "tool_calls_hash": _prompt_debug_hash(tool_calls),
        "tool_call_count": len(tool_calls),
        "tool_call_id": str(message.get("tool_call_id") or "") or None,
        "message_kind": str(metadata.get("message_kind") or "") or None,
        "agent_context_kind": str(metadata.get("agent_context_kind") or "") or None,
        "cache_policy": str(metadata.get("cache_policy") or "") or None,
        "context_hash": str(metadata.get("context_hash") or "") or None,
        "metadata_hash": _prompt_debug_hash(metadata),
        "idempotency_key_hash": _prompt_debug_optional_hash(metadata.get("idempotency_key")),
        "ledger_turn_key_hash": _prompt_debug_optional_hash(metadata.get("ledger_turn_key")),
    }


def _prompt_debug_wire_fingerprint(message: dict[str, Any]) -> dict[str, Any]:
    tool_calls = message.get("tool_calls") if isinstance(message.get("tool_calls"), list) else []
    return {
        "role": str(message.get("role") or ""),
        "content_hash": _prompt_debug_hash(message.get("content")),
        "tool_calls_hash": _prompt_debug_hash(tool_calls),
        "tool_call_id": str(message.get("tool_call_id") or "") or None,
    }


def _prompt_debug_message_entry(message: dict[str, Any], *, index: int, include_full: bool) -> dict[str, Any]:
    entry = {"index": index, **_prompt_debug_message_fingerprint(message)}
    if include_full:
        entry["content"] = deepcopy(message.get("content"))
        if isinstance(message.get("tool_calls"), list):
            entry["tool_calls"] = deepcopy(message.get("tool_calls"))
    return entry


def _load_latest_prompt_cache_debug_trace(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    debug_dir = ensure_harness_meta(user_id, conversation_id) / "prompt_cache_debug"
    if not debug_dir.exists():
        return None
    paths = sorted(debug_dir.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            if str(payload.get("trace_type") or "prompt_cache_render") != "prompt_cache_render":
                continue
            if not isinstance(payload.get("message_fingerprints"), list):
                continue
            return payload
    return None


def _prompt_cache_debug_diff(
    *,
    previous: dict[str, Any] | None,
    system_hash: str,
    tools_hash: str,
    message_fingerprints: list[dict[str, Any]],
    previous_fingerprint_key: str = "message_fingerprints",
    current_fingerprints_label: str = "messages",
) -> dict[str, Any]:
    if not isinstance(previous, dict):
        return {
            "previous_trace": None,
            "same_system": None,
            "same_tools": None,
            "common_prefix_message_count": 0,
            "first_changed_message_index": None,
            "first_changed_reason": "no_previous_trace",
        }
    previous_messages = previous.get(previous_fingerprint_key)
    previous_messages = previous_messages if isinstance(previous_messages, list) else []
    common = 0
    first_reason = None
    for left, right in zip(previous_messages, message_fingerprints):
        if left == right:
            common += 1
            continue
        first_reason = _prompt_debug_first_message_diff_reason(left, right)
        break
    first_index = common if common < min(len(previous_messages), len(message_fingerprints)) else None
    if first_index is None and len(previous_messages) != len(message_fingerprints):
        first_index = common
        first_reason = "message_count_changed"
    return {
        "previous_trace": previous.get("trace_file"),
        "same_system": previous.get("system_hash") == system_hash,
        "same_tools": previous.get("tools_hash") == tools_hash,
        "common_prefix_message_count": common,
        "first_changed_message_index": first_index,
        "first_changed_reason": first_reason,
        "previous_message_count": len(previous_messages),
        "current_message_count": len(message_fingerprints),
        "fingerprint_key": previous_fingerprint_key,
        "current_fingerprints_label": current_fingerprints_label,
    }


def _prompt_debug_first_message_diff_reason(left: Any, right: Any) -> str:
    if not isinstance(left, dict) or not isinstance(right, dict):
        return "message_shape_changed"
    for key in (
        "role",
        "content_hash",
        "tool_calls_hash",
        "tool_call_id",
        "message_kind",
        "agent_context_kind",
        "context_hash",
        "idempotency_key_hash",
    ):
        if left.get(key) != right.get(key):
            return f"{key}_changed"
    return "message_metadata_changed"


def _persist_prompt_cache_debug_trace(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    render_step_id: str | None = None,
    turn: int | None = None,
    ledger_turn_key: str | None = None,
    turn_context: dict[str, Any],
    checkpoint: dict[str, Any],
    diagnostics: dict[str, Any],
) -> str | None:
    if not bool(getattr(settings, "HARNESS_PROMPT_CACHE_DEBUG", False)):
        return None
    include_full = bool(getattr(settings, "HARNESS_PROMPT_CACHE_DEBUG_FULL", False))
    system = str(turn_context.get("system") or "")
    messages = [message for message in list(turn_context.get("messages") or []) if isinstance(message, dict)]
    tools = [tool for tool in list(turn_context.get("tools") or []) if isinstance(tool, dict)]
    system_hash = _prompt_debug_text_hash(system)
    tools_hash = _prompt_debug_hash(tools)
    message_fingerprints = [_prompt_debug_message_fingerprint(message) for message in messages]
    wire_message_fingerprints = [_prompt_debug_wire_fingerprint(message) for message in messages]
    previous = _load_latest_prompt_cache_debug_trace(user_id, conversation_id)
    trace_file = (
        f"turn-{int((checkpoint or {}).get('message_seq_end') or 0):08d}"
        f"-event-{int((checkpoint or {}).get('event_seq_end') or 0):08d}"
        f"-{time.time_ns()}-{run_id}.json"
    )
    trace = {
        "version": 1,
        "trace_type": "prompt_cache_render",
        "trace_file": trace_file,
        "created_at": utc_now(),
        "run_id": run_id,
        "conversation_id": conversation_id,
        "render_step_id": render_step_id,
        "turn": turn,
        "ledger_turn_key_hash": _prompt_debug_optional_hash(ledger_turn_key),
        "model": turn_context.get("model"),
        "model_provider": diagnostics.get("model_provider"),
        "language": turn_context.get("language"),
        "prompt_cache_key": turn_context.get("prompt_cache_key"),
        "system_hash": system_hash,
        "system_chars": len(system),
        "tools_hash": tools_hash,
        "tool_schema_count": len(tools),
        "messages_hash": _prompt_debug_hash(message_fingerprints),
        "wire_messages_hash": _prompt_debug_hash(wire_message_fingerprints),
        "message_count": len(messages),
        "message_fingerprints": message_fingerprints,
        "wire_message_fingerprints": wire_message_fingerprints,
        "messages": [
            _prompt_debug_message_entry(message, index=index, include_full=include_full)
            for index, message in enumerate(messages)
        ],
        "agent_context": {
            "message_kinds": [
                message.get("metadata", {}).get("agent_context_kind")
                for message in messages
                if isinstance(message.get("metadata"), dict)
                and message.get("metadata", {}).get("message_kind") == "agent_context"
            ],
            "snapshot_hash": (checkpoint or {}).get("dynamic_context_digest"),
        },
        "prefix_diff": _prompt_cache_debug_diff(
            previous=previous,
            system_hash=system_hash,
            tools_hash=tools_hash,
            message_fingerprints=message_fingerprints,
            previous_fingerprint_key="message_fingerprints",
            current_fingerprints_label="messages",
        ),
        "wire_prefix_diff": _prompt_cache_debug_diff(
            previous=previous,
            system_hash=system_hash,
            tools_hash=tools_hash,
            message_fingerprints=wire_message_fingerprints,
            previous_fingerprint_key="wire_message_fingerprints",
            current_fingerprints_label="wire_messages",
        ),
        "checkpoint": {
            "message_seq_end": (checkpoint or {}).get("message_seq_end"),
            "event_seq_end": (checkpoint or {}).get("event_seq_end"),
            "history_source": (checkpoint or {}).get("history_source"),
            "dynamic_context_digest": (checkpoint or {}).get("dynamic_context_digest"),
        },
        "diagnostics": deepcopy(diagnostics),
        "full_content_included": include_full,
    }
    if include_full:
        trace["system"] = system
        trace["tools"] = deepcopy(tools)
    meta_dir = ensure_harness_meta(user_id, conversation_id)
    debug_dir = meta_dir / "prompt_cache_debug"
    with system_write_lease(
        user_id=user_id,
        conversation_id=conversation_id,
        owner="prompt_cache_debug",
        paths=(".meta/prompt_cache_debug",),
        ttl_seconds=30.0,
        run_id=run_id,
    ):
        write_json(debug_dir / trace_file, sanitize_persistent_payload(trace))
    return trace_file


def validate_context_session_integrity(session: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    static_payload = _context_session_static_payload(session)
    expected_static_hash = _sha256_payload(static_payload)
    expected_fingerprint = _context_session_fingerprint(static_payload)
    ok = (
        str(session.get("static_context_hash") or "") == expected_static_hash
        and str(session.get("fingerprint") or "") == expected_fingerprint
    )
    return ok, {
        "expected_static_context_hash": expected_static_hash,
        "actual_static_context_hash": session.get("static_context_hash"),
        "expected_fingerprint": expected_fingerprint,
        "actual_fingerprint": session.get("fingerprint"),
    }


def _conversation_with_session(conversation: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    merged = dict(conversation)
    runtime_state = dict(merged.get("runtime_state") or {})
    if isinstance(session.get("runtime_contract"), dict):
        runtime_state["runtime_contract"] = deepcopy(session.get("runtime_contract"))
    if isinstance(session.get("workspace_runtime_session"), dict):
        runtime_state["workspace_runtime_session"] = deepcopy(session.get("workspace_runtime_session"))
    if isinstance(session.get("prepared_workspace"), dict):
        runtime_state["prepared_workspace"] = deepcopy(session.get("prepared_workspace"))
    merged["runtime_state"] = runtime_state
    return merged


def apply_context_session_to_context(ctx: HarnessContext, session: dict[str, Any]) -> None:
    runtime_contract = dict(session.get("runtime_contract") or {}) if isinstance(session.get("runtime_contract"), dict) else {}
    if runtime_contract:
        setattr(ctx, "runtime_contract", runtime_contract)
    if isinstance(session.get("prepared_workspace"), dict):
        prepared = dict(session["prepared_workspace"])
        ctx.prepared_workspace = prepared_workspace_from_payload(prepared)
        ctx.artifact_work_root = str(prepared.get("artifact_work_root") or "").strip() or None
        ctx.prepared_entry_file = str(prepared.get("entry_file") or "").strip() or None
    if isinstance(session.get("workspace_runtime_session"), dict):
        workspace_runtime_session = dict(session["workspace_runtime_session"])
        if runtime_contract:
            workspace_runtime_session.setdefault("runtime_contract", runtime_contract)
        ctx.workspace_runtime_session = workspace_runtime_session
    elif runtime_contract:
        ctx.workspace_runtime_session = {"runtime_contract": runtime_contract}
    skill_root = str(runtime_contract.get("active_skill_runtime", {}).get("staged_root") or "skill")
    runtime_root = (ctx.conversation_dir / skill_root).resolve()
    ctx.active_skill_dir = runtime_root
    ctx.skill_runtime_dir = runtime_root
    if session.get("skill_id"):
        ctx.skill_id = str(session.get("skill_id"))
    if session.get("model"):
        ctx.multimodal_model = str(session.get("model"))
    if session.get("multimodal_provider"):
        ctx.multimodal_provider = str(session.get("multimodal_provider"))


class ContextSessionManager:
    def build(
        self,
        *,
        user_id: int,
        conversation_id: str,
        run_id: str,
        payload: dict[str, Any],
        conversation: dict[str, Any],
    ) -> dict[str, Any]:
        language = str(payload.get("language") or conversation.get("language") or "zh")
        skill_id = str(conversation.get("skill_id") or conversation.get("resolved_skill_id") or "").strip()
        skill = get_skill(skill_id) if skill_id else None
        no_skill_context = skill is None and _allows_no_skill_context(conversation)
        if skill is None and not no_skill_context:
            raise RuntimeError("execution context session requires a selected skill")
        phase = _context_session_phase(conversation)

        ctx = create_workflow_context(
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            language=language,
            conversation=conversation,
        )
        ctx.ensure_dirs()
        if skill is not None:
            ctx.skill_id = getattr(skill, "id", skill_id)
            prepared_runtime = prepare_execution_runtime_context(ctx=ctx, conversation=conversation, skill=skill)
        else:
            prepared_runtime = {
                "runtime_contract": {},
                "workspace_runtime_session": {},
                "prepared_workspace": {},
                "active_skill_runtime_trace": None,
            }
        runtime_contract = dict(prepared_runtime.get("runtime_contract") or {})
        workspace_runtime_session = dict(prepared_runtime.get("workspace_runtime_session") or {})
        prepared_workspace = dict(prepared_runtime.get("prepared_workspace") or {})
        prepared_conversation = _conversation_with_session(
            {
                **conversation,
                "phase": phase,
                "run_state": str(conversation.get("run_state") or phase),
            },
            {
                "runtime_contract": runtime_contract,
                "workspace_runtime_session": workspace_runtime_session,
                "prepared_workspace": prepared_workspace,
            },
        )

        registry = create_harness_registry(web_search_enabled=bool(payload.get("web_search_enabled", True)))
        model = str(ctx.multimodal_model or "")
        if not model:
            from app.services.agent_harness.core.engine_helpers.engine_utils import resolve_harness_multimodal_model

            model = resolve_harness_multimodal_model(prepared_conversation)
            ctx.multimodal_model = model
        model_preferences = prepared_conversation.get("model_preferences") if isinstance(prepared_conversation, dict) else {}
        explicit_multimodal_provider = (
            str((model_preferences or {}).get("multimodal_provider") or "").strip()
            if isinstance(model_preferences, dict)
            else ""
        )
        multimodal_provider = _resolve_multimodal_provider_for_budget(model, explicit_multimodal_provider or None)
        ctx.multimodal_provider = multimodal_provider
        if no_skill_context:
            tools = _stable_tool_schemas(home_informational_tool_schemas(registry, language=language))
        else:
            skill_tool_names = list(getattr(skill, "tools", []) or [])
            disabled_tool_names = list(getattr(skill, "disabled_tools", []) or [])
            tools = _stable_tool_schemas(
                tool_schemas_for_phase(
                    registry,
                    phase=phase,
                    language=language,
                    skill_tool_names=skill_tool_names,
                    disabled_tool_names=disabled_tool_names,
                    repair_required=bool(prepared_conversation.get("user_plan_repair_required")),
                    hide_ask_user=_is_plan_execution_in_progress(prepared_conversation),
                )
            )

        from app.services.agent_harness.authoring.prompt.context_builder import render_main_turn_prompt_partitions

        prompt_partitions = render_main_turn_prompt_partitions(
            language=language,
            model_name=model,
            conversation=prepared_conversation,
            skill=skill,
            skill_prompt=(skill.system_prompt if language == "zh" else skill.system_prompt_en) if skill is not None else None,
            artifact_mode=str(prepared_conversation.get("artifact_mode") or "web"),
            skill_id=str(getattr(skill, "id", skill_id) or skill_id),
            skill_runtime_dir=getattr(ctx, "skill_runtime_dir", None) or getattr(ctx, "active_skill_dir", None),
            prepared_workspace=getattr(ctx, "prepared_workspace", None),
            workspace_runtime_session=workspace_runtime_session,
            runtime_contract=runtime_contract,
            tool_schemas=tools,
        )
        system_prompt = str(prompt_partitions.get("stable_system") or "")
        context_snapshot_blocks = list(prompt_partitions.get("context_snapshot_blocks") or [])
        turn_append_blocks = list(prompt_partitions.get("turn_append_blocks") or [])
        critique_payload = critique_runtime_payload(harness_run_id=run_id)

        static_payload = {
            "version": CONTEXT_SESSION_VERSION,
            "phase": phase,
            "language": language,
            "model": model,
            "multimodal_provider": multimodal_provider,
            "skill_id": str(getattr(skill, "id", skill_id) or skill_id),
            "artifact_mode": str(prepared_conversation.get("artifact_mode") or "web"),
            "system_prompt": system_prompt,
            "context_snapshot_blocks": context_snapshot_blocks,
            "turn_append_blocks": turn_append_blocks,
            "tool_schemas": tools,
            "runtime_contract": runtime_contract,
            "workspace_runtime_session": workspace_runtime_session,
            "prepared_workspace": prepared_workspace,
        }
        # critique is dynamic per-run state (a fresh critique-{uuid} every PREPARE);
        # it must not enter the static integrity hash, otherwise the validation-side
        # extractor (_context_session_static_payload, which omits critique) recomputes
        # a different hash and every reuse fails as a fingerprint mismatch. Compute the
        # hashes from the critique-free static payload, then attach critique as a sibling.
        fingerprint = _context_session_fingerprint(static_payload)
        static_context_hash = _sha256_payload(static_payload)
        session = {
            **static_payload,
            "fingerprint": fingerprint,
            "runtime_preparation_fingerprint": fingerprint,
            "static_context_hash": static_context_hash,
            "created_at": utc_now(),
            "active_skill_runtime_trace": prepared_runtime.get("active_skill_runtime_trace"),
        }
        if critique_payload:
            session["critique"] = critique_payload
        return session


def _maybe_microcompact(context_bundle: Any, *, max_tokens: int) -> Any:
    """Clear stale tool results once context crosses the microcompact threshold.

    Keeps the most recent compactable tool results verbatim; older ones get the
    neutral cleared marker. No-op below the threshold or when nothing is cleared.
    """
    budget = build_model_context_budget(max_tokens=max_tokens)
    if estimate_messages_tokens(context_bundle.messages) <= int(budget.microcompact_threshold_tokens):
        return context_bundle
    messages, cleared = microcompact_messages(context_bundle.messages)
    if not cleared:
        return context_bundle
    compact_messages, _ = microcompact_messages(context_bundle.compact_messages)
    return replace(context_bundle, messages=messages, compact_messages=compact_messages)


class ContextProjector:
    def render(
        self,
        *,
        user_id: int,
        conversation_id: str,
        run_id: str,
        render_step_id: str | None = None,
        turn: int = 0,
        attempt: int = 1,
        context_session: dict[str, Any],
        conversation: dict[str, Any] | None = None,
        previous_checkpoint: dict[str, Any] | None = None,
        current_user_message: dict[str, Any] | None = None,
        include_runtime_time: bool | None = None,
        transient_messages: list[dict[str, Any]] | None = None,
        llm_compact_adapter: Any | None = None,
    ) -> dict[str, Any]:
        normalized_render_step_id = str(render_step_id or "render-context").strip() or "render-context"
        normalized_turn = int(turn or 0)
        normalized_attempt = int(attempt or 1)
        ledger_turn_key = (
            f"run:{run_id}:render:{normalized_render_step_id}:"
            f"turn:{normalized_turn}:attempt:{normalized_attempt}"
        )
        language = str(context_session.get("language") or "zh")
        frozen_system = str(context_session.get("system_prompt") or "")
        tools = list(context_session.get("tool_schemas") or [])
        model = str(context_session.get("model") or "")
        provider_code = str(context_session.get("multimodal_provider") or "").strip() or None
        budget_details = _model_message_budget_details(
            system=frozen_system,
            model=model,
            provider_code=provider_code,
            tool_schemas=tools,
        )
        message_token_budget = int(budget_details["message_token_budget"])
        context_messages, agent_prompt_context = _context_ledger_messages(
            run_id=run_id,
            context_session=context_session,
            conversation=conversation,
            ledger_turn_key=ledger_turn_key,
            render_step_id=normalized_render_step_id,
            turn=normalized_turn,
        )
        current_user_messages = [current_user_message] if isinstance(current_user_message, dict) else []
        should_include_runtime_time = (
            bool(current_user_messages)
            if include_runtime_time is None
            else bool(include_runtime_time)
        )
        runtime_time_message = (
            _runtime_time_ledger_message(
                ledger_turn_key=ledger_turn_key,
                render_step_id=normalized_render_step_id,
                turn=normalized_turn,
                language=language,
            )
            if should_include_runtime_time
            else None
        )
        turn_append_message = _turn_append_ledger_message(
            ledger_turn_key=ledger_turn_key,
            render_step_id=normalized_render_step_id,
            turn=normalized_turn,
            context_session=context_session,
        )
        append_each_turn_messages = [
            message for message in [runtime_time_message, turn_append_message] if isinstance(message, dict)
        ]
        user_intent_message = _user_intent_ledger_message(
            current_user_message=current_user_message,
            run_id=run_id,
            ledger_turn_key=ledger_turn_key,
            render_step_id=normalized_render_step_id,
            turn=normalized_turn,
        )
        ledger_transient_messages = [
            *context_messages,
            *append_each_turn_messages,
            *current_user_messages,
            *list(transient_messages or []),
        ]

        context_bundle = build_model_context(user_id, conversation_id, extra_messages=ledger_transient_messages)
        # Tier 1: cheap lazy microcompact (clear stale tool results, keep recent
        # raw) under token pressure, before resorting to the expensive LLM summary.
        context_bundle = _maybe_microcompact(context_bundle, max_tokens=message_token_budget)
        compact_result = compact_if_needed(
            user_id,
            conversation_id,
            context_bundle,
            max_tokens=message_token_budget,
            llm_compact_adapter=llm_compact_adapter,
            model=model,
            run_id=run_id,
            runtime_contract=(
                dict(context_session.get("runtime_contract"))
                if isinstance(context_session.get("runtime_contract"), dict)
                else None
            ),
            workspace_runtime_session=(
                dict(context_session.get("workspace_runtime_session"))
                if isinstance(context_session.get("workspace_runtime_session"), dict)
                else None
            ),
        )
        if compact_result is not None:
            context_bundle = build_model_context(user_id, conversation_id, extra_messages=ledger_transient_messages)
            context_bundle = _maybe_microcompact(context_bundle, max_tokens=message_token_budget)
            # Compaction succeeded, but the rebuilt window can still exceed the blocking
            # limit when restore_messages (runtime_contract / workspace_runtime_session)
            # are themselves large. Re-check here and fail cleanly instead of shipping an
            # over-budget prompt to the provider (which would only surface as a late
            # "prompt too long" provider error).
            recheck_budget = build_model_context_budget(max_tokens=message_token_budget)
            recheck_state = calculate_token_state(
                estimate_messages_tokens(context_bundle.messages),
                recheck_budget,
            )
            if recheck_state.is_at_blocking_limit:
                raise ModelContextLimitExceeded(
                    "Context still exceeds the blocking limit after compaction; "
                    "the restored context is too large for the model window.",
                    token_usage=int(recheck_state.token_usage),
                    blocking_limit_tokens=int(recheck_budget.blocking_limit_tokens),
                    auto_compact_enabled=bool(recheck_budget.auto_compact_enabled),
                )
        messages = list(context_bundle.messages)
        checkpoint_summary_message = deepcopy(getattr(context_bundle.boundary, "summary_message", None))
        checkpoint_restore_messages = deepcopy(getattr(context_bundle.boundary, "restore_messages", []))
        # Serialize the context window once; reuse for both the token estimate and the
        # digest instead of canonicalizing the same messages twice per turn.
        canonical_messages = _canonical_json(messages)
        checkpoint = {
            "version": RENDER_CONTEXT_CHECKPOINT_VERSION,
            "message_seq_end": int(context_bundle.message_row_id_end or 0),
            "event_seq_end": int(context_bundle.event_sequence_end or 0),
            "summary_message": checkpoint_summary_message,
            "restore_messages": checkpoint_restore_messages,
            "token_state": {
                "estimated_message_tokens": estimate_tokens(canonical_messages),
                "message_count": len(messages),
            },
            "dynamic_context_digest": hashlib.sha256(canonical_messages.encode("utf-8")).hexdigest(),
            "history_source": context_bundle.source,
            "previous_message_seq_end": int((previous_checkpoint or {}).get("message_seq_end") or 0),
            "previous_event_seq_end": int((previous_checkpoint or {}).get("event_seq_end") or 0),
        }
        turn_context = {
            "system": frozen_system,
            "messages": messages,
            "tools": tools,
            "model": model,
            "language": language,
            "prompt_cache_key": f"agent:{conversation_id}",
        }
        diagnostics = {
            "render_step_id": normalized_render_step_id,
            "turn": normalized_turn,
            "ledger_turn_key_hash": _prompt_debug_optional_hash(ledger_turn_key),
            "message_count": len(messages),
            "tool_schema_count": len(tools),
            "history_source": context_bundle.source,
            "static_context_hash": context_session.get("static_context_hash"),
            "agent_context_message_count": len(context_messages) + len(append_each_turn_messages),
            "runtime_time_included": should_include_runtime_time,
            **budget_details,
        }
        debug_trace_file = None
        try:
            debug_trace_file = _persist_prompt_cache_debug_trace(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=run_id,
                render_step_id=normalized_render_step_id,
                turn=normalized_turn,
                ledger_turn_key=ledger_turn_key,
                turn_context=turn_context,
                checkpoint=checkpoint,
                diagnostics=diagnostics,
            )
        except Exception:
            # Prompt cache diagnostics are strictly best-effort; a debug write
            # must never block the model turn itself.
            pass
        if debug_trace_file:
            turn_context["prompt_cache_debug_trace_file"] = debug_trace_file
        return {
            "turn_context": turn_context,
            "persist_messages": [
                *context_messages,
                *append_each_turn_messages,
                *([user_intent_message] if isinstance(user_intent_message, dict) else []),
            ],
            "runtime_patch": {"agent_prompt_context_v2": agent_prompt_context},
            "checkpoint": checkpoint,
            "diagnostics": diagnostics,
        }
