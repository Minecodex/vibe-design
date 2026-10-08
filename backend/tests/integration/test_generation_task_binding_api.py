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
        email=f"generation-binding-{suffix}@example.com",
        username=f"generationbinding-{suffix}",
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
async def test_generate_image_passes_client_request_id_to_generation_service(client: AsyncClient, db_session, monkeypatch):
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Binding Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    captured_kwargs = {}

    async def fake_generate_image(self, **kwargs):
        captured_kwargs.update(kwargs)
        return SimpleNamespace(
            id=321,
            project_id=project.id,
            task_type="text2image",
            provider_code="builtin",
            model_name="gemini-3.1-flash-image-preview",
            model_label="NanoBanana2",
            prompt=kwargs["prompt"],
            status="processing",
            progress=0,
            external_task_id="provider-image-321",
            result_url=None,
            result_urls=None,
            error_message=None,
            params={"aspect_ratio": "1:1", "resolution": "1K"},
            client_request_id=kwargs["client_request_id"],
            created_at=datetime(2026, 5, 13, 0, 0, 0),
            updated_at=datetime(2026, 5, 13, 0, 0, 0),
        )

    monkeypatch.setattr(
        "app.services.generation_service.GenerationService.generate_image",
        fake_generate_image,
    )
    async def fake_enqueue_task(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "app.services.generation_intake_service.task_poller.enqueue_task",
        fake_enqueue_task,
    )
    async def fake_reserve_builtin_billing(*args, **kwargs):
        return 0

    monkeypatch.setattr(
        "app.services.generation_intake_service.GenerationIntakeService._reserve_builtin_billing",
        fake_reserve_builtin_billing,
    )

    response = await client.post(
        f"/api/v1/projects/{project.id}/generate/image",
        json={
            "prompt": "make it cinematic",
            "model_name": "gemini-3.1-flash-image-preview",
            "provider_code": "builtin",
            "aspect_ratio": "1:1",
            "resolution": "1K",
            "client_request_id": "canvas-image-request-1",
        },
    )

    assert response.status_code == 200
    assert captured_kwargs["client_request_id"] == "canvas-image-request-1"
    assert response.json()["client_request_id"] == "canvas-image-request-1"


@pytest.mark.asyncio
async def test_recover_generation_tasks_by_client_request_id(client: AsyncClient, db_session, monkeypatch):
    from app.models.generation import GenerationTask
    from app.models.project import Project

    monkeypatch.setattr(settings, "DEPLOY_TYPE", "saas")
    user = await _create_authenticated_user(client, db_session)
    project = Project(user_id=user.id, title="Binding Recovery Project")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    found_task = GenerationTask(
        user_id=user.id,
        project_id=project.id,
        task_type="text2image",
        provider_code="builtin",
        model_name="gemini-3.1-flash-image-preview",
        model_label="NanoBanana2",
        prompt="recover me",
        params={"aspect_ratio": "1:1", "resolution": "1K"},
        status="processing",
        progress=35,
        external_task_id="provider-recovery-1",
        client_request_id="canvas-image-request-1",
    )
    db_session.add(found_task)
    await db_session.commit()
    await db_session.refresh(found_task)

    response = await client.post(
        f"/api/v1/projects/{project.id}/generation-tasks/recover",
        json={
            "items": [
                {
                    "client_request_id": "canvas-image-request-1",
                    "task_type": "text2image",
                },
                {
                    "client_request_id": "missing-request",
                    "task_type": "text2video",
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "tasks": {
            "text2image:canvas-image-request-1": {
                "id": found_task.id,
                "project_id": project.id,
                "task_type": "text2image",
                "provider_code": "builtin",
                "model_name": "gemini-3.1-flash-image-preview",
                "model_label": "NanoBanana2",
                "prompt": "recover me",
                "status": "processing",
                "progress": 35,
                "external_task_id": "provider-recovery-1",
                "builtin_provider_code": None,
                "provider_request_id": None,
                "provider_trace_id": None,
                "result_url": None,
                "result_urls": None,
                "error_message": None,
                "params": {"aspect_ratio": "1:1", "resolution": "1K"},
                "client_request_id": "canvas-image-request-1",
                "created_at": found_task.created_at.isoformat(),
                "updated_at": found_task.updated_at.isoformat(),
            }
        }
    }
