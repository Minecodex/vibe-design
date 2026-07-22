from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.user_apimart_key_service import (
    APIMART_KEY_REQUIRED_ADMIN,
    APIMART_KEY_REQUIRED_USER,
    UserApimartKeyService,
    mask_apimart_key,
)


def test_mask_apimart_key_never_returns_full_value():
    assert mask_apimart_key("sk-test-key") == "sk***ey"
    assert mask_apimart_key("abc") == "****"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "code"),
    [("admin", APIMART_KEY_REQUIRED_ADMIN), ("user", APIMART_KEY_REQUIRED_USER)],
)
async def test_missing_key_error_depends_on_user_role(role, code):
    service = UserApimartKeyService(object())
    service.repo = SimpleNamespace(get_current=_empty)
    with pytest.raises(HTTPException) as exc_info:
        await service.resolve_key(7, user_role=role)
    assert exc_info.value.detail["code"] == code


async def _empty(_user_id):
    return None
