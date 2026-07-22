import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash
from app.models.photoshop_edit_job import PhotoshopEditJob
from app.models.project import Project
from app.models.project_user_canvas import ProjectUserCanvas
from app.models.user import User


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _build_license_code(
    private_key,
    *,
    expires_at: datetime,
    builtin_provider_api_key: str,
    edition: str,
) -> str:
    payload = {
        "expires_at": expires_at.isoformat(),
        "builtin_provider_api_key": builtin_provider_api_key,
        "edition": edition,
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
    monkeypatch.setattr(settings, "LICENSE_ENVELOPE_KEY", "license-capabilities-envelope-key")
    return private_key


async def _create_user(client, db_session, *, suffix: str = "premium") -> User:
    user = User(
        email=f"license-capability-{suffix}@example.com",
        username=f"license_capability_{suffix}",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    client.headers["Authorization"] = f"Bearer {create_access_token(subject=user.id)}"
    return user


async def _activate_license(client, private_key, *, edition: str) -> None:
    code = _build_license_code(
        private_key,
        expires_at=datetime.now(UTC) + timedelta(days=7),
        builtin_provider_api_key=f"sk-{edition}-capability",
        edition=edition,
    )
    response = await client.post("/api/v1/license/activate", json={"code": code})
    assert response.status_code == 200


async def _create_project(db_session, *, user_id: int, title: str = "Capability Project") -> Project:
    project = Project(user_id=user_id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_premium_license_blocks_harness_send_message(client, db_session, license_keypair):
    user = await _create_user(client, db_session, suffix="harness")
    await _activate_license(client, license_keypair, edition="premium")

    create_response = await client.post("/api/v1/agent/harness/conversations", json={})
    assert create_response.status_code == 200
    conversation_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/agent/harness/conversations/{conversation_id}/messages",
        json={"content": "hello"},
    )

    assert user.id > 0
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_premium_license_allows_canvas_harness_send_message(
    client,
    db_session,
    license_keypair,
    monkeypatch,
):
    user = await _create_user(client, db_session, suffix="canvas-harness")
    await _activate_license(client, license_keypair, edition="premium")
    project = await _create_project(db_session, user_id=user.id, title="Canvas Harness Capability Project")
    enqueue_calls: list[dict] = []

    create_response = await client.post(
        "/api/v1/agent/harness/conversations",
        json={"runtime_profile": "canvas", "project_id": project.id},
    )
    assert create_response.status_code == 200
    conversation_id = create_response.json()["id"]

    async def _stream_live_events(_user_id, _conversation_id, **_kwargs):
        if False:
            yield ""

    async def _load_canvas_items(*_args, **_kwargs):
        return []

    async def _enqueue_message_run(*, user_id, conversation_id, payload, idempotency_key):
        enqueue_calls.append({
            "user_id": user_id,
            "conversation_id": conversation_id,
            "payload": payload,
            "idempotency_key": idempotency_key,
        })
        return SimpleNamespace(id=123, run_id="run-canvas-test")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_message_run",
        _enqueue_message_run,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.harness._stream_live_events",
        _stream_live_events,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.canvas.load_canvas_items",
        _load_canvas_items,
    )

    response = await client.post(
        f"/api/v1/agent/harness/conversations/{conversation_id}/messages",
        json={"content": "hello from canvas"},
    )

    assert response.status_code == 200
    assert enqueue_calls == [{
        "user_id": user.id,
        "conversation_id": conversation_id,
        "payload": enqueue_calls[0]["payload"],
        "idempotency_key": enqueue_calls[0]["idempotency_key"],
    }]


@pytest.mark.asyncio
async def test_premium_license_blocks_prompt_extractor(client, db_session, license_keypair):
    await _create_user(client, db_session, suffix="prompt")
    await _activate_license(client, license_keypair, edition="premium")

    response = await client.post(
        "/api/v1/extension/prompt-extractor/analyze",
        data={"locale": "zh-CN"},
        files={"image": ("sample.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_premium_license_blocks_photoshop_edit_job_creation(client, db_session, license_keypair):
    user = await _create_user(client, db_session, suffix="ps-create")
    await _activate_license(client, license_keypair, edition="premium")
    project = await _create_project(db_session, user_id=user.id)
    db_session.add(
        ProjectUserCanvas(
            project_id=project.id,
            user_id=user.id,
            canvas_data=[{
                "id": "image-1",
                "type": "image",
                "url": "/api/v1/uploads/canvas/1/source.svg",
                "x": 0,
                "y": 0,
                "width": 512,
                "height": 512,
                "asset_origin": "local_upload",
            }],
            canvas_meta=None,
        )
    )
    await db_session.commit()

    response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-edit-jobs",
        json={
            "source_canvas_item_id": "image-1",
            "svg_url": "/api/v1/uploads/canvas/1/source.svg",
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_premium_license_blocks_photoshop_edit_job_save_and_plugin_save(client, db_session, license_keypair):
    user = await _create_user(client, db_session, suffix="ps-save")
    await _activate_license(client, license_keypair, edition="premium")
    project = await _create_project(db_session, user_id=user.id)
    job = PhotoshopEditJob(
        project_id=project.id,
        request_user_id=user.id,
        source_canvas_item_id="image-1",
        svg_url="/api/v1/uploads/canvas/1/source.svg",
        status="claimed",
        claimed_by_user_id=user.id,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    save_job_response = await client.post(
        f"/api/v1/photoshop-edit-jobs/{job.id}/save",
        json={
            "result_url": "/api/v1/uploads/generated/result.png",
            "width": 512,
            "height": 512,
        },
    )
    save_plugin_response = await client.post(
        f"/api/v1/projects/{project.id}/photoshop-plugin/save",
        json={
            "result_url": "/api/v1/uploads/generated/plugin-result.png",
            "width": 512,
            "height": 512,
        },
    )

    assert save_job_response.status_code == 403
    assert save_plugin_response.status_code == 403
