from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.apimart_key import ApimartKeyStatus, ApimartKeyWrite
from app.services.user_apimart_key_service import UserApimartKeyService

router = APIRouter(prefix="/users", tags=["apimart-key"])


def _require_admin(user) -> None:
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")


@router.get("/me/apimart-key/status", response_model=ApimartKeyStatus)
async def get_my_apimart_key_status(db: DbSession, current_user: CurrentUser) -> ApimartKeyStatus:
    return ApimartKeyStatus(**(await UserApimartKeyService(db).status(current_user.id)))


@router.get("/{user_id}/apimart-key/status", response_model=ApimartKeyStatus)
async def get_apimart_key_status(user_id: int, db: DbSession, current_user: CurrentUser) -> ApimartKeyStatus:
    _require_admin(current_user)
    return ApimartKeyStatus(**(await UserApimartKeyService(db).status(user_id)))


@router.put("/{user_id}/apimart-key", response_model=ApimartKeyStatus)
async def set_apimart_key(
    user_id: int,
    body: ApimartKeyWrite,
    db: DbSession,
    current_user: CurrentUser,
) -> ApimartKeyStatus:
    _require_admin(current_user)
    return ApimartKeyStatus(
        **(await UserApimartKeyService(db).set_key(user_id, body.api_key, current_user.id))
    )


@router.delete("/{user_id}/apimart-key", response_model=ApimartKeyStatus)
async def revoke_apimart_key(user_id: int, db: DbSession, current_user: CurrentUser) -> ApimartKeyStatus:
    _require_admin(current_user)
    return ApimartKeyStatus(**(await UserApimartKeyService(db).revoke_key(user_id)))
