import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest
from PIL import Image
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import API_V1_STR, settings
from app.core.security import create_access_token
from app.models.user import User


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _build_license_code(private_key, *, expires_at: datetime, builtin_provider_api_key: str) -> str:
    payload = {
        "expires_at": expires_at.isoformat(),
        "builtin_provider_api_key": builtin_provider_api_key,
        "edition": "flagship",
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode()
    signature = private_key.sign(
        payload_bytes,
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    envelope_bytes = json.dumps(
        {
            "version": 2,
            "payload": _b64url_encode(payload_bytes),
            "signature": _b64url_encode(signature),
        },
        separators=(",", ":"),
    ).encode()
    aesgcm = AESGCM(hashlib.sha256(settings.LICENSE_ENVELOPE_KEY.encode()).digest())
    nonce = os.urandom(12)
    return _b64url_encode(nonce + aesgcm.encrypt(nonce, envelope_bytes, None))


@pytest.fixture
def license_keypair(monkeypatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "private")
    monkeypatch.setattr(
        settings,
        "REDEMPTION_PUBLIC_KEY",
        public_pem.decode().replace("\n", "\\n"),
    )
    monkeypatch.setattr(settings, "LICENSE_ENVELOPE_KEY", "integration-test-envelope-key")
    return private_key


@pytest.fixture
async def licensed_client(client: AsyncClient, license_keypair):
    code = _build_license_code(
        license_keypair,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        builtin_provider_api_key="sk-users-tests",
    )
    response = await client.post("/api/v1/license/activate", json={"code": code})
    assert response.status_code == 200
    return client


@pytest.mark.asyncio
async def test_get_user_detail(licensed_client: AsyncClient, db_session: AsyncSession):
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

    response = await licensed_client.get(f"/api/v1/users/{user.id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "detail_user"


@pytest.mark.asyncio
async def test_update_avatar(licensed_client: AsyncClient, db_session: AsyncSession):
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
    response = await licensed_client.patch(
        f"/api/v1/users/{user.id}",
        headers=headers,
        json={"avatar_url": new_avatar},
    )
    assert response.status_code == 200
    assert response.json()["avatar_url"] == new_avatar


@pytest.mark.asyncio
async def test_get_me(licensed_client: AsyncClient, db_session: AsyncSession):
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

    response = await licensed_client.get("/api/v1/users/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "me_user"


@pytest.mark.asyncio
async def test_update_user_forbidden(licensed_client: AsyncClient, db_session: AsyncSession):
    user1 = User(email="u1@example.com", username="u1", hashed_password="pw")
    user2 = User(email="u2@example.com", username="u2", hashed_password="pw")
    db_session.add(user1)
    db_session.add(user2)
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    token = create_access_token(user1.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await licensed_client.patch(
        f"/api/v1/users/{user2.id}",
        headers=headers,
        json={"username": "new_name"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "权限不足"


@pytest.mark.asyncio
async def test_update_user_not_found(licensed_client: AsyncClient, db_session: AsyncSession):
    admin = User(email="admin@example.com", username="admin", hashed_password="pw", role="admin")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await licensed_client.patch(
        "/api/v1/users/99999",
        headers=headers,
        json={"username": "new_name"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "用户不存在"


@pytest.mark.asyncio
async def test_get_user_not_found(licensed_client: AsyncClient, db_session: AsyncSession):
    user = User(email="find@example.com", username="find", hashed_password="pw")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    response = await licensed_client.get("/api/v1/users/99999", headers=headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "用户不存在"


@pytest.mark.asyncio
async def test_upload_avatar_forbidden(licensed_client: AsyncClient, db_session: AsyncSession):
    user1 = User(email="ava1@example.com", username="ava1", hashed_password="pw")
    user2 = User(email="ava2@example.com", username="ava2", hashed_password="pw")
    db_session.add_all([user1, user2])
    await db_session.commit()
    await db_session.refresh(user1)
    await db_session.refresh(user2)

    token = create_access_token(user1.id)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("test.png", b"test data", "image/png")}
    response = await licensed_client.post(
        f"/api/v1/users/{user2.id}/avatar",
        headers=headers,
        files=files,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_avatar_not_found(licensed_client: AsyncClient, db_session: AsyncSession):
    admin = User(email="admin2@example.com", username="admin2", hashed_password="pw", role="admin")
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("test.png", b"test data", "image/png")}
    response = await licensed_client.post(
        "/api/v1/users/99999/avatar",
        headers=headers,
        files=files,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_avatar_replaces_old_local_avatar(
    licensed_client: AsyncClient,
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
    response = await licensed_client.post(
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
    licensed_client: AsyncClient,
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

    username_response = await licensed_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"query": "spark"},
    )
    assert username_response.status_code == 200
    username_items = username_response.json()["data"]
    assert [item["username"] for item in username_items] == ["spark_designer"]

    nickname_response = await licensed_client.get(
        "/api/v1/users/search",
        headers=headers,
        params={"query": "拿铁"},
    )
    assert nickname_response.status_code == 200
    nickname_items = nickname_response.json()["data"]
    assert [item["username"] for item in nickname_items] == ["coffee_artist"]
