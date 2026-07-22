from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .parser import infer_mode, normalize_surface


ENTRY_CANDIDATES: dict[str, set[str]] = {
    "web": {"web", "web-prototype", "dashboard", "docs-page", "pricing-page", "saas-landing"},
    "document": {"docx", "design-brief", "pm-spec", "eng-runbook", "finance-report"},
    "spreadsheet": {"xlsx"},
    "slides": {"pptx", "html-ppt", "simple-deck", "replit-deck", "guizang-ppt", "weekly-update"},
    "image": {"image-poster"},
    "video": {"video-shortform"},
}
ARTIFACT_MODE_TO_SKILL_MODES: dict[str, set[str]] = {
    "web": {"prototype", "template"},
    "document": {"document", "design-system", "prototype"},
    "spreadsheet": {"spreadsheet"},
    "slides": {"deck", "document"},
    "image": {"image"},
    "video": {"video"},
}


@dataclass(slots=True)
class OpenDesignCatalogMetadata:
    mode: str
    artifact_mode: str | None
    template_roots: list[str] = field(default_factory=list)
    fragment_roots: list[str] = field(default_factory=list)
    authoring_guides: list[str] = field(default_factory=list)
    scaffold_scripts: list[str] = field(default_factory=list)
    execution_strategy: str = "free_generate"
    runtime_capabilities: dict[str, Any] = field(default_factory=dict)


def derive_catalog_metadata(
    *,
    skill_id: str,
    skill_dir: Path,
    raw_mode: Any,
    raw_surface: Any = None,
    description: str | None = None,
    body: str | None = None,
    preview_entry: str | None,
    primary_output: str | None = None,
) -> OpenDesignCatalogMetadata:
    mode = normalize_skill_mode(
        raw_mode,
        skill_id,
        raw_surface=raw_surface,
        description=description,
        body=body,
    )
    surface = normalize_surface(raw_surface, mode)
    artifact_mode = infer_artifact_mode(skill_id, mode, surface=surface, primary_output=primary_output)
    template_roots = existing_relative_dirs(skill_dir, "templates", "examples")
    fragment_roots = existing_relative_dirs(skill_dir, "templates/single-page", "templates/fragments")
    authoring_guides = existing_relative_files(
        skill_dir,
        "references/authoring-guide.md",
        "references/presenter-mode.md",
        "README.md",
        "README.zh-CN.md",
    )
    scaffold_scripts = existing_relative_files(skill_dir, "scripts/new-deck.sh", "scripts/render.sh")
    execution_strategy = detect_execution_strategy(
        skill_id=skill_id,
        skill_dir=skill_dir,
        mode=mode,
        artifact_mode=artifact_mode,
        preview_entry=preview_entry,
    )
    return OpenDesignCatalogMetadata(
        mode=mode,
        artifact_mode=artifact_mode,
        template_roots=template_roots,
        fragment_roots=fragment_roots,
        authoring_guides=authoring_guides,
        scaffold_scripts=scaffold_scripts,
        execution_strategy=execution_strategy,
        runtime_capabilities={
            "has_templates_dir": (skill_dir / "templates").is_dir(),
            "has_full_decks": (skill_dir / "templates" / "full-decks").is_dir(),
            "has_fragment_library": bool(fragment_roots),
            "has_authoring_guide": any(path.endswith("authoring-guide.md") for path in authoring_guides),
            "has_scaffold_script": any(path.endswith("new-deck.sh") for path in scaffold_scripts),
        },
    )


def normalize_skill_mode(
    raw_mode: Any,
    skill_id: str,
    *,
    raw_surface: Any = None,
    description: str | None = None,
    body: str | None = None,
) -> str:
    text = str(raw_mode or "").strip().lower()
    if text in {"prototype", "template", "deck", "image", "video", "audio", "utility", "design-system"}:
        return text
    if skill_id == "docx":
        return "document"
    if skill_id == "xlsx":
        return "spreadsheet"
    if skill_id == "pptx":
        return "document"
    if text in {"document", "spreadsheet"}:
        return text
    inferred = infer_mode(description=description, body=body)
    if str(raw_surface or "").strip().lower() == "web" and inferred in {"image", "video", "audio"}:
        inferred = "template" if "template" in f"{description or ''}\n{body or ''}".lower() else "prototype"
    return inferred if inferred in {"prototype", "template", "deck", "image", "video", "audio", "design-system"} else "other"


def infer_artifact_mode(
    skill_id: str,
    mode: str,
    *,
    surface: str | None = None,
    primary_output: str | None = None,
) -> str | None:
    for artifact_mode, skill_ids in ENTRY_CANDIDATES.items():
        if skill_id in skill_ids:
            return artifact_mode
    output_name = str(primary_output or "").strip().lower()
    if output_name.endswith(".docx"):
        return "document"
    if output_name.endswith(".xlsx"):
        return "spreadsheet"
    if output_name.endswith(".pptx"):
        return "slides"
    if surface in {"image", "video"}:
        return surface
    if surface == "web":
        if mode in {"prototype", "template", "design-system", "other"}:
            return "web"
    for artifact_mode, skill_modes in ARTIFACT_MODE_TO_SKILL_MODES.items():
        if mode in skill_modes:
            return artifact_mode
    return None


def existing_relative_dirs(skill_dir: Path, *candidates: str) -> list[str]:
    return [candidate for candidate in candidates if (skill_dir / candidate).is_dir()]


def existing_relative_files(skill_dir: Path, *candidates: str) -> list[str]:
    return [candidate for candidate in candidates if (skill_dir / candidate).is_file()]


def detect_execution_strategy(
    *,
    skill_id: str,
    skill_dir: Path,
    mode: str,
    artifact_mode: str | None,
    preview_entry: str | None,
) -> str:
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
