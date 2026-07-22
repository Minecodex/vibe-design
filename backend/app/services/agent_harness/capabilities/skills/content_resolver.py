from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .markdown_parser import parse_skill_markdown

_HELPER_DIRS = ("assets", "references", "scripts")
_HELPER_FILES = ("example.html", "inputs.example.json", "schema.ts")


@dataclass(slots=True)
class ResolvedSkillContent:
    body: str
    resolved_language: str
    source_root: Path
    frontmatter_status: str
    helper_files: list[str]
    used_runtime_root: bool


def resolve_skill_content(
    skill: Any,
    *,
    language: str,
    runtime_skill_dir: Path | None = None,
) -> ResolvedSkillContent:
    runtime_root = runtime_skill_dir.resolve() if isinstance(runtime_skill_dir, Path) and runtime_skill_dir.is_dir() else None
    raw_source_root = getattr(skill, "skill_dir", None)
    source_root = Path(raw_source_root).resolve() if raw_source_root else None
    if source_root is None and runtime_root is None:
        raise FileNotFoundError("Skill root is unavailable")
    if runtime_root is None and source_root is not None and not source_root.is_dir():
        raise FileNotFoundError("Skill root is unavailable")
    selected_root = runtime_root or source_root
    if selected_root is None:
        raise FileNotFoundError("Skill root is unavailable")
    used_runtime_root = runtime_root is not None

    normalized_language = str(language or "").strip().lower()
    selected_language = "zh"
    selected_path = selected_root / "SKILL.md"
    if normalized_language.startswith("en"):
        english_path = selected_root / "SKILL.en.md"
        if english_path.is_file():
            selected_language = "en"
            selected_path = english_path

    text = selected_path.read_text(encoding="utf-8")
    parsed = parse_skill_markdown(text)
    return ResolvedSkillContent(
        body=parsed.body,
        resolved_language=selected_language,
        source_root=selected_root,
        frontmatter_status=parsed.frontmatter_status,
        helper_files=_discover_helper_files(selected_root),
        used_runtime_root=used_runtime_root,
    )


def _discover_helper_files(root: Path) -> list[str]:
    helper_files: list[str] = []
    for name in _HELPER_DIRS:
        if (root / name).is_dir():
            helper_files.append(name)
    for name in _HELPER_FILES:
        if (root / name).is_file():
            helper_files.append(name)
    return helper_files
