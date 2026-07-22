from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from app.core.default_models import get_default_multimodal_model
from app.services.agent_harness.authoring.prompt.runtime_time import runtime_time_payload
from app.services.agent_harness.capabilities.design_systems.resolver_registry import (
    DesignSystemResolverMetadata,
)
from app.services.agent_harness.capabilities.skills.router import normalize_artifact_mode
from app.services.agent_harness.catalog import (
    DesignSystemSummary,
    SkillSummary,
    get_skill_summary,
    read_design_system_summaries,
)
from app.services.agent_harness.prompt_runtime import Phase, PromptMode, PromptRuntime, TurnSpec
from app.services.agent_harness.prompt_runtime.tracing import persist_prompt_bundle_trace
from app.services.agent_harness.runtime.execution_support.harness_model_provider import (
    create_harness_model_provider,
)
from app.services.llm_runtime.tool_calls import tool_call_arguments, tool_call_name
from app.services.multimodal_service import resolve_effective_max_tokens
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context

_TOKEN_SPLIT_RE = re.compile(r"[\s_/,:;|()+-]+")
_MAX_RECALLED_CANDIDATES = 30
_MAX_RECOMMENDATIONS = 6
_FALLBACK_DESIGN_SYSTEM_SELECTION_MAX_TOKENS = 1200
_PROMPT_RUNTIME = PromptRuntime()


class _RecommendationInput(BaseModel):
    id: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning_summary: str = ""


class _RecommendationToolInput(BaseModel):
    recommendations: list[_RecommendationInput] = Field(default_factory=list, max_length=_MAX_RECOMMENDATIONS)


@dataclass(slots=True)
class DesignSystemRecommendation:
    id: str
    title: str
    description: str
    category: str | None
    palette: list[str]
    confidence: float
    reasoning_summary: str
    rank: int


@dataclass(slots=True)
class ResolveDesignSystemSelectionResult:
    recommendations: list[DesignSystemRecommendation]
    model_name: str | None = None
    usage: dict[str, Any] | None = None
    elapsed_ms: int = 0


@dataclass(slots=True)
class _ResolverModelResult:
    decision: _RecommendationToolInput | None
    usage: dict[str, Any] | None
    elapsed_ms: int


@dataclass(slots=True)
class _CandidateSummary:
    id: str
    title: str
    description: str
    category: str | None
    palette: list[str]
    resolver_summary: str
    resolver_tags: list[str]
    preferred_for: list[str]
    tone: str
    density: str
    featured: int | None
    is_default: bool
    recall_score: int


def _design_system_selection_system_prompt() -> str:
    bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.DESIGN_SYSTEM_SELECTION,
            phase=Phase.PLANNING,
            language="en",
        )
    )
    return bundle.rendered_system


def _resolve_design_system_selection_max_tokens(model_name: str) -> int:
    max_tokens = int(resolve_effective_max_tokens(model_name, 0) or 0)
    return max_tokens if max_tokens > 0 else _FALLBACK_DESIGN_SYSTEM_SELECTION_MAX_TOKENS


def _tokenize(value: str) -> list[str]:
    return [token for token in _TOKEN_SPLIT_RE.split(str(value or "").lower()) if len(token) >= 3]


def _brief_keywords(*values: Any) -> set[str]:
    keywords: set[str] = set()
    for value in values:
        if isinstance(value, list):
            keywords.update(_brief_keywords(*value))
            continue
        text = str(value or "").strip().lower()
        if not text:
            continue
        normalized = (
            text.replace("/", " ")
            .replace("_", " ")
            .replace("-", " ")
            .replace(",", " ")
        )
        keywords.update(part for part in normalized.split() if part)
    return keywords


def _score_overlap(prompt: str, fields: list[str]) -> int:
    prompt_text = str(prompt or "").lower()
    prompt_tokens = set(_tokenize(prompt_text))
    score = 0
    for field in fields:
        text = str(field or "").strip().lower()
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


def _clean_design_system_title(title: str) -> str:
    return (
        str(title or "")
        .replace("Design System Inspired by ", "")
        .replace("Design System for ", "")
        .strip()
    )


