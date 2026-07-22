from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.photoshop_edit_job import PhotoshopEditJob
from app.repositories.base_repository import BaseRepository


class PhotoshopEditJobRepository(BaseRepository[PhotoshopEditJob]):
    def __init__(self, db: AsyncSession):
        super().__init__(PhotoshopEditJob, db)

    async def get_active_duplicate(
        self,
        *,
        project_id: int,
        request_user_id: int,
        source_canvas_item_id: str,
    ) -> PhotoshopEditJob | None:
        result = await self.db.execute(
            select(PhotoshopEditJob)
            .where(
                PhotoshopEditJob.project_id == project_id,
                PhotoshopEditJob.request_user_id == request_user_id,
                PhotoshopEditJob.source_canvas_item_id == source_canvas_item_id,
                PhotoshopEditJob.status.in_(("pending", "claimed")),
            )
            .order_by(desc(PhotoshopEditJob.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_pending_for_user(self, user_id: int) -> list[PhotoshopEditJob]:
        result = await self.db.execute(
            select(PhotoshopEditJob)
            .where(
                PhotoshopEditJob.request_user_id == user_id,
                PhotoshopEditJob.status == "pending",
            )
            .order_by(desc(PhotoshopEditJob.updated_at), desc(PhotoshopEditJob.id))
        )
        return list(result.scalars().all())

