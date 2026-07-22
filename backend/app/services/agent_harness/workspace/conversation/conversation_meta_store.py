"""HomeHarness conversation metadata storage and lifecycle derivation."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.services.agent_harness.core.constants import RUN_INACTIVITY_TIMEOUT_SECONDS
from app.services.agent_harness.runtime.presentation_v2.protocol import PROTOCOL_VERSION
from .conversation_store_support import (
    generate_conversation_id,
    get_conversation_dir,
    normalize_runtime_scope,
    read_json,
    workspace_root,
    write_json,
)

logger = logging.getLogger(__name__)

DEFAULT_RUNTIME_STATUS = "idle"
DEFAULT_RUN_STATE = "idle"
RUNTIME_META_FIELDS = frozenset({
    "protocol_version",
    "status",
    "phase",
    "user_interaction",
    "planning_draft",
    "plan_state",
    "outline_runtime",
    "recovery_summary",
    "recovery_history",
    "parent_usage_log_id",
    "runtime_status",
    "display_status",
    "run_state",
    "activity",
    "turn_route",
    "stall_reason",
    "last_tool",
    "last_error_summary",
    "failure",
    "last_activity_at",
    "last_activity_source",
    "turn_status",
    "run_id",
    "run_output_anchor",
    "started_at",
    "finished_at",
})


def _non_empty_string(value: Any, default: str) -> str:
    text = str(value or "").strip()
    return text or default


def _parse_iso8601(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _normalize_design_system_id(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _sync_design_system_fields(meta: dict[str, Any]) -> None:
    meta["design_system_id"] = _normalize_design_system_id(meta.get("design_system_id"))


def _build_display_status(meta: dict[str, Any]) -> str:
    status = str(meta.get("status") or "").lower()
    if status == "deleted":
        return "已删除"
    runtime_status = str(meta.get("runtime_status") or DEFAULT_RUNTIME_STATUS).lower()
    run_state = str(meta.get("run_state") or DEFAULT_RUN_STATE).lower()
    phase = str(meta.get("phase") or "").lower()
    activity = str(meta.get("activity") or "").lower()
    last_activity_source = str(meta.get("last_activity_source") or "").lower()

    if runtime_status == "completed" or run_state == "completed":
        return "已完成"
    if runtime_status == "waiting_input" or run_state == "waiting_input":
        return "等待输入"
    if runtime_status == "blocked" or run_state in {"blocked", "stalled"}:
        return "阻塞"
    if runtime_status == "cancelled" or run_state in {"cancelled", "canceled"}:
        return "已取消"
    if runtime_status == "failed" or run_state == "failed":
        return "异常" if last_activity_source == "engine_exception" else "失败"
    if runtime_status == "running":
        if activity == "planning_outline":
            return "规划中"
        if activity == "searching" or str(meta.get("last_tool") or "").lower() in {"web_search", "fetch_webpage"}:
            return "搜索中"
        if activity == "analyzing":
            return "分析中"
        return "进行中"
    if activity == "planning_outline":
        return "规划中"
    return "空闲"


def _sync_plan_state_with_runtime(meta: dict[str, Any]) -> dict[str, Any] | None:
    plan_state = meta.get("plan_state")
    if not isinstance(plan_state, dict):
        return None

    runtime_status = str(meta.get("runtime_status") or DEFAULT_RUNTIME_STATUS).lower()
    run_state = str(meta.get("run_state") or DEFAULT_RUN_STATE).lower()
    plan_status = str(plan_state.get("status") or "").lower()

    if runtime_status == "failed" and plan_status not in {"", "completed", "pending_approval", "failed"}:
        next_plan_state = deepcopy(plan_state)
        next_plan_state["status"] = "failed"
        meta["plan_state"] = next_plan_state
        return next_plan_state

    if (
        runtime_status == "running"
        and run_state in {"planning", "executing", "waiting_model", "waiting_tool", "recovering"}
        and plan_status == "failed"
    ):
        next_plan_state = deepcopy(plan_state)
        next_plan_state["status"] = "in_progress"
        meta["plan_state"] = next_plan_state
        return next_plan_state

    return plan_state


def _derive_lifecycle_fields(meta: dict[str, Any]) -> None:
    runtime_status = str(meta.get("runtime_status") or DEFAULT_RUNTIME_STATUS).lower()
    run_state = str(meta.get("run_state") or DEFAULT_RUN_STATE).lower()
    current_status = str(meta.get("status") or "").lower()
    current_phase = str(meta.get("phase") or "").lower()

    if current_status == "deleted":
        return

    if runtime_status == "completed":
        meta["status"] = "completed"
        meta["phase"] = "completed"
        if run_state in {"", "idle", "executing", "waiting_model", "waiting_tool", "recovering"}:
            meta["run_state"] = "completed"
        return

    if current_status == "completed" and runtime_status not in {"completed", "idle"}:
        meta["status"] = "active"

    if runtime_status in {"running", "waiting_input"}:
        meta["status"] = "active"
        if current_phase == "completed":
            meta["phase"] = "executing"
        return

    if runtime_status in {"failed", "blocked", "cancelled"}:
        meta["status"] = "active"
        if current_phase == "completed":
            meta["phase"] = "executing"


def normalize_runtime_meta(meta: dict[str, Any]) -> dict[str, Any]:
    from app.services.agent_harness.runtime.execution_support.interaction_policy import interaction_profile

    meta["id"] = _non_empty_string(meta.get("id") or meta.get("conversation_id"), "")
    meta["title"] = str(meta.get("title") or "")
    runtime_profile, project_id = normalize_runtime_scope(
        meta.get("runtime_profile"),
        meta.get("project_id"),
    )
    meta["runtime_profile"] = runtime_profile
    meta["project_id"] = project_id
    meta["protocol_version"] = PROTOCOL_VERSION
    meta["interaction_profile"] = interaction_profile(meta)
    _sync_design_system_fields(meta)
    phase = _non_empty_string(
        meta.get("phase"),
        "planning" if meta.get("skill_id") else "executing",
    )
    if phase not in {
        "planning",
        "planning_ready",
        "awaiting_plan_review",
        "revising_plan",
        "executing",
        "completed",
        "failed",
        "blocked",
        "cancelled",
    }:
        phase = "executing"
    meta["phase"] = phase
    artifact_mode = _non_empty_string(meta.get("artifact_mode"), "web").lower()
    if artifact_mode not in {"web", "document", "spreadsheet", "slides", "image", "video"}:
        artifact_mode = "web"
    meta["artifact_mode"] = artifact_mode
    skill_selection_mode = str(meta.get("skill_selection_mode") or "").strip().lower()
    if skill_selection_mode not in {"auto", "manual"}:
        skill_selection_mode = "manual" if meta.get("skill_id") else "auto"
    meta["skill_selection_mode"] = skill_selection_mode
    meta["last_skill_decision_reason"] = str(meta.get("last_skill_decision_reason") or "").strip() or None
    try:
        meta["last_skill_decision_confidence"] = (
            float(meta.get("last_skill_decision_confidence"))
            if meta.get("last_skill_decision_confidence") is not None
            else None
        )
    except (TypeError, ValueError):
        meta["last_skill_decision_confidence"] = None
    meta["mode"] = _non_empty_string(meta.get("mode"), "fast")
    meta["status"] = _non_empty_string(meta.get("status"), "active")
    meta["runtime_status"] = _non_empty_string(meta.get("runtime_status"), DEFAULT_RUNTIME_STATUS)
    meta["run_state"] = _non_empty_string(meta.get("run_state"), DEFAULT_RUN_STATE)
    meta["activity"] = str(meta.get("activity") or "").strip() or None
    if not isinstance(meta.get("turn_route"), dict):
        meta["turn_route"] = None
    meta["created_at"] = str(meta.get("created_at") or "")
    meta["updated_at"] = str(meta.get("updated_at") or meta.get("created_at") or "")
    if not isinstance(meta.get("web_search_enabled"), bool):
        meta["web_search_enabled"] = True

    _derive_lifecycle_fields(meta)
    runtime_status = str(meta.get("runtime_status") or DEFAULT_RUNTIME_STATUS).lower()
    run_state = str(meta.get("run_state") or DEFAULT_RUN_STATE).lower()
    _sync_plan_state_with_runtime(meta)

    last_activity_at = _parse_iso8601(meta.get("last_activity_at"))
    if (
        runtime_status == "running"
        and run_state == "waiting_model"
        and last_activity_at is not None
        and (datetime.now(timezone.utc) - last_activity_at).total_seconds()
        >= RUN_INACTIVITY_TIMEOUT_SECONDS
    ):
        meta["runtime_status"] = "blocked"
        meta["run_state"] = "stalled"
        meta["stall_reason"] = "llm_call_timeout_or_hang"
        meta["last_error_summary"] = meta.get("last_error_summary") or "waiting_model timeout after tool activity"
        _derive_lifecycle_fields(meta)

    meta["display_status"] = _build_display_status(meta)
    return meta


def _runtime_state_snapshot(meta: dict[str, Any]) -> dict[str, Any]:
    normalized_meta = normalize_runtime_meta(dict(meta))
    snapshot = {
        "conversation_id": str(normalized_meta.get("id") or ""),
        "updated_at": normalized_meta.get("updated_at"),
    }
    for key in RUNTIME_META_FIELDS:
        snapshot[key] = deepcopy(normalized_meta.get(key))
    return snapshot


def get_runtime_state(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    from app.services.agent_harness.workspace.session_v2.db_store import read_runtime_state_payload

    payload = read_runtime_state_payload(user_id, conversation_id)
    if payload is None:
        return None
    return _runtime_state_snapshot(payload)


def iter_running_conversation_refs() -> list[tuple[int, str]]:
    from app.services.agent_harness.workspace.session_v2.db_store import (
        iter_running_conversation_refs as iter_db_running_conversation_refs,
    )

    return iter_db_running_conversation_refs()


def create_conversation(
    user_id: int,
    *,
    title: str = "新会话",
    runtime_profile: str = "home",
    project_id: int | None = None,
    skill_id: str | None = None,
    artifact_mode: str = "web",
    design_system_id: str | None = None,
    resolved_skill_id: str | None = None,
    skill_resolution_source: str | None = None,
    skill_selection_mode: str = "auto",
    last_skill_decision_reason: str | None = None,
    last_skill_decision_confidence: float | None = None,
    mode: str = "fast",
    web_search_enabled: bool = True,
    model_preferences: dict | None = None,
) -> dict:
    conv_id = generate_conversation_id()
    now = datetime.now(timezone.utc).isoformat()
    normalized_runtime_profile, normalized_project_id = normalize_runtime_scope(
        runtime_profile,
        project_id,
        require_project_for_canvas=True,
    )
    inferred_artifact_mode = artifact_mode
    if skill_id and artifact_mode == "web":
        try:
            from app.services.agent_harness.capabilities.skills import get_skill

            skill = get_skill(skill_id)
            if skill and str(getattr(skill, "artifact_mode", "") or "").strip():
                inferred_artifact_mode = str(skill.artifact_mode)
        except Exception:
            inferred_artifact_mode = artifact_mode
    initial_phase = "executing"
    if normalized_runtime_profile != "canvas" and (
        skill_id or str(inferred_artifact_mode or "").strip().lower() in {"web", "document", "spreadsheet", "slides"}
    ):
        initial_phase = "planning"

    metadata = {
        "id": conv_id,
        "user_id": user_id,
        "title": title,
        "protocol_version": PROTOCOL_VERSION,
        "runtime_profile": normalized_runtime_profile,
        "project_id": normalized_project_id,
        "skill_id": skill_id,
        "resolved_skill_id": resolved_skill_id,
        "skill_resolution_source": skill_resolution_source,
        "skill_selection_mode": skill_selection_mode,
        "artifact_mode": inferred_artifact_mode,
        "design_system_id": design_system_id,
        "last_skill_decision_reason": last_skill_decision_reason,
        "last_skill_decision_confidence": last_skill_decision_confidence,
        "phase": initial_phase,
        "mode": mode,
        "web_search_enabled": web_search_enabled,
        "status": "active",
        "engine_version": "harness",
        "model_preferences": model_preferences,
        "user_interaction": None,
        "planning_draft": None,
        "plan_state": None,
        "outline_runtime": None,
        "recovery_summary": None,
        "parent_usage_log_id": None,
        "runtime_status": DEFAULT_RUNTIME_STATUS,
        "display_status": "空闲",
        "run_state": DEFAULT_RUN_STATE,
        "activity": None,
        "turn_route": None,
        "stall_reason": None,
        "last_tool": None,
        "last_error_summary": None,
        "failure": None,
        "last_activity_at": None,
        "last_activity_source": None,
        "turn_status": DEFAULT_RUNTIME_STATUS,
        "run_id": None,
        "started_at": None,
        "finished_at": None,
        "created_at": now,
        "updated_at": now,
    }
    metadata = normalize_runtime_meta(metadata)

    from app.services.agent_harness.workspace.session_v2.service import create_conversation_files

    metadata = create_conversation_files(user_id, metadata)
    conv_dir = get_conversation_dir(
        user_id,
        conv_id,
        runtime_profile=normalized_runtime_profile,
        project_id=normalized_project_id,
    )

    logger.info("Created harness conversation %s (workspace: %s)", conv_id, conv_dir)
    return metadata


def get_conversation(user_id: int, conversation_id: str) -> dict | None:
    from app.services.agent_harness.workspace.session_v2.service import get_conversation as get_v2_conversation

    v2_conversation = get_v2_conversation(user_id, conversation_id)
    if v2_conversation is not None:
        return normalize_runtime_meta(v2_conversation)
    return None


async def get_conversation_async(user_id: int, conversation_id: str) -> dict | None:
    from app.services.agent_harness.workspace.session_v2.service import get_conversation_async as get_v2_conversation_async

    v2_conversation = await get_v2_conversation_async(user_id, conversation_id)
    if v2_conversation is not None:
        return normalize_runtime_meta(v2_conversation)
    return None


def update_conversation(user_id: int, conversation_id: str, **updates: Any) -> dict | None:
    from app.services.agent_harness.workspace.session_v2.service import (
        get_conversation as get_v2_conversation,
        update_conversation as update_v2_conversation,
    )

    v2_conversation = get_v2_conversation(user_id, conversation_id)
    if v2_conversation is not None:
        merged = dict(v2_conversation)
        merged.update(updates)
        if "updated_at" not in updates:
            merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        return normalize_runtime_meta(update_v2_conversation(user_id, conversation_id, normalize_runtime_meta(merged)) or merged)
    return None


async def update_conversation_async(user_id: int, conversation_id: str, **updates: Any) -> dict | None:
    from app.services.agent_harness.workspace.session_v2.service import (
        get_conversation_async as get_v2_conversation_async,
        update_conversation_async as update_v2_conversation_async,
    )

    v2_conversation = await get_v2_conversation_async(user_id, conversation_id)
    if v2_conversation is not None:
        merged = dict(v2_conversation)
        merged.update(updates)
        if "updated_at" not in updates:
            merged["updated_at"] = datetime.now(timezone.utc).isoformat()
        return normalize_runtime_meta(
            await update_v2_conversation_async(user_id, conversation_id, normalize_runtime_meta(merged)) or merged
        )
    return None


def delete_conversation(user_id: int, conversation_id: str) -> bool:
    from app.services.agent_harness.workspace.session_v2.service import delete_conversation as delete_v2_conversation

    return delete_v2_conversation(user_id, conversation_id)


def list_conversations(
    user_id: int,
    *,
    runtime_profile: str = "home",
    project_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    from app.services.agent_harness.workspace.session_v2.service import list_conversations as list_v2_conversations

    normalized_runtime_profile, normalized_project_id = normalize_runtime_scope(
        runtime_profile,
        project_id,
        require_project_for_canvas=str(runtime_profile or "").strip().lower() == "canvas",
    )
    v2_items, v2_total = list_v2_conversations(
        user_id,
        runtime_profile=normalized_runtime_profile,
        project_id=normalized_project_id,
        page=page,
        page_size=page_size,
    )
    return [normalize_runtime_meta(dict(item)) for item in v2_items], v2_total