def _clean_design_system_description(description: str, category: str | None) -> str:
    category_text = str(category or "").strip()
    summary = str(description or "").strip()
    if category_text and summary.lower().startswith("category:"):
        return category_text
    return summary or category_text


def _score_design_system_candidate(
    *,
    metadata: DesignSystemResolverMetadata | None,
    artifact_family: str,
    prompt: str,
    discovery_brief: dict[str, Any] | None,
    skill: Any | None,
    title: str,
    description: str,
    category: str | None,
) -> int:
    score = 30
    brief = discovery_brief or {}
    tone = str(brief.get("tone") or "").strip().lower()
    platform = str(brief.get("platform") or "").strip().lower()
    output = str(brief.get("output") or prompt or "").strip().lower()
    audience = str(brief.get("audience") or "").strip().lower()
    scale = str(brief.get("scale") or brief.get("page_or_screen_count") or "").strip().lower()
    keywords = _brief_keywords(
        prompt,
        tone,
        platform,
        output,
        audience,
        scale,
        getattr(skill, "id", None),
        getattr(skill, "name", None),
        title,
        description,
        category,
    )
    score += _score_overlap(
        prompt,
        [
            title,
            description,
            category or "",
            getattr(skill, "id", None) or "",
            getattr(skill, "name", None) or "",
        ],
    )

    if metadata is None:
        return score

    preferred_map = {
        "web": {"landing-page", "company-site", "product-page", "dashboard"},
        "document": {"docs"},
        "slides": {"landing-page", "company-site", "product-page"},
    }
    for preferred in metadata.preferred_for:
        if preferred in preferred_map.get(artifact_family, set()):
            score += 12
            break

    tone_map = {
        "professional_restrained": {"professional", "balanced"},
        "confident_modern": {"modern", "product", "technical", "structured"},
        "warm_approachable": {"friendly", "creative", "marketing"},
        "premium_confident": {"premium", "luxury", "editorial", "brand-led"},
    }
    for tag in tone_map.get(tone, set()):
        if tag in {item.lower() for item in metadata.resolver_tags} or tag == metadata.tone.lower():
            score += 7

    keyword_bonus_map = {
        "dashboard": {"dashboard", "analytics", "data", "admin"},
        "docs": {"docs", "documentation", "knowledge", "report", "memo"},
        "product": {"product", "saas", "app", "application"},
        "marketing": {"marketing", "campaign", "launch", "landing"},
        "editorial": {"editorial", "story", "content", "narrative"},
        "creative": {"creative", "portfolio", "studio", "brand"},
        "enterprise": {"enterprise", "internal", "ops", "b2b"},
    }
    lowered_tags = {item.lower() for item in metadata.resolver_tags}
    for tag, tag_keywords in keyword_bonus_map.items():
        if tag in lowered_tags and keywords.intersection(tag_keywords):
            score += 6

    if artifact_family == "document" and metadata.density in {"dense", "balanced"}:
        score += 4
    if artifact_family == "slides" and metadata.tone in {"professional", "premium", "editorial"}:
        score += 4
    if artifact_family == "web" and metadata.category.lower() in {"product & saas", "commerce & marketing", "dashboard & data"}:
        score += 4

    penalty_keywords = _brief_keywords(metadata.avoid_for)
    if keywords.intersection(penalty_keywords):
        score -= 8
    if metadata.featured_priority is not None:
        score += max(0, 6 - min(metadata.featured_priority, 6))
    return score


