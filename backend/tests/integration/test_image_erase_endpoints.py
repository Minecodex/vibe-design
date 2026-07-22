from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.config import settings


async def _create_authenticated_user(client: AsyncClient, db_session):
    from app.core.security import create_access_token
    from app.models.user import User

    suffix = uuid4().hex[:8]
    user = User(
        email=f"image-erase-{suffix}@example.com",
        username=f"imageerase-{suffix}",
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
async def test_removed_local_media_endpoints_return_not_found(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")

    responses = [
        await client.post("/api/v1/projects/1/erase/segments", json={"image_url": "/demo.png"}),
        await client.post(
            "/api/v1/projects/1/generate/subject-separation",
            json={"source_image_url": "/demo.png", "source_width": 100, "source_height": 100},
        ),
        await client.get("/api/v1/media-operations/retired-operation"),
    ]

    assert [response.status_code for response in responses] == [404, 404, 404]


@pytest.mark.asyncio
async def test_generate_erase_returns_generation_task(client: AsyncClient, db_session, monkeypatch):
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Erase Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    poller_calls = []
    usage_log_calls = []

    async def fake_generate_image(self, **kwargs):
        assert kwargs["user_id"] == user.id
        assert kwargs["project_id"] == project.id
        assert kwargs["image_urls"] == ["/api/v1/uploads/canvas/composite.png"]
        assert "mask_url" not in kwargs or kwargs.get("mask_url") is None
        assert kwargs["model_name"] == "gemini-3.1-flash-image-preview-official"
        assert kwargs["prompt"]
        return SimpleNamespace(
            id=456,
            project_id=project.id,
            task_type="text2image",
            provider_code="builtin",
            model_name="gemini-3.1-flash-image-preview-official",
            model_label="NanoBanana2",
            prompt=kwargs["prompt"],
            status="processing",
            progress=0,
            external_task_id="erase-task",
            result_url=None,
            result_urls=None,
            error_message=None,
            created_at=datetime(2026, 3, 20, 0, 0, 0),
            updated_at=datetime(2026, 3, 20, 0, 0, 0),
            params={
                "generation_kind": "image_erase",
            },
        )

    async def fake_enqueue_task(task_id, **kwargs):
        kwargs["task_id"] = task_id
        poller_calls.append(kwargs)

    async def fake_reserve_builtin_billing(self, *, user_id, model_name, task_type, resolution, duration, params):
        assert user_id == user.id
        assert model_name == "gemini-3.1-flash-image-preview-official"
        assert task_type == "image_erase"
        return 11

    async def fake_validate_provider_model(self, request, *, task_type):
        assert request.provider_code == "builtin"
        assert task_type == "image_erase"

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
        "app.services.generation_intake_service.GenerationIntakeService._validate_provider_model",
        fake_validate_provider_model,
    )
    monkeypatch.setattr(
        "app.services.billing_service.BillingService.create_usage_log",
        fake_create_usage_log,
    )
    monkeypatch.setattr(
        "app.api.v1.endpoints.generation.get_feature_image_model",
        lambda feature_name: "gemini-3.1-flash-image-preview-official" if feature_name == "erase" else f"unexpected-{feature_name}",
    )
    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        fake_enqueue_task,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/generate/erase",
        json={
            "source_image_url": "/api/v1/uploads/canvas/composite.png",
            "source_width": 960,
            "source_height": 600,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["task_type"] == "text2image"
    assert response.json()["status"] == "processing"
    assert response.json()["prompt"]
    assert usage_log_calls == [
        {
            "user_id": user.id,
            "task_id": 456,
            "model_name": "gemini-3.1-flash-image-preview-official",
            "task_type": "image_erase",
            "amount_cents": 11,
            "parent_id": None,
            "params": {"resolution": "2K", "aspect_ratio": "3:2"},
            "task_status": "pending",
            "billing_label": "billing.labels.image_erase",
            "provider_code": "apimart",
            "billing_mode": "local_price",
        }
    ]
    assert poller_calls == [
        {
            "task_id": 456,
            "workflow_stage": "provider_query",
        }
    ]
