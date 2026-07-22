import base64
import hashlib
import json
import time
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from httpx import AsyncClient

from app.core.config import settings


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _build_license_code(private_key, *, expires_at: datetime) -> str:
    payload = {
        "expires_at": expires_at.isoformat(),
        "builtin_provider_api_key": "sk-share-api-tests",
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
    monkeypatch.setattr(settings, "LICENSE_ENVELOPE_KEY", "share-api-envelope-key")
    return private_key


async def _activate_license(client: AsyncClient, private_key) -> None:
    code = _build_license_code(
        private_key,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    response = await client.post("/api/v1/license/activate", json={"code": code})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_viewer_share_assets_are_accessible_without_login(client: AsyncClient, db_session, license_keypair):
    from app.core.security import get_password_hash
    from app.models.project import Project
    from app.models.project_asset import ProjectAsset
    from app.models.user import User

    await _activate_license(client, license_keypair)

    owner = User(
        email="share-owner@example.com",
        username="share_owner",
        hashed_password=get_password_hash("Test1234!"),
        nickname="Owner",
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)

    project = Project(
        user_id=owner.id,
        title="Readonly Share Project",
        share_token="viewer-token",
        share_permission="viewer",
        share_expiration=int(time.time()) + 3600,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    image_asset = ProjectAsset(
        project_id=project.id,
        user_id=owner.id,
        asset_type="image",
        url="https://example.com/image.png",
        origin_kind="ai_generated",
    )
    video_asset = ProjectAsset(
        project_id=project.id,
        user_id=owner.id,
        asset_type="video",
        url="https://example.com/video.mp4",
        origin_kind="local_upload",
    )
    db_session.add_all([image_asset, video_asset])
    await db_session.commit()

    response = await client.get(f"/api/v1/share/{project.share_token}/assets")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert {asset["asset_type"] for asset in payload} == {"video", "image"}
    assert payload[0]["project_name"] == "Readonly Share Project"
    assert payload[0]["is_favorite"] is False


@pytest.mark.asyncio
async def test_viewer_share_assets_support_asset_type_filter(client: AsyncClient, db_session, license_keypair):
    from app.core.security import get_password_hash
    from app.models.project import Project
    from app.models.project_asset import ProjectAsset
    from app.models.user import User

    await _activate_license(client, license_keypair)

    owner = User(
        email="share-filter@example.com",
        username="share_filter",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)

    project = Project(
        user_id=owner.id,
        title="Filtered Share Project",
        share_token="viewer-filter-token",
        share_permission="viewer",
        share_expiration=int(time.time()) + 3600,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    db_session.add_all(
        [
            ProjectAsset(
                project_id=project.id,
                user_id=owner.id,
                asset_type="image",
                url="https://example.com/one.png",
                origin_kind="ai_generated",
            ),
            ProjectAsset(
                project_id=project.id,
                user_id=owner.id,
                asset_type="video",
                url="https://example.com/two.mp4",
                origin_kind="ai_generated",
            ),
        ]
    )
    await db_session.commit()

    response = await client.get(f"/api/v1/share/{project.share_token}/assets", params={"asset_type": "image"})

    assert response.status_code == 200
    payload = response.json()["data"]
    assert len(payload) == 1
    assert payload[0]["asset_type"] == "image"


@pytest.mark.asyncio
async def test_viewer_share_assets_include_preview_fields(client: AsyncClient, db_session, license_keypair, monkeypatch: pytest.MonkeyPatch):
    from app.core.security import get_password_hash
    from app.models.project import Project
    from app.models.project_asset import ProjectAsset
    from app.models.user import User
    from app.services.asset_preview_service import asset_preview_service

    await _activate_license(client, license_keypair)

    owner = User(
        email="share-preview@example.com",
        username="share_preview",
        hashed_password=get_password_hash("Test1234!"),
    )
    db_session.add(owner)
    await db_session.commit()
    await db_session.refresh(owner)

    project = Project(
        user_id=owner.id,
        title="Preview Share Project",
        share_token="viewer-preview-token",
        share_permission="viewer",
        share_expiration=int(time.time()) + 3600,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    db_session.add(
        ProjectAsset(
            project_id=project.id,
            user_id=owner.id,
            asset_type="image",
            url="/api/v1/uploads/generated/share-image.png",
            origin_kind="ai_generated",
        )
    )
    await db_session.commit()

    async def fake_get_list_preview(**_kwargs):
        return SimpleNamespace(
            url="/api/v1/uploads/generated/share-image__list_320.webp",
            status="ready",
            target_path=None,
        )

    monkeypatch.setattr(asset_preview_service, "get_list_preview", fake_get_list_preview)

    response = await client.get(f"/api/v1/share/{project.share_token}/assets")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload[0]["list_preview_url"] == "/api/v1/uploads/generated/share-image__list_320.webp"
    assert payload[0]["list_preview_status"] == "ready"
