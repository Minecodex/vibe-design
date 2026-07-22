"""Helpers for structured artifact path metadata."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


def build_artifact_metadata(path: str | Path | None, ctx: HarnessContext) -> dict | None:
    """Return absolute/relative/base-dir metadata for a workspace artifact."""
    if not path:
        return None

    raw = str(path).replace("\\", "/")
    raw_path = Path(raw)
    if raw_path.is_absolute():
        resolved = raw_path.resolve()
    elif raw.startswith(("project/", "references/", "published/", "skill/")):
        workspace_path = ctx.resolve_workspace_path(raw, default_scope="code", allow_fallback_to_files=False)
        if workspace_path is None:
            return None
        resolved = workspace_path.resolve()
    else:
        resolved = (ctx.conversation_dir / raw_path).resolve()

    references_dir = ctx.references_dir.resolve()
    project_dir = ctx.project_dir.resolve()
    published_dir = ctx.published_dir.resolve()
    conversation_dir = ctx.conversation_dir.resolve()

    if resolved.is_relative_to(references_dir):
        return {
            "absolute_path": str(resolved),
            "relative_path": str(resolved.relative_to(conversation_dir)).replace("\\", "/"),
            "base_dir": "REFERENCES_DIR",
        }
    if resolved.is_relative_to(project_dir):
        return {
            "absolute_path": str(resolved),
            "relative_path": str(resolved.relative_to(conversation_dir)).replace("\\", "/"),
            "base_dir": "PROJECT_DIR",
        }
    if resolved.is_relative_to(published_dir):
        return {
            "absolute_path": str(resolved),
            "relative_path": str(resolved.relative_to(conversation_dir)).replace("\\", "/"),
            "base_dir": "PUBLISHED_DIR",
        }
    if resolved.is_relative_to(conversation_dir):
        return {
            "absolute_path": str(resolved),
            "relative_path": str(resolved.relative_to(conversation_dir)).replace("\\", "/"),
            "base_dir": "CONVERSATION_DIR",
        }
    return None
