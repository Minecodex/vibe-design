from sqlalchemy.ext.asyncio import AsyncSession
from app.db.base import Base
from app.db.session import engine


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
