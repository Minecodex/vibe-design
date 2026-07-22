"""Deprecated compatibility shim for the removed global provider key flow."""

from fastapi import HTTPException, status
from app.core.license_runtime import license_runtime_state


async def ensure_builtin_provider_api_key(_db) -> str:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "code": "APIMART_KEY_REQUIRED_USER",
            "message": "当前账号尚未配置 APIMart Key，请联系管理员配置",
        },
    )
