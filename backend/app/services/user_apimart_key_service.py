from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import LoopSafeAsyncSessionLocal
from app.models.user import User
from app.models.user_apimart_credential import UserApimartCredential
from app.repositories.user_apimart_credential_repository import UserApimartCredentialRepository

APIMART_KEY_REQUIRED_ADMIN = "APIMART_KEY_REQUIRED_ADMIN"
APIMART_KEY_REQUIRED_USER = "APIMART_KEY_REQUIRED_USER"
APIMART_KEY_INVALID = "APIMART_KEY_INVALID"


def mask_apimart_key(api_key: str) -> str:
    value = str(api_key or "")
    if len(value) <= 4:
        return "****"
    return f"{value[:2]}***{value[-2:]}"


class UserApimartKeyService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = UserApimartCredentialRepository(db)

    async def get_current_credential(self, user_id: int) -> UserApimartCredential | None:
        return await self.repo.get_current(user_id)

    async def resolve_key(
        self,
        user_id: int,
        *,
        credential_id: int | None = None,
        user_role: str | None = None,
    ) -> tuple[str, int]:
        credential = (
            await self.repo.get_for_task(credential_id, user_id)
            if credential_id is not None
            else await self.repo.get_current(user_id)
        )
        if credential is None:
            code = APIMART_KEY_REQUIRED_ADMIN if user_role == "admin" else APIMART_KEY_REQUIRED_USER
            message = (
                "请前往组织管理配置 APIMart Key"
                if code == APIMART_KEY_REQUIRED_ADMIN
                else "当前账号尚未配置 APIMart Key，请联系管理员配置"
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": code, "message": message})
        if credential.status == "invalid":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": APIMART_KEY_INVALID, "message": "APIMart Key 无效，请联系管理员重新配置"},
            )
        return credential.api_key, credential.id

    async def status(self, user_id: int) -> dict:
        credential = await self.repo.get_current(user_id)
        if credential is None:
            return {"configured": False, "status": None, "key_hint": None, "updated_at": None}
        return {
            "configured": True,
            "status": credential.status,
            "key_hint": mask_apimart_key(credential.api_key),
            "updated_at": credential.updated_at,
        }

    async def set_key(self, user_id: int, api_key: str, created_by_user_id: int) -> dict:
        credential = await self.repo.replace_current(user_id, api_key.strip(), created_by_user_id)
        return {
            "configured": True,
            "status": credential.status,
            "key_hint": mask_apimart_key(credential.api_key),
            "updated_at": credential.updated_at,
        }

    async def revoke_key(self, user_id: int) -> dict:
        credential = await self.repo.revoke_current(user_id)
        return {
            "configured": False,
            "status": credential.status if credential else None,
            "key_hint": mask_apimart_key(credential.api_key) if credential else None,
            "updated_at": credential.updated_at if credential else None,
        }

    async def mark_invalid(self, credential_id: int, user_id: int) -> None:
        credential = await self.repo.get_for_task(credential_id, user_id)
        if credential is None:
            return
        credential.status = "invalid"
        credential.last_checked_at = datetime.now(UTC)
        await self.db.commit()


async def resolve_user_apimart_key_for_context(user_id: int) -> str:
    """Resolve a user key for worker/activity code that owns no request session."""
    async with LoopSafeAsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        api_key, _ = await UserApimartKeyService(db).resolve_key(
            user_id,
            user_role=getattr(user, "role", None),
        )
        return api_key
