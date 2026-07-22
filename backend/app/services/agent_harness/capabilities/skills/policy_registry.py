from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ArtifactMode = Literal["web", "document", "spreadsheet", "slides", "image", "video"]
RolloutState = Literal["selectable", "loaded_hidden", "disabled"]
SemanticKind = Literal["artifact_template", "functional", "media", "unclassified"]

FIRST_PHASE_ARTIFACT_MODES = frozenset({"web", "document", "spreadsheet", "slides"})
FUNCTIONAL_HIDDEN_SKILL_IDS = frozenset(
    {
        "design_workflow",
        "brand_strategy_architect",
        "logo",
        "vi-design-guide",
        "tweaks",
    }
)
DISABLED_SKILL_IDS = frozenset(
    {
        "audio-jingle",
        "hyperframes",
        # Depends on sibling assets from another skill folder; excluded from phase one.
        "open-design-landing-deck",
    }
)
NON_DESIGN_HOME_HIDDEN_SKILL_IDS = frozenset(
    {
        "blog-post",
        "clinical-case-report",
        "dating-web",
        "dcf-valuation",
        "digital-eguide",
        "email-marketing",
        "flowai-live-dashboard-template",
        "github-dashboard",
        "hr-onboarding",
        "invoice",
        "kanban-board",
        "last30days",
        "live-artifact",
        "live-dashboard",
        "magazine-poster",
        "meeting-notes",
        "motion-frames",
        "orbit-general",
        "orbit-github",
        "orbit-gmail",
        "orbit-linear",
        "orbit-notion",
        "social-carousel",
        "social-media-dashboard",
        "social-media-matrix-tracker-template",
        "sprite-animation",
        "team-okrs",
        "trading-analysis-dashboard-template",
        "x-research",
    }
)

CANVAS_DEFAULT_SKILL_ID = "design_workflow"
MENSWEAR_ECOMMERCE_HERO_SKILL_ID = "menswear-ecommerce-hero"
LEGACY_PRODUCT_HERO_SKILL_ID = "product-hero"
ECOMMERCE_PRODUCT_SKILL_IDS = frozenset({MENSWEAR_ECOMMERCE_HERO_SKILL_ID, LEGACY_PRODUCT_HERO_SKILL_ID})
CANVAS_EXPLICIT_SKILL_IDS = frozenset({"brand_strategy_architect", "logo", MENSWEAR_ECOMMERCE_HERO_SKILL_ID, "vi-design-guide"})
CANVAS_ONLY_SKILL_IDS = frozenset({CANVAS_DEFAULT_SKILL_ID, *CANVAS_EXPLICIT_SKILL_IDS})

MODE_DEFAULT_SKILLS: dict[str, str] = {
    "web": "web",
    "document": "docx",
    "spreadsheet": "xlsx",
    "slides": "pptx",
    "image": "image-poster",
    "video": "video-shortform",
}


def canonical_skill_id(skill_id: str | None) -> str:
    normalized = str(skill_id or "").strip()
    if normalized == LEGACY_PRODUCT_HERO_SKILL_ID:
        return MENSWEAR_ECOMMERCE_HERO_SKILL_ID
    return normalized


@dataclass(slots=True)
class SkillPolicy:
    skill_id: str
    mode_override: str | None
    artifact_mode: str | None
    rollout_state: RolloutState
    semantic_kind: SemanticKind
    home_visible: bool
    selection_enabled: bool
    phase_enabled: bool
    notes: str | None = None
    canvas_visible: bool = True
    canvas_only: bool = False
    canvas_default: bool = False
    canvas_explicit: bool = False
    helper_eligible: bool = False
    default_route_for: str | None = None
    default_route_priority: int = 0

    def to_runtime_capabilities(self) -> dict[str, object]:
        return {
            "semantic_kind": self.semantic_kind,
            "rollout_state": self.rollout_state,
            "selection_enabled": self.selection_enabled,
            "phase_enabled": self.phase_enabled,
            "classification_notes": self.notes,
            "home_visible": self.home_visible,
            "canvas_visible": self.canvas_visible,
            "canvas_only": self.canvas_only,
            "canvas_default": self.canvas_default,
            "canvas_explicit": self.canvas_explicit,
            "helper_eligible": self.helper_eligible,
            "default_route_for": self.default_route_for,
            "default_route_priority": self.default_route_priority,
        }


