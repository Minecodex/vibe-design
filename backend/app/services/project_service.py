from collections import defaultdict
from datetime import datetime, timezone
import asyncio
import hashlib

from app.core.datetime_utils import get_app_timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_member import ProjectMember
from app.models.user import User
from app.repositories.project_repository import ProjectRepository
from app.schemas.project import ProjectCreate, ProjectListItemRead, ProjectPreviewItemRead, ProjectUpdate
from app.services.asset_preview_service import asset_preview_service
from app.services.canvas_asset_sync_service import CanvasAssetSyncService
from app.services.canvas_media_rehost_service import CanvasMediaRehostService
from app.services.project_canvas_service import ProjectCanvasService


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.repo = ProjectRepository(db)
        self.canvas_service = ProjectCanvasService(db)

    async def _attach_users(self, projects: list[Project]) -> list[Project]:
        if not projects:
            return projects

        project_ids = [p.id for p in projects]
        owner_ids = list({p.user_id for p in projects})

        owners_result = await self.repo.db.execute(select(User).where(User.id.in_(owner_ids)))
        owners_map = {u.id: u for u in owners_result.scalars().all()}

        members_result = await self.repo.db.execute(
            select(ProjectMember, User)
            .join(User, ProjectMember.user_id == User.id)
            .where(ProjectMember.project_id.in_(project_ids))
        )
        memberships = members_result.all()

        proj_users = defaultdict(list)
        for pm, u in memberships:
            proj_users[pm.project_id].append(
                {
                    "id": u.id,
                    "nickname": u.nickname,
                    "username": u.username,
                    "avatar_url": u.avatar_url,
                    "role": pm.role,
                }
            )

        for project in projects:
            owner = owners_map.get(project.user_id)
            project.users = []
            if owner:
                project.users.append(
                    {
                        "id": owner.id,
                        "nickname": owner.nickname,
                        "username": owner.username,
                        "avatar_url": owner.avatar_url,
                        "role": "owner",
                    }
                )
            project.users.extend(proj_users.get(project.id, []))

        return projects

    async def _attach_canvas_data(self, projects: list[Project], user_id: int) -> list[Project]:
        for project in projects:
            project.canvas_data = await self.canvas_service.get_effective_canvas_payload(project, user_id)
        return projects

    async def _attach_project_preview_items(self, projects: list[Project]) -> list[Project]:
        if not projects:
            return projects

        await asyncio.gather(*(self._attach_project_preview_items_for_project(project) for project in projects))
        return projects

    async def _attach_project_preview_items_for_project(self, project: Project) -> None:
        canvas_items = project.canvas_data if isinstance(project.canvas_data, list) else []
        project.project_preview_items = await self._build_project_preview_items(project.id, canvas_items)

    async def _build_project_preview_items(
        self,
        project_id: int,
        canvas_items: list[dict],
    ) -> list[dict]:
        image_items = [
            item for item in canvas_items
            if isinstance(item, dict) and item.get("type") == "image" and isinstance(item.get("url"), str) and item["url"]
        ][:4]

        if image_items:
            return await asyncio.gather(
                *(self._build_project_preview_item(project_id, item) for item in image_items)
            )

        video_item = next(
            (
                item for item in canvas_items
                if isinstance(item, dict) and item.get("type") == "video" and isinstance(item.get("url"), str) and item["url"]
            ),
            None,
        )
        if video_item is not None:
            return [
                {
                    "asset_type": "video",
                    "url": str(video_item["url"]),
                    "list_preview_url": None,
                    "list_preview_status": None,
                }
            ]

        return []

    async def _build_project_preview_item(self, project_id: int, item: dict) -> dict:
        url = str(item["url"])
        item_key = str(item.get("id") or url)
        preview = await asset_preview_service.get_list_preview(
            asset_id=self._build_project_preview_asset_key(project_id, item_key, url),
            asset_type="image",
            asset_url=url,
        )
        return {
            "asset_type": "image",
            "url": url,
            "list_preview_url": preview.url,
            "list_preview_status": preview.status,
        }

    @staticmethod
    def _build_project_preview_asset_key(project_id: int, item_key: str, url: str) -> str:
        digest = hashlib.sha1(f"{item_key}:{url}".encode("utf-8")).hexdigest()[:12]
        return f"project:{project_id}:{digest}"

    async def create(self, user_id: int, data: ProjectCreate) -> Project:
        project = Project(user_id=user_id, title=data.title)
        project = await self.repo.create(project)
        await self.canvas_service.get_user_canvas(project, user_id, create_if_missing=True)
        await self.repo.db.commit()
        projects = await self._attach_users([project])
        projects = await self._attach_canvas_data(projects, user_id)
        return (await self._attach_project_preview_items(projects))[0]

    async def list_by_user(
        self,
        user_id: int,
        page: int,
        page_size: int,
        is_admin: bool = False,
    ) -> tuple[int, list[ProjectListItemRead]]:
        total, projects = await self.repo.get_by_user_paginated(user_id, page, page_size, is_admin=is_admin)
        projects = await self._attach_users(projects)
        project_ids = [project.id for project in projects]
        canvas_payloads = await self.canvas_service.get_effective_canvas_payloads(project_ids, user_id)

        preview_items_by_project_id = {
            project_id: items
            for project_id, items in zip(
                project_ids,
                await asyncio.gather(
                    *(self._build_project_preview_items(project_id, canvas_payloads.get(project_id, [])) for project_id in project_ids)
                ),
                strict=True,
            )
        }

        return total, [
            ProjectListItemRead(
                id=project.id,
                user_id=project.user_id,
                title=project.title,
                status=project.status,
                thumbnail_url=project.thumbnail_url,
                project_preview_items=[
                    ProjectPreviewItemRead.model_validate(item)
                    for item in preview_items_by_project_id.get(project.id, [])
                ],
                share_token=project.share_token,
                share_permission=project.share_permission,
                share_password=project.share_password,
                share_expiration=project.share_expiration,
                created_at=project.created_at,
                updated_at=project.updated_at,
                users=project.users,
            )
            for project in projects
        ]

    async def get(self, project_id: int, user_id: int, is_admin: bool = False) -> Project:
        project = await self.repo.get_by_id_and_user(project_id, user_id, is_admin=is_admin)
        if not project:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")

        projects = await self._attach_users([project])
        projects = await self._attach_canvas_data(projects, user_id)
        return (await self._attach_project_preview_items(projects))[0]

    async def update(self, project_id: int, user_id: int, data: ProjectUpdate) -> Project:
        project = await self.get(project_id, user_id, is_admin=False)
        update_data = data.model_dump(exclude_unset=True)

        canvas_data_provided = "canvas_data" in update_data
        canvas_payload = update_data.pop("canvas_data", None)
        canvas_base_revision = update_data.pop("canvas_base_revision", None)

        for key, value in update_data.items():
            setattr(project, key, value)

        if canvas_data_provided:
            canvas_payload = await CanvasMediaRehostService(self.repo.db).rehost_canvas_payload(
                canvas_payload,
                target_project_id=project.id,
                user_id=user_id,
            )
            await self.canvas_service.replace_user_canvas(
                project,
                user_id,
                canvas_payload,
                base_revision=canvas_base_revision,
            )
            project.updated_at = datetime.now(get_app_timezone())
            sync_service = CanvasAssetSyncService(self.repo.db)
            await sync_service.sync_user_canvas_assets(
                project=project,
                canvas_owner_user_id=user_id,
                canvas_payload=canvas_payload,
                actor_user_id=user_id,
            )

        await self.repo.db.commit()
        await self.repo.db.refresh(project)
        projects = await self._attach_users([project])
        projects = await self._attach_canvas_data(projects, user_id)
        return (await self._attach_project_preview_items(projects))[0]

    async def delete(self, project_id: int, user_id: int, is_admin: bool = False) -> None:
        project = await self.get(project_id, user_id, is_admin=is_admin)
        await self.repo.soft_delete(project)
