import re
from pydantic import BaseModel, EmailStr, field_validator


class UserBase(BaseModel):
    email: EmailStr
    username: str
    avatar_url: str | None = None
    nickname: str | None = None
    bio: str | None = None


class UserCreate(UserBase):
    password: str
    role: str | None = "user"

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码需包含大写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含数字")
        return v


class UserCreateByAdmin(UserBase):
    password: str = "123456"
    role: str = "user"


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = None
    is_active: bool | None = None
    avatar_url: str | None = None
    nickname: str | None = None
    bio: str | None = None
    role: str | None = None
    password: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError("密码至少 8 位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码需包含大写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含数字")
        return v

class UserRead(UserBase):
    id: int
    role: str
    is_active: bool
    balance_cents: int = 0

    model_config = {"from_attributes": True}


class UserChangePassword(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("密码至少 8 位")
        if not re.search(r"[A-Z]", v):
            raise ValueError("密码需包含大写字母")
        if not re.search(r"\d", v):
            raise ValueError("密码需包含数字")
        return v
