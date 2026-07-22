from __future__ import annotations

import shutil
import uuid
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import API_V1_STR
from app.models.project import Project
from app.models.project_member import ProjectMember


CANVAS_UPLOAD_ROOT = Path("uploads") / "canvas"


class CanvasMediaRehostService:
    """Copies local canvas media into the target project before persisting it.

    Canvas items can enter a project from another project's asset library or from
    an internal canvas clipboard payload. The browser can display those URLs, but
    agent references require the media to belong to the active project.
    """

    def __init__(self, db: AsyncSession, *, upload_root: Path | None = None):
        self.db = db
        self.upload_root = upload_root or CANVAS_UPLOAD_ROOT

    async def rehost_canvas_payload(
        self,
        canvas_payload: Any,
        *,
        target_project_id: int,
        user_id: int,
    ) -> Any:
        if not isinstance(canvas_payload, list):
            return canvas_payload

        copied_by_url: dict[str, str] = {}
        next_payload: list[Any] = []
        changed = False
        for item in canvas_payload:
            if not isinstance(item, dict):
                next_payload.append(item)
                continue

            normalized_url = await self.rehost_url(
                item.get("url"),
                target_project_id=target_project_id,
                user_id=user_id,
                copied_by_url=copied_by_url,
            )
            if normalized_url is None or normalized_url == item.get("url"):
                next_payload.append(item)
                continue

            next_item = dict(item)
            next_item["url"] = normalized_url
            next_payload.append(next_item)
            changed = True

        return next_payload if changed else canvas_payload

    async def rehost_url(
        self,
        value: Any,
        *,
        target_project_id: int,
        user_id: int,
        copied_by_url: dict[str, str] | None = None,
    ) -> str | None:
        parsed = _parse_canvas_upload_url(value)
        if parsed is None:
            return None

        source_project_id, source_filename, normalized_url = parsed
        if source_project_id == target_project_id:
            return normalized_url

        if copied_by_url is not None and normalized_url in copied_by_url:
            return copied_by_url[normalized_url]

        if not await self._can_access_project(source_project_id, user_id):
            return normalized_url

        source_path = _resolve_canvas_upload_file(
            self.upload_root,
            project_id=source_project_id,
            filename=source_filename,
        )
        if source_path is None:
            return normalized_url

        target_url = _copy_canvas_upload_file(
            self.upload_root,
            target_project_id=target_project_id,
            source_path=source_path,
        )
        if copied_by_url is not None:
            copied_by_url[normalized_url] = target_url
        return target_url

    async def _can_access_project(self, project_id: int, user_id: int) -> bool:
        member_projects = select(ProjectMember.project_id).where(ProjectMember.user_id == user_id)
        result = await self.db.execute(
            select(Project.id)
            .where(
                and_(
                    Project.id == project_id,
                    Project.deleted_at.is_(None),
                    or_(
                        Project.user_id == user_id,
                        Project.id.in_(member_projects),
                    ),
                )
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None


def _parse_canvas_upload_url(value: Any) -> tuple[int, str, str] | None:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return None

    parsed = urlsplit(raw)
    path_value = parsed.path if parsed.scheme or parsed.netloc else raw
    decoded = unquote(path_value).replace("\\", "/")
    if not decoded.startswith(f"{API_V1_STR}/uploads/canvas/"):
        return None

    path = PurePosixPath(decoded)
    parts = path.parts
    expected_prefix = ("/", "api", "v1", "uploads", "canvas")
    if parts[:5] != expected_prefix or len(parts) != 7:
        return None
    if any(part in {"", ".", ".."} for part in parts):
        return None
    if not parts[5].isdigit():
        return None
    filename = parts[6]
    if "/" in filename or "\\" in filename or not filename:
        return None
    return int(parts[5]), filename, path.as_posix()


def _resolve_canvas_upload_file(
    upload_root: Path,
    *,
    project_id: int,
    filename: str,
) -> Path | None:
    root = upload_root.resolve()
    source_dir = (root / str(project_id)).resolve()
    source_path = (source_dir / filename).resolve()
    if source_path.parent != source_dir:
        return None
    if source_dir != root and root not in source_dir.parents:
        return None
    if not source_path.exists() or not source_path.is_file():
        return None
    return source_path


def _copy_canvas_upload_file(
    upload_root: Path,
    *,
    target_project_id: int,
    source_path: Path,
) -> str:
    root = upload_root.resolve()
    target_dir = (root / str(target_project_id)).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = source_path.suffix.lower()
    target_path = (target_dir / f"{uuid.uuid4().hex}{suffix}").resolve()
    if target_path.parent != target_dir:
        raise ValueError("Invalid canvas upload target path")
    if target_dir != root and root not in target_dir.parents:
        raise ValueError("Invalid canvas upload target directory")

    shutil.copy2(source_path, target_path)
    return f"{API_V1_STR}/uploads/canvas/{target_project_id}/{target_path.name}"
