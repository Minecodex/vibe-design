from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .contracts import CritiqueConfig
from .work_root import normalize_relpath as _normal_path
from .work_root import safe_work_root as _safe_root
from .work_root import work_root_from_entry as _work_root_from_entry

_ELIGIBLE_HOME_ARTIFACT_MODES = {"document", "html", "slides", "web"}


def should_run_critique(
    cfg: CritiqueConfig,
    *,
    runtime_profile: str | None,
    artifact_mode: str | None,
    skill_id: str | None,
) -> bool:
    normalized_skill_id = str(skill_id or "").strip().lower()
    normalized_artifact_mode = str(artifact_mode or "").strip().lower()
    has_active_skill = bool(normalized_skill_id)
    return (
        cfg.enabled
        and str(runtime_profile or "").strip().lower() == "home"
        and has_active_skill
        and normalized_artifact_mode in _ELIGIBLE_HOME_ARTIFACT_MODES
    )


def _html_entry_candidate(entry: str, work_root: str) -> str:
    if not entry:
        return ""
    suffix = PurePosixPath(entry).suffix.lower()
    if suffix in {".html", ".htm"}:
        return entry
    if suffix:
        return ""
    trimmed = entry.rstrip("/")
    if not trimmed:
        return ""
    if trimmed == work_root:
        return f"{work_root}/index.html" if work_root else ""
    return f"{trimmed}/index.html"


def should_critique_active_entry(*, active_entry: str | None, artifact_work_root: str | None) -> bool:
    entry = _normal_path(active_entry)
    work_root = _safe_root(artifact_work_root)
    html_entry = _html_entry_candidate(entry, work_root)
    if not html_entry or not work_root or not html_entry.startswith(f"{work_root}/"):
        return False
    return PurePosixPath(html_entry).suffix.lower() in {".html", ".htm"}


def should_critique_manifest_entry(manifest: dict[str, Any] | None, *, artifact_work_root: str | None) -> bool:
    if not isinstance(manifest, dict):
        return False
    entry = str(manifest.get("entry") or "")
    work_root = artifact_work_root
    if not _safe_root(work_root):
        # The critique run can freeze an empty artifact_work_root when it is
        # created before the workspace is fully prepared (create_run is
        # idempotent per harness run and never refreshes the value afterwards).
        # The registered manifest entry is the authoritative published path, so
        # fall back to deriving the work root from its top-level directory.
        candidate_root = _work_root_from_entry(entry)
        work_root = candidate_root or _safe_root(entry)
    if not should_critique_active_entry(
        active_entry=entry,
        artifact_work_root=work_root,
    ):
        return False
    renderer = str(manifest.get("renderer") or "").strip().lower()
    if renderer not in {"html", "deck-html"}:
        return False
    validation = manifest.get("validation") if isinstance(manifest.get("validation"), dict) else {}
    validation_kind = str(validation.get("kind") or "").strip().lower()
    details = validation.get("details") if isinstance(validation.get("details"), dict) else {}
    details_kind = str(details.get("kind") or "").strip().lower()
    return not validation or validation_kind in {"html_bundle", "html"} or details_kind == "html_bundle"


def critique_eligibility_diagnostics(
    manifest: dict[str, Any] | None,
    *,
    artifact_work_root: str | None,
) -> dict[str, Any]:
    manifest = manifest if isinstance(manifest, dict) else {}
    entry = str(manifest.get("entry") or "")
    work_root = str(artifact_work_root or "")
    return {
        "entry": entry,
        "artifact_work_root": work_root,
        "normalized_entry": _normal_path(entry),
        "normalized_artifact_work_root": _safe_root(work_root),
        "kind": str(manifest.get("kind") or "").strip().lower(),
        "renderer": str(manifest.get("renderer") or "").strip().lower(),
        "validation_kind": str(((manifest.get("validation") or {}).get("details") or {}).get("kind") or "").strip().lower()
        if isinstance(manifest.get("validation"), dict)
        else "",
    }
