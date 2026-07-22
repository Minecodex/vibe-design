from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.license import LicenseRecord
from app.repositories.base_repository import BaseRepository


class LicenseRepository(BaseRepository[LicenseRecord]):
    def __init__(self, db: AsyncSession):
        super().__init__(LicenseRecord, db)

    async def get_latest(self) -> LicenseRecord | None:
        result = await self.db.execute(
            select(LicenseRecord)
            .order_by(LicenseRecord.created_at.desc(), LicenseRecord.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_token_hash(self, token_hash: str) -> LicenseRecord | None:
        result = await self.db.execute(
            select(LicenseRecord).where(LicenseRecord.token_hash == token_hash)
        )
        return result.scalar_one_or_none()
