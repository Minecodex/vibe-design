from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.project_repository import ProjectRepository


class ProjectAccessService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = ProjectRepository(db)

    async def ensure_can_read_project(self, *, project_id: int, user_id: int, is_admin: bool = False) -> None:
        project = await self.repo.get_by_id_and_user(project_id, user_id, is_admin=is_admin)
        if project is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
