from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider import UserProvider, ProviderCredential, ProviderModel
from app.repositories.base_repository import BaseRepository


class UserProviderRepository(BaseRepository[UserProvider]):
    def __init__(self, db: AsyncSession):
        super().__init__(UserProvider, db)

    async def get_by_user(self, user_id: int) -> list[UserProvider]:
        result = await self.db.execute(
            select(UserProvider).where(
                and_(
                    UserProvider.user_id == user_id,
                    UserProvider.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_user_and_code(
        self, user_id: int, provider_code: str
    ) -> UserProvider | None:
        result = await self.db.execute(
            select(UserProvider).where(
                and_(
                    UserProvider.user_id == user_id,
                    UserProvider.provider_code == provider_code,
                    UserProvider.deleted_at.is_(None),
                )
            )
        )
        return result.scalar_one_or_none()


class ProviderCredentialRepository(BaseRepository[ProviderCredential]):
    def __init__(self, db: AsyncSession):
        super().__init__(ProviderCredential, db)

    async def get_by_user_and_provider(
        self, user_id: int, provider_code: str
    ) -> list[ProviderCredential]:
        result = await self.db.execute(
            select(ProviderCredential).where(
                and_(
                    ProviderCredential.user_id == user_id,
                    ProviderCredential.provider_code == provider_code,
                    ProviderCredential.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def count_by_user_and_provider(
        self, user_id: int, provider_code: str
    ) -> int:
        rows = await self.get_by_user_and_provider(user_id, provider_code)
        return len(rows)


class ProviderModelRepository(BaseRepository[ProviderModel]):
    def __init__(self, db: AsyncSession):
        super().__init__(ProviderModel, db)

    async def get_by_user_and_provider(
        self, user_id: int, provider_code: str
    ) -> list[ProviderModel]:
        result = await self.db.execute(
            select(ProviderModel).where(
                and_(
                    ProviderModel.user_id == user_id,
                    ProviderModel.provider_code == provider_code,
                    ProviderModel.deleted_at.is_(None),
                )
            )
        )
        return list(result.scalars().all())

    async def count_by_user_and_provider(
        self, user_id: int, provider_code: str
    ) -> int:
        rows = await self.get_by_user_and_provider(user_id, provider_code)
        return len(rows)
