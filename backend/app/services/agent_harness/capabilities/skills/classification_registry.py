from __future__ import annotations

from typing import Literal

from app.services.agent_harness.capabilities.skills.policy_registry import (
    SkillPolicy,
    resolve_skill_policy,
)


ArtifactMode = Literal["web", "document", "spreadsheet", "slides", "image", "video"]
RolloutState = Literal["selectable", "loaded_hidden", "disabled"]
SemanticKind = Literal["artifact_template", "functional", "media", "unclassified"]

SkillClassification = SkillPolicy


def classify_skill(
    *,
    skill_id: str,
    artifact_mode: str | None,
    mode: str,
) -> SkillClassification:
    return resolve_skill_policy(
        skill_id=skill_id,
        artifact_mode=artifact_mode,
        mode=mode,
    )


def is_skill_selectable(skill: object) -> bool:
    capabilities = getattr(skill, "runtime_capabilities", None)
    if not isinstance(capabilities, dict):
        return True
    if capabilities.get("phase_enabled") is False:
        return False
    return capabilities.get("selection_enabled") is not False


def is_skill_home_visible(skill: object) -> bool:
    capabilities = getattr(skill, "runtime_capabilities", None)
    if not isinstance(capabilities, dict):
        return True
    if capabilities.get("phase_enabled") is False:
        return False
    if capabilities.get("selection_enabled") is False:
        return False
    return capabilities.get("home_visible") is not False
