"""Realtime persistence for HomeHarness preflight stages."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.agent_harness.runtime.execution_support.plan_gate_controller import PlanGateController
from app.services.agent_harness.workspace.conversation.conversation_service import (
    get_conversation_dir,
    get_conversation,
    update_conversation,
)
from app.services.agent_harness.runtime.eventing.persistence import append_trace
from app.services.agent_harness.runtime.state.store_core import read_json, utc_now, write_json
from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

PLAN_FIRST_ARTIFACT_MODES = {"web", "document", "spreadsheet", "slides"}


def _stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()[:16]


def build_preflight_billing_key(kind: str, conversation_id: str, *parts: Any) -> str:
    suffix = ":".join(stable_hash(part) if isinstance(part, (dict, list)) else str(part) for part in parts)
    return f"{kind}:{conversation_id}:{suffix}" if suffix else f"{kind}:{conversation_id}"


def _phase_diagnostic_payload(
    conversation: dict[str, Any] | None,
    *,
    source: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    conversation = conversation or {}
    plan_state = conversation.get("plan_state")
    plan_state_payload: dict[str, Any] = {
        "plan_state_type": "none" if plan_state is None else type(plan_state).__name__,
        "plan_state_truthy": bool(plan_state),
        "has_valid_plan_state": isinstance(plan_state, dict),
    }
    if isinstance(plan_state, dict):
        plan_state_payload["plan_state_status"] = str(plan_state.get("status") or "")
        plan_state_payload["plan_state_keys"] = sorted(str(key) for key in plan_state.keys())

    return {
        "source": source,
        "conversation_phase": str(conversation.get("phase") or ""),
        "updated_phase": str(updates.get("phase") or ""),
        "artifact_mode": str(conversation.get("artifact_mode") or updates.get("artifact_mode") or ""),
        "skill_id": str(conversation.get("skill_id") or updates.get("skill_id") or ""),
        "resolved_skill_id": str(conversation.get("resolved_skill_id") or updates.get("resolved_skill_id") or ""),
        "skill_selection_mode": str(conversation.get("skill_selection_mode") or updates.get("skill_selection_mode") or ""),
        "skill_resolution_source": str(conversation.get("skill_resolution_source") or updates.get("skill_resolution_source") or ""),
        "runtime_status": str(conversation.get("runtime_status") or ""),
        "run_state": str(conversation.get("run_state") or ""),
        "turn_status": str(conversation.get("turn_status") or ""),
        "requires_initial_plan": PlanGateController.requires_initial_plan({**conversation, **updates}),
        **plan_state_payload,
    }


def _ledger_path(user_id: int, conversation_id: str):
    return get_conversation_dir(user_id, conversation_id) / ".meta" / "preflight_billing_ledger.json"


def _read_ledger(user_id: int, conversation_id: str) -> dict[str, Any]:
    payload = read_json(_ledger_path(user_id, conversation_id), {"entries": {}})
    if not isinstance(payload, dict):
        return {"entries": {}}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        payload["entries"] = {}
    return payload


def has_preflight_billing_key(user_id: int, conversation_id: str, key: str) -> bool:
    if not key:
        return False
    return str(key) in (_read_ledger(user_id, conversation_id).get("entries") or {})


def mark_preflight_billing_key(
    user_id: int,
    conversation_id: str,
    key: str,
    *,
    detail: dict[str, Any] | None = None,
) -> None:
    if not key:
        return
    ledger = _read_ledger(user_id, conversation_id)
    entries = dict(ledger.get("entries") or {})
    entries.setdefault(
        str(key),
        {
            "key": str(key),
            "detail": detail or {},
            "created_at": utc_now(),
        },
    )
    ledger["entries"] = entries
    ledger["updated_at"] = utc_now()
    write_json(_ledger_path(user_id, conversation_id), ledger)


async def record_preflight_model_billing_once(
    engine: Any,
    *,
    conversation: dict[str, Any],
    ctx: Any,
    billing_key: str,
    model_name: str | None,
    usage: Any,
    elapsed_ms: int,
    kind: str,
    detail: dict[str, Any] | None = None,
) -> bool:
    from app.services.agent_harness.runtime.execution_support.billing_controller import record_preflight_model_billing

    user_id = int(ctx.user_id)
    conversation_id = str(ctx.conversation_id)
    if has_preflight_billing_key(user_id, conversation_id, billing_key):
        return False
    recorded = await record_preflight_model_billing(
        engine,
        conversation=conversation,
        ctx=ctx,
        model_name=model_name,
        usage=usage,
        elapsed_ms=elapsed_ms,
        kind=kind,
    )
    if not recorded:
        return False
    mark_preflight_billing_key(
        user_id,
        conversation_id,
        billing_key,
        detail={
            **(detail or {}),
            "kind": kind,
            "model_name": model_name,
            "elapsed_ms": elapsed_ms,
        },
    )
    return True


def _rederive_preflight_phase(
    user_id: int,
    conversation_id: str,
    *,
    updates: dict[str, Any],
) -> dict[str, Any]:
    current = get_conversation(user_id, conversation_id) or {"id": conversation_id}
    merged = {
        **current,
        **updates,
    }
    runtime_profile = str(merged.get("runtime_profile") or "home").strip().lower()
    artifact_mode = str(merged.get("artifact_mode") or "").strip().lower()
    has_plan = isinstance(merged.get("plan_state"), dict) or (
        isinstance(merged.get("outline_runtime"), dict)
        and isinstance((merged.get("outline_runtime") or {}).get("current_outline"), dict)
    )
    if (
        runtime_profile != "canvas"
        and artifact_mode in PLAN_FIRST_ARTIFACT_MODES
        and not has_plan
        and not isinstance(merged.get("turn_route"), dict)
    ):
        return {
            **updates,
            "phase": "planning",
        }
    return {
        **updates,
        "phase": PlanGateController.initial_phase(merged),
    }


def persist_skill_resolution(
    *,
    user_id: int,
    conversation_id: str,
    previous_skill_id: str | None,
    next_skill_id: str | None,
    artifact_mode: str | None = None,
    model_preferences: dict[str, Any] | None = None,
    reason: str | None = None,
    confidence: float | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    normalized_skill_id = str(next_skill_id or "").strip() or None
    updates: dict[str, Any] = {
        "skill_id": normalized_skill_id,
        "resolved_skill_id": normalized_skill_id,
        "skill_selection_mode": "auto",
        "skill_resolution_source": "auto",
        "last_skill_decision_reason": reason,
        "last_skill_decision_confidence": confidence,
        "last_activity_source": "preflight_skill_resolution",
        "last_activity_at": utc_now(),
    }
    if artifact_mode:
        updates["artifact_mode"] = artifact_mode
    if model_preferences is not None:
        updates["model_preferences"] = model_preferences
    updates = _rederive_preflight_phase(
        user_id,
        conversation_id,
        updates=updates,
    )
    conversation = update_conversation(user_id, conversation_id, **updates)
    try:
        append_trace(
            user_id,
            conversation_id,
            trace_type="preflight_skill_resolution_phase_diagnostic",
            phase=str(conversation.get("phase")) if isinstance(conversation, dict) and conversation.get("phase") else None,
            run_status=str(conversation.get("runtime_status")) if isinstance(conversation, dict) and conversation.get("runtime_status") else None,
            summary="preflight skill resolution phase diagnostic",
            payload=_phase_diagnostic_payload(
                conversation,
                source="preflight.persist_skill_resolution",
                updates=updates,
            ),
        )
    except Exception:
        pass

    if not normalized_skill_id:
        return conversation

    return conversation


def _interaction_payload(interaction: dict[str, Any]) -> dict[str, Any]:
    request_id = str(interaction.get("request_id") or interaction.get("requestId") or "").strip()
    tool_call_id = interaction.get("tool_call_id") or interaction.get("toolCallId") or request_id
    return {
        **interaction,
        "request_id": request_id,
        "requestId": request_id,
        "tool_call_id": tool_call_id,
        "toolCallId": tool_call_id,
        "answers": interaction.get("answers"),
        "status": interaction.get("status") or "pending",
    }


def persist_interaction_request(
    *,
    user_id: int,
    conversation_id: str,
    interaction: dict[str, Any],
    run_state: str,
) -> dict[str, Any] | None:
    payload = _interaction_payload(interaction)
    return patch_runtime_state(
        user_id,
        conversation_id,
        {
            "runtime_status": "waiting_input",
            "turn_status": "waiting_input",
            "run_state": run_state,
            "user_interaction": payload,
            "last_activity_source": "preflight_interaction_request",
        },
    )

def persist_interaction_submission(
    *,
    user_id: int,
    conversation_id: str,
    request_id: str,
    kind: str | None = None,
    answer: Any,
    display_label: str | None = None,
    approved: bool | None = None,
    answers: dict[str, Any] | None = None,
    design_system_id: str | None = None,
    next_run_state: str = "running",
) -> dict[str, Any] | None:
    updates: dict[str, Any] = {
        "runtime_status": "running",
        "turn_status": "running",
        "run_state": next_run_state,
        "user_interaction": None,
        "last_activity_source": "preflight_interaction_submission",
    }
    if design_system_id is not None:
        updates["design_system_id"] = design_system_id
    return patch_runtime_state(user_id, conversation_id, updates)


__all__ = [
    "build_preflight_billing_key",
    "has_preflight_billing_key",
    "mark_preflight_billing_key",
    "persist_interaction_request",
    "persist_interaction_submission",
    "persist_skill_resolution",
    "record_preflight_model_billing_once",
    "stable_hash",
]

