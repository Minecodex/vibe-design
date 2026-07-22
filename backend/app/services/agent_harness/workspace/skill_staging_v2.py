from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any


def stage_active_skill_v2(ctx, source_skill_dir: str | Path, *, linked_master_ids: list[str] | None = None) -> dict[str, Any]:
    """Copy the active skill into the v2 visible skill/ root.

    The copy is replaced wholesale and symlinks are dereferenced by copytree so
    the staged skill is self-contained and cannot write back to source files.
    """

    source = Path(source_skill_dir).resolve()
    target_root = getattr(ctx, "skill_dir", None)
    if target_root is None:
        conversation_dir = getattr(ctx, "conversation_dir", None)
        if conversation_dir is not None:
            target_root = Path(conversation_dir) / "skill"
        else:
            work_dir = getattr(ctx, "work_dir", None)
            target_root = Path(work_dir).parent / "skill" if work_dir is not None else Path.cwd() / "skill"
        ctx.skill_dir = Path(target_root)
    target = Path(target_root).resolve()
    if not source.exists() or not source.is_dir():
        return {"ok": False, "path": "skill", "reason_code": "source_missing", "reason": "Skill source is not a directory."}
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, symlinks=False)
    linked = _stage_linked_master_templates(source, target, linked_master_ids=linked_master_ids)
    ctx.active_skill_dir = target
    ctx.skill_runtime_dir = target
    return {
        "ok": True,
        "path": "skill",
        "source": str(source),
        "target": str(target),
        "linked_templates": linked,
    }


def _stage_linked_master_templates(source: Path, target: Path, *, linked_master_ids: list[str] | None = None) -> list[str]:
    """Expose linked masters inside the staged skill root."""

    linked: list[str] = []
    master_ids = _linked_master_ids(source, linked_master_ids=linked_master_ids)

    for master_id in master_ids:
        master_source = source.parent / master_id
        if not master_source.is_dir() or not (master_source / "SKILL.md").is_file():
            continue
        master_target = target / "_linked" / master_id
        if master_target.exists():
            shutil.rmtree(master_target)
        master_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(master_source, master_target, symlinks=False)
        linked.append(master_id)
    return linked


def _linked_master_ids(source: Path, *, linked_master_ids: list[str] | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    def add(value: str) -> None:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            return
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", cleaned):
            return
        seen.add(cleaned)
        out.append(cleaned)

    for item in list(linked_master_ids or []):
        add(str(item))

    skill_path = source / "SKILL.md"
    try:
        body = skill_path.read_text(encoding="utf-8")
    except Exception:
        body = ""
    for match in re.finditer(r"(?:\.\./|skills[/\\]|\.od-skills[/\\])([A-Za-z0-9_-]+)[/\\]SKILL\.md", body):
        add(match.group(1))
    return out
