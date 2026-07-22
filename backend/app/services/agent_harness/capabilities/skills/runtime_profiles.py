from __future__ import annotations

from app.services.agent_harness.capabilities.skills.policy_registry import (
    CANVAS_DEFAULT_SKILL_ID,
    CANVAS_EXPLICIT_SKILL_IDS,
    CANVAS_ONLY_SKILL_IDS,
    ECOMMERCE_PRODUCT_SKILL_IDS,
    LEGACY_PRODUCT_HERO_SKILL_ID,
    MENSWEAR_ECOMMERCE_HERO_SKILL_ID,
    build_skill_runtime_capabilities as build_policy_runtime_capabilities,
    canonical_skill_id,
    is_canvas_only_skill,
)


def build_skill_runtime_capabilities(skill_id: str) -> dict[str, bool]:
    return build_policy_runtime_capabilities(skill_id)


__all__ = [
    "CANVAS_DEFAULT_SKILL_ID",
    "CANVAS_EXPLICIT_SKILL_IDS",
    "CANVAS_ONLY_SKILL_IDS",
    "ECOMMERCE_PRODUCT_SKILL_IDS",
    "LEGACY_PRODUCT_HERO_SKILL_ID",
    "MENSWEAR_ECOMMERCE_HERO_SKILL_ID",
    "build_skill_runtime_capabilities",
    "canonical_skill_id",
    "is_canvas_only_skill",
]
