from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_paginated_users(self, page: int, page_size: int, search: str | None = None) -> tuple[int, list[User]]:
        from sqlalchemy import or_, func

        query = select(User)
        count_query = select(func.count()).select_from(User)

        if search:
            search_clause = or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.nickname.ilike(f"%{search}%")
            )
            query = query.where(search_clause)
            count_query = count_query.where(search_clause)

        total_result = await self.db.execute(count_query)
        total = total_result.scalar_one()

        query = query.offset((page - 1) * page_size).limit(page_size).order_by(User.created_at.desc())
        result = await self.db.execute(query)
        items = list(result.scalars().all())

        return total, items

    async def search(self, query: str) -> list[User]:
        from sqlalchemy import or_
        q = select(User).where(
            or_(
                User.username.ilike(f"%{query}%"),
                User.nickname.ilike(f"%{query}%")
            )
        )
        result = await self.db.execute(q)
        return list(result.scalars().all())
