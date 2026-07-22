import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

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
        "builtin_provider_api_key": "sk-project-admin-tests",
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
    monkeypatch.setattr(settings, "LICENSE_ENVELOPE_KEY", "project-admin-envelope-key")
    return private_key


async def _activate_license(client: AsyncClient, private_key) -> None:
    code = _build_license_code(
        private_key,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    response = await client.post("/api/v1/license/activate", json={"code": code})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_generate_share_link_for_other_users_project(client: AsyncClient, db_session, license_keypair):
    from app.core.security import create_access_token, get_password_hash
    from app.models.project import Project
    from app.models.user import User

    await _activate_license(client, license_keypair)

    owner = User(
        email="project-owner@example.com",
        username="project_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    admin = User(
        email="project-admin@example.com",
        username="project_admin",
        hashed_password=get_password_hash("Test1234!"),
        role="admin",
    )
    db_session.add_all([owner, admin])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)

    project = Project(user_id=owner.id, title="Owner Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    response = await client.post(
        f"/api/v1/share/projects/{project.id}/generate",
        headers=headers,
        json={"share_permission": "viewer"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["id"] == project.id
    assert payload["share_permission"] == "viewer"
    assert payload["share_token"]


@pytest.mark.asyncio
async def test_admin_can_delete_other_users_project(client: AsyncClient, db_session, license_keypair):
    from app.core.security import create_access_token, get_password_hash
    from app.models.project import Project
    from app.models.user import User

    await _activate_license(client, license_keypair)

    owner = User(
        email="delete-owner@example.com",
        username="delete_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    admin = User(
        email="delete-admin@example.com",
        username="delete_admin",
        hashed_password=get_password_hash("Test1234!"),
        role="admin",
    )
    db_session.add_all([owner, admin])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)

    project = Project(user_id=owner.id, title="Delete Me")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    response = await client.delete(f"/api/v1/projects/{project.id}", headers=headers)

    assert response.status_code == 200

    await db_session.refresh(project)
    assert project.deleted_at is not None


@pytest.mark.asyncio
async def test_admin_can_add_project_member_for_other_users_project(client: AsyncClient, db_session, license_keypair):
    from app.core.security import create_access_token, get_password_hash
    from app.models.project import Project
    from app.models.project_member import ProjectMember
    from app.models.user import User
    from sqlalchemy import select

    await _activate_license(client, license_keypair)

    owner = User(
        email="member-owner@example.com",
        username="member_owner",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    admin = User(
        email="member-admin@example.com",
        username="member_admin",
        hashed_password=get_password_hash("Test1234!"),
        role="admin",
    )
    new_member = User(
        email="new-member@example.com",
        username="new_member",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add_all([owner, admin, new_member])
    await db_session.commit()
    await db_session.refresh(owner)
    await db_session.refresh(admin)
    await db_session.refresh(new_member)

    project = Project(user_id=owner.id, title="Member Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    headers = {"Authorization": f"Bearer {create_access_token(subject=admin.id)}"}
    response = await client.post(
        f"/api/v1/projects/{project.id}/members",
        headers=headers,
        json={"user_id": new_member.id, "role": "editor"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project_id"] == project.id
    assert payload["user_id"] == new_member.id
    assert payload["role"] == "editor"

    member_result = await db_session.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == new_member.id,
        )
    )
    assert member_result.scalar_one_or_none() is not None