def resolve_skill_policy(
    *,
    skill_id: str,
    artifact_mode: str | None,
    mode: str,
) -> SkillPolicy:
    normalized_id = canonical_skill_id(skill_id)
    normalized_artifact_mode = str(artifact_mode or "").strip().lower() or None
    normalized_mode = str(mode or "").strip().lower()

    explicit_mode = _explicit_mode_override(normalized_id)
    if explicit_mode is not None:
        normalized_mode = explicit_mode
    explicit_artifact_mode = _explicit_artifact_mode_override(normalized_id)
    if explicit_artifact_mode is not None:
        normalized_artifact_mode = explicit_artifact_mode

    canvas_only = is_canvas_only_skill(normalized_id)
    default_route_for = _default_route_for_skill(normalized_id, normalized_artifact_mode)
    base = {
        "skill_id": normalized_id,
        "mode_override": normalized_mode,
        "artifact_mode": normalized_artifact_mode,
        "canvas_visible": True,
        "canvas_only": canvas_only,
        "canvas_default": normalized_id == CANVAS_DEFAULT_SKILL_ID,
        "canvas_explicit": normalized_id in CANVAS_EXPLICIT_SKILL_IDS,
        "default_route_for": default_route_for,
        "default_route_priority": 100 if default_route_for else 0,
    }

    if normalized_id in DISABLED_SKILL_IDS:
        note = "phase_one_excluded_sibling_assets" if normalized_id == "open-design-landing-deck" else "phase_one_disabled"
        return SkillPolicy(
            **base,
            rollout_state="disabled",
            semantic_kind=_semantic_kind_for(mode=normalized_mode, artifact_mode=normalized_artifact_mode),
            home_visible=False,
            selection_enabled=False,
            phase_enabled=False,
            notes=note,
            helper_eligible=False,
        )

    if normalized_id in FUNCTIONAL_HIDDEN_SKILL_IDS:
        return SkillPolicy(
            **base,
            rollout_state="loaded_hidden",
            semantic_kind="functional",
            home_visible=False,
            selection_enabled=False,
            phase_enabled=True,
            notes="functional_hidden",
            helper_eligible=not canvas_only,
        )

    if normalized_id in NON_DESIGN_HOME_HIDDEN_SKILL_IDS:
        return SkillPolicy(
            **base,
            rollout_state="loaded_hidden",
            semantic_kind=_semantic_kind_for(mode=normalized_mode, artifact_mode=normalized_artifact_mode),
            home_visible=False,
            selection_enabled=False,
            phase_enabled=True,
            notes="non_design_home_hidden",
            helper_eligible=False,
        )

    if normalized_artifact_mode in FIRST_PHASE_ARTIFACT_MODES:
        return SkillPolicy(
            **base,
            rollout_state="selectable",
            semantic_kind="artifact_template",
            home_visible=not canvas_only,
            selection_enabled=not canvas_only,
            phase_enabled=True,
            notes="phase_one_supported",
            helper_eligible=False,
        )

    if normalized_artifact_mode in {"image", "video"} or normalized_mode in {"image", "video", "audio"}:
        return SkillPolicy(
            **base,
            rollout_state="loaded_hidden",
            semantic_kind="media",
            home_visible=False,
            selection_enabled=False,
            phase_enabled=True,
            notes="deferred_media",
            helper_eligible=False,
        )

    return SkillPolicy(
        **base,
        rollout_state="loaded_hidden",
        semantic_kind="unclassified",
        home_visible=False,
        selection_enabled=False,
        phase_enabled=True,
        notes="unclassified_hidden",
        helper_eligible=False,
    )


def is_canvas_only_skill(skill_id: str | None) -> bool:
    normalized = canonical_skill_id(skill_id)
    if not normalized:
        return False
    return normalized in CANVAS_ONLY_SKILL_IDS


def build_skill_runtime_capabilities(skill_id: str) -> dict[str, bool]:
    normalized = canonical_skill_id(skill_id)
    canvas_only = is_canvas_only_skill(normalized)
    return {
        "home_visible": not canvas_only,
        "canvas_visible": True,
        "canvas_only": canvas_only,
        "canvas_default": normalized == CANVAS_DEFAULT_SKILL_ID,
        "canvas_explicit": normalized in CANVAS_EXPLICIT_SKILL_IDS,
    }


def default_skill_id_for_artifact_mode(artifact_mode: str | None) -> str | None:
    normalized = str(artifact_mode or "").strip().lower()
    return MODE_DEFAULT_SKILLS.get(normalized)


def is_default_route_skill(skill_id: str | None, artifact_mode: str | None) -> bool:
    return canonical_skill_id(skill_id) == str(default_skill_id_for_artifact_mode(artifact_mode) or "").strip()


def is_helper_eligible_skill(skill: object) -> bool:
    capabilities = getattr(skill, "runtime_capabilities", None)
    if not isinstance(capabilities, dict):
        return False
    return capabilities.get("helper_eligible") is True


def _default_route_for_skill(skill_id: str, artifact_mode: str | None) -> str | None:
    for mode, default_skill_id in MODE_DEFAULT_SKILLS.items():
        if skill_id == default_skill_id and artifact_mode == mode:
            return mode
    return None


def _explicit_artifact_mode_override(skill_id: str) -> ArtifactMode | None:
    if skill_id.startswith("html-ppt-"):
        return "slides"
    if skill_id.startswith("web-prototype-"):
        return "web"
    if skill_id.endswith("-template"):
        return "web"
    if skill_id in {"social-media-dashboard", "live-dashboard", "flowai-live-dashboard-template"}:
        return "web"
    return None


def _explicit_mode_override(skill_id: str) -> str | None:
    if skill_id.startswith("html-ppt-"):
        return "deck"
    if skill_id.startswith("web-prototype-"):
        return "prototype"
    if skill_id.endswith("-template"):
        return "template"
    return None


def _semantic_kind_for(*, mode: str, artifact_mode: str | None) -> SemanticKind:
    if artifact_mode in FIRST_PHASE_ARTIFACT_MODES:
        return "artifact_template"
    if artifact_mode in {"image", "video"} or mode in {"image", "video", "audio"}:
        return "media"
    if mode == "utility":
        return "functional"
    return "unclassified"
