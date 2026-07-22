from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.core.default_models import get_default_multimodal_model
from app.services.agent_harness.authoring.prompt.runtime_time import runtime_time_payload
from app.services.agent_harness.capabilities.skills.router import normalize_artifact_mode
from app.services.agent_harness.catalog import SkillSummary, read_skill_summaries
from app.services.agent_harness.prompt_runtime import Phase, PromptMode, PromptRuntime, TurnSpec
from app.services.agent_harness.prompt_runtime.tracing import persist_prompt_bundle_trace
from app.services.agent_harness.runtime.execution_support.harness_model_provider import (
    create_harness_model_provider,
)
from app.services.llm_runtime.tool_calls import tool_call_arguments, tool_call_name
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context

from .design_system_selection_resolver import (
    DesignSystemRecommendation,
)

_TOKEN_SPLIT_RE = re.compile(r"[\s_/,:;|()+-]+")
_MAX_SKILL_CANDIDATES = 10
_PROMPT_RUNTIME = PromptRuntime()


class _ResolverDecisionInput(BaseModel):
    id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning_summary: str = ""
    should_replace_current: bool = False


class _ResolverToolInput(BaseModel):
    skill: _ResolverDecisionInput | None = None
    internal_skill_ids: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class SelectionDecision:
    id: str | None
    confidence: float
    reasoning_summary: str
    should_replace_current: bool


@dataclass(slots=True)
class ResolveSelectionResult:
    skill: SelectionDecision | None
    internal_skill_ids: list[str] = field(default_factory=list)
    design_system_recommendations: list[DesignSystemRecommendation] | None = None
    preflight_model_calls: list[PreflightModelCall] | None = None


@dataclass(slots=True)
class PreflightModelCall:
    model_name: str | None
    usage: dict[str, Any] | None
    elapsed_ms: int
    kind: str


@dataclass(slots=True)
class _ResolverModelResult:
    decision: _ResolverToolInput | None
    usage: dict[str, Any] | None
    elapsed_ms: int


def _selection_resolver_system_prompt() -> str:
    bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.SKILL_SELECTION,
            phase=Phase.PLANNING,
            language="en",
        )
    )
    return bundle.rendered_system


def _tokenize(value: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT_RE.split(str(value or "").lower()) if len(token) >= 3]


def _score_overlap(prompt: str, fields: list[str]) -> int:
    prompt_text = str(prompt or "").lower()
    prompt_tokens = set(_tokenize(prompt_text))
    score = 0
    for candidate_field in fields:
        text = str(candidate_field or "").strip().lower()
        if not text:
            continue
        if text in prompt_text:
            score += 12
        for token in _tokenize(text)[:10]:
            if token in prompt_tokens:
                score += 2
    return score


def _summarize_attachments(attachments: list[dict[str, Any]] | None) -> str:
    if not attachments:
        return "none"
    parts: list[str] = []
    for item in attachments[:8]:
        item_type = str(item.get("type") or "file")
        name = str(item.get("name") or item.get("filename") or "").strip()
        if name:
            parts.append(f"{item_type}:{name}")
        else:
            parts.append(item_type)
    return ", ".join(parts) if parts else "none"


def _build_skill_candidates(skills: list[SkillSummary], artifact_mode: str, prompt: str) -> list[SkillSummary]:
    candidates = [
        skill
        for skill in skills
        if skill.artifact_mode == artifact_mode
        and skill.capabilities.get("phase_enabled") is not False
        and skill.capabilities.get("selection_enabled") is not False
    ]
    scored = sorted(
        candidates,
        key=lambda skill: (
            _score_overlap(
                prompt,
                [
                    skill.id,
                    skill.name,
                    skill.name_en,
                    skill.name_zh,
                    skill.description,
                    *(skill.triggers or []),
                ],
            ),
            -(skill.featured or 9999),
        ),
        reverse=True,
    )
    return scored[:_MAX_SKILL_CANDIDATES]


def _build_internal_skill_candidates(
    skills: list[SkillSummary],
    prompt: str,
    current_skill_id: str | None,
) -> list[SkillSummary]:
    normalized_current_skill_id = str(current_skill_id or "").strip()
    candidates = [
        skill
        for skill in skills
        if skill.id != normalized_current_skill_id and skill.capabilities.get("helper_eligible") is True
    ]
    scored = sorted(
        candidates,
        key=lambda skill: (
            _score_overlap(
                prompt,
                [
                    skill.id,
                    skill.name,
                    skill.name_en,
                    skill.name_zh,
                    skill.description,
                    *(skill.triggers or []),
                ],
            ),
            -(skill.featured or 9999),
        ),
        reverse=True,
    )
    return scored[:_MAX_SKILL_CANDIDATES]


def _normalize_decision(
    raw: _ResolverDecisionInput | None,
    *,
    allowed_ids: set[str],
    current_id: str | None,
) -> SelectionDecision | None:
    if raw is None:
        return None
    target_id = str(raw.id or "").strip() or None
    if target_id and target_id not in allowed_ids:
        target_id = None
    replace = bool(raw.should_replace_current)
    if current_id and target_id is None:
        replace = True
    if current_id == target_id:
        replace = False
    return SelectionDecision(
        id=target_id,
        confidence=max(0.0, min(1.0, float(raw.confidence or 0.0))),
        reasoning_summary=str(raw.reasoning_summary or "").strip(),
        should_replace_current=replace,
    )


