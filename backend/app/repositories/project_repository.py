from datetime import datetime, timezone

from app.core.datetime_utils import get_app_timezone
from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.project import Project
from app.models.project_member import ProjectMember
from app.repositories.base_repository import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, db: AsyncSession):
        super().__init__(Project, db)

    async def get_by_user_paginated(
        self,
        user_id: int,
        page: int,
        page_size: int,
        is_admin: bool = False,
    ) -> tuple[int, list[Project]]:
        where_clause = Project.deleted_at.is_(None)
        if not is_admin:
            where_clause = and_(
                or_(
                    Project.user_id == user_id,
                    ProjectMember.user_id == user_id
                ),
                Project.deleted_at.is_(None),
            )

        total_result = await self.db.execute(
            select(func.count(func.distinct(Project.id)))
            .select_from(Project)
            .outerjoin(ProjectMember, ProjectMember.project_id == Project.id)
            .where(where_clause)
        )
        total = total_result.scalar_one()

        result = await self.db.execute(
            select(Project)
            .outerjoin(ProjectMember, ProjectMember.project_id == Project.id)
            .where(where_clause)
            .distinct()
            .order_by(Project.updated_at.desc(), Project.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return total, list(result.scalars().all())

    async def get_by_id_and_user(self, project_id: int, user_id: int, is_admin: bool = False) -> Project | None:
        where_clause = and_(Project.id == project_id, Project.deleted_at.is_(None))
        if not is_admin:
            where_clause = and_(
                Project.id == project_id,
                or_(
                    Project.user_id == user_id,
                    ProjectMember.user_id == user_id
                ),
                Project.deleted_at.is_(None),
            )

        result = await self.db.execute(
            select(Project)
            .outerjoin(ProjectMember, ProjectMember.project_id == Project.id)
            .where(where_clause)
            .distinct()
        )
        return result.scalar_one_or_none()

    async def lock_by_id(self, project_id: int) -> Project | None:
        """Acquire a row lock on the project to serialize concurrent canvas saves.

        Two overlapping ``PUT`` canvas saves for the same project would otherwise both
        read no existing ``project_assets`` row for a freshly added media item and both
        INSERT it, hitting the ``uq_project_assets_project_user_canvas_item`` unique
        constraint (MySQL error 1062). Taking ``SELECT ... FOR UPDATE`` on the project
        row first makes those saves run one at a time, so the read-then-insert in
        ``CanvasAssetSyncService`` is no longer racy.
        """
        result = await self.db.execute(
            select(Project).where(Project.id == project_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def soft_delete(self, project: Project) -> None:
        project.deleted_at = datetime.now(get_app_timezone())
        await self.db.commit()