def _build_recalled_candidates(
    *,
    design_systems: list[DesignSystemSummary],
    artifact_mode: str,
    prompt: str,
    discovery_brief: dict[str, Any] | None,
    skill: Any | None,
) -> list[_CandidateSummary]:
    scored: list[_CandidateSummary] = []
    for system in design_systems:
        metadata = _metadata_from_summary(system)
        title = _clean_design_system_title(system.title)
        description = _clean_design_system_description(system.description, system.category)
        recall_score = _score_design_system_candidate(
            metadata=metadata,
            artifact_family=artifact_mode,
            prompt=prompt,
            discovery_brief=discovery_brief,
            skill=skill,
            title=title,
            description=description,
            category=system.category,
        )
        scored.append(
            _CandidateSummary(
                id=system.id,
                title=title,
                description=description,
                category=system.category,
                palette=list(system.palette or []),
                resolver_summary=metadata.resolver_summary if metadata is not None else description,
                resolver_tags=list(metadata.resolver_tags) if metadata is not None else [],
                preferred_for=list(metadata.preferred_for) if metadata is not None else list(system.sections or []),
                tone=metadata.tone if metadata is not None else "",
                density=metadata.density if metadata is not None else "",
                featured=metadata.featured_priority if metadata is not None else system.featured,
                is_default=bool(system.is_default),
                recall_score=recall_score,
            )
        )
    ranked = sorted(
        scored,
        key=lambda item: (
            -item.recall_score,
            item.featured if item.featured is not None else 999,
            item.title.lower(),
        ),
    )
    return ranked[:_MAX_RECALLED_CANDIDATES]


def _metadata_from_summary(system: DesignSystemSummary) -> DesignSystemResolverMetadata:
    return DesignSystemResolverMetadata(
        id=system.id,
        resolver_summary=system.resolver_summary,
        resolver_tags=list(system.resolver_tags),
        preferred_for=list(system.preferred_for),
        avoid_for=list(system.avoid_for),
        tone=system.tone,
        density=system.density,
        category=str(system.category or "Product & SaaS"),
        featured_priority=system.featured,
    )


async def _call_design_system_selection_model(
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
            "name": "recommend_design_systems",
            "description": "Pick the six strongest design system candidates from the provided list and rank them from best to good alternatives.",
            "parameters": _RecommendationToolInput.model_json_schema(),
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
        max_tokens=_resolve_design_system_selection_max_tokens(model_name),
    ):
        if chunk.usage:
            usage = chunk.usage
        if chunk.tool_calls:
            for tool_call in chunk.tool_calls:
                if tool_call_name(tool_call) == "recommend_design_systems":
                    last_tool_call = tool_call
        if chunk.content:
            accumulated_text.append(str(chunk.content))

    elapsed_ms = int((time.monotonic() - started) * 1000)
    if last_tool_call:
        arguments = tool_call_arguments(last_tool_call)
        if isinstance(arguments, dict):
            return _ResolverModelResult(
                decision=_RecommendationToolInput.model_validate(arguments),
                usage=usage,
                elapsed_ms=elapsed_ms,
            )

    raw_text = "".join(accumulated_text).strip()
    if not raw_text:
        return _ResolverModelResult(decision=None, usage=usage, elapsed_ms=elapsed_ms)
    try:
        return _ResolverModelResult(
            decision=_RecommendationToolInput.model_validate(json.loads(raw_text)),
            usage=usage,
            elapsed_ms=elapsed_ms,
        )
    except Exception:
        return _ResolverModelResult(decision=None, usage=usage, elapsed_ms=elapsed_ms)


def _normalize_recommendations(
    raw: list[_RecommendationInput] | None,
    *,
    recalled_candidates: list[_CandidateSummary],
) -> list[DesignSystemRecommendation]:
    recalled_by_id = {candidate.id: candidate for candidate in recalled_candidates}
    normalized: list[DesignSystemRecommendation] = []
    seen_ids: set[str] = set()
    for item in raw or []:
        target_id = str(item.id or "").strip()
        if not target_id or target_id in seen_ids or target_id not in recalled_by_id:
            continue
        candidate = recalled_by_id[target_id]
        seen_ids.add(target_id)
        normalized.append(
            DesignSystemRecommendation(
                id=candidate.id,
                title=candidate.title,
                description=candidate.description,
                category=candidate.category,
                palette=list(candidate.palette),
                confidence=max(0.0, min(1.0, float(item.confidence or 0.0))),
                reasoning_summary=str(item.reasoning_summary or "").strip(),
                rank=len(normalized) + 1,
            )
        )
        if len(normalized) >= _MAX_RECOMMENDATIONS:
            break

    if normalized:
        return normalized

    fallback: list[DesignSystemRecommendation] = []
    for candidate in recalled_candidates[:_MAX_RECOMMENDATIONS]:
        fallback.append(
            DesignSystemRecommendation(
                id=candidate.id,
                title=candidate.title,
                description=candidate.description,
                category=candidate.category,
                palette=list(candidate.palette),
                confidence=0.0,
                reasoning_summary="",
                rank=len(fallback) + 1,
            )
        )
    return fallback


