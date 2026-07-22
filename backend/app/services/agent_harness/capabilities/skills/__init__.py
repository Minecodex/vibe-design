"""Open-design-compatible skill loading for the Home Harness agent."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.services.agent_harness.capabilities.skill_protocols.open_design.catalog import derive_catalog_metadata
from app.services.agent_harness.capabilities.skill_protocols.open_design.design_templates import (
    build_imported_template_metadata,
)
from app.services.agent_harness.capabilities.skills.policy_registry import canonical_skill_id
from app.services.agent_harness.capabilities.skills.classification_registry import (
    classify_skill,
    is_skill_home_visible,
    is_skill_selectable,
)
from app.services.agent_harness.capabilities.skills.markdown_parser import parse_skill_markdown

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).parent

ArtifactMode = Literal["web", "document", "spreadsheet", "slides", "image", "video"]
SkillMode = Literal["prototype", "template", "deck", "image", "video", "audio", "utility", "design-system", "document", "spreadsheet", "other"]
RuntimeStrategy = Literal[
    "template_driven_deck",
    "template_driven_bundle",
    "free_generate",
    "office_pipeline",
    "media_pipeline",
    "utility_pipeline",
]

_ENTRY_CANDIDATES: dict[str, set[str]] = {
    "web": {"web", "web-prototype", "dashboard", "docs-page", "pricing-page", "saas-landing"},
    "document": {"docx", "design-brief", "pm-spec", "eng-runbook", "finance-report"},
    "spreadsheet": {"xlsx"},
    "slides": {"pptx", "html-ppt", "simple-deck", "replit-deck", "guizang-ppt", "weekly-update"},
    "image": {"image-poster"},
    "video": {"video-shortform"},
}

_ARTIFACT_MODE_TO_SKILL_MODES: dict[str, set[str]] = {
    "web": {"prototype", "template"},
    "document": {"document", "design-system", "prototype"},
    "spreadsheet": {"spreadsheet"},
    "slides": {"deck", "document"},
    "image": {"image"},
    "video": {"video"},
}


@dataclass(slots=True)
class SkillPreview:
    type: str = "html"
    entry: str | None = None
    reload: str | None = None


@dataclass(slots=True)
class SkillDesignSystem:
    requires: bool = False
    generates: bool = False
    sections: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillCraft:
    requires: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SkillDefinition:
    id: str
    name: str
    name_en: str
    name_zh: str
    description: str
    description_en: str
    description_zh: str
    system_prompt: str
    system_prompt_en: str
    tools: list[str] = field(default_factory=list)
    disabled_tools: list[str] = field(default_factory=list)
    icon: str = ""
    color: str = ""
    skill_dir: Path | None = None
    triggers: list[str] = field(default_factory=list)
    mode: str = "other"
    surface: str | None = None
    platform: str | None = None
    scenario: str | None = None
    default_for: list[str] = field(default_factory=list)
    featured: int | None = None
    preview: SkillPreview = field(default_factory=SkillPreview)
    design_system: SkillDesignSystem = field(default_factory=SkillDesignSystem)
    craft: SkillCraft = field(default_factory=SkillCraft)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)
    example_prompt: str | None = None
    upstream: str | None = None
    artifact_mode: str | None = None
    execution_strategy: RuntimeStrategy = "free_generate"
    preview_entry: str | None = None
    primary_output: str | None = None
    template_roots: list[str] = field(default_factory=list)
    fragment_roots: list[str] = field(default_factory=list)
    authoring_guides: list[str] = field(default_factory=list)
    scaffold_scripts: list[str] = field(default_factory=list)
    input_schema: list[dict[str, Any]] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    output_schema: dict[str, Any] = field(default_factory=dict)
    directions: list[dict[str, Any]] = field(default_factory=list)
    seed_assets: list[dict[str, Any] | str] = field(default_factory=list)
    metadata_health: dict[str, Any] = field(default_factory=dict)
    runtime_capabilities: dict[str, Any] = field(default_factory=dict)

def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, list):
        out: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            out.append(text)
            seen.add(text)
        return out
    return []


def _coerce_object_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        normalized: list[dict[str, Any]] = []
        for key, raw in value.items():
            if isinstance(raw, dict):
                item = dict(raw)
                item.setdefault("name", str(item.get("name") or key))
                item.setdefault("id", str(item.get("id") or item.get("name") or key))
                normalized.append(item)
            else:
                normalized.append({
                    "name": str(key),
                    "id": str(key),
                    "value": raw,
                })
        return normalized
    return []


def _coerce_seed_assets(value: Any) -> list[dict[str, Any] | str]:
    if isinstance(value, list):
        normalized: list[dict[str, Any] | str] = []
        for item in value:
            if isinstance(item, dict):
                normalized.append(dict(item))
            elif isinstance(item, str) and item.strip():
                normalized.append(item.strip())
        return normalized
    if isinstance(value, dict):
        return [dict(value)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce_direction_list(value: Any) -> list[dict[str, Any]]:
    explicit = _coerce_object_list(value)
    if explicit:
        return explicit
    if isinstance(value, list):
        normalized: list[dict[str, Any]] = []
        for item in value:
            text = str(item or "").strip()
            if not text:
                continue
            normalized.append({"id": text, "name": text})
        return normalized
    if isinstance(value, str) and value.strip():
        return [{"id": value.strip(), "name": value.strip()}]
    return []


def _detect_direction_definitions(skill_dir: Path, meta: dict[str, Any], od_meta: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = _coerce_direction_list(od_meta.get("directions") or meta.get("directions"))
    if explicit:
        return explicit

    discovered: list[dict[str, Any]] = []
    for folder_name in ("directions", "variants"):
        folder = skill_dir / folder_name
        if not folder.is_dir():
            continue
        for child in sorted(folder.iterdir()):
            if not child.is_dir():
                continue
            discovered.append(
                {
                    "id": child.name,
                    "name": child.name.replace("-", " "),
                    "source": folder_name,
                    "path": f"{folder_name}/{child.name}",
                }
            )
    return discovered


def _normalize_parameter_contracts(
    raw_parameters: Any,
    *,
    execution_strategy: RuntimeStrategy,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in _coerce_object_list(raw_parameters):
        parameter_id = str(item.get("id") or item.get("name") or "").strip()
        if not parameter_id:
            continue
        parameter_type = str(item.get("type") or "text").strip().lower() or "text"
        enum_values = item.get("enum_values")
        if not isinstance(enum_values, list):
            values = item.get("values")
            enum_values = list(values) if isinstance(values, list) else []
        runtime_scope = str(item.get("runtime_scope") or "").strip()
        if runtime_scope not in {"discovery_only", "prepare_time", "live_preview"}:
            runtime_scope = (
                "prepare_time"
                if execution_strategy in {"template_driven_bundle", "template_driven_deck"}
                else "live_preview"
            )
        normalized_item = dict(item)
        normalized_item["id"] = parameter_id
        normalized_item.setdefault("name", parameter_id)
        normalized_item["type"] = parameter_type
        normalized_item["default"] = item.get("default")
        normalized_item["enum_values"] = [value for value in enum_values if value is not None]
        normalized_item["description"] = str(item.get("description") or "").strip() or None
        normalized_item["runtime_scope"] = runtime_scope
        normalized.append(normalized_item)
    return normalized


def _normalize_skill_mode(raw_mode: Any, skill_id: str) -> str:
    text = str(raw_mode or "").strip().lower()
    if text in {"prototype", "deck", "image", "video", "audio", "utility", "design-system"}:
        return text
    if skill_id == "docx":
        return "document"
    if skill_id == "xlsx":
        return "spreadsheet"
    if skill_id == "pptx":
        return "document"
    if text in {"document", "spreadsheet"}:
        return text
    return "other"


def _infer_artifact_mode(skill_id: str, mode: str) -> str | None:
    for artifact_mode, skill_ids in _ENTRY_CANDIDATES.items():
        if skill_id in skill_ids:
            return artifact_mode
    for artifact_mode, skill_modes in _ARTIFACT_MODE_TO_SKILL_MODES.items():
        if mode in skill_modes:
            return artifact_mode
    return None


def _existing_relative_dirs(skill_dir: Path, *candidates: str) -> list[str]:
    existing: list[str] = []
    for candidate in candidates:
        normalized = candidate.replace("\\", "/").strip().strip("/")
        if not normalized:
            continue
        if (skill_dir / normalized).is_dir():
            existing.append(normalized)
    return existing


def _existing_relative_files(skill_dir: Path, *candidates: str) -> list[str]:
    existing: list[str] = []
    for candidate in candidates:
        normalized = candidate.replace("\\", "/").strip().strip("/")
        if not normalized:
            continue
        if (skill_dir / normalized).is_file():
            existing.append(normalized)
    return existing


def _detect_execution_strategy(
    *,
    skill_id: str,
    skill_dir: Path,
    mode: str,
    artifact_mode: str | None,
    preview_entry: str | None,
) -> RuntimeStrategy:
    if artifact_mode in {"image", "video"} or mode in {"image", "video", "audio"}:
        return "media_pipeline"
    if artifact_mode in {"document", "spreadsheet"} or skill_id in {"docx", "pptx", "xlsx"} or mode in {"document", "spreadsheet"}:
        return "office_pipeline"
    if mode == "utility":
        return "utility_pipeline"

    has_templates_dir = (skill_dir / "templates").is_dir()
    has_full_decks = (skill_dir / "templates" / "full-decks").is_dir()
    has_fragments = (skill_dir / "templates" / "single-page").is_dir()
    has_authoring_guide = (skill_dir / "references" / "authoring-guide.md").is_file()
    has_example = (skill_dir / "example.html").is_file()
    has_input_schema = (skill_dir / "schema.ts").is_file() or (skill_dir / "inputs.example.json").is_file()

    if mode == "deck":
        if has_templates_dir or has_full_decks or has_fragments or has_authoring_guide or has_example or preview_entry:
            return "template_driven_deck"
        return "free_generate"

    if has_input_schema and has_example and ((skill_dir / "assets").is_dir() or (skill_dir / "styles.css").is_file()):
        return "template_driven_bundle"

    return "free_generate"


def _load_skill_from_dir(skill_dir: Path) -> SkillDefinition | None:
    if not skill_dir.is_dir() or skill_dir.name.startswith("_"):
        return None
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.exists():
        return None

    try:
        text = skill_file.read_text(encoding="utf-8")
        parsed = parse_skill_markdown(text)
        meta = parsed.meta
        body = parsed.body
        frontmatter_status = parsed.frontmatter_status
    except Exception:
        logger.warning("Failed to load skill %s", skill_dir.name, exc_info=True)
        return None

    skill_id = skill_dir.name
    en_file = skill_dir / "SKILL.en.md"
    if en_file.exists():
        try:
            en_text = en_file.read_text(encoding="utf-8")
            en_body = parse_skill_markdown(en_text).body
        except Exception:
            en_body = body
    else:
        en_body = body

    tools_list = _coerce_list(meta.get("tools"))
    od_meta = meta.get("od") if isinstance(meta.get("od"), dict) else {}
    preview_meta = od_meta.get("preview") if isinstance(od_meta.get("preview"), dict) else {}
    design_system_meta = od_meta.get("design_system") if isinstance(od_meta.get("design_system"), dict) else {}
    craft_meta = od_meta.get("craft") if isinstance(od_meta.get("craft"), dict) else {}

    preview_entry = str(
        preview_meta.get("entry")
        or meta.get("preview_entry")
        or ""
    ).strip() or None
    raw_outputs = meta.get("outputs") if isinstance(meta.get("outputs"), dict) else (
        od_meta.get("outputs") if isinstance(od_meta.get("outputs"), dict) else {}
    )
    primary_output = str(
        (raw_outputs.get("primary") if isinstance(raw_outputs, dict) else None)
        or preview_entry
        or ""
    ).strip() or None
    catalog_meta = derive_catalog_metadata(
        skill_id=skill_id,
        skill_dir=skill_dir,
        raw_mode=od_meta.get("mode"),
        raw_surface=od_meta.get("surface"),
        description=str(meta.get("description", "")),
        body=body,
        preview_entry=preview_entry,
        primary_output=primary_output,
    )
    imported_template_meta = build_imported_template_metadata(
        skill_id,
        skill_dir,
        body=body,
    )
    mode = catalog_meta.mode
    artifact_mode = catalog_meta.artifact_mode
    classification = classify_skill(
        skill_id=skill_id,
        artifact_mode=artifact_mode,
        mode=mode,
    )
    mode = classification.mode_override or mode
    artifact_mode = classification.artifact_mode
    template_roots = list(catalog_meta.template_roots)
    fragment_roots = list(catalog_meta.fragment_roots)
    authoring_guides = list(catalog_meta.authoring_guides)
    scaffold_scripts = list(catalog_meta.scaffold_scripts)
    execution_strategy = _detect_execution_strategy(
        skill_id=skill_id,
        skill_dir=skill_dir,
        mode=mode,
        artifact_mode=artifact_mode,
        preview_entry=preview_entry,
    )
    inputs = meta.get("inputs") if isinstance(meta.get("inputs"), list) else (
        od_meta.get("inputs") if isinstance(od_meta.get("inputs"), list) else []
    )
    outputs = raw_outputs if isinstance(raw_outputs, dict) else {}
    parameters = meta.get("parameters")
    if not isinstance(parameters, (list, dict)):
        parameters = od_meta.get("parameters")
    directions = _detect_direction_definitions(skill_dir, meta, od_meta)
    seed_assets = _coerce_seed_assets(
        od_meta.get("seed_assets")
        if od_meta.get("seed_assets") is not None
        else meta.get("seed_assets")
    )
    normalized_parameters = _normalize_parameter_contracts(
        parameters,
        execution_strategy=execution_strategy,
    )

    return SkillDefinition(
        id=skill_id,
        name=str(meta.get("display_name", meta.get("name", skill_id))),
        name_en=str(meta.get("display_name_en", meta.get("name_en", skill_id))),
        name_zh=str(meta.get("display_name_zh", meta.get("name_zh", meta.get("display_name", meta.get("name", skill_id))))),
        description=str(meta.get("description", "")),
        description_en=str(meta.get("description_en", meta.get("description", ""))),
        description_zh=str(meta.get("description_zh", meta.get("description", ""))),
        system_prompt=body,
        system_prompt_en=en_body,
        tools=tools_list,
        disabled_tools=_coerce_list(meta.get("disabled_tools")),
        icon=str(meta.get("icon", "")),
        color=str(meta.get("color", "")),
        skill_dir=skill_dir.resolve(),
        triggers=_coerce_list(meta.get("triggers")),
        mode=mode,
        surface=str(od_meta.get("surface") or "").strip() or None,
        platform=str(od_meta.get("platform") or "").strip() or None,
        scenario=str(od_meta.get("scenario") or "").strip() or None,
        default_for=_coerce_list(od_meta.get("default_for")),
        featured=int(od_meta.get("featured")) if str(od_meta.get("featured") or "").strip().isdigit() else None,
        preview=SkillPreview(
            type=str(preview_meta.get("type") or "html"),
            entry=preview_entry,
            reload=str(preview_meta.get("reload") or "").strip() or None,
        ),
        design_system=SkillDesignSystem(
            requires=bool(design_system_meta.get("requires", False)),
            generates=bool(design_system_meta.get("generates", False)),
            sections=_coerce_list(design_system_meta.get("sections")),
        ),
        craft=SkillCraft(requires=_coerce_list(craft_meta.get("requires"))),
        inputs=inputs,
        outputs=outputs,
        example_prompt=str(od_meta.get("example_prompt") or meta.get("example_prompt") or "").strip() or None,
        upstream=str(od_meta.get("upstream") or "").strip() or None,
        artifact_mode=artifact_mode,
        execution_strategy=execution_strategy,
        preview_entry=preview_entry,
        primary_output=primary_output,
        template_roots=template_roots,
        fragment_roots=fragment_roots,
        authoring_guides=authoring_guides,
        scaffold_scripts=scaffold_scripts,
        input_schema=inputs if isinstance(inputs, list) else [],
        parameters=normalized_parameters,
        output_schema=outputs if isinstance(outputs, dict) else {},
        directions=directions,
        seed_assets=seed_assets,
        metadata_health={
            "frontmatter_status": frontmatter_status,
        },
        runtime_capabilities={
            **dict(catalog_meta.runtime_capabilities),
            **imported_template_meta.to_runtime_capabilities(),
            "semantic_kind": classification.semantic_kind,
            "rollout_state": classification.rollout_state,
            "selection_enabled": classification.selection_enabled,
            "phase_enabled": classification.phase_enabled,
            "classification_notes": classification.notes,
            "home_visible": classification.home_visible,
            "canvas_visible": classification.canvas_visible,
            "canvas_only": classification.canvas_only,
            "canvas_default": classification.canvas_default,
            "canvas_explicit": classification.canvas_explicit,
            "helper_eligible": classification.helper_eligible,
            "default_route_for": classification.default_route_for,
            "default_route_priority": classification.default_route_priority,
        },
    )


def _load_skill_by_id(skill_id: str) -> SkillDefinition | None:
    normalized = canonical_skill_id(skill_id)
    if not normalized or normalized.startswith("_") or "/" in normalized or "\\" in normalized:
        return None
    return _load_skill_from_dir(_SKILLS_DIR / normalized)


def _load_skills_from_md() -> dict[str, SkillDefinition]:
    skills: dict[str, SkillDefinition] = {}

    for skill_dir in sorted(_SKILLS_DIR.iterdir()):
        skill = _load_skill_from_dir(skill_dir)
        if skill is not None:
            skills[skill.id] = skill

    return skills


SKILLS: dict[str, SkillDefinition] | None = None
_SKILLS_FULLY_LOADED = False
_SKILLS_GENERATION = 1


def _ensure_skills_loaded() -> dict[str, SkillDefinition]:
    global SKILLS, _SKILLS_FULLY_LOADED
    if not _SKILLS_FULLY_LOADED:
        loaded = _load_skills_from_md()
        if SKILLS:
            loaded.update(SKILLS)
        SKILLS = loaded
        _SKILLS_FULLY_LOADED = True
    return SKILLS


def get_skill(skill_id: str | None) -> SkillDefinition | None:
    global SKILLS
    normalized = canonical_skill_id(skill_id)
    if not normalized:
        return None
    if SKILLS is None:
        SKILLS = {}
    existing = SKILLS.get(normalized)
    if existing is not None:
        return existing
    skill = _load_skill_by_id(normalized)
    if skill is not None:
        SKILLS[skill.id] = skill
    return skill


def list_skills() -> list[SkillDefinition]:
    return list(_ensure_skills_loaded().values())


def list_skills_for_mode(
    artifact_mode: str,
    *,
    selectable_only: bool = False,
    home_visible_only: bool = False,
) -> list[SkillDefinition]:
    normalized = str(artifact_mode or "").strip().lower()
    skills = [skill for skill in _ensure_skills_loaded().values() if skill.artifact_mode == normalized]
    if selectable_only:
        skills = [skill for skill in skills if is_skill_selectable(skill)]
    if home_visible_only:
        skills = [skill for skill in skills if is_skill_home_visible(skill)]
    return skills


def skills_generation() -> int:
    return _SKILLS_GENERATION


def reload_skills() -> None:
    global SKILLS, _SKILLS_FULLY_LOADED, _SKILLS_GENERATION
    SKILLS = None
    _SKILLS_FULLY_LOADED = False
    _SKILLS_GENERATION += 1
    try:
        from app.services.agent_harness.catalog import invalidate_agent_catalog_cache_sync

        invalidate_agent_catalog_cache_sync()
    except Exception:
        logger.debug("Failed to invalidate agent catalog cache after skill reload", exc_info=True)
