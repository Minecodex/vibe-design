from sqlalchemy.ext.asyncio import AsyncSession
import random
import string
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.exceptions import ConflictException, UnauthorizedException
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse, RegisterRequest
from app.schemas.user import UserRead


class AuthService:
    def __init__(self, db: AsyncSession):
        self.repo = UserRepository(db)

    async def register(self, data: RegisterRequest) -> UserRead:
        if await self.repo.get_by_email(data.email):
            raise ConflictException("该邮箱已被注册")
        if await self.repo.get_by_username(data.username):
            raise ConflictException("该用户名已被使用")

        random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        
        user = User(
            email=data.email,
            username=data.username,
            hashed_password=get_password_hash(data.password),
            nickname=f"User_{random_suffix}"
        )
        user = await self.repo.create(user)
        return UserRead.model_validate(user)

    async def authenticate(self, account: str, password: str) -> LoginResponse | None:
        user = await self.repo.get_by_email(account)
        if not user:
            user = await self.repo.get_by_username(account)
            
        if not user or not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            raise UnauthorizedException("账户已被禁用")

        return LoginResponse(
            access_token=create_access_token(subject=user.id),
            refresh_token=create_refresh_token(subject=user.id),
            user=UserRead.model_validate(user),
        )

    async def refresh(self, refresh_token: str) -> LoginResponse:
        try:
            payload = decode_token(refresh_token)
            if payload.get("type") != "refresh":
                raise UnauthorizedException("无效的 refresh token")
            user_id = int(payload["sub"])
        except (ValueError, KeyError) as e:
            raise UnauthorizedException("无效的 refresh token") from e

        user = await self.repo.get(user_id)
        if not user or not user.is_active:
            raise UnauthorizedException("用户不存在或已被禁用")

        return LoginResponse(
            access_token=create_access_token(subject=user.id),
            refresh_token=create_refresh_token(subject=user.id),
            user=UserRead.model_validate(user),
        )