def _normalize_internal_skill_ids(raw_ids: list[str] | None, *, allowed_ids: set[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in list(raw_ids or []):
        skill_id = str(raw_id or "").strip()
        if not skill_id or skill_id not in allowed_ids or skill_id in seen:
            continue
        normalized.append(skill_id)
        seen.add(skill_id)
    return normalized


async def _call_selection_model(
    *,
    system_prompt: str,
    user_prompt: str,
    model_name: str,
    api_key: str,
) -> _ResolverModelResult:
    provider = create_harness_model_provider(api_key=api_key)
    tool_schema = {
        "type": "function",
        "function": {
            "name": "resolve_selection",
            "description": "Resolve the most helpful main skill for the current request. Return a null id when no explicit selection is necessary.",
            "parameters": _ResolverToolInput.model_json_schema(),
        },
    }

    last_tool_call: dict[str, Any] | None = None
    accumulated_text: list[str] = []
    usage: dict[str, Any] | None = None
    started = time.monotonic()
    async for chunk in provider.chat_stream(
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
        tools=[tool_schema],
        model=model_name,
        temperature=0.1,
        max_tokens=600,
    ):
        if chunk.usage:
            usage = chunk.usage
        if chunk.tool_calls:
            for tool_call in chunk.tool_calls:
                if tool_call_name(tool_call) == "resolve_selection":
                    last_tool_call = tool_call
        if chunk.content:
            accumulated_text.append(str(chunk.content))

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if last_tool_call:
        arguments = tool_call_arguments(last_tool_call)
        if isinstance(arguments, dict):
            return _ResolverModelResult(
                decision=_ResolverToolInput.model_validate(arguments),
                usage=usage,
                elapsed_ms=elapsed_ms,
            )

    raw_text = "".join(accumulated_text).strip()
    if not raw_text:
        return _ResolverModelResult(decision=None, usage=usage, elapsed_ms=elapsed_ms)
    try:
        return _ResolverModelResult(
            decision=_ResolverToolInput.model_validate(json.loads(raw_text)),
            usage=usage,
            elapsed_ms=elapsed_ms,
        )
    except Exception:
        return _ResolverModelResult(decision=None, usage=usage, elapsed_ms=elapsed_ms)


async def resolve_selection(
    *,
    artifact_mode: str | None,
    prompt: str,
    attachments: list[dict[str, Any]] | None = None,
    current_skill_id: str | None = None,
    resolve_skill: bool = True,
    model_preferences: dict[str, Any] | None = None,
    user_id: int | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> ResolveSelectionResult:
    normalized_mode = normalize_artifact_mode(artifact_mode)
    skills = await read_skill_summaries()
    skill_candidates = _build_skill_candidates(skills, normalized_mode, prompt) if resolve_skill else []
    internal_skill_candidates = _build_internal_skill_candidates(skills, prompt, current_skill_id)
    skill_result: SelectionDecision | None = None
    internal_skill_ids: list[str] = []
    preflight_model_calls: list[PreflightModelCall] = []

    if skill_candidates or internal_skill_candidates:
        skill_candidate_summaries = [
            {
                "id": skill.id,
                "name": skill.name_en or skill.name,
                "description": skill.description_en or skill.description,
                "triggers": skill.triggers,
            }
            for skill in skill_candidates
        ]
        internal_skill_candidate_summaries = [
            {
                "id": skill.id,
                "name": skill.name_en or skill.name,
                "description": skill.description_en or skill.description,
                "triggers": skill.triggers,
            }
            for skill in internal_skill_candidates
        ]

        model_name = (
            (model_preferences or {}).get("multimodal_model")
            or get_default_multimodal_model()
        )
        system_prompt = _selection_resolver_system_prompt()
        bundle = _PROMPT_RUNTIME.build_bundle(
            TurnSpec(
                mode=PromptMode.SKILL_SELECTION,
                phase=Phase.PLANNING,
                language="en",
                side_payload={
                    "runtime_time": runtime_time_payload(),
                    "artifact_mode": normalized_mode,
                    "request": prompt,
                    "attachments_summary": _summarize_attachments(attachments),
                    "current_skill_id": current_skill_id,
                    "resolve_skill": resolve_skill,
                    "skill_candidates": skill_candidate_summaries,
                    "internal_skill_candidates": internal_skill_candidate_summaries,
                },
            )
        )
        persist_prompt_bundle_trace(
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=run_id,
            bundle=bundle,
            summary="Prompt bundle assembled (skill selection)",
        )
        user_prompt = str(bundle.messages[0]["content"])

        started = time.monotonic()
        try:
            raw_result = await _call_selection_model(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model_name=model_name,
                api_key=(await resolve_user_apimart_key_for_context(user_id) if user_id is not None else ""),
            )
        except Exception:
            raw_result = _ResolverModelResult(
                decision=None,
                usage=None,
                elapsed_ms=int((time.monotonic() - started) * 1000),
            )
        preflight_model_calls.append(
            PreflightModelCall(
                model_name=model_name,
                usage=raw_result.usage,
                elapsed_ms=raw_result.elapsed_ms,
                kind="selection_resolver",
            )
        )
        skill_allowed_ids = {skill.id for skill in skill_candidates}
        if raw_result.decision is None:
            skill_result = (
                SelectionDecision(id=None, confidence=0.0, reasoning_summary="", should_replace_current=bool(current_skill_id))
                if resolve_skill
                else None
            )
            internal_skill_ids = []
        else:
            skill_result = (
                _normalize_decision(raw_result.decision.skill, allowed_ids=skill_allowed_ids, current_id=current_skill_id)
                if resolve_skill
                else None
            )
            internal_skill_ids = _normalize_internal_skill_ids(
                raw_result.decision.internal_skill_ids,
                allowed_ids={skill.id for skill in internal_skill_candidates},
            )

    return ResolveSelectionResult(
        skill=skill_result,
        internal_skill_ids=internal_skill_ids,
        design_system_recommendations=[],
        preflight_model_calls=preflight_model_calls,
    )

