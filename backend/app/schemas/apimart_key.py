from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ApimartKeyWrite(BaseModel):
    api_key: str = Field(..., min_length=1, max_length=2000)

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("APIMart Key 不能为空")
        return value


class ApimartKeyStatus(BaseModel):
    configured: bool
    status: str | None = None
    key_hint: str | None = None
    updated_at: datetime | None = None
