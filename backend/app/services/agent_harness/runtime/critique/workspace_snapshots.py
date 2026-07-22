from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .contracts import CritiqueEvidence, CritiqueFinding, CritiqueWarning
from .work_root import normalize_relpath
from .work_root import safe_work_root as _safe_work_root
from .work_root import work_root_from_entry

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

_SNAPSHOT_EXCLUDED_PARTS = frozenset({".cache", ".git", "node_modules", "__pycache__"})


def _safe_component(value: str, *, label: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip().strip("/")
    if not normalized or "/" in normalized or normalized in {".", ".."}:
        raise ValueError(f"{label} must be a single safe path component")
    return normalized


def _require_safe_work_root(value: str | None) -> str:
    safe = _safe_work_root(value)
    if not safe:
        raise ValueError("artifact_work_root must be a single safe path component")
    return safe


def _work_root_from_snapshot(snapshot: Path) -> str:
    """Read the canonical work root the snapshot was written with (self-describing)."""
    round_path = snapshot / "round.json"
    if not round_path.is_file():
        return ""
    try:
        data = json.loads(round_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ""
    if not isinstance(data, dict):
        return ""
    return _safe_work_root(data.get("artifact_work_root"))


def _is_excluded_snapshot_path(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return any(part in _SNAPSHOT_EXCLUDED_PARTS for part in relative.parts)


def _copytree_ignore(root: str, names: list[str]) -> set[str]:
    root_path = Path(root)
    ignored: set[str] = set()
    for name in names:
        if name in _SNAPSHOT_EXCLUDED_PARTS:
            ignored.add(name)
            continue
        candidate = root_path / name
        if candidate.is_symlink():
            ignored.add(name)
    return ignored


def _assert_no_symlinks(root: Path) -> None:
    if root.is_symlink():
        raise ValueError("snapshot source must not contain symlink paths")
    for item in root.rglob("*"):
        if _is_excluded_snapshot_path(item, root):
            continue
        if item.is_symlink():
            raise ValueError("snapshot source must not contain symlink paths")


def _assert_inside(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("snapshot path escapes conversation directory") from exc
    return resolved


def snapshot_round(
    ctx: "HarnessContext",
    *,
    critique_run_id: str,
    round_number: int,
    artifact_work_root: str,
    active_entry: str,
    manifest: dict[str, Any],
    composite: float,
    must_fix_count: int,
    findings: tuple[CritiqueFinding, ...],
    evidence: tuple[CritiqueEvidence, ...] = (),
    warnings: tuple[CritiqueWarning | dict[str, Any], ...] = (),
) -> Path:
    if round_number < 1:
        raise ValueError("round_number must be positive")
    safe_run_id = _safe_component(critique_run_id, label="critique_run_id")
    safe_work_root = _require_safe_work_root(artifact_work_root)
    normalized_entry = normalize_relpath(active_entry)
    if not normalized_entry.startswith(f"{safe_work_root}/"):
        raise ValueError("active_entry must stay inside artifact work root")

    conversation_dir = Path(ctx.conversation_dir).resolve()
    source = _assert_inside(Path(ctx.project_dir) / safe_work_root, conversation_dir)
    if not source.is_dir():
        raise ValueError("artifact work root does not exist")
    _assert_no_symlinks(source)

    run_dir = _assert_inside(conversation_dir / "critique" / safe_run_id, conversation_dir)
    target = _assert_inside(run_dir / f"round-{round_number}", conversation_dir)
    if target.exists():
        return target

    run_dir.mkdir(parents=True, exist_ok=True)
    temporary = _assert_inside(run_dir / f".round-{round_number}.{uuid.uuid4().hex}.tmp", conversation_dir)
    try:
        temporary.mkdir()
        shutil.copytree(source, temporary / "artifact-work-root", ignore=_copytree_ignore)
        (temporary / "artifact_manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (temporary / "round.json").write_text(
            json.dumps(
                {
                    "artifact_work_root": safe_work_root,
                    "active_entry": normalized_entry,
                    "composite": float(composite),
                    "must_fix_count": int(must_fix_count),
                    "findings": [
                        {"role": finding.role, "text": finding.text}
                        for finding in findings
                    ],
                    "evidence": [
                        {
                            "entry": item.entry,
                            "path": item.path,
                            "kind": item.kind,
                        }
                        for item in evidence
                    ],
                    "warnings": [_warning_to_json(item) for item in warnings],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        try:
            os.replace(temporary, target)
        except FileExistsError:
            shutil.rmtree(temporary, ignore_errors=True)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return target


def restore_round_snapshot(
    ctx: "HarnessContext",
    *,
    snapshot_dir: Path,
    artifact_work_root: str | None = None,
) -> dict[str, Any]:
    conversation_dir = Path(ctx.conversation_dir).resolve()
    snapshot = _assert_inside(Path(snapshot_dir), conversation_dir)
    source = _assert_inside(snapshot / "artifact-work-root", conversation_dir)
    if not source.is_dir():
        raise ValueError("snapshot artifact work root does not exist")
    _assert_no_symlinks(source)

    manifest_path = _assert_inside(snapshot / "artifact_manifest.json", conversation_dir)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = normalize_relpath(manifest.get("entry"))

    # The snapshot is self-describing: prefer the work root recorded in its own
    # round.json (validated when the snapshot was written), then derive it from
    # the manifest entry, and only then fall back to the caller-supplied hint.
    # This keeps restore symmetric with snapshot_round even when the critique run
    # froze an empty or non-canonical artifact_work_root.
    safe_work_root = (
        _work_root_from_snapshot(snapshot)
        or work_root_from_entry(entry)
        or _safe_work_root(artifact_work_root)
    )
    if not safe_work_root:
        raise ValueError("artifact_work_root must be a single safe path component")
    if not entry.startswith(f"{safe_work_root}/"):
        raise ValueError("snapshot manifest entry must stay inside artifact work root")

    project_dir = Path(ctx.project_dir).resolve()
    target = _assert_inside(project_dir / safe_work_root, conversation_dir)
    temporary = _assert_inside(project_dir / f".{safe_work_root}.{uuid.uuid4().hex}.tmp", conversation_dir)
    backup = _assert_inside(project_dir / f".{safe_work_root}.{uuid.uuid4().hex}.bak", conversation_dir)
    try:
        shutil.copytree(source, temporary)
        if target.exists():
            os.replace(target, backup)
        os.replace(temporary, target)
        if backup.exists():
            shutil.rmtree(backup)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
        if backup.exists() and not target.exists():
            os.replace(backup, target)
        raise
    return manifest


def _warning_to_json(warning: CritiqueWarning | dict[str, Any]) -> dict[str, str]:
    if isinstance(warning, CritiqueWarning):
        return {"code": warning.code, "message": warning.message}
    return {
        "code": str(warning.get("code") or ""),
        "message": str(warning.get("message") or ""),
    }
