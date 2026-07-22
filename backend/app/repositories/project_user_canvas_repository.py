from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_user_canvas import ProjectUserCanvas
from app.repositories.base_repository import BaseRepository


class ProjectUserCanvasRepository(BaseRepository[ProjectUserCanvas]):
    def __init__(self, db: AsyncSession):
        super().__init__(ProjectUserCanvas, db)

    async def get_by_project_and_user(
        self,
        project_id: int,
        user_id: int,
    ) -> ProjectUserCanvas | None:
        result = await self.db.execute(
            select(ProjectUserCanvas).where(
                and_(
                    ProjectUserCanvas.project_id == project_id,
                    ProjectUserCanvas.user_id == user_id,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_projects_and_user(
        self,
        project_ids: list[int],
        user_id: int,
    ) -> list[ProjectUserCanvas]:
        if not project_ids:
            return []

        result = await self.db.execute(
            select(ProjectUserCanvas).where(
                and_(
                    ProjectUserCanvas.project_id.in_(project_ids),
                    ProjectUserCanvas.user_id == user_id,
                )
            )
        )
        return list(result.scalars().all())
