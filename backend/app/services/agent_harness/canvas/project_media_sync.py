from __future__ import annotations

import shutil
import uuid
from pathlib import Path, PurePosixPath

from app.core.config import API_V1_STR


CANVAS_UPLOAD_ROOT = Path("uploads") / "canvas"


def _resolve_workspace_media_path(ctx, workspace_path: str) -> Path | None:
    raw = str(workspace_path or "").strip()
    if not raw:
        return None

    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or not relative.name:
        return None

    candidate = (ctx.conversation_dir / Path(*relative.parts)).resolve()
    conversation_root = ctx.conversation_dir.resolve()
    if candidate != conversation_root and conversation_root not in candidate.parents:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def publish_canvas_generated_media(
    ctx,
    workspace_path: str,
    *,
    upload_root: Path | None = None,
) -> str | None:
    if str(getattr(ctx, "runtime_profile", "") or "").strip().lower() != "canvas":
        return None

    project_id = getattr(ctx, "project_id", None)
    if project_id is None:
        return None

    source_path = _resolve_workspace_media_path(ctx, workspace_path)
    if source_path is None:
        return None

    suffix = source_path.suffix.lower()
    filename = f"{uuid.uuid4().hex}{suffix}"
    root = (upload_root or CANVAS_UPLOAD_ROOT).resolve()
    target_dir = (root / str(project_id)).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = (target_dir / filename).resolve()
    if target_path != target_dir and target_dir not in target_path.parents:
        return None

    shutil.copy2(source_path, target_path)
    return f"{API_V1_STR}/uploads/canvas/{project_id}/{filename}"
