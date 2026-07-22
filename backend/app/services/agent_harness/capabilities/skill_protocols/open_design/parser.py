from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MEDIA_MODES = {"image", "video", "audio"}
PREFLIGHT_PATHS = (
    "assets/template.html",
    "references/layouts.md",
    "references/themes.md",
    "references/components.md",
    "references/checklist.md",
    "references/html-in-canvas.md",
)


@dataclass(slots=True)
class OpenDesignSkillFacts:
    mode: str
    surface: str
    has_seed_template: bool
    preflight_paths: list[str] = field(default_factory=list)
    side_files: list[str] = field(default_factory=list)
    checklist_path: str | None = None


def infer_mode(*, description: str | None, body: str | None) -> str:
    text = f"{description or ''}\n{body or ''}".lower()
    if any(token in text for token in ("image", "poster")):
        return "image"
    if any(token in text for token in ("video", "motion")):
        return "video"
    if any(token in text for token in ("audio", "music")):
        return "audio"
    if any(token in text for token in ("ppt", "deck", "slide")):
        return "deck"
    if "design-system" in text or "design system" in text:
        return "design-system"
    if "template" in text:
        return "template"
    return "prototype"


def normalize_surface(raw_surface: Any, mode: str) -> str:
    surface = str(raw_surface or "").strip().lower()
    if surface in {"web", "image", "video", "audio"}:
        return surface
    return mode if mode in MEDIA_MODES else "web"


def parse_open_design_facts(skill: Any) -> OpenDesignSkillFacts:
    body = str(getattr(skill, "system_prompt", "") or "")
    mode = str(getattr(skill, "mode", "") or "").strip().lower()
    if not mode or mode == "other":
        mode = infer_mode(description=getattr(skill, "description", None), body=body)
    surface = normalize_surface(getattr(skill, "surface", None), mode)
    preflight_paths = [path for path in PREFLIGHT_PATHS if path in body]
    has_seed_template = "assets/template.html" in preflight_paths
    checklist_path = "references/checklist.md" if "references/checklist.md" in preflight_paths else None
    side_files = _discover_side_files(getattr(skill, "skill_dir", None))
    return OpenDesignSkillFacts(
        mode=mode,
        surface=surface,
        has_seed_template=has_seed_template,
        preflight_paths=preflight_paths,
        side_files=side_files,
        checklist_path=checklist_path,
    )


def _discover_side_files(skill_dir: Any) -> list[str]:
    if skill_dir is None:
        return []
    root = Path(skill_dir)
    discovered: list[str] = []
    for name in ("assets", "references", "scripts"):
        if (root / name).exists():
            discovered.append(name)
    for name in ("example.html", "inputs.example.json", "schema.ts"):
        if (root / name).is_file():
            discovered.append(name)
    return discovered
