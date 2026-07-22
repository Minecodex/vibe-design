import logging
import uuid
from pathlib import Path
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status, File, UploadFile, Query
from app.api.deps import DbSession, CurrentUser
from app.schemas.user import UserRead, UserUpdate, UserChangePassword, UserCreate, UserCreateByAdmin
from app.schemas.common import ResponseBase, PaginatedData
from app.repositories.user_repository import UserRepository
from app.core.config import API_V1_STR, settings
from app.core.security import verify_password, get_password_hash
from app.models.user import User
from app.services.upload_writer import IMAGE_RASTER_EXTENSIONS, verify_image_file, write_upload_with_limit

router = APIRouter(prefix="/users", tags=["users"])
logger = logging.getLogger(__name__)

@router.get("/", response_model=ResponseBase[PaginatedData[UserRead]])
async def get_users_list(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None)
):
    """获取用户列表 (仅限管理员)"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    repo = UserRepository(db)
    total, users = await repo.get_paginated_users(page, page_size, search)
    
    return ResponseBase(
        data=PaginatedData(
            items=[UserRead.model_validate(u) for u in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=(total + page_size - 1) // page_size
        )
    )

@router.post("/", response_model=ResponseBase[UserRead], status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
    user_in: UserCreateByAdmin,
    db: DbSession,
    current_user: CurrentUser
):
    """管理员创建用户"""
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
    
    repo = UserRepository(db)
    if await repo.get_by_email(user_in.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")
    if await repo.get_by_username(user_in.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已被注册")

    hashed_password = get_password_hash(user_in.password)
    new_user_data = user_in.model_dump(exclude={"password"})
    new_user_data["hashed_password"] = hashed_password
    
    user_obj = User(**new_user_data)
    created_user = await repo.create(user_obj)
    
    return ResponseBase(data=UserRead.model_validate(created_user))

@router.get("/search", response_model=ResponseBase[list[UserRead]])
async def search_users(
    db: DbSession,
    current_user: CurrentUser,
    query: str = Query(..., min_length=1, description="用户名、昵称或邮箱的精准搜索")
):
    """精准搜索用户 (供邀请使用)"""
    repo = UserRepository(db)
    users = await repo.search(query)
    
    # 转换为 UserRead 返回
    return ResponseBase(data=[UserRead.model_validate(u) for u in users])


@router.post("/{user_id}/avatar", response_model=UserRead)
async def upload_avatar(
    user_id: int,
    db: DbSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
):
    """上传并更新用户头像"""
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    ext = file.filename.split('.')[-1] if file.filename and '.' in file.filename else 'png'
    filename = f"{uuid.uuid4()}.{ext}"
    file_path = Path("uploads/avatars") / filename
    await write_upload_with_limit(
        file,
        file_path,
        max_bytes=settings.AVATAR_UPLOAD_MAX_BYTES,
    )
    try:
        verify_image_file(
            file_path,
            allowed_extensions=IMAGE_RASTER_EXTENSIONS,
            content_type=file.content_type,
        )
    except Exception:
        file_path.unlink(missing_ok=True)
        raise

    old_avatar_url = str(getattr(user, "avatar_url", "") or "")
    avatar_url = f"{API_V1_STR}/uploads/avatars/{filename}"
    updated_user = await repo.update(user, {"avatar_url": avatar_url})
    old_relative = old_avatar_url.removeprefix(API_V1_STR).lstrip("/")
    if old_relative.startswith("uploads/avatars/"):
        try:
            old_path = Path(old_relative)
            if old_path.resolve() != file_path.resolve():
                old_path.unlink(missing_ok=True)
        except Exception:
            logger.warning("Failed to delete old avatar for user %s", user_id, exc_info=True)
    return updated_user


@router.get("/me", response_model=UserRead)
async def get_me(current_user: CurrentUser):
    """获取当前登录用户信息"""
    return current_user


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: DbSession, current_user: CurrentUser):
    """获取指定用户信息"""
    repo = UserRepository(db)
    user = await repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """更新用户信息"""
    # 仅允许更新自己的信息，或管理员更新他人信息
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    update_data = user_in.model_dump(exclude_unset=True)
    if user.username == "admin":
        # Keep the bootstrap administrator privileged; profile and APIMart Key
        # management remain editable through their dedicated flows.
        update_data.pop("role", None)
        update_data.pop("is_active", None)
    if "password" in update_data:
        raw_password = update_data.pop("password")
        if raw_password:
            update_data["hashed_password"] = get_password_hash(raw_password)

    updated_user = await repo.update(user, update_data)
    return updated_user


@router.put("/{user_id}/password")
async def change_password(
    user_id: int,
    password_data: UserChangePassword,
    db: DbSession,
    current_user: CurrentUser,
):
    """修改密码"""
    if current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只能修改自己的密码",
        )

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    if not verify_password(password_data.old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )

    new_hashed_password = get_password_hash(password_data.new_password)
    await repo.update(user, {"hashed_password": new_hashed_password})
    return {"message": "密码修改成功"}



