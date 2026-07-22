from __future__ import annotations

import shutil
from pathlib import Path

from ..base import PreparedWorkspace


def materialize_open_design_prepared_workspace(
    *,
    skill_root: Path,
    work_dir: Path,
    candidate_name: str,
    family: str,
    strategy: str,
    skill_id: str,
    entry_file: str | None = None,
) -> PreparedWorkspace:
    artifact_work_dir = _fresh_artifact_work_dir(work_dir, candidate_name)
    resolved_entry = _safe_entry_file(entry_file) or "index.html"
    copied_files: list[str] = []
    source_template = skill_root / "assets" / "template.html"
    entry_target = artifact_work_dir / resolved_entry
    if source_template.is_file():
        entry_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_template, entry_target)
        copied_files.append(entry_target.relative_to(artifact_work_dir).as_posix())
    else:
        entry_target.parent.mkdir(parents=True, exist_ok=True)
    return PreparedWorkspace(
        family=family,
        strategy=strategy or family,
        skill_id=skill_id,
        artifact_work_root=artifact_work_dir.name,
        entry_file=resolved_entry,
        selected_template=None,
        source_root="skill",
        copied_files=sorted(set(copied_files)),
    )


def materialize_seed_assets(
    *,
    skill_root: Path,
    work_dir: Path,
    candidate_name: str,
    seed_assets: list[object],
    entry_file: str | None,
) -> PreparedWorkspace | None:
    artifact_work_dir = _fresh_artifact_work_dir(work_dir, candidate_name)
    copied: list[str] = []
    for asset in seed_assets:
        if isinstance(asset, dict):
            relative_path = str(asset.get("path") or asset.get("file") or "").strip()
        else:
            relative_path = str(asset or "").strip()
        if not relative_path:
            continue
        source_path = skill_root / relative_path
        if not source_path.exists():
            continue
        destination = artifact_work_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source_path.is_dir():
            shutil.copytree(source_path, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, destination)
        copied.append(relative_path.replace("\\", "/"))
    resolved_entry = _safe_entry_file(entry_file)
    if not copied or not resolved_entry:
        return None
    return PreparedWorkspace(
        family="open_design_seed_assets",
        strategy="free_generate",
        artifact_work_root=artifact_work_dir.name,
        entry_file=resolved_entry,
        copied_files=sorted(set(copied)),
    )


def _fresh_artifact_work_dir(work_dir: Path, candidate_name: str) -> Path:
    artifact_work_dir = (work_dir / candidate_name).resolve()
    if artifact_work_dir.exists():
        shutil.rmtree(artifact_work_dir)
    artifact_work_dir.mkdir(parents=True, exist_ok=True)
    return artifact_work_dir


def _safe_entry_file(entry_file: str | None) -> str | None:
    normalized = str(entry_file or "").replace("\\", "/").strip().strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        return None
    if not normalized.lower().endswith((".html", ".htm")):
        return None
    return normalized
