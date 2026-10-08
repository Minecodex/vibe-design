"""The retired license runtime cannot gate access or mutate provider keys."""
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.core.license_runtime import LicenseRuntimeState
from app.models.license import LicenseRecord


@pytest.mark.asyncio
@pytest.mark.parametrize("deploy_type", ["private", "saas"])
async def test_runtime_is_active_without_a_license_database(monkeypatch, deploy_type):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", deploy_type)
    database = AsyncMock()
    state = LicenseRuntimeState()

    for status in (await state.get_status(database), await state.force_refresh(database)):
        assert status.status == "active"
        assert status.edition == "flagship"
        assert status.expired is False
        assert status.expires_at is None
    assert database.mock_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_token", ["expired-test-record", "invalid-test-record"])
async def test_legacy_records_cannot_replace_provider_credentials(
    db_session, monkeypatch, legacy_token,
):
    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_API_KEY", "test-account-key")
    monkeypatch.setattr(settings, "BUILTIN_PROVIDER_CODE", "apimart")
    db_session.add(LicenseRecord(token_hash=legacy_token, license_token=legacy_token))
    await db_session.commit()
    state = LicenseRuntimeState()

    state.invalidate()
    state.reset()
    status = await state.force_refresh(db_session)

    assert status.status == "active"
    assert status.edition == "flagship"
    assert settings.BUILTIN_PROVIDER_API_KEY == "test-account-key"
    assert settings.BUILTIN_PROVIDER_CODE == "apimart"
