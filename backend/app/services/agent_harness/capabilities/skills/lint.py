from __future__ import annotations

from pathlib import Path


FORBIDDEN_SKILL_PHRASES = (
    "files/ is removed",
    "legacy final-output",
    "Path Routing In Harness",
    "Harness Versioned File Publishing",
    "runtime capability profile",
    "Runtime capability profile",
    "default author",
    "Default author",
    "HARNESS_AUTHOR_NAME",
    "$SCRATCH_DIR",
    "$GENERATED_DIR",
    "$CONVERSATION_DIR",
    "sandbox cwd",
    "publishing.",
    "before publishing",
    "_".join(("start", "file", "edit")),
    "_".join(("publish", "file")),
    "_".join(("list", "workspace", "items")),
)

FORBIDDEN_SYSTEM_PROMPT_PHRASES = (
    ".work/generated/<run",
    "_".join(("start", "file", "edit")),
    "_".join(("publish", "file")),
    "_".join(("list", "workspace", "items")),
)

_WORKSPACE_CONTRACT_REQUIRED_SKILLS = {"docx", "pptx", "xlsx", "web"}


def lint_skill_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    for phrase in FORBIDDEN_SKILL_PHRASES:
        if phrase in text:
            errors.append(f"{path}: duplicates workspace contract phrase {phrase!r}")
    if path.parent.name in _WORKSPACE_CONTRACT_REQUIRED_SKILLS and "workspace contract" not in text.lower():
        errors.append(f"{path}: must reference the workspace contract briefly")
    return errors


def lint_all_skills(skills_dir: Path) -> dict[str, list[str]]:
    return {
        str(path): errors
        for path in sorted(skills_dir.glob("*/SKILL.md"))
        if (errors := lint_skill_markdown(path))
    }


def lint_system_prompt(text: str) -> list[str]:
    errors: list[str] = []
    for phrase in FORBIDDEN_SYSTEM_PROMPT_PHRASES:
        if phrase in text:
            errors.append(f"system prompt contains forbidden phrase {phrase!r}")
    return errors
