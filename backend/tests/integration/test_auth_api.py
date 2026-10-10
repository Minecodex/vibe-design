import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "username": "newuser",
            "password": "Test1234!",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["data"]["email"] == "newuser@example.com"


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, db_session):
    from app.models.user import User
    from app.core.security import get_password_hash

    user = User(
        email="dup@example.com",
        username="dupuser",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "dup@example.com", "username": "otheruser", "password": "Test1234!"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db_session):
    from app.models.user import User
    from app.core.security import get_password_hash

    user = User(
        email="login@example.com",
        username="loginuser",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"account": "login@example.com", "password": "Test1234!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["email"] == "login@example.com"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, db_session):
    from app.models.user import User
    from app.core.security import get_password_hash

    user = User(
        email="wrongpwd@example.com",
        username="wrongpwduser",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(user)
    await db_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"account": "wrongpwd@example.com", "password": "WrongPass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(auth_client: AsyncClient):
    response = await auth_client.get("/api/v1/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("catalog_status, expected_status", [
    ("ready", "healthy"), ("unavailable", "unhealthy"),
])
async def test_health_check(client: AsyncClient, monkeypatch, catalog_status, expected_status):
    monkeypatch.setattr(
        "app.services.license_service.agent_catalog_health",
        AsyncMock(return_value={"status": catalog_status}),
    )
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == expected_status


@pytest.mark.asyncio
async def test_public_config_returns_localized_app_names(client: AsyncClient):
    response = await client.get("/api/v1/public-config")

    assert response.status_code == 200
    data = response.json()
    assert data["app_name"] == "像素重组"
    assert data["app_name_en"] == "Pixel Reorganization"
    assert data["upload_limits"]["avatar_max_bytes"] == 5 * 1024 * 1024
    assert data["upload_limits"]["canvas_image_max_bytes"] == 20 * 1024 * 1024
    assert data["upload_limits"]["canvas_video_max_bytes"] == 500 * 1024 * 1024
    assert data["upload_limits"]["harness_attachment_max_bytes"] == 50 * 1024 * 1024
