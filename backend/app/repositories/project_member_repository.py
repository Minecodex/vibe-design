from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.project_member import ProjectMember
from app.repositories.base_repository import BaseRepository

class ProjectMemberRepository(BaseRepository[ProjectMember]):
    def __init__(self, db: AsyncSession):
        super().__init__(ProjectMember, db)

    async def get_by_project_id(self, project_id: int) -> list[ProjectMember]:
        # Using selectinload isn't available easily here because it requires mapping,
        # but we can return just the members and let service manual fetch or we can join user.
        # Actually in FastAPI, we can join User in queries or define relationship in model.
        # Since I didn't define a SQLAlchemy relationship on ProjectMember to User, I'll fetch it differently or just add it.
        # Let's write the query to return just members for now
        result = await self.db.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id)
            .order_by(ProjectMember.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_project_and_user(self, project_id: int, user_id: int) -> ProjectMember | None:
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def remove_member(self, project_id: int, user_id: int):
        await self.db.execute(
            delete(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id
            )
        )
        await self.db.commit()
