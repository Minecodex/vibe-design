from __future__ import annotations

from copy import deepcopy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.services.agent_harness.capabilities.skill_protocols.base import PreparedWorkspace
from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.capabilities.skills.active_manifest import (
    build_active_skill_manifest,
)
from app.services.agent_harness.capabilities.skills.router import (
    build_mode_contract,
    normalize_artifact_mode,
)
from app.services.agent_harness.core.utils.token_counter import estimate_tokens
from app.services.agent_harness.prompt_runtime import PromptMode, PromptRuntime, TurnSpec
from app.services.multimodal_service import get_multimodal_model_config, resolve_multimodal_provider

from .harness_prompt import build_system_prompt

DEFAULT_CONTEXT_TOKEN_BUDGET = 100_000
CONTEXT_SAFETY_MARGIN_TOKENS = 4_096
_MODE_CONTRACT_CACHE: dict[tuple[str, str | None], str] = {}
_PROMPT_RUNTIME = PromptRuntime()


@lru_cache(maxsize=64)
def _static_system_prompt(language: str, runtime_profile: str, artifact_mode: str) -> str:
    return build_system_prompt(language, runtime_profile=runtime_profile, artifact_mode=artifact_mode)


def clear_static_context_cache() -> None:
    _static_system_prompt.cache_clear()
    _MODE_CONTRACT_CACHE.clear()


def _cached_mode_contract(artifact_mode: str, skill) -> str:
    normalized_mode = normalize_artifact_mode(artifact_mode)
    skill_mode = str(getattr(skill, "mode", "") or "") or None
    key = (normalized_mode, skill_mode)
    cached = _MODE_CONTRACT_CACHE.get(key)
    if cached is not None:
        return cached
    value = build_mode_contract(normalized_mode, skill=skill)
    _MODE_CONTRACT_CACHE[key] = value
    return value


def _resolve_current_outline(conversation: dict[str, Any]) -> dict[str, Any] | None:
    outline_runtime = conversation.get("outline_runtime") if isinstance(conversation.get("outline_runtime"), dict) else {}
    runtime_outline = (
        outline_runtime.get("current_outline")
        if isinstance(outline_runtime.get("current_outline"), dict)
        else None
    )
    if isinstance(runtime_outline, dict):
        current_outline = deepcopy(runtime_outline)
        execution_state = outline_runtime.get("execution_state")
        if "execution_state" not in current_outline and isinstance(execution_state, dict):
            current_outline["execution_state"] = deepcopy(execution_state)
        projection_state = outline_runtime.get("projection_state")
        if "projection_state" not in current_outline and isinstance(projection_state, dict):
            current_outline["projection_state"] = deepcopy(projection_state)
        return current_outline

    plan_state = conversation.get("plan_state") if isinstance(conversation.get("plan_state"), dict) else {}
    outline_state = plan_state.get("outline_state") if isinstance(plan_state.get("outline_state"), dict) else None
    if not isinstance(outline_state, dict):
        return None
    current_outline = deepcopy(outline_state)
    execution_state = plan_state.get("execution_state")
    if isinstance(execution_state, dict):
        current_outline["execution_state"] = deepcopy(execution_state)
    projection_state = plan_state.get("projection_state")
    if isinstance(projection_state, dict):
        current_outline["projection_state"] = deepcopy(projection_state)
    return current_outline


def render_static_system_context(
    *,
    language: str,
    conversation: dict[str, Any],
    model_name: str | None,
    skill: Any | None,
    skill_prompt: str | None,
    artifact_mode: str | None,
    skill_id: str | None,
    skill_runtime_dir: Path | None,
    prepared_workspace: PreparedWorkspace | None,
    workspace_runtime_session: dict[str, Any] | None,
    runtime_contract: dict[str, Any] | None,
    tool_schemas: list[dict[str, Any]] | None,
) -> str:
    return render_main_turn_prompt_partitions(
        language=language,
        conversation=conversation,
        model_name=model_name,
        skill=skill,
        skill_prompt=skill_prompt,
        artifact_mode=artifact_mode,
        skill_id=skill_id,
        skill_runtime_dir=skill_runtime_dir,
        prepared_workspace=prepared_workspace,
        workspace_runtime_session=workspace_runtime_session,
        runtime_contract=runtime_contract,
        tool_schemas=tool_schemas,
    )["stable_system"]


