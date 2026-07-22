from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_asset import ProjectAsset
from app.repositories.base_repository import BaseRepository


class ProjectAssetRepository(BaseRepository[ProjectAsset]):
    def __init__(self, db: AsyncSession):
        super().__init__(ProjectAsset, db)
