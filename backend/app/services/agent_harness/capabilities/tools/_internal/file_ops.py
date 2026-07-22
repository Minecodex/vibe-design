from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.services.agent_harness.isolation.security.paths import (
    read_text_file,
    resolve_project_file_path as _resolve_project_file_path,
    resolve_semantic_path as _resolve_semantic_path,
    resolve_workspace_file_path as _resolve_workspace_file_path,
    sha256_text,
    workspace_path_for_base_tool as _workspace_path_for_base_tool,
)

WorkspaceLocation = Literal["root", "project", "references", "published", "meta", "skill"]


@dataclass(frozen=True, slots=True)
class WorkPathResolution:
    resolved: Path
    normalized_path: str
    warning: str | None = None
    original_path: str | None = None
    audit_metadata: dict | None = None


def resolve_semantic_path(location: WorkspaceLocation, path: str, ctx) -> Path | None:
    return _resolve_semantic_path(location, path, ctx)


def resolve_work_file_path(file_path: str, ctx, *, base: str | None = None) -> WorkPathResolution | None:
    resolved = _resolve_project_file_path(file_path, ctx, base=base)
    if resolved is None:
        return None
    return WorkPathResolution(
        resolved=resolved.resolved,
        normalized_path=resolved.normalized_path,
        warning=resolved.warning,
        original_path=resolved.original_path,
        audit_metadata=getattr(resolved, "audit_metadata", None),
    )


def resolve_workspace_file_path(file_path: str, ctx) -> Path | None:
    return _resolve_workspace_file_path(file_path, ctx)


def workspace_path_for_base_tool(base: str | None, path: str, ctx, *, default_base: str = "work") -> str:
    return _workspace_path_for_base_tool(base, path, ctx, default_base=default_base)


def split_workspace_location_path(workspace_path: str) -> tuple[str, str]:
    normalized = str(workspace_path or "").replace("\\", "/").strip().lstrip("/")
    if not normalized:
        return "root", "."
    first, _, rest = normalized.partition("/")
    if first in {"project", "references", "published", "skill"}:
        if rest.startswith(f"{first}/"):
            return first, normalized
        return first, rest or "."
    return "root", normalized


def add_normalization_warning(
    *,
    output: str,
    metadata: dict,
    warning: str | None,
    normalized_path: str | None = None,
    normalized_command: str | None = None,
    original: str | None = None,
    audit_metadata: dict | None = None,
    kind: str = "path_normalization",
) -> tuple[str, dict]:
    merged = dict(metadata or {})
    if audit_metadata:
        merged["path_normalization"] = audit_metadata
    if not warning:
        return output, merged
    merged["normalization_kind"] = kind
    merged["normalization_warning"] = warning
    if normalized_path:
        merged["normalized_path"] = normalized_path
    if normalized_command:
        merged["normalized_command"] = normalized_command
    if original:
        merged["original_input"] = original
    prefix = json.dumps(
        {
            "warning": warning,
            **({"normalized_path": normalized_path} if normalized_path else {}),
            **({"normalized_command": normalized_command} if normalized_command else {}),
        },
        ensure_ascii=False,
    )
    return f"{prefix}\n{output}" if output else prefix, merged


def workspace_path_metadata(ctx, resolved: Path, *, location: str, file_path: str | None = None) -> dict:
    """Return model-friendly path forms for a resolved workspace file."""
    resolved_path = resolved.resolve()
    normalized_location = str(location or "project").replace("\\", "/").strip().strip("/") or "project"
    normalized_file_path = str(file_path or "").replace("\\", "/").strip().lstrip("/")

    if normalized_location == "skill":
        active_skill_dir = getattr(ctx, "active_skill_dir", None)
        if active_skill_dir:
            try:
                skill_relative = resolved_path.relative_to(Path(active_skill_dir).resolve()).as_posix()
                normalized_file_path = normalized_file_path or skill_relative
                return {
                    "path": f"skill/{skill_relative}",
                    "location": "skill",
                    "file_path": normalized_file_path,
                    "conversation_path": _conversation_path(ctx, resolved_path),
                }
            except ValueError:
                pass

    location_root = _location_root(ctx, normalized_location)
    if location_root is not None and not normalized_file_path:
        try:
            normalized_file_path = resolved_path.relative_to(location_root.resolve()).as_posix()
        except ValueError:
            normalized_file_path = resolved_path.name
    if normalized_file_path in {"", "."}:
        normalized_file_path = "."

    conversation_path = _conversation_path(ctx, resolved_path)
    return {
        "path": conversation_path,
        "location": normalized_location,
        "file_path": normalized_file_path,
        "conversation_path": conversation_path,
    }


def _conversation_path(ctx, resolved: Path) -> str:
    try:
        return resolved.resolve().relative_to(ctx.conversation_dir.resolve()).as_posix()
    except ValueError:
        return resolved.resolve().as_posix()


def _location_root(ctx, location: str) -> Path | None:
    if location == "project":
        return ctx.project_dir
    if location == "references":
        return ctx.references_dir
    if location == "published":
        return ctx.published_dir
    if location == "meta":
        return ctx.meta_dir
    return None