async def resolve_design_system_selection(
    *,
    artifact_mode: str | None,
    prompt: str,
    attachments: list[dict[str, Any]] | None = None,
    current_design_system_id: str | None = None,
    discovery_brief: dict[str, Any] | None = None,
    skill_id: str | None = None,
    model_preferences: dict[str, Any] | None = None,
    user_id: int | None = None,
    conversation_id: str | None = None,
    run_id: str | None = None,
) -> ResolveDesignSystemSelectionResult:
    normalized_mode = normalize_artifact_mode(artifact_mode)
    skill: SkillSummary | None = await get_skill_summary(skill_id) if skill_id else None
    design_systems = await read_design_system_summaries()
    recalled_candidates = _build_recalled_candidates(
        design_systems=design_systems,
        artifact_mode=normalized_mode,
        prompt=prompt,
        discovery_brief=discovery_brief,
        skill=skill,
    )
    if not recalled_candidates:
        return ResolveDesignSystemSelectionResult(recommendations=[])

    candidate_summaries = [
        {
            "id": candidate.id,
            "title": candidate.title,
            "description": candidate.description,
            "category": candidate.category,
            "palette": candidate.palette,
            "resolver_summary": candidate.resolver_summary,
            "resolver_tags": candidate.resolver_tags,
            "preferred_for": candidate.preferred_for,
            "tone": candidate.tone,
            "density": candidate.density,
            "featured": candidate.featured,
            "is_default": candidate.is_default,
            "recall_score": candidate.recall_score,
        }
        for candidate in recalled_candidates
    ]
    model_name = (
        (model_preferences or {}).get("multimodal_model")
        or get_default_multimodal_model()
    )
    system_prompt = _design_system_selection_system_prompt()
    bundle = _PROMPT_RUNTIME.build_bundle(
        TurnSpec(
            mode=PromptMode.DESIGN_SYSTEM_SELECTION,
            phase=Phase.PLANNING,
            language="en",
            side_payload={
                "runtime_time": runtime_time_payload(),
                "artifact_mode": normalized_mode,
                "request": prompt,
                "attachments_summary": _summarize_attachments(attachments),
                "current_design_system_id": current_design_system_id,
                "discovery_brief": discovery_brief or {},
                "skill_context": (
                    {
                        "id": skill.id,
                        "name": skill.name_en or skill.name,
                        "description": skill.description_en or skill.description,
                    }
                    if skill is not None
                    else None
                ),
                "design_system_candidates": candidate_summaries,
            },
        )
    )
    persist_prompt_bundle_trace(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id=run_id,
        bundle=bundle,
        summary="Prompt bundle assembled (design system selection)",
    )
    user_prompt = str(bundle.messages[0]["content"])
    try:
        raw_result = await _call_design_system_selection_model(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model_name=model_name,
            api_key=(await resolve_user_apimart_key_for_context(user_id) if user_id is not None else ""),
        )
    except Exception:
        raw_result = _ResolverModelResult(
            decision=None,
            usage=None,
            elapsed_ms=0,
        )
    recommendations = _normalize_recommendations(
        raw_result.decision.recommendations if raw_result.decision is not None else None,
        recalled_candidates=recalled_candidates,
    )
    return ResolveDesignSystemSelectionResult(
        recommendations=recommendations,
        model_name=model_name,
        usage=raw_result.usage,
        elapsed_ms=raw_result.elapsed_ms,
    )

