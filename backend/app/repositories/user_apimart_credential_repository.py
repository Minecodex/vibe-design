from datetime import UTC, datetime

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_apimart_credential import UserApimartCredential
from app.repositories.base_repository import BaseRepository


class UserApimartCredentialRepository(BaseRepository[UserApimartCredential]):
    def __init__(self, db: AsyncSession):
        super().__init__(UserApimartCredential, db)

    async def get_current(self, user_id: int) -> UserApimartCredential | None:
        result = await self.db.execute(
            select(UserApimartCredential)
            .where(
                and_(
                    UserApimartCredential.user_id == user_id,
                    UserApimartCredential.is_current.is_(True),
                    UserApimartCredential.status.in_(("active", "invalid")),
                )
            )
            .order_by(UserApimartCredential.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_for_task(self, credential_id: int, user_id: int) -> UserApimartCredential | None:
        result = await self.db.execute(
            select(UserApimartCredential).where(
                UserApimartCredential.id == credential_id,
                UserApimartCredential.user_id == user_id,
                UserApimartCredential.status.in_(("active", "invalid", "replaced", "revoked")),
            )
        )
        return result.scalar_one_or_none()

    async def list_current_active_after_id(
        self,
        after_id: int,
        limit: int,
    ) -> list[UserApimartCredential]:
        result = await self.db.execute(
            select(UserApimartCredential)
            .where(
                UserApimartCredential.id > max(int(after_id), 0),
                UserApimartCredential.is_current.is_(True),
                UserApimartCredential.status == "active",
            )
            .order_by(UserApimartCredential.id.asc())
            .limit(max(int(limit), 1))
        )
        return list(result.scalars().all())

    async def mark_credentials_invalid(self, credential_ids: list[int]) -> int:
        normalized_ids = sorted({int(value) for value in credential_ids if int(value) > 0})
        if not normalized_ids:
            return 0
        result = await self.db.execute(
            update(UserApimartCredential)
            .where(
                UserApimartCredential.id.in_(normalized_ids),
                UserApimartCredential.is_current.is_(True),
                UserApimartCredential.status == "active",
            )
            .values(status="invalid", last_checked_at=datetime.now(UTC))
        )
        await self.db.commit()
        return int(result.rowcount or 0)

    async def replace_current(self, user_id: int, api_key: str, created_by_user_id: int) -> UserApimartCredential:
        now = datetime.now(UTC)
        # Serialize rotations for one user across Python worker processes. This
        # prevents two concurrent admin requests from both creating a current row.
        await self.db.execute(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        await self.db.execute(
            update(UserApimartCredential)
            .where(
                UserApimartCredential.user_id == user_id,
                UserApimartCredential.is_current.is_(True),
            )
            .values(is_current=False, status="replaced", replaced_at=now)
        )
        credential = UserApimartCredential(
            user_id=user_id,
            api_key=api_key,
            status="active",
            is_current=True,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(credential)
        await self.db.commit()
        await self.db.refresh(credential)
        return credential

    async def revoke_current(self, user_id: int) -> UserApimartCredential | None:
        await self.db.execute(
            select(User.id).where(User.id == user_id).with_for_update()
        )
        credential = await self.get_current(user_id)
        if credential is None:
            return None
        credential.is_current = False
        credential.status = "revoked"
        credential.revoked_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(credential)
        return credential
