from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock

import pytest
import pytest_asyncio

from app.core.security import create_access_token, get_password_hash
from app.models.photoshop_edit_job import PhotoshopEditJob
from app.models.project import Project
from app.models.project_user_canvas import ProjectUserCanvas
from app.models.user import User


@pytest_asyncio.fixture(autouse=True)
async def _ready_catalog(monkeypatch):
    """Feature access tests own their catalog and do not depend on test order."""
    from app.core.config import Settings
    from app.core.redis_coordination import InProcessRedisCoordinator
    from app.services.agent_harness import catalog

    coordinator = InProcessRedisCoordinator(settings=Settings(
        _env_file=None, REDIS_ENABLED=True, REDIS_REQUIRED=False,
    ))
    coordinator.health = AsyncMock(return_value={"status": "healthy", "enabled": True})
    monkeypatch.setattr(catalog, "get_redis_coordinator", lambda: coordinator)
    monkeypatch.setattr(catalog, "_LOCAL_SKILL_SNAPSHOT", None)
    monkeypatch.setattr(catalog, "_LOCAL_DESIGN_SYSTEM_SNAPSHOT", None)
    await catalog.warmup_agent_catalog()


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


async def _create_project(db_session, *, user_id: int, title: str = "Capability Project") -> Project:
    project = Project(user_id=user_id, title=title)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.mark.asyncio
async def test_harness_send_message_is_available_without_license(client, db_session, monkeypatch):
    user = await _create_user(client, db_session, suffix="harness")
    enqueue = AsyncMock(return_value=SimpleNamespace(id=123, run_id="run-unlicensed-test"))

    async def live_events(*_args, **_kwargs):
        if False:
            yield ""

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_message_run", enqueue,
    )
    monkeypatch.setattr("app.api.v1.endpoints.harness._stream_live_events", live_events)

    create_response = await client.post("/api/v1/agent/harness/conversations", json={})
    assert create_response.status_code == 200
    conversation_id = create_response.json()["id"]

    response = await client.post(
        f"/api/v1/agent/harness/conversations/{conversation_id}/messages",
        json={"content": "hello"},
    )

    assert response.status_code == 200
    enqueue.assert_awaited_once()
    assert enqueue.await_args.kwargs["user_id"] == user.id
    assert enqueue.await_args.kwargs["conversation_id"] == conversation_id


@pytest.mark.asyncio
async def test_canvas_harness_send_message_is_available_without_license(
    client,
    db_session,
    monkeypatch,
):
    user = await _create_user(client, db_session, suffix="canvas-harness")
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

    async def _enqueue_message_run(
        *, user_id, conversation_id, payload, idempotency_key, parent_usage_log_id=None,
        parent_billing_conversation=None,
        wake_worker=True,
    ):
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
async def test_prompt_extractor_is_available_without_license(client, db_session, monkeypatch):
    user = await _create_user(client, db_session, suffix="prompt")
    analyze = AsyncMock(return_value=SimpleNamespace(
        prompt="测试提示词", prompts={"zh": "测试提示词"}, language="zh-CN",
        model="gemini-3.1-pro-preview", amount_cents=0,
    ))
    monkeypatch.setattr("app.services.prompt_extractor.PromptExtractorService.analyze", analyze)

    response = await client.post(
        "/api/v1/extension/prompt-extractor/analyze",
        data={"locale": "zh-CN"},
        files={"image": ("sample.png", b"fake-image-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert response.json()["prompt"] == "测试提示词"
    analyze.assert_awaited_once_with(user_id=user.id, locale="zh-CN", image=ANY)


@pytest.mark.asyncio
async def test_photoshop_edit_job_creation_is_available_without_license(client, db_session):
    user = await _create_user(client, db_session, suffix="ps-create")
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

    assert response.status_code == 200
    assert response.json()["source_canvas_item_id"] == "image-1"


@pytest.mark.asyncio
async def test_photoshop_save_is_available_without_license(client, db_session):
    user = await _create_user(client, db_session, suffix="ps-save")
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

    assert save_job_response.status_code == 200
    assert save_plugin_response.status_code == 200


@pytest.mark.asyncio
async def test_unlicensed_features_still_require_authentication(client):
    response = await client.post("/api/v1/agent/harness/conversations", json={})
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/extension/prompt-extractor/analyze",
        data={"locale": "zh-CN"},
        files={"image": ("sample.png", b"test-image", "image/png")},
    )
    assert response.status_code == 403
