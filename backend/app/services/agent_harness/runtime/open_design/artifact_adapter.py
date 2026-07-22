from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.services.agent_harness.runtime.artifacts.manifest import (
    build_artifact_manifest,
    normalize_project_relative,
    write_artifact_manifest,
)

from .artifact_block import ArtifactBlockError, parse_artifact_block
from .contracts import ArtifactCaptureResult
from .eligibility import is_home_open_design_html_run

# Matches a genuine artifact open tag (`<artifact ...>` / `<artifact>`) but NOT
# lookalike tags such as the Design Jury critique protocol's `<ARTIFACT_REF .../>`.
# The trailing \b is a word boundary: it holds before whitespace/`>` (a real tag)
# yet fails before `_` (`<artifact_ref`), and mirrors parse_artifact_block's own
# regex so the trigger and the parser agree on what counts as an artifact block.
_ARTIFACT_OPEN_TAG_RE = re.compile(r"<artifact\b", re.IGNORECASE)


def has_artifact_open_tag(text: str | None) -> bool:
    """Return True only for a real artifact open tag, not <ARTIFACT_REF>/<artifactx>."""
    return bool(_ARTIFACT_OPEN_TAG_RE.search(str(text or "")))


async def capture_artifact_block(
    ctx: Any,
    assistant_text: str,
    *,
    protocol: Any | None = None,
    return_errors: bool = False,
) -> ArtifactCaptureResult | None:
    if not has_artifact_open_tag(assistant_text):
        return None
    if not is_home_open_design_html_run(ctx, protocol):
        return None
    try:
        block = parse_artifact_block(assistant_text)
    except ArtifactBlockError as exc:
        if return_errors:
            return ArtifactCaptureResult(
                entry=None,
                title=None,
                manifest=None,
                replacement_text="Artifact capture failed; repair required.",
                error_text=(
                    "<artifact-error>\n"
                    "The artifact block could not be captured by the runtime.\n"
                    f"Reason: {exc}\n"
                    "Repair by emitting exactly one complete `<artifact type=\"text/html\">` block with a full `<!doctype html>` document, "
                    "or use write_file + register_artifact + publish_output.\n"
                    "</artifact-error>"
                ),
            )
        return None
    entry = _target_entry(ctx, block.identifier)
    target = ctx.project_dir / entry
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(block.html, encoding="utf-8", newline="\n")
    manifest, errors = build_artifact_manifest(
        ctx,
        entry=entry,
        kind="html",
        title=block.title or block.identifier or Path(entry).stem,
        metadata={"source": "open_design_artifact_block", "identifier": block.identifier},
    )
    if manifest is None:
        try:
            target.unlink(missing_ok=True)
        except Exception:
            pass
        return None
    manifest = write_artifact_manifest(ctx, manifest)
    return ArtifactCaptureResult(
        entry=entry,
        title=block.title,
        manifest=manifest,
        replacement_text="Artifact captured and queued for publishing.",
    )


def _target_entry(ctx: Any, identifier: str | None) -> str:
    prepared = getattr(ctx, "prepared_workspace", None)
    entry = str(getattr(prepared, "entry_path", "") or "").replace("\\", "/").strip("/")
    if entry:
        return normalize_project_relative(entry)
    root = str(getattr(ctx, "artifact_work_root", "") or "").replace("\\", "/").strip("/")
    if not root:
        root = _slug(identifier or "artifact")
    return normalize_project_relative(f"{root}/index.html")


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "artifact")).strip("-").lower()
    return slug or "artifact"
