from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.agent_harness.core.context import HarnessContext


def _resolve_design_system_id(conversation: dict[str, Any] | None) -> str | None:
    design_system_id = str((conversation or {}).get("design_system_id") or "").strip()
    if design_system_id:
        return design_system_id

    runtime_state = (conversation or {}).get("runtime_state")
    if isinstance(runtime_state, dict):
        runtime_contract = runtime_state.get("runtime_contract")
        if isinstance(runtime_contract, dict):
            design_system_id = str(runtime_contract.get("design_system_id") or "").strip()
            if design_system_id:
                return design_system_id

    return None


def create_context(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
    language: str = "zh",
    conversation: dict[str, Any] | None = None,
) -> HarnessContext:
    prefs = (conversation or {}).get("model_preferences") or {}
    runtime_profile = str((conversation or {}).get("runtime_profile") or "home").strip().lower() or "home"
    project_id = (conversation or {}).get("project_id")
    runtime_state = (
        (conversation or {}).get("runtime_state")
        if isinstance((conversation or {}).get("runtime_state"), dict)
        else (conversation or {}).get("runtime_snapshot")
    )
    run_output_anchor = (
        runtime_state.get("run_output_anchor")
        if isinstance(runtime_state, dict) and isinstance(runtime_state.get("run_output_anchor"), dict)
        else (conversation or {}).get("run_output_anchor")
        if isinstance((conversation or {}).get("run_output_anchor"), dict)
        else {}
    )
    return HarnessContext(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        language=language,
        runtime_profile=runtime_profile,
        project_id=int(project_id) if project_id is not None else None,
        skill_id=(conversation or {}).get("skill_id") or (conversation or {}).get("resolved_skill_id"),
        artifact_mode=str((conversation or {}).get("artifact_mode") or "web"),
        design_system_id=_resolve_design_system_id(conversation),
        model_preferences=dict(prefs),
        workspace_runtime_session=dict(runtime_state) if isinstance(runtime_state, dict) else None,
        image_model=prefs.get("image_model"),
        image_provider=prefs.get("image_provider"),
        video_model=prefs.get("video_model"),
        video_provider=prefs.get("video_provider"),
        multimodal_model=prefs.get("multimodal_model"),
        multimodal_provider=prefs.get("multimodal_provider") or "builtin",
        parent_usage_log_id=(conversation or {}).get("parent_usage_log_id"),
        run_output_anchor_message_id=run_output_anchor.get("anchor_message_id"),
        run_output_anchor_created_at=run_output_anchor.get("anchor_created_at"),
        run_output_anchor_source=run_output_anchor.get("anchor_source"),
    )


def resolve_workspace_path(ctx: HarnessContext, file_path: str, *, default_scope: str = "code") -> Path | None:
    return ctx.resolve_workspace_path(file_path, default_scope=default_scope)
