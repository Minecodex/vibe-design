from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.agent_harness.runtime.context_hygiene import is_low_signal_dir_name

from . import get_skill
from .content_resolver import resolve_skill_content

_MAX_SKILL_ENTRIES = 4
_MAX_SIDE_FILES = 6
_MAX_NOTABLE_PATHS = 3
_SCAN_FILE_SUFFIXES = {".md", ".txt", ".json", ".py", ".ts", ".js", ".html", ".yaml", ".yml"}


def build_active_skill_manifest(
    *,
    language: str,
    skill: Any | None,
    skill_id: str | None,
    prompt_body: str | None,
    runtime_skill_dir: Path | None,
    runtime_contract: dict[str, Any] | None,
) -> dict[str, Any] | None:
    entries: list[dict[str, Any]] = []
    if skill is not None or str(prompt_body or "").strip() or str(skill_id or "").strip():
        entries.append(
            _build_skill_entry(
                language=language,
                skill=skill,
                skill_id=skill_id,
                prompt_body=prompt_body,
                runtime_skill_dir=runtime_skill_dir,
                activation_role="selected_skill",
            )
        )
    for item in list((runtime_contract or {}).get("internal_hidden_skills") or [])[: _MAX_SKILL_ENTRIES - len(entries)]:
        if not isinstance(item, dict):
            continue
        helper_id = str(item.get("id") or "").strip()
        if not helper_id:
            continue
        helper_skill = get_skill(helper_id)
        entries.append(
            _build_skill_entry(
                language=language,
                skill=helper_skill,
                skill_id=getattr(helper_skill, "id", None) or helper_id,
                prompt_body=None,
                runtime_skill_dir=None,
                activation_role="internal_helper",
            )
        )
    entries = [entry for entry in entries if entry]
    if not entries:
        return None
    return {
        "version": 1,
        "selected_skill_id": str(skill_id or getattr(skill, "id", None) or "").strip() or None,
        "skills": entries[:_MAX_SKILL_ENTRIES],
    }


def _build_skill_entry(
    *,
    language: str,
    skill: Any | None,
    skill_id: str | None,
    prompt_body: str | None,
    runtime_skill_dir: Path | None,
    activation_role: str,
) -> dict[str, Any]:
    resolved_content = None
    if skill is not None:
        try:
            resolved_content = resolve_skill_content(
                skill,
                language=language,
                runtime_skill_dir=runtime_skill_dir,
            )
        except Exception:
            resolved_content = None

    resolved_body = str(getattr(resolved_content, "body", "") or prompt_body or "").strip()
    source_root = getattr(resolved_content, "source_root", None)
    if source_root is None and getattr(skill, "skill_dir", None) is not None:
        try:
            source_root = Path(getattr(skill, "skill_dir")).resolve()
        except Exception:
            source_root = None
    helper_files = list(getattr(resolved_content, "helper_files", []) or [])
    used_runtime_root = bool(getattr(resolved_content, "used_runtime_root", False))
    display_name = str(
        getattr(skill, "name_en", None)
        or getattr(skill, "name", None)
        or getattr(skill, "name_zh", None)
        or skill_id
        or "skill"
    ).strip()
    purpose = _first_line(
        resolved_body,
        fallback=str(
            getattr(skill, "description_en", None)
            or getattr(skill, "description", None)
            or getattr(skill, "description_zh", None)
            or display_name
        ).strip(),
    )
    when_to_use = _first_line(
        getattr(skill, "description_en", None)
        or getattr(skill, "description", None)
        or getattr(skill, "description_zh", None)
        or "",
        fallback=purpose,
    )
    available_side_files = _available_side_files(source_root if isinstance(source_root, Path) else None)
    constraints = [
        'Read skill inputs through the read-only `skill/` root; do not treat skill-local files as final output paths.',
        "Read side files only when the loaded skill body or current task requires omitted details.",
    ]
    return {
        "id": str(skill_id or getattr(skill, "id", None) or "").strip() or None,
        "name": display_name,
        "activation_role": activation_role,
        "purpose": purpose,
        "when_to_use": when_to_use,
        "available_side_files": available_side_files,
        "side_file_index": available_side_files,
        "helper_files": helper_files[:_MAX_SIDE_FILES],
        "must_follow_constraints": constraints,
        "used_runtime_root": used_runtime_root,
        "source_root": "skill",
    }


def _available_side_files(source_root: Path | None) -> list[str]:
    files: list[str] = []
    if source_root is None or not source_root.exists():
        return files
    direct_helper_files = ["example.html", "inputs.example.json", "schema.ts"]
    for name in direct_helper_files:
        if len(files) >= _MAX_SIDE_FILES:
            break
        if (source_root / name).is_file():
            files.append(f"skill/{name}")

    for folder_name in ("references", "scripts", "assets"):
        folder = source_root / folder_name
        if not folder.is_dir() or len(files) >= _MAX_SIDE_FILES:
            continue
        files.extend(_scan_folder(folder, prefix=f"skill/{folder_name}"))
        files = files[:_MAX_SIDE_FILES]
    return _dedupe(files)[:_MAX_SIDE_FILES]


def _scan_folder(folder: Path, *, prefix: str) -> list[str]:
    candidates: list[str] = []
    for child in sorted(folder.iterdir(), key=lambda item: (not item.is_file(), item.name.lower())):
        if is_low_signal_dir_name(child.name):
            continue
        if child.is_file():
            if child.suffix.lower() in _SCAN_FILE_SUFFIXES:
                candidates.append(f"{prefix}/{child.name}")
        elif child.is_dir():
            nested = next(
                (
                    grandchild
                    for grandchild in sorted(child.iterdir(), key=lambda item: item.name.lower())
                    if grandchild.is_file() and grandchild.suffix.lower() in _SCAN_FILE_SUFFIXES
                ),
                None,
            )
            if nested is not None:
                candidates.append(f"{prefix}/{child.name}/{nested.name}")
            else:
                candidates.append(f"{prefix}/{child.name}")
        if len(candidates) >= _MAX_NOTABLE_PATHS:
            break
    return candidates


def _first_line(value: Any, *, fallback: str = "") -> str:
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip().lstrip("#").strip().lstrip("-").strip()
        if line and line != "---":
            return line[:240]
    return fallback[:240]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out
