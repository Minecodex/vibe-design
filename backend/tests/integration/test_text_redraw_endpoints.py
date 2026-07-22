from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.default_models import get_default_image_analysis_model


async def _create_authenticated_user(client: AsyncClient, db_session):
    from app.core.security import create_access_token
    from app.models.user import User

    suffix = uuid4().hex[:8]
    user = User(
        email=f"text-redraw-{suffix}@example.com",
        username=f"textredraw-{suffix}",
        hashed_password="not-needed-for-token-auth",
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(subject=user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return user


@pytest.mark.asyncio
async def test_text_redraw_extract_returns_segments(client: AsyncClient, db_session, monkeypatch):
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Text Redraw Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    async def fake_chat(
        self,
        *,
        user_id,
        model_name,
        provider_code=None,
        messages,
        temperature=1.0,
        max_tokens=8192,
        **kwargs,
    ):
        assert user_id == user.id
        assert model_name == get_default_image_analysis_model()
        assert provider_code == "builtin"
        assert messages[0]["content"][0]["type"] == "text"
        return {
            "choices": [
                {
                    "message": {
                        "content": '[{"text":"MARSHALL","order":1},{"text":"EST.1962","order":2}]'
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "app.services.multimodal_service.MultimodalService.chat",
        fake_chat,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/text-redraw/extract",
        json={"image_url": "/api/v1/uploads/canvas/demo.png"},
    )

    assert response.status_code == 200
    assert response.json()["segments"] == [
        {"id": "seg-1", "text": "MARSHALL", "order": 1},
        {"id": "seg-2", "text": "EST.1962", "order": 2},
    ]


@pytest.mark.asyncio
async def test_text_redraw_extract_uses_inline_data_for_local_uploads(
    client: AsyncClient, db_session, monkeypatch
):
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Text Redraw Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    async def fake_chat(
        self,
        *,
        user_id,
        model_name,
        provider_code=None,
        messages,
        temperature=1.0,
        max_tokens=8192,
        **kwargs,
    ):
        assert model_name == get_default_image_analysis_model()
        assert provider_code == "builtin"
        image_part = messages[0]["content"][1]
        assert image_part["image_url"]["url"] == "data:image/png;base64,ZmFrZS1pbWFnZS1kYXRh"
        return {
            "choices": [
                {
                    "message": {
                        "content": '[{"text":"MARSHALL","order":1}]'
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "app.services.multimodal_service.MultimodalService.chat",
        fake_chat,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.generation.resolve_url_for_api",
        lambda url, prefer="base64": {
            "type": "base64",
            "mime_type": "image/png",
            "data": "ZmFrZS1pbWFnZS1kYXRh",
        },
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/text-redraw/extract",
        json={"image_url": "/api/v1/uploads/canvas/demo.png"},
    )

    assert response.status_code == 200
    assert response.json()["segments"] == [
        {"id": "seg-1", "text": "MARSHALL", "order": 1},
    ]


@pytest.mark.asyncio
async def test_text_redraw_extract_uses_ollama_default_model_when_enabled(
    client: AsyncClient, db_session, monkeypatch
):
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_ANALYSIS_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Text Redraw Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    async def fake_chat(self, *, user_id, model_name, provider_code=None, messages, temperature=1.0, max_tokens=8192, **kwargs):
        assert user_id == user.id
        assert model_name == "gemma4:e4b"
        assert provider_code == "ollama"
        return {
            "choices": [
                {
                    "message": {
                        "content": '[{"text":"MARSHALL","order":1}]'
                    }
                }
            ]
        }

    monkeypatch.setattr(
        "app.services.multimodal_service.MultimodalService.chat",
        fake_chat,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/text-redraw/extract",
        json={"image_url": "/api/v1/uploads/canvas/demo.png"},
    )

    assert response.status_code == 200
    assert response.json()["segments"] == [
        {"id": "seg-1", "text": "MARSHALL", "order": 1},
    ]


@pytest.mark.asyncio
async def test_text_redraw_submit_returns_generation_task(client: AsyncClient, db_session, monkeypatch):
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Text Redraw Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    poller_calls = []
    usage_log_calls = []

    async def fake_generate_image(self, **kwargs):
        assert kwargs["user_id"] == user.id
        assert kwargs["project_id"] == project.id
        assert kwargs["image_urls"] == ["/api/v1/uploads/canvas/demo.png"]
        assert kwargs["model_name"] == "gemini-3.1-flash-image-preview-official"
        assert '"MARSHALL" -> "NEW BRAND"' in kwargs["prompt"]
        return SimpleNamespace(
            id=123,
            project_id=project.id,
            task_type="text2image",
            provider_code="builtin",
            model_name="gemini-3.1-flash-image-preview-official",
            model_label="NanoBanana2",
            prompt=kwargs["prompt"],
            status="processing",
            progress=0,
            external_task_id="abc",
            result_url=None,
            result_urls=None,
            error_message=None,
            created_at=datetime(2026, 3, 19, 0, 0, 0),
            updated_at=datetime(2026, 3, 19, 0, 0, 0),
        )

    async def fake_enqueue_task(task_id, **kwargs):
        kwargs["task_id"] = task_id
        poller_calls.append(kwargs)

    async def fake_reserve_builtin_billing(self, *, user_id, model_name, task_type, resolution, duration, params):
        assert user_id == user.id
        assert model_name == "gemini-3.1-flash-image-preview-official"
        assert task_type == "text_redraw"
        return 7

    async def fake_create_usage_log(self, **kwargs):
        usage_log_calls.append(kwargs)
        return None

    monkeypatch.setattr(
        "app.services.generation_service.GenerationService.generate_image",
        fake_generate_image,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.generation.DEFAULT_IMAGE_PROVIDER",
        "builtin",
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.GenerationIntakeService._reserve_builtin_billing",
        fake_reserve_builtin_billing,
    )
    monkeypatch.setattr(
        "app.services.billing_service.BillingService.create_usage_log",
        fake_create_usage_log,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.generation.get_feature_image_model",
        lambda feature_name: "gemini-3.1-flash-image-preview-official" if feature_name == "text_redraw" else f"unexpected-{feature_name}",
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        fake_enqueue_task,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/generate/text-redraw",
        json={
            "source_image_url": "/api/v1/uploads/canvas/demo.png",
            "original_segments": [{"id": "1", "text": "MARSHALL", "order": 1}],
            "edited_segments": [{"id": "1", "text": "NEW BRAND", "order": 1}],
        },
    )

    assert response.status_code == 200
    assert response.json()["task_type"] == "text2image"
    assert response.json()["status"] == "processing"
    assert usage_log_calls == [
        {
            "user_id": user.id,
            "task_id": 123,
            "model_name": "gemini-3.1-flash-image-preview-official",
            "task_type": "text_redraw",
            "amount_cents": 7,
            "params": {"resolution": "1K", "aspect_ratio": "1:1"},
            "task_status": "pending",
            "billing_label": "billing.labels.text_redraw",
            "provider_code": "apimart",
            "billing_mode": "local_price",
        }
    ]
    assert poller_calls == [
        {
            "task_id": 123,
            "workflow_stage": "provider_query",
        }
    ]
