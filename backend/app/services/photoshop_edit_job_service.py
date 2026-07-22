from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photoshop_edit_job import PhotoshopEditJob
from app.models.project import Project
from app.models.project_asset import ProjectAsset
from app.models.user import User
from app.repositories.photoshop_edit_job_repository import PhotoshopEditJobRepository
from app.schemas.photoshop_edit_job import PhotoshopEditJobCreate, PhotoshopEditJobSaveRequest, PhotoshopPluginSaveRequest
from app.services.project_canvas_service import ProjectCanvasService
from app.services.project_service import ProjectService


def _normalize_controlled_asset_url(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path or url).strip()
    if not path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材地址不能为空")
    if parsed.scheme or parsed.netloc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材地址必须为站内受控路径")
    if ".." in path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材地址非法")
    if not path.startswith("/api/v1/uploads/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="素材地址必须为站内上传文件")
    return path


class PhotoshopEditJobService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PhotoshopEditJobRepository(db)
        self.project_service = ProjectService(db)
        self.canvas_service = ProjectCanvasService(db)

    async def create_job(
        self,
        *,
        project_id: int,
        user: User,
        data: PhotoshopEditJobCreate,
    ) -> PhotoshopEditJob:
        project = await self.project_service.get(project_id, user.id, is_admin=user.role == "admin")
        canvas_payload = await self.canvas_service.get_effective_canvas_payload(project, user.id)
        source_item = self._find_canvas_item(canvas_payload, data.source_canvas_item_id)
        if not source_item or source_item.get("type") != "image":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到可编辑图片")

        normalized_svg_url = _normalize_controlled_asset_url(data.svg_url)
        duplicate = await self.repo.get_active_duplicate(
            project_id=project_id,
            request_user_id=user.id,
            source_canvas_item_id=data.source_canvas_item_id,
        )
        if duplicate:
            return duplicate

        source_asset_id = await self._resolve_source_asset_id(project_id, user.id, data.source_canvas_item_id, source_item)
        job = PhotoshopEditJob(
            project_id=project_id,
            request_user_id=user.id,
            source_canvas_item_id=data.source_canvas_item_id,
            source_asset_id=source_asset_id,
            svg_url=normalized_svg_url,
        )
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def list_pending_jobs(self, user: User) -> list[PhotoshopEditJob]:
        return await self.repo.list_pending_for_user(user.id)

    async def claim_job(self, *, job_id: int, user: User) -> PhotoshopEditJob:
        job = await self._get_owned_job(job_id, user)
        if job.status == "saved":
            return job
        if job.status == "cancelled":
            return job
        if job.claimed_by_user_id and job.claimed_by_user_id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已被其他会话认领")
        job.claimed_by_user_id = user.id
        job.status = "claimed"
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def cancel_job(self, *, job_id: int, user: User) -> PhotoshopEditJob:
        job = await self._get_owned_job(job_id, user)
        if job.status in {"saved", "cancelled"}:
            return job
        if job.claimed_by_user_id and job.claimed_by_user_id != user.id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="任务已被其他会话认领")
        job.claimed_by_user_id = user.id
        job.status = "cancelled"
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def save_job_result(
        self,
        *,
        job_id: int,
        user: User,
        data: PhotoshopEditJobSaveRequest,
    ) -> PhotoshopEditJob:
        job = await self._get_owned_job(job_id, user)
        if job.result_asset_id and job.result_canvas_item_id and job.status == "saved":
            return job

        target_project_id = data.target_project_id or job.project_id
        project = await self.project_service.get(target_project_id, user.id, is_admin=user.role == "admin")
        result_url = _normalize_controlled_asset_url(data.result_url)

        asset = ProjectAsset(
            project_id=project.id,
            user_id=user.id,
            asset_type="image",
            url=result_url,
            origin_kind="local_upload",
            source_asset_id=job.source_asset_id,
        )
        self.db.add(asset)
        await self.db.flush()

        result_canvas_item_id = job.result_canvas_item_id or f"ps-edit-result-{job.id}"
        now_iso = datetime.now(timezone.utc).isoformat()

        def upsert_result_item(
            canvas_items: list[dict[str, Any]],
            canvas_meta: dict[str, Any] | None,
        ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            next_items = list(canvas_items)
            existing = next((item for item in next_items if item.get("id") == result_canvas_item_id), None)
            result_item = {
                "id": result_canvas_item_id,
                "type": "image",
                "url": result_url,
                "name": data.name or "Photoshop Edit Result",
                "x": self._resolve_result_x(next_items, existing),
                "y": self._resolve_result_y(next_items, existing),
                "width": data.width,
                "height": data.height,
                "asset_origin": "local_upload",
                "source_asset_id": asset.id,
                "created_at": now_iso,
            }
            if existing is None:
                next_items.append(result_item)
            else:
                existing.update(result_item)
            return next_items, canvas_meta

        await self.canvas_service.mutate_user_canvas(
            project,
            user.id,
            upsert_result_item,
            create_if_missing=True,
        )
        job.claimed_by_user_id = user.id
        job.status = "saved"
        job.result_asset_id = asset.id
        job.result_canvas_item_id = result_canvas_item_id

        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def save_plugin_result(
        self,
        *,
        project_id: int,
        user: User,
        data: PhotoshopPluginSaveRequest,
    ) -> tuple[ProjectAsset, str]:
        project = await self.project_service.get(project_id, user.id, is_admin=user.role == "admin")
        result_url = _normalize_controlled_asset_url(data.result_url)

        asset = ProjectAsset(
            project_id=project.id,
            user_id=user.id,
            asset_type="image",
            url=result_url,
            origin_kind="local_upload",
        )
        self.db.add(asset)
        await self.db.flush()

        result_canvas_item_id = f"ps-plugin-save-{asset.id}"
        asset.canvas_item_id = result_canvas_item_id

        now_iso = datetime.now(timezone.utc).isoformat()

        def append_plugin_result(
            canvas_items: list[dict[str, Any]],
            canvas_meta: dict[str, Any] | None,
        ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
            next_items = list(canvas_items)
            x, y = self._resolve_plugin_result_position(next_items, data.width, data.height)
            next_items.append(
                {
                    "id": result_canvas_item_id,
                    "type": "image",
                    "url": result_url,
                    "name": "PS添加",
                    "x": x,
                    "y": y,
                    "width": data.width,
                    "height": data.height,
                    "asset_origin": "local_upload",
                    "source_asset_id": asset.id,
                    "created_at": now_iso,
                }
            )
            return next_items, canvas_meta

        await self.canvas_service.mutate_user_canvas(
            project,
            user.id,
            append_plugin_result,
            create_if_missing=True,
        )

        await self.db.commit()
        await self.db.refresh(asset)
        return asset, result_canvas_item_id

    async def _get_owned_job(self, job_id: int, user: User) -> PhotoshopEditJob:
        job = await self.repo.get(job_id)
        if job is None or job.request_user_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        return job

    async def _resolve_source_asset_id(
        self,
        project_id: int,
        user_id: int,
        source_canvas_item_id: str,
        source_item: dict[str, Any],
    ) -> int | None:
        if isinstance(source_item.get("source_asset_id"), int):
            return source_item["source_asset_id"]

        result = await self.db.execute(
            select(ProjectAsset.id).where(
                ProjectAsset.project_id == project_id,
                ProjectAsset.user_id == user_id,
                ProjectAsset.canvas_item_id == source_canvas_item_id,
            )
        )
        asset_id = result.scalar_one_or_none()
        if asset_id is not None:
            return asset_id
        return source_item.get("source_asset_id")

    def _find_canvas_item(self, canvas_payload: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
        for item in canvas_payload:
            if isinstance(item, dict) and item.get("id") == item_id:
                return item
        return None

    def _resolve_result_x(self, existing_items: list[dict[str, Any]], existing_item: dict[str, Any] | None) -> int:
        if existing_item and isinstance(existing_item.get("x"), (int, float)):
            return int(existing_item["x"])
        if not existing_items:
            return 0
        max_x = max(int(item.get("x", 0)) for item in existing_items if isinstance(item, dict))
        return max_x + 40

    def _resolve_result_y(self, existing_items: list[dict[str, Any]], existing_item: dict[str, Any] | None) -> int:
        if existing_item and isinstance(existing_item.get("y"), (int, float)):
            return int(existing_item["y"])
        if not existing_items:
            return 0
        max_y = max(int(item.get("y", 0)) for item in existing_items if isinstance(item, dict))
        return max_y + 40

    def _resolve_plugin_result_position(
        self,
        existing_items: list[dict[str, Any]],
        width: int,
        height: int,
    ) -> tuple[int, int]:
        boxes = [self._canvas_item_box(item) for item in existing_items if isinstance(item, dict)]
        boxes = [box for box in boxes if box is not None]
        if not boxes:
            return 0, 0

        min_x = min(box["x"] for box in boxes)
        min_y = min(box["y"] for box in boxes)
        max_x = max(box["x"] + box["width"] for box in boxes)
        max_y = max(box["y"] + box["height"] for box in boxes)
        gap = 20
        candidates = [
            (max_x + gap, min_y),
            (min_x, max_y + gap),
            (max(min_x - width - gap, 0), min_y),
            (min_x, max(min_y - height - gap, 0)),
        ]

        for candidate in candidates:
            if not self._position_overlaps(candidate[0], candidate[1], width, height, boxes):
                return int(candidate[0]), int(candidate[1])

        step = 40
        start_x = max(min_x - step, 0)
        start_y = max(min_y - step, 0)
        search_limit_x = max_x + width + gap + step * 8
        search_limit_y = max_y + height + gap + step * 8
        y = start_y
        while y <= search_limit_y:
            x = start_x
            while x <= search_limit_x:
                if not self._position_overlaps(x, y, width, height, boxes):
                    return int(x), int(y)
                x += step
            y += step

        return int(max_x + gap), int(max_y + gap)

    def _canvas_item_box(self, item: dict[str, Any]) -> dict[str, int] | None:
        if not all(isinstance(item.get(key), (int, float)) for key in ("x", "y", "width", "height")):
            return None
        return {
            "x": int(item["x"]),
            "y": int(item["y"]),
            "width": int(item["width"]),
            "height": int(item["height"]),
        }

    def _position_overlaps(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        boxes: list[dict[str, int]],
    ) -> bool:
        for box in boxes:
            if not (
                x + width <= box["x"]
                or box["x"] + box["width"] <= x
                or y + height <= box["y"]
                or box["y"] + box["height"] <= y
            ):
                return True
        return False
