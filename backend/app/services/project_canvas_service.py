from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select

from app.models.project import Project
from app.models.project_user_canvas import ProjectUserCanvas
from app.repositories.project_user_canvas_repository import ProjectUserCanvasRepository


class CanvasRevisionConflictError(HTTPException):
    def __init__(self, current_revision: int):
        self.status_code = status.HTTP_409_CONFLICT
        self.detail = {
            "code": "canvas_revision_conflict",
            "message": "Canvas has been updated in another window",
            "canvas_revision": current_revision,
        }
        self.headers = None


class ProjectCanvasService:
    """Encapsulates per-user canvas storage."""

    def __init__(self, db):
        self.db = db
        self.repo = ProjectUserCanvasRepository(db)

    async def lock_project_canvas_scope(self, project: Project) -> None:
        await self.db.execute(
            select(Project)
            .where(Project.id == project.id)
            .with_for_update()
        )

    @staticmethod
    def split_canvas_payload(canvas_payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        if not isinstance(canvas_payload, list):
            return [], None

        items: list[dict[str, Any]] = []
        meta: dict[str, Any] | None = None
        for item in canvas_payload:
            if not isinstance(item, dict):
                continue
            if item.get("id") == "global_state":
                meta = item
            else:
                items.append(item)
        return items, meta

    @classmethod
    def merge_canvas_payload(
        cls,
        canvas_items: list[dict[str, Any]] | None,
        canvas_meta: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        merged = list(canvas_items or [])
        if canvas_meta:
            merged.append(canvas_meta)
        return merged

    async def get_user_canvas(
        self,
        project: Project,
        user_id: int,
        *,
        create_if_missing: bool = False,
    ) -> ProjectUserCanvas | None:
        canvas = await self.repo.get_by_project_and_user(project.id, user_id)
        if canvas:
            return canvas

        if not create_if_missing:
            return None

        canvas = ProjectUserCanvas(
            project_id=project.id,
            user_id=user_id,
            canvas_data=[],
            canvas_meta=None,
            canvas_revision=0,
        )
        self.db.add(canvas)
        await self.db.flush()
        return canvas

    async def get_effective_canvas_payload(
        self,
        project: Project,
        user_id: int,
    ) -> list[dict[str, Any]]:
        canvas = await self.get_user_canvas(project, user_id, create_if_missing=False)
        if not canvas:
            project.canvas_revision = 0
            return []
        project.canvas_revision = int(canvas.canvas_revision or 0)
        return self.merge_canvas_payload(canvas.canvas_data, canvas.canvas_meta)

    async def get_effective_canvas_payloads(
        self,
        project_ids: list[int],
        user_id: int,
    ) -> dict[int, list[dict[str, Any]]]:
        canvases = await self.repo.get_by_projects_and_user(project_ids, user_id)
        payloads = {
            canvas.project_id: self.merge_canvas_payload(canvas.canvas_data, canvas.canvas_meta)
            for canvas in canvases
        }
        for project_id in project_ids:
            payloads.setdefault(project_id, [])
        return payloads

    async def get_canvas_revision(self, project: Project, user_id: int) -> int:
        canvas = await self.get_user_canvas(project, user_id, create_if_missing=False)
        return int(canvas.canvas_revision or 0) if canvas else 0

    async def replace_user_canvas(
        self,
        project: Project,
        user_id: int,
        canvas_payload: Any,
        *,
        base_revision: int | None,
    ) -> ProjectUserCanvas:
        await self.lock_project_canvas_scope(project)
        canvas = await self.get_user_canvas(project, user_id, create_if_missing=True)
        assert canvas is not None

        current_revision = int(canvas.canvas_revision or 0)
        if base_revision is None or int(base_revision) != current_revision:
            raise CanvasRevisionConflictError(current_revision)

        canvas_items, canvas_meta = self.split_canvas_payload(canvas_payload)
        canvas.canvas_data = canvas_items
        canvas.canvas_meta = canvas_meta
        canvas.canvas_revision = current_revision + 1
        await self.db.flush()
        return canvas

    async def mutate_user_canvas(
        self,
        project: Project,
        user_id: int,
        mutator: Callable[[list[dict[str, Any]], dict[str, Any] | None], tuple[list[dict[str, Any]], dict[str, Any] | None] | None],
        *,
        create_if_missing: bool = False,
    ) -> ProjectUserCanvas | None:
        await self.lock_project_canvas_scope(project)
        canvas = await self.get_user_canvas(project, user_id, create_if_missing=create_if_missing)
        if canvas is None:
            return None

        current_items = list(canvas.canvas_data or [])
        current_meta = dict(canvas.canvas_meta) if isinstance(canvas.canvas_meta, dict) else None
        result = mutator(current_items, current_meta)
        if result is None:
            return canvas

        next_items, next_meta = result
        if next_items == (canvas.canvas_data or []) and next_meta == canvas.canvas_meta:
            return canvas

        canvas.canvas_data = next_items
        canvas.canvas_meta = next_meta
        canvas.canvas_revision = int(canvas.canvas_revision or 0) + 1
        await self.db.flush()
        return canvas