def render_main_turn_prompt_partitions(
    *,
    language: str,
    conversation: dict[str, Any],
    model_name: str | None,
    skill: Any | None,
    skill_prompt: str | None,
    artifact_mode: str | None,
    skill_id: str | None,
    skill_runtime_dir: Path | None,
    prepared_workspace: PreparedWorkspace | None,
    workspace_runtime_session: dict[str, Any] | None,
    runtime_contract: dict[str, Any] | None,
    tool_schemas: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    spec = _main_turn_spec(
        language=language,
        conversation=conversation,
        model_name=model_name,
        skill=skill,
        skill_prompt=skill_prompt,
        artifact_mode=artifact_mode,
        skill_id=skill_id,
        skill_runtime_dir=skill_runtime_dir,
        prepared_workspace=prepared_workspace,
        workspace_runtime_session=workspace_runtime_session,
        runtime_contract=runtime_contract,
        tool_schemas=tool_schemas,
    )
    partitions = _PROMPT_RUNTIME.build_partitions(spec)
    return {
        "stable_system": partitions.stable_system_text,
        "context_snapshot_blocks": [
            {
                "id": block.id,
                "content": block.content,
                "metadata": dict(block.metadata or {}),
                "rule_family": block.rule_family,
            }
            for block in partitions.context_snapshot_blocks
            if str(block.content or "").strip()
        ],
        "turn_append_blocks": [
            {
                "id": block.id,
                "content": block.content,
                "metadata": dict(block.metadata or {}),
                "rule_family": block.rule_family,
            }
            for block in partitions.turn_append_blocks
            if str(block.content or "").strip()
        ],
        "trace": partitions.trace,
    }


def _main_turn_spec(
    *,
    language: str,
    conversation: dict[str, Any],
    model_name: str | None,
    skill: Any | None,
    skill_prompt: str | None,
    artifact_mode: str | None,
    skill_id: str | None,
    skill_runtime_dir: Path | None,
    prepared_workspace: PreparedWorkspace | None,
    workspace_runtime_session: dict[str, Any] | None,
    runtime_contract: dict[str, Any] | None,
    tool_schemas: list[dict[str, Any]] | None,
) -> TurnSpec:
    runtime_profile = str(conversation.get("runtime_profile") or "home").strip().lower() or "home"
    phase = str(conversation.get("phase") or "executing").strip().lower() or "executing"
    resolved_skill = skill or get_skill(skill_id or conversation.get("skill_id"))
    resolved_artifact_mode = normalize_artifact_mode(artifact_mode or conversation.get("artifact_mode"))
    active_skill_manifest = build_active_skill_manifest(
        language=language,
        skill=resolved_skill,
        skill_id=skill_id or getattr(resolved_skill, "id", None),
        prompt_body=skill_prompt,
        runtime_skill_dir=skill_runtime_dir,
        runtime_contract=runtime_contract if isinstance(runtime_contract, dict) else None,
    )
    spec = TurnSpec(
        mode=PromptMode.MAIN_TURN,
        phase=phase,
        language=language,
        conversation={**conversation, "phase": phase},
        message_history=[],
        base_instructions_override=_static_system_prompt(language, runtime_profile, resolved_artifact_mode),
        skill=resolved_skill,
        skill_id=skill_id or getattr(resolved_skill, "id", None),
        skill_prompt=skill_prompt,
        skill_runtime_dir=skill_runtime_dir,
        active_skill_manifest=active_skill_manifest,
        artifact_mode=resolved_artifact_mode,
        mode_contract_text=_cached_mode_contract(resolved_artifact_mode, resolved_skill),
        prepared_workspace=prepared_workspace,
        workspace_runtime_session=workspace_runtime_session,
        runtime_contract=runtime_contract,
        current_outline=_resolve_current_outline(conversation),
        tool_schemas=tool_schemas,
        builtin_provider=_builtin_provider_for_model(model_name),
    )
    return spec


def _builtin_provider_for_model(model_name: str | None) -> str:
    normalized = str(model_name or "").strip().lower()
    if normalized.startswith("claude-"):
        return "anthropic"
    if normalized.startswith("gpt-") or normalized.startswith("o"):
        return "openai"
    if normalized.startswith("gemini-"):
        return "gemini"
    return "generic"


def _message_token_budget(
    system: str,
    *,
    model_name: str | None,
    max_input_tokens: int | None,
    provider_code: str | None = None,
    tool_schemas: list[dict[str, Any]] | None = None,
) -> int:
    configured_limit = int(max_input_tokens or 0)
    if configured_limit <= 0 and model_name:
        resolved_provider = str(provider_code or "").strip() or resolve_multimodal_provider(str(model_name or ""))
        config = get_multimodal_model_config(model_name, resolved_provider)
        if isinstance(config, dict):
            configured_limit = int(config.get("max_input_tokens") or 0)
    if configured_limit <= 0:
        configured_limit = DEFAULT_CONTEXT_TOKEN_BUDGET

    system_tokens = estimate_tokens(system)
    tools_tokens = estimate_tokens(json.dumps(tool_schemas or [], ensure_ascii=False, separators=(",", ":")))
    budget = configured_limit - system_tokens - tools_tokens - CONTEXT_SAFETY_MARGIN_TOKENS
    return max(4_096, budget)
