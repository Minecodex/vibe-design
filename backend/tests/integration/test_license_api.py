from datetime import UTC, datetime

import pytest

from app.models.license import LicenseRecord


@pytest.mark.asyncio
async def test_protected_routes_no_longer_depend_on_license(auth_client):
    response = await auth_client.get("/api/v1/auth/me")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_license_activation_route_is_removed(client):
    response = await client.post(
        "/api/v1/license/activate",
        json={"code": "not-a-real-license"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("deploy_type", ["private", "saas"])
async def test_health_reports_flagship_and_apimart_balance_mode(
    client,
    monkeypatch,
    deploy_type,
):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEPLOY_TYPE", deploy_type)

    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["license_status"] == "active"
    assert payload["license_edition"] == "flagship"
    assert payload["license_expired"] is False
    assert payload["license_expires_at"] is None
    assert payload["provider_balance_sync_enabled"] is True
    assert "balance_cents" not in payload["background"]["provider_balance_sync"]


@pytest.mark.asyncio
async def test_legacy_license_records_do_not_change_health(client, db_session):
    db_session.add(
        LicenseRecord(
            token_hash="legacy-record-hash",
            license_token="legacy-record-token",
            created_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["license_status"] == "active"
    assert response.json()["license_edition"] == "flagship"
