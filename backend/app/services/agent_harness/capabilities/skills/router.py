from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.services.agent_harness.capabilities.skills.policy_registry import (
    default_skill_id_for_artifact_mode,
    is_default_route_skill,
)
from app.services.agent_harness.catalog import (
    SkillSummary,
    get_skill_summary_sync,
    list_skill_summaries_sync,
)

if TYPE_CHECKING:
    from app.services.agent_harness.capabilities.skills import SkillDefinition

ARTIFACT_MODES = ("web", "document", "spreadsheet", "slides", "image", "video")
DESIGN_SYSTEM_ELIGIBLE_MODES = {"web", "document", "slides"}


@dataclass(slots=True)
class SkillResolution:
    skill_id: str | None
    source: str


def normalize_artifact_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in ARTIFACT_MODES:
        return normalized
    return "web"


def resolve_mode_skill(
    *,
    artifact_mode: str | None,
    preferred_skill_id: str | None,
    prompt: str,
    attachments: list[dict[str, Any]] | None = None,
) -> SkillResolution:
    normalized_mode = normalize_artifact_mode(artifact_mode)
    preferred = get_skill_summary_sync(preferred_skill_id)
    if preferred and preferred.artifact_mode == normalized_mode:
        return SkillResolution(skill_id=preferred.id, source="user_selected")

    candidates = [
        skill
        for skill in list_skill_summaries_sync()
        if skill.artifact_mode == normalized_mode
        and skill.capabilities.get("phase_enabled") is not False
        and skill.capabilities.get("selection_enabled") is not False
    ]
    if not candidates:
        fallback_skill = get_skill_summary_sync(default_skill_id_for_artifact_mode(normalized_mode))
        return SkillResolution(skill_id=fallback_skill.id if fallback_skill else None, source="fallback_default")

    scored = sorted(
        candidates,
        key=lambda skill: _score_candidate(skill, prompt=prompt, attachments=attachments),
        reverse=True,
    )
    winner = scored[0]
    if _score_candidate(winner, prompt=prompt, attachments=attachments) <= 0:
        fallback_id = default_skill_id_for_artifact_mode(normalized_mode)
        fallback = get_skill_summary_sync(fallback_id) or winner
        return SkillResolution(skill_id=fallback.id, source="mode_default")
    return SkillResolution(skill_id=winner.id, source="auto_routed")


def build_mode_contract(artifact_mode: str, *, skill: SkillDefinition | None) -> str:
    mode = normalize_artifact_mode(artifact_mode)
    if mode == "web":
        return (
            "Artifact mode: web.\n"
            "Produce web-native outputs that are previewable inside the workspace. "
            "Favor HTML/CSS/JS artifacts and preserve clear file structure."
        )
    if mode == "document":
        return (
            "Artifact mode: document.\n"
            "The primary deliverable is a native document workflow. Preserve doc-friendly structure, "
            "respect office preview requirements, and keep content suitable for structured outlines."
        )
    if mode == "spreadsheet":
        return (
            "Artifact mode: spreadsheet.\n"
            "The primary deliverable is workbook or table-oriented. Prefer tabular organization, formulas, "
            "sheet naming discipline, and data clarity."
        )
    if mode == "slides":
        contract = (
            "Artifact mode: slides.\n"
            "The primary deliverable is a presentation workflow. Preserve slide structure, speaker-note awareness, "
            "and preview fidelity."
        )
        if skill is not None and getattr(skill, "mode", None) == "deck":
            contract += (
                "\nThis selected skill is HTML-deck based. Apply deck-style navigation, slide sizing, "
                "and presentation rhythm expectations."
            )
        return contract
    if mode == "image":
        return (
            "Artifact mode: image.\n"
            "Do not ask the user to choose image tools or models. Infer composition and art direction from the request, "
            "then use the internal image-generation toolchain."
        )
    return (
        "Artifact mode: video.\n"
        "Do not ask the user to choose video tools or models. Infer shots, pacing, framing, and prompts from the request, "
        "then use the internal video-generation toolchain."
    )


def _score_candidate(skill: SkillSummary, *, prompt: str, attachments: list[dict[str, Any]] | None) -> int:
    score = 0
    normalized_prompt = str(prompt or "").lower()
    if skill.id in normalized_prompt:
        score += 100

    searchable_parts = [skill.name, skill.name_en, skill.description, skill.example_prompt or ""]
    searchable_parts.extend(skill.triggers)
    for part in searchable_parts:
        text = str(part or "").strip().lower()
        if not text:
            continue
        if text in normalized_prompt:
            score += 30
            continue
        tokens = [token for token in re.split(r"[\s_/,-]+", text) if len(token) >= 4]
        for token in tokens[:8]:
            if token in normalized_prompt:
                score += 5

    if attachments and skill.artifact_mode in {"image", "video"}:
        score += 3
    if skill.featured is not None:
        score += max(0, 20 - skill.featured)
    if is_default_route_skill(skill.id, skill.artifact_mode):
        score += 2
    return score
