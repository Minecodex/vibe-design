from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.skill_protocols.base import prepared_workspace_from_payload
from app.services.agent_harness.capabilities.skills.active_context import persist_selected_skill_active_context
from app.services.agent_harness.core.context import HarnessContext, create_context
from app.services.agent_harness.runtime.active_skill_runtime import ActiveSkillRuntime
from app.services.agent_harness.workspace.skill_staging_v2 import stage_active_skill_v2

_PREPARED_ROOT_SAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_ACTIVE_SKILL_RUNTIME = ActiveSkillRuntime()


def create_workflow_context(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    conversation: dict[str, Any],
    language: str,
) -> HarnessContext:
    conversation = dict(conversation or {})
    from app.services.agent_harness.workflow.repositories import get_run_parent_usage_log_id, set_run_parent_usage_log_id

    parent_usage_log_id = get_run_parent_usage_log_id(run_id)
    if parent_usage_log_id is not None:
        conversation["parent_usage_log_id"] = parent_usage_log_id
    elif conversation.get("parent_usage_log_id") is not None:
        try:
            parent_usage_log_id = int(conversation.get("parent_usage_log_id") or 0)
        except (TypeError, ValueError):
            parent_usage_log_id = None
        if parent_usage_log_id:
            set_run_parent_usage_log_id(run_id, parent_usage_log_id)
            conversation["parent_usage_log_id"] = parent_usage_log_id
    ctx = create_context(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        language=language,
        conversation=conversation,
    )
    hydrate_context_from_conversation(ctx=ctx, conversation=conversation)
    return ctx


def hydrate_context_from_conversation(*, ctx: HarnessContext, conversation: dict[str, Any]) -> None:
    runtime_state = _runtime_state_from_conversation(conversation)
    prepared_workspace = runtime_state.get("prepared_workspace") if isinstance(runtime_state, dict) else None
    workspace_session = runtime_state.get("workspace_runtime_session") if isinstance(runtime_state, dict) else None
    if isinstance(prepared_workspace, dict):
        ctx.prepared_workspace = prepared_workspace_from_payload(prepared_workspace)
        ctx.artifact_work_root = str(prepared_workspace.get("artifact_work_root") or "").strip() or None
        ctx.prepared_entry_file = str(prepared_workspace.get("entry_file") or "").strip() or None
    if isinstance(workspace_session, dict):
        ctx.workspace_runtime_session = dict(workspace_session)


def prepare_active_skill_runtime_context(
    *,
    ctx: HarnessContext,
    skill: Any,
    persist_context: bool = True,
) -> dict[str, Any]:
    source_skill_dir = getattr(skill, "skill_dir", None)
    skill_id = str(getattr(skill, "id", "") or "").strip()
    if not source_skill_dir or not skill_id:
        raise ValueError("Active skill must provide both id and skill_dir")

    source_root = Path(source_skill_dir).resolve()
    result = stage_active_skill_v2(ctx, source_root)
    if not result.get("ok"):
        raise RuntimeError(str(result.get("error") or result.get("reason") or "failed to stage active skill"))

    runtime_root = Path(ctx.skill_dir).resolve()
    ctx.skill_runtime_dir = runtime_root
    ctx.active_skill_dir = runtime_root
    active_context: dict[str, Any] | None = None
    if persist_context:
        active_context = persist_selected_skill_active_context(
            int(ctx.user_id),
            str(ctx.conversation_id),
            skill,
            language=str(ctx.language or "zh"),
            runtime_skill_dir=runtime_root,
        )
    return {
        "runtime_root": str(runtime_root),
        "active_skill_context": active_context,
        "staged_skill": {
            "ok": True,
            "source_path": str(result.get("source") or ""),
            "target_path": str(result.get("target") or ""),
            "linked_dependencies": list(result.get("linked_templates") or []),
        },
    }


def prepare_execution_runtime_context(
    *,
    ctx: HarnessContext,
    conversation: dict[str, Any],
    skill: Any,
    latest_user_request: str = "",
) -> dict[str, Any]:
    active_runtime = _ACTIVE_SKILL_RUNTIME.prepare(
        ctx=ctx,
        skill=skill,
        conversation=conversation,
        latest_user_request=latest_user_request,
    )
    prepared_workspace = dict(active_runtime.prepared_workspace or {})
    if prepared_workspace:
        ctx.prepared_workspace = prepared_workspace_from_payload(prepared_workspace)
        ctx.artifact_work_root = str(prepared_workspace.get("artifact_work_root") or "").strip() or None
        ctx.prepared_entry_file = str(prepared_workspace.get("entry_file") or "").strip() or None

    runtime_contract = _runtime_contract_from_conversation(conversation)
    runtime_contract.update(active_runtime.runtime_contract_patch)
    if prepared_workspace:
        runtime_contract["protocol_family"] = prepared_workspace.get("family") or prepared_workspace.get("strategy")

    workspace_session = _workspace_runtime_session(
        conversation=conversation,
        skill=skill,
        prepared_workspace=prepared_workspace,
    )
    ctx.workspace_runtime_session = workspace_session
    return {
        "prepared_workspace": prepared_workspace or None,
        "workspace_runtime_session": workspace_session,
        "runtime_contract": runtime_contract,
        "active_skill_runtime_trace": active_runtime.trace,
        "active_skill_events": list(active_runtime.events or []),
    }


def _runtime_state_from_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    runtime_state = conversation.get("runtime_state")
    if isinstance(runtime_state, dict):
        return dict(runtime_state)
    return {}


def _runtime_contract_from_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    runtime_state = _runtime_state_from_conversation(conversation)
    runtime_snapshot = (
        conversation.get("runtime_snapshot")
        if isinstance(conversation.get("runtime_snapshot"), dict)
        else conversation.get("runtime_snapshot_json")
        if isinstance(conversation.get("runtime_snapshot_json"), dict)
        else {}
    )
    for source in (runtime_state, runtime_snapshot, conversation):
        if not isinstance(source, dict):
            continue
        runtime_contract = source.get("runtime_contract")
        if isinstance(runtime_contract, dict):
            return dict(runtime_contract)
    return {}


def _workspace_runtime_session(
    *,
    conversation: dict[str, Any],
    skill: Any,
    prepared_workspace: dict[str, Any],
) -> dict[str, Any]:
    runtime_state = _runtime_state_from_conversation(conversation)
    existing = runtime_state.get("workspace_runtime_session")
    session = dict(existing) if isinstance(existing, dict) else {}
    artifact_work_root = str(prepared_workspace.get("artifact_work_root") or "").replace("\\", "/").strip("/")
    entry_file = str(prepared_workspace.get("entry_file") or "").replace("\\", "/").strip("/")
    session.update(
        {
            "selected_skill": str(getattr(skill, "id", "") or "") or session.get("selected_skill"),
            "artifact_work_root": artifact_work_root or session.get("artifact_work_root"),
            "agent_cwd": f"project/{artifact_work_root}" if artifact_work_root else session.get("agent_cwd"),
            "active_entry": f"{artifact_work_root}/{entry_file}".strip("/") if artifact_work_root and entry_file else session.get("active_entry"),
        }
    )
    return {key: value for key, value in session.items() if value is not None}


def default_active_skill_work_root(skill: Any) -> str | None:
    skill_id = str(getattr(skill, "id", "") or "").strip()
    if not skill_id:
        return None
    normalized = _PREPARED_ROOT_SAFE_CHARS.sub("-", skill_id).strip("-")
    return f"{normalized or 'skill'}-prepared"
