from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.persistence_sanitizer import sanitize_persistent_payload
from app.services.agent_harness.runtime.artifacts.kind_registry import (
    default_exports_for_entry,
    default_renderer_for_entry,
    validate_kind_contract,
)
from app.services.agent_harness.workspace.generated_content.entry_validation_service import (
    validate_entry_path,
    validate_html_bundle_entry_path,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    read_runtime_state_payload,
    update_conversation_record,
)

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


ARTIFACT_MANIFEST_KEY = "artifact_manifest"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_project_relative(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").strip()
    if not normalized:
        raise ValueError("path is required")
    if Path(normalized).is_absolute() or normalized.startswith("/"):
        raise ValueError("absolute paths are not allowed")
    normalized = normalized.lstrip("/")
    if normalized.startswith("project/"):
        normalized = normalized[8:]
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise ValueError("path must stay inside project/")
    return "/".join(parts)


def project_file(ctx: "HarnessContext", relative_path: str) -> Path:
    normalized = normalize_project_relative(relative_path)
    resolved = (ctx.project_dir / normalized).resolve()
    try:
        resolved.relative_to(ctx.project_dir.resolve())
    except ValueError as exc:
        raise ValueError("path must stay inside project/") from exc
    return resolved


def read_artifact_manifest(user_id: int, conversation_id: str) -> dict[str, Any] | None:
    payload = read_runtime_state_payload(user_id, conversation_id) or {}
    runtime_state = payload.get("runtime_state") if isinstance(payload.get("runtime_state"), dict) else {}
    manifest = runtime_state.get(ARTIFACT_MANIFEST_KEY)
    return deepcopy(manifest) if isinstance(manifest, dict) else None


def validate_manifest_entry(ctx: "HarnessContext", manifest: dict[str, Any]) -> dict[str, Any]:
    entry = normalize_project_relative(str(manifest.get("entry") or ""))
    entry_path = project_file(ctx, entry)
    kind = str(manifest.get("kind") or "").strip().lower()
    renderer = str(manifest.get("renderer") or "").strip().lower()
    exports = [str(item or "").strip().lower() for item in list(manifest.get("exports") or []) if str(item or "").strip()]

    ok, contract_errors, spec = validate_kind_contract(
        kind=kind,
        renderer=renderer,
        exports=exports,
        entry=entry,
    )
    if not ok:
        return {"valid": False, "errors": contract_errors, "entry": entry, "kind": kind}
    if not entry_path.exists() or not entry_path.is_file():
        return {"valid": False, "errors": ["entry file does not exist"], "entry": entry, "kind": kind}

    if renderer in {"html", "deck-html"}:
        validation = validate_html_bundle_entry_path(entry_path)
    else:
        suffix = entry_path.suffix.lower()
        if suffix == ".pdf":
            validation = {"valid": True, "kind": "pdf", "errors": []}
        elif suffix == ".csv":
            validation_kind = "text"
            validation = validate_entry_path(entry_path, kind=validation_kind)
        elif suffix == ".md":
            validation_kind = "markdown"
            validation = validate_entry_path(entry_path, kind=validation_kind)
        elif suffix == ".pptx":
            validation_kind = "presentation"
            validation = validate_entry_path(entry_path, kind=validation_kind)
        else:
            validation_kind = spec.validation_kind if spec is not None else None
            validation = validate_entry_path(entry_path, kind=validation_kind)
    if not validation.get("valid"):
        return {
            "valid": False,
            "errors": list(validation.get("errors") or []),
            "entry": entry,
            "kind": kind,
            "validation": validation,
        }
    return {"valid": True, "errors": [], "entry": entry, "kind": kind, "validation": validation}


def build_artifact_manifest(
    ctx: "HarnessContext",
    *,
    entry: str,
    kind: str,
    title: str | None = None,
    renderer: str | None = None,
    exports: list[str] | None = None,
    supporting_files: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        normalized_entry = normalize_project_relative(entry)
    except ValueError as exc:
        return None, [str(exc)]

    normalized_supporting: list[str] = []
    for item in list(supporting_files or []):
        try:
            normalized_supporting.append(normalize_project_relative(item))
        except ValueError as exc:
            errors.append(f"supporting_files item is invalid: {exc}")

    entry_path = project_file(ctx, normalized_entry)
    if not entry_path.exists():
        errors.append(
            f"entry file does not exist: {normalized_entry} "
            f"(paths are relative to project/, e.g. open-design-landing-prepared/index.html)"
        )
    elif not entry_path.is_file():
        errors.append(f"entry is a directory, not a file: {normalized_entry}")
    for item in normalized_supporting:
        path = project_file(ctx, item)
        if not path.exists():
            errors.append(
                f"supporting file does not exist: {item} "
                f"(paths are relative to project/, not the work dir — prefix with your work folder, "
                f"e.g. open-design-landing-prepared/)"
            )
        elif not path.is_file():
            errors.append(
                f"supporting file is a directory, not a file: {item} "
                f"(list individual files; directories are not allowed)"
            )

    normalized_kind = str(kind or "").strip().lower()
    normalized_renderer = str(renderer or "").strip().lower() or default_renderer_for_entry(
        kind=normalized_kind,
        entry=normalized_entry,
    ) or ""
    normalized_exports = [str(item or "").strip().lower() for item in list(exports or []) if str(item or "").strip()]
    if not normalized_exports:
        normalized_exports = default_exports_for_entry(kind=normalized_kind, entry=normalized_entry)
    ok, contract_errors, _spec = validate_kind_contract(
        kind=normalized_kind,
        renderer=normalized_renderer,
        exports=normalized_exports,
        entry=normalized_entry,
    )
    if not ok:
        errors.extend(contract_errors)

    manifest = {
        "version": 1,
        "kind": normalized_kind,
        "entry": normalized_entry,
        "title": str(title or Path(normalized_entry).stem).strip() or Path(normalized_entry).stem,
        "renderer": normalized_renderer,
        "exports": normalized_exports,
        "status": "complete",
        "supporting_files": normalized_supporting,
        "validation": {
            "status": "pending",
            "checked_at": None,
        },
        "metadata": sanitize_persistent_payload(dict(metadata or {})),
        "registered_at": utc_now(),
    }
    if errors:
        return None, errors

    validation = validate_manifest_entry(ctx, manifest)
    if not validation.get("valid"):
        return None, list(validation.get("errors") or ["entry validation failed"])
    manifest["validation"] = {
        "status": "passed",
        "checked_at": utc_now(),
        "details": validation.get("validation"),
    }
    return manifest, []


def write_artifact_manifest(ctx: "HarnessContext", manifest: dict[str, Any]) -> dict[str, Any]:
    payload = read_runtime_state_payload(ctx.user_id, ctx.conversation_id) or {}
    runtime_state = (
        dict(payload.get("runtime_state") or {})
        if isinstance(payload.get("runtime_state"), dict)
        else {}
    )
    runtime_state[ARTIFACT_MANIFEST_KEY] = sanitize_persistent_payload(manifest)

    workspace_session = (
        dict(runtime_state.get("workspace_runtime_session") or {})
        if isinstance(runtime_state.get("workspace_runtime_session"), dict)
        else {}
    )
    workspace_session["active_entry"] = manifest["entry"]
    runtime_state["workspace_runtime_session"] = workspace_session

    update_conversation_record(
        ctx.user_id,
        ctx.conversation_id,
        {
            "runtime_state": runtime_state,
            "updated_at": utc_now(),
        },
    )
    ctx.workspace_runtime_session = workspace_session
    return deepcopy(manifest)


def mark_artifact_published(
    ctx: "HarnessContext",
    *,
    publish_payload: dict[str, Any],
) -> dict[str, Any]:
    payload = read_runtime_state_payload(ctx.user_id, ctx.conversation_id) or {}
    runtime_state = (
        dict(payload.get("runtime_state") or {})
        if isinstance(payload.get("runtime_state"), dict)
        else {}
    )
    manifest = (
        dict(runtime_state.get(ARTIFACT_MANIFEST_KEY) or {})
        if isinstance(runtime_state.get(ARTIFACT_MANIFEST_KEY), dict)
        else {}
    )
    if not manifest:
        raise ValueError("artifact_manifest is missing")
    manifest["publication"] = {
        "status": "published",
        "published_at": utc_now(),
        "payload": sanitize_persistent_payload(dict(publish_payload or {})),
    }
    runtime_state[ARTIFACT_MANIFEST_KEY] = manifest
    update_conversation_record(
        ctx.user_id,
        ctx.conversation_id,
        {
            "runtime_state": runtime_state,
            "updated_at": utc_now(),
        },
    )
    return deepcopy(manifest)
