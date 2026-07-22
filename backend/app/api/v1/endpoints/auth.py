from fastapi import APIRouter, HTTPException, status
from app.api.deps import DbSession, CurrentUser
from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, RegisterRequest
from app.schemas.user import UserRead
from app.schemas.common import ResponseBase
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ResponseBase[UserRead], status_code=201)
async def register(body: RegisterRequest, db: DbSession) -> ResponseBase[UserRead]:
    service = AuthService(db)
    user = await service.register(body)
    return ResponseBase(message="注册成功", data=user)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: DbSession) -> LoginResponse:
    service = AuthService(db)
    result = await service.authenticate(body.account, body.password)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名/邮箱或密码错误",
        )
    return result


@router.post("/refresh", response_model=LoginResponse)
async def refresh_token(body: RefreshRequest, db: DbSession) -> LoginResponse:
    service = AuthService(db)
    return await service.refresh(body.refresh_token)


@router.post("/logout", response_model=ResponseBase[None])
async def logout(current_user: CurrentUser) -> ResponseBase[None]:
    return ResponseBase(message="已成功退出登录", data=None)


@router.get("/me", response_model=ResponseBase[UserRead])
async def get_me(current_user: CurrentUser) -> ResponseBase[UserRead]:
    return ResponseBase(data=UserRead.model_validate(current_user))
