from io import BytesIO

import pytest
from PIL import Image
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import API_V1_STR
from app.core.security import create_access_token
from app.models.user import User


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.asyncio
async def test_get_user_detail(client: AsyncClient, db_session: AsyncSession):
    user = User(
        email="detail@example.com",
        username="detail_user",
        hashed_password="hashed_password",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get(f"/api/v1/users/{user.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "detail_user"


@pytest.mark.asyncio
async def test_update_avatar(client: AsyncClient, db_session: AsyncSession):
    user = User(
        email="update@example.com",
        username="update_user",
        hashed_password="hashed_password",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    new_avatar = "https://example.com/new_avatar.png"
    response = await client.patch(
        f"/api/v1/users/{user.id}",
        headers=headers,
        json={"avatar_url": new_avatar},
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"] == new_avatar


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, db_session: AsyncSession):
    user = User(
        email="me@example.com",
        username="me_user",
        hashed_password="hashed_password",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "me_user"


@pytest.mark.asyncio
async def test_update_user_forbidden(client: AsyncClient, db_session: AsyncSession):
    user1 = User(email="u1@example.com", username="u1", hashed_password="pw")
    user2 = User(email="u2@example.com", username="u2", hashed_password="pw")
    db_session.add(user1)
    db_session.add(user2)
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    token = create_access_token(user1.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.patch(
        f"/api/v1/users/{user2.id}",
        headers=headers,
        json={"username": "new_name"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "权限不足"


@pytest.mark.asyncio
async def test_update_user_not_found(client: AsyncClient, db_session: AsyncSession):
    admin = User(email="admin@example.com", username="admin", hashed_password="pw", role="admin")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.patch(
        "/api/v1/users/99999",
        headers=headers,
        json={"username": "new_name"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "用户不存在"


@pytest.mark.asyncio
async def test_get_user_not_found(client: AsyncClient, db_session: AsyncSession):
    user = User(email="find@example.com", username="find", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.get("/api/v1/users/99999", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "用户不存在"


@pytest.mark.asyncio
async def test_upload_avatar_forbidden(client: AsyncClient, db_session: AsyncSession):
    user1 = User(email="ava1@example.com", username="ava1", hashed_password="pw")
    user2 = User(email="ava2@example.com", username="ava2", hashed_password="pw")
    db_session.add_all([user1, user2])
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    token = create_access_token(user1.id)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("test.png", b"test data", "image/png")}
    response = await client.post(
        f"/api/v1/users/{user2.id}/avatar",
        headers=headers,
        files=files,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_avatar_not_found(client: AsyncClient, db_session: AsyncSession):
    admin = User(email="admin2@example.com", username="admin2", hashed_password="pw", role="admin")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("test.png", b"test data", "image/png")}
    response = await client.post(
        "/api/v1/users/99999/avatar",
        headers=headers,
        files=files,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_avatar_replaces_old_local_avatar(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    avatars_dir = tmp_path / "uploads" / "avatars"
    avatars_dir.mkdir(parents=True)
    old_avatar = avatars_dir / "old.png"
    old_avatar.write_bytes(_png_bytes())

    user = User(
        email="avatar-replace@example.com",
        username="avatar_replace",
        hashed_password="pw",
        avatar_url=f"{API_V1_STR}/uploads/avatars/old.png",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.post(
        f"/api/v1/users/{user.id}/avatar",
        headers=headers,
        files={"file": ("new.png", _png_bytes(), "image/png")},
    )

    assert response.status_code == 200
    assert not old_avatar.exists()
    new_avatar_url = response.json()["avatar_url"]
    assert new_avatar_url.startswith(f"{API_V1_STR}/uploads/avatars/")
    assert (tmp_path / new_avatar_url.removeprefix(API_V1_STR).lstrip("/")).exists()


@pytest.mark.asyncio
async def test_search_users_supports_partial_username_and_nickname(
    client: AsyncClient,
    db_session: AsyncSession,
):
    admin = User(email="admin-search@example.com", username="admin_search", hashed_password="pw", role="admin")
    username_match = User(
        email="spark@example.com",
        username="spark_designer",
        nickname="火花设计师",
        hashed_password="pw",
    )
    nickname_match = User(
        email="latte@example.com",
        username="coffee_artist",
        nickname="拿铁小鹿",
        hashed_password="pw",
    )
    unrelated = User(
        email="other@example.com",
        username="unrelated_user",
        nickname="路人甲",
        hashed_password="pw",
    )
    db_session.add_all([admin, username_match, nickname_match, unrelated])
    await db_session.commit()
    await db_session.refresh(admin)

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    username_response = await client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"query": "spark"},
    )
    assert username_response.status_code == 200
    username_items = username_response.json()["data"]
    assert [item["username"] for item in username_items] == ["spark_designer"]

    nickname_response = await client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"query": "拿铁"},
    )
    assert nickname_response.status_code == 200
    nickname_items = nickname_response.json()["data"]
    assert [item["username"] for item in nickname_items] == ["coffee_artist"]
