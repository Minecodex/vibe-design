import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.models.generation import GenerationTask
from app.models.project import Project
from app.models.project_user_canvas import ProjectUserCanvas
from app.models.user import User
from app.repositories.generation_repository import GenerationTaskRepository
from app.services.task_poller import TaskPoller


def test_task_poller_uses_extended_generation_timeouts():
    poller = TaskPoller()

    assert poller._get_timeout("text2image") == 30 * 60
    assert poller._get_timeout("text2video") == 5 * 60 * 60


@pytest.mark.asyncio
async def test_generation_scheduler_idle_wait_uses_idle_setting(monkeypatch):
    poller = TaskPoller()
    waits: list[float] = []

    async def fake_run_once():
        return 0

    async def fake_wait(*, timeout_seconds: float):
        waits.append(timeout_seconds)
        poller._shutdown_event.set()

    monkeypatch.setattr(poller, "run_scheduler_once", fake_run_once)
    monkeypatch.setattr(
        "app.services.task_poller.wait_generation_scheduler_wakeup",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.task_poller.GENERATION_SCHEDULER_IDLE_WAIT_SECONDS",
        17.0,
        raising=False,
    )

    await poller._scheduler_loop()

    assert waits == [17.0]


@pytest.mark.asyncio
async def test_generation_task_active_poll_uses_active_poll_setting(monkeypatch):
    poller = TaskPoller()
    sleeps: list[float] = []
    released: list[tuple[int, str]] = []

    async def fake_renew(_task_id, _claim_token):
        return True

    async def fake_poll_once(_task_id, _user_id, _claim_token):
        return False

    async def fake_release(task_id, claim_token):
        released.append((task_id, claim_token))

    async def fake_sleep(seconds: float):
        sleeps.append(seconds)
        poller._shutdown_event.set()

    monkeypatch.setattr(poller, "_renew_scheduler_task_claim", fake_renew)
    monkeypatch.setattr(poller, "_poll_once", fake_poll_once)
    monkeypatch.setattr(poller, "_release_scheduler_task_claim", fake_release)
    monkeypatch.setattr("app.services.task_poller.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(
        "app.services.task_poller.GENERATION_TASK_ACTIVE_POLL_SECONDS",
        3.5,
        raising=False,
    )

    await poller._poll_loop(
        task_id=303,
        user_id=9,
        provider_code="builtin",
        task_type="text2image",
        created_at=datetime.now(UTC),
        claim_token="claim-303",
    )

    assert sleeps == [3.5]
    assert released == [(303, "claim-303")]


@pytest.mark.asyncio
async def test_poll_loop_applies_image_task_timeout_before_running_executor(monkeypatch):
    poller = TaskPoller()
    timed_out: list[tuple[int, int]] = []
    released: list[tuple[int, str]] = []

    async def fake_renew(task_id, claim_token):
        return True

    async def fake_timeout(task_id, user_id):
        timed_out.append((task_id, user_id))

    async def fake_release(task_id, claim_token):
        released.append((task_id, claim_token))

    async def fail_poll_once(task_id, user_id, claim_token):
        raise AssertionError("expired image tasks should time out before executor runs")

    monkeypatch.setattr(poller, "_renew_scheduler_task_claim", fake_renew)
    monkeypatch.setattr(poller, "_handle_timeout", fake_timeout)
    monkeypatch.setattr(poller, "_release_scheduler_task_claim", fake_release)
    monkeypatch.setattr(poller, "_poll_once", fail_poll_once)

    created_at = datetime.now(UTC) - timedelta(seconds=poller._get_timeout("text2image") + 1)

    await poller._poll_loop(
        task_id=303,
        user_id=9,
        provider_code="builtin",
        task_type="text2image",
        created_at=created_at,
        claim_token="claim-303",
    )

    assert timed_out == [(303, 9)]
    assert released == [(303, "claim-303")]


@pytest.mark.asyncio
async def test_generation_scheduler_claim_allows_stale_takeover_and_rejects_lost_owner_updates(db_session):
    user = User(
        email="poller-claim@example.test",
        username="poller-claim",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    expired_at = datetime.now(UTC) - timedelta(seconds=30)
    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="processing",
        external_task_id="provider-task-1",
        scheduler_claim_token="old-token",
        scheduler_claimed_at=expired_at - timedelta(seconds=30),
        scheduler_lease_expires_at=expired_at,
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    repo = GenerationTaskRepository(db_session)
    now = datetime.now(UTC)
    claimed = await repo.claim_scheduler_task(
        task_id=task.id,
        now=now,
        lease_expires_at=now + timedelta(seconds=30),
        claim_token="new-token",
    )

    assert claimed is not None
    assert claimed.scheduler_claim_token == "new-token"

    lost_owner_update = await repo.update_for_scheduler_claim(
        task_id=task.id,
        user_id=user.id,
        claim_token="old-token",
        data={"status": "completed", "result_url": "https://cdn.example/old.png"},
    )
    assert lost_owner_update is None

    current_owner_update = await repo.update_for_scheduler_claim(
        task_id=task.id,
        user_id=user.id,
        claim_token="new-token",
        data={"status": "completed", "result_url": "https://cdn.example/new.png"},
    )
    assert current_owner_update is not None
    assert current_owner_update.status == "completed"
    assert current_owner_update.result_url == "https://cdn.example/new.png"


@pytest.mark.asyncio
async def test_task_poller_enqueue_task_persists_scheduler_work_without_process_local_polling(db_session):
    user = User(
        email="poller-enqueue@example.test",
        username="poller-enqueue",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="processing",
        external_task_id="provider-task-1",
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    poller = TaskPoller()

    class ExistingSessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    from app.services import task_poller as task_poller_mod

    original_session_factory = task_poller_mod.LoopSafeAsyncSessionLocal
    task_poller_mod.LoopSafeAsyncSessionLocal = lambda: ExistingSessionContext()
    try:
        updated = await poller.enqueue_task(task.id, workflow_stage="provider_query")
    finally:
        task_poller_mod.LoopSafeAsyncSessionLocal = original_session_factory

    assert updated is not None
    assert updated.scheduler_next_run_at is not None
    assert updated.workflow_stage == "provider_query"
    assert poller.active_count == 0


@pytest.mark.asyncio
async def test_task_poller_scheduler_tick_claims_due_task_and_starts_one_polling_owner(db_session, monkeypatch):
    user = User(
        email="poller-scheduler-tick@example.test",
        username="poller-scheduler-tick",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="processing",
        external_task_id="provider-task-1",
        scheduler_next_run_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    class ExistingSessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    started: list[dict] = []
    poller = TaskPoller()

    monkeypatch.setattr("app.services.task_poller.AsyncSessionLocal", lambda: ExistingSessionContext())
    monkeypatch.setattr(poller, "start_polling", lambda **kwargs: started.append(kwargs))

    processed = await poller.run_scheduler_once(limit=20)

    started_for_task = [item for item in started if item["task_id"] == task.id]
    assert processed >= 1
    assert len(started_for_task) == 1
    assert started_for_task[0]["user_id"] == user.id
    assert started_for_task[0]["provider_code"] == "builtin"
    assert started_for_task[0]["task_type"] == "text2image"
    assert started_for_task[0]["claim_token"]

    await poller.run_scheduler_once(limit=20)
    started_for_task_again = [item for item in started if item["task_id"] == task.id]
    assert len(started_for_task_again) == 1


@pytest.mark.asyncio
async def test_handle_completion_writes_harness_generation_result_to_workspace_asset(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    poller = TaskPoller()
    downloaded: dict = {}
    published: dict = {}

    class FakeBillingService:
        def __init__(self, _db):
            pass

        async def update_usage_log_status(self, task_id: int, new_status: str):
            return None

        async def finalize_apimart_generation_billing(self, task):
            return None

    async def fake_download_media_to_workspace(ctx, file_url, *, ext_hint, media_kind, asset_id=None):
        downloaded.update({
            "conversation_id": ctx.conversation_id,
            "file_url": file_url,
            "ext_hint": ext_hint,
            "media_kind": media_kind,
            "asset_id": asset_id,
        })
        return "assets/references/generated_asset/original.png"

    def fake_publish_canvas_generated_media(ctx, workspace_path):
        published.update({"workspace_path": workspace_path, "project_id": ctx.project_id})
        return "/api/v1/uploads/canvas/65/published.png"

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.download_media_to_workspace",
        fake_download_media_to_workspace,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_canvas_generated_media",
        fake_publish_canvas_generated_media,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        lambda *args, **kwargs: None,
    )

    task = SimpleNamespace(
        id=42,
        user_id=7,
        project_id=65,
        provider_code="builtin",
        task_type="text2image",
        status="completed",
        result_url="/api/v1/uploads/generated/image.png",
        error_message=None,
        params={
            "conversation_id": "conv-assets",
            "artifact_ref": "artifact_ref:image",
            "asset_id": "generated_asset",
            "canvas_item": {"id": "item-1"},
        },
    )

    await poller._handle_completion(db=object(), task=task)

    assert downloaded == {
        "conversation_id": "conv-assets",
        "file_url": "/api/v1/uploads/generated/image.png",
        "ext_hint": "png",
        "media_kind": "image",
        "asset_id": "generated_asset",
    }
    assert published == {
        "workspace_path": "assets/references/generated_asset/original.png",
        "project_id": 65,
    }


@pytest.mark.asyncio
async def test_handle_completion_preserves_harness_generation_metadata_for_media_card(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    poller = TaskPoller()
    published_update: dict = {}

    from app.services.agent_harness.core.context import HarnessContext
    from app.services.agent_harness.core.utils import generation_store

    ctx = HarnessContext(
        user_id=7,
        conversation_id="conv-meta",
        run_id="test",
        runtime_profile="canvas",
        project_id=65,
    )
    generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="assets/references/generated_asset/original.png",
        artifact_ref="artifact_ref:image-meta",
    )
    generation_store.update_artifact(
        ctx,
        "artifact_ref:image-meta",
        {
            "canvas_item": {
                "id": "canvas-image-meta",
                "type": "image_generator",
                "task_id": "42",
                "prompt": "a monkey portrait",
                "aspect_ratio": "1:1",
                "resolution": "2K",
                "model_name": "doubao-seedream-5-0-lite",
                "model_label": "Seedream 5.0 Lite",
                "provider_code": "builtin",
                "status": "generating",
                "url": "",
            }
        },
    )

    class FakeBillingService:
        def __init__(self, _db):
            pass

        async def finalize_apimart_generation_billing(self, task):
            return None

    async def fake_download_media_to_workspace(ctx, file_url, *, ext_hint, media_kind, asset_id=None):
        return "assets/references/generated_asset/original.png"

    def fake_publish_canvas_generated_media(ctx, workspace_path):
        return "/api/v1/uploads/canvas/65/published.png"

    def fake_publish_generation_media_update(ctx, *, task_id, task, artifact, status, result_url=None, error=None):
        published_update.update({
            "task_id": task_id,
            "task": task,
            "artifact": artifact,
            "status": status,
            "result_url": result_url,
            "error": error,
        })

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.download_media_to_workspace",
        fake_download_media_to_workspace,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_canvas_generated_media",
        fake_publish_canvas_generated_media,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        fake_publish_generation_media_update,
    )

    task = SimpleNamespace(
        id=42,
        user_id=7,
        project_id=65,
        provider_code="builtin",
        model_name="doubao-seedream-5-0-lite",
        model_label="Seedream 5.0 Lite",
        task_type="text2image",
        status="completed",
        result_url="/api/v1/uploads/generated/image.png",
        error_message=None,
        params={
            "conversation_id": "conv-meta",
            "artifact_ref": "artifact_ref:image-meta",
            "asset_id": "generated_asset",
            "resolution": "2K",
            "aspect_ratio": "1:1",
            "tool_call_id": "functions.generate_image:0",
        },
    )

    await poller._handle_completion(db=object(), task=task)

    assert published_update["task"]["model_name"] == "doubao-seedream-5-0-lite"
    assert published_update["task"]["model_label"] == "Seedream 5.0 Lite"
    assert published_update["task"]["provider_code"] == "builtin"
    assert published_update["task"]["resolution"] == "2K"
    assert published_update["task"]["aspect_ratio"] == "1:1"
    assert published_update["task"]["canvas_item"]["id"] == "canvas-image-meta"
    assert published_update["artifact"]["canvas_item"]["id"] == "canvas-image-meta"


@pytest.mark.asyncio
async def test_handle_completion_does_not_publish_duplicate_terminal_media_event(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    poller = TaskPoller()
    publish_calls: list[dict] = []
    appended_events: list[dict] = []
    download_calls = 0

    class FakeBillingService:
        def __init__(self, _db):
            pass

        async def finalize_apimart_generation_billing(self, task):
            return None

    async def fake_download_media_to_workspace(ctx, file_url, *, ext_hint, media_kind, asset_id=None):
        nonlocal download_calls
        download_calls += 1
        return "assets/references/generated_asset/original.png"

    def fake_publish_canvas_generated_media(ctx, workspace_path):
        return "/api/v1/uploads/canvas/65/published.png"

    def fake_publish_generation_media_update(ctx, *, task_id, task, artifact, status, result_url=None, error=None):
        publish_calls.append(
            {
                "task_id": task_id,
                "status": status,
                "result_url": result_url,
                "error": error,
            }
        )

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.download_media_to_workspace",
        fake_download_media_to_workspace,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_canvas_generated_media",
        fake_publish_canvas_generated_media,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        fake_publish_generation_media_update,
    )

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    task = SimpleNamespace(
        id=42,
        user_id=7,
        project_id=65,
        provider_code="builtin",
        model_name="doubao-seedream-5-0-lite",
        model_label="Seedream 5.0 Lite",
        task_type="text2image",
        status="completed",
        result_url="/api/v1/uploads/generated/image.png",
        error_message=None,
        params={
            "conversation_id": "conv-idempotent",
            "artifact_ref": "artifact_ref:image-idempotent",
            "asset_id": "generated_asset",
            "canvas_item": {"id": "canvas-image-idempotent", "status": "generating"},
        },
    )

    await poller._handle_completion(db=object(), task=task)
    await poller._handle_completion(db=object(), task=task)

    assert download_calls == 1
    assert publish_calls == [
        {
            "task_id": "42",
            "status": "completed",
            "result_url": "/api/v1/uploads/canvas/65/published.png",
            "error": None,
        }
    ]
    assert [event["event_type"] for event in appended_events] == ["item_completed"]
    assert appended_events[0]["idempotency_key"] == "run:generation-task-poller:generation:artifact_ref:image-idempotent:completed:completed"
    assert appended_events[0]["payload"]["status"] == "completed"
    assert appended_events[0]["payload"]["payload"]["result_url"] == "/api/v1/uploads/canvas/65/published.png"


@pytest.mark.asyncio
async def test_publish_generation_task_artifact_update_suppresses_standard_media_card(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    appended_events: list[dict] = []
    publish_calls: list[dict] = []

    async def fake_download_media_to_workspace(ctx, file_url, *, ext_hint, media_kind, asset_id=None):
        return "assets/references/white/original.png"

    def fake_publish_canvas_generated_media(ctx, workspace_path):
        return "/api/v1/uploads/canvas/65/white.png"

    def fake_publish_generation_media_update(ctx, *, task_id, task, artifact, status, result_url=None, error=None):
        publish_calls.append(
            {
                "task_id": task_id,
                "status": status,
                "result_url": result_url,
                "error": error,
            }
        )

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.download_media_to_workspace",
        fake_download_media_to_workspace,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_canvas_generated_media",
        fake_publish_canvas_generated_media,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        fake_publish_generation_media_update,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    from app.services.generation_artifact_events import publish_generation_task_artifact_update

    task = SimpleNamespace(
        id=89,
        user_id=7,
        project_id=65,
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        task_type="text2image",
        status="completed",
        result_url="/provider/white.png",
        result_urls=None,
        progress=100,
        error_message=None,
        prompt="white-background product image",
        params={
            "agent_run_id": "run-white",
            "conversation_id": "conv-white",
            "artifact_ref": "artifact_ref:white",
            "asset_id": "white",
            "canvas_item": {"id": "canvas-white", "status": "generating", "url": ""},
            "suppress_standard_media_card": True,
        },
    )

    await publish_generation_task_artifact_update(task)

    assert publish_calls == []
    assert [event["event_type"] for event in appended_events] == ["item_completed"]
    payload = appended_events[0]["payload"]["payload"]
    assert payload["result_url"] == "/api/v1/uploads/canvas/65/white.png"
    assert payload["suppress_standard_media_card"] is True
    assert payload["canvas_item"]["status"] == "completed"


@pytest.mark.asyncio
async def test_publish_generation_task_artifact_update_persists_agent_canvas_item(
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    appended_events: list[dict] = []

    user = User(
        email="async-agent-canvas@example.test",
        username="async_agent_canvas",
        hashed_password="pw",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    project = Project(user_id=user.id, title="Async Agent Canvas")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    db_session.add(
        ProjectUserCanvas(
            project_id=project.id,
            user_id=user.id,
            canvas_revision=3,
            canvas_data=[
                {
                    "id": "agent-generated-async",
                    "type": "image_generator",
                    "url": "",
                    "x": 123,
                    "y": 456,
                    "width": 640,
                    "height": 480,
                    "z_index": 7,
                    "groupId": "group-user-moved",
                    "task_id": "90",
                    "artifact_ref": "artifact_ref:async-canvas",
                    "agent_media_key": "artifact_ref:async-canvas",
                    "agent_group_order": 2,
                    "status": "generating",
                }
            ],
            canvas_meta=None,
        )
    )
    await db_session.commit()

    @asynccontextmanager
    async def override_session_factory():
        yield db_session

    from app.main import app

    monkeypatch.setattr(app.state, "db_session_factory", override_session_factory, raising=False)

    async def fake_download_media_to_workspace(ctx, file_url, *, ext_hint, media_kind, asset_id=None):
        return "assets/references/async/original.png"

    def fake_publish_canvas_generated_media(ctx, workspace_path):
        return "/api/v1/uploads/canvas/1/async.png"

    def fake_publish_generation_media_update(*_args, **_kwargs):
        return None

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.download_media_to_workspace",
        fake_download_media_to_workspace,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_canvas_generated_media",
        fake_publish_canvas_generated_media,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        fake_publish_generation_media_update,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    from app.services.agent_harness.core.context import HarnessContext
    from app.services.agent_harness.core.utils import generation_store
    from app.services.generation_artifact_events import publish_generation_task_artifact_update

    ctx = HarnessContext(
        user_id=user.id,
        conversation_id="conv-async-canvas",
        run_id="generation-task-poller",
        runtime_profile="canvas",
        project_id=project.id,
    )
    artifact_ref = "artifact_ref:async-canvas"
    generation_store.update_artifact(
        ctx,
        artifact_ref,
        {
            "kind": "image",
            "status": "processing",
            "current_task_id": "90",
            "canvas_item": {
                "id": "agent-generated-async",
                "type": "image_generator",
                "url": "",
                "task_id": "90",
                "artifact_ref": artifact_ref,
                "agent_media_key": artifact_ref,
                "status": "generating",
            },
        },
    )
    task = SimpleNamespace(
        id=90,
        user_id=user.id,
        project_id=project.id,
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        task_type="text2image",
        status="completed",
        result_url="/provider/async.png",
        result_urls=None,
        progress=100,
        error_message=None,
        prompt="async image",
        params={
            "agent_run_id": "generation-task-poller",
            "conversation_id": "conv-async-canvas",
            "artifact_ref": artifact_ref,
            "canvas_item": {
                "id": "agent-generated-async",
                "type": "image_generator",
                "url": "",
                "task_id": "90",
                "artifact_ref": artifact_ref,
                "agent_media_key": artifact_ref,
                "status": "generating",
            },
        },
    )

    await publish_generation_task_artifact_update(task)

    canvas = await db_session.scalar(select(ProjectUserCanvas).where(ProjectUserCanvas.project_id == project.id))
    assert canvas.canvas_revision == 4
    assert canvas.canvas_data[0] == {
        "id": "agent-generated-async",
        "type": "image",
        "url": "/api/v1/uploads/canvas/1/async.png",
        "x": 123,
        "y": 456,
        "width": 640,
        "height": 480,
        "z_index": 7,
        "groupId": "group-user-moved",
        "task_id": "90",
        "artifact_ref": artifact_ref,
        "agent_media_key": artifact_ref,
        "agent_group_order": 2,
        "status": "completed",
        "asset_origin": "ai_generated",
        "suppressCompletionToast": True,
    }
    assert [event["event_type"] for event in appended_events] == ["item_completed"]
    payload = appended_events[0]["payload"]["payload"]
    payload_canvas_item = payload["canvas_item"]
    assert payload["canvas_revision"] == 4
    assert payload.get("canvas_item_deleted") is not True
    assert payload_canvas_item["url"] == "/api/v1/uploads/canvas/1/async.png"
    assert payload_canvas_item["x"] == 123
    assert payload_canvas_item["groupId"] == "group-user-moved"
    artifact = generation_store.read_artifact(ctx, artifact_ref)
    assert artifact["canvas_item"]["url"] == "/api/v1/uploads/canvas/1/async.png"
    assert artifact["canvas_item"]["x"] == 123
    assert artifact["canvas_revision"] == 4
    assert artifact["canvas_item_deleted"] is False


@pytest.mark.asyncio
async def test_publish_generation_task_artifact_update_repairs_precompleted_artifact_projection(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    appended_events: list[dict] = []
    publish_calls: list[dict] = []

    from app.services.agent_harness.core.context import HarnessContext
    from app.services.agent_harness.core.utils import generation_store
    from app.services.generation_artifact_events import TERMINAL_PROJECTION_FINALIZED_AT

    ctx = HarnessContext(
        user_id=7,
        conversation_id="conv-precompleted",
        run_id="generation-task-poller",
        runtime_profile="canvas",
        project_id=65,
    )
    artifact_ref = "artifact_ref:image-precompleted"
    generation_store.update_artifact(
        ctx,
        artifact_ref,
        {
            "kind": "image",
            "status": "completed",
            "current_task_id": "43",
            "result_url": "/api/v1/uploads/canvas/65/already-published.png",
            "internal_result_url": "references/generated/image-precompleted/original.png",
            "canvas_item": {"id": "canvas-image-precompleted", "status": "generating", "url": ""},
        },
    )

    async def fail_download_media_to_workspace(*_args, **_kwargs):
        raise AssertionError("pre-materialized generation media should not be downloaded again")

    def fake_publish_generation_media_update(ctx, *, task_id, task, artifact, status, result_url=None, error=None):
        publish_calls.append(
            {
                "task_id": task_id,
                "status": status,
                "result_url": result_url,
                "canvas_status": (task.get("canvas_item") or {}).get("status"),
                "artifact_canvas_status": (artifact.get("canvas_item") or {}).get("status"),
                "error": error,
            }
        )

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.download_media_to_workspace",
        fail_download_media_to_workspace,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        fake_publish_generation_media_update,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    from app.services.generation_artifact_events import publish_generation_task_artifact_update

    task = SimpleNamespace(
        id=43,
        user_id=7,
        project_id=65,
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        task_type="text2image",
        status="completed",
        result_url="/provider/original.png",
        result_urls=None,
        progress=100,
        error_message=None,
        prompt="precompleted image",
        params={
            "agent_run_id": "generation-task-poller",
            "conversation_id": "conv-precompleted",
            "artifact_ref": artifact_ref,
            "canvas_item": {"id": "canvas-image-precompleted", "status": "generating", "url": ""},
        },
    )

    await publish_generation_task_artifact_update(task)

    assert [event["event_type"] for event in appended_events] == ["item_completed"]
    assert appended_events[0]["payload"]["payload"]["result_url"] == "/api/v1/uploads/canvas/65/already-published.png"
    assert appended_events[0]["payload"]["payload"]["canvas_item"]["status"] == "completed"
    assert publish_calls == [
        {
            "task_id": "43",
            "status": "completed",
            "result_url": "/api/v1/uploads/canvas/65/already-published.png",
            "canvas_status": "completed",
            "artifact_canvas_status": "completed",
            "error": None,
        }
    ]
    repaired_artifact = generation_store.read_artifact(ctx, artifact_ref)
    assert repaired_artifact["canvas_item"]["status"] == "completed"
    assert repaired_artifact["canvas_item"]["url"] == "/api/v1/uploads/canvas/65/already-published.png"
    assert repaired_artifact[TERMINAL_PROJECTION_FINALIZED_AT]


@pytest.mark.asyncio
async def test_publish_generation_task_artifact_update_emits_failed_item_completed(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    appended_events: list[dict] = []

    def fake_publish_generation_media_update(*_args, **_kwargs):
        return None

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_generation_media_update",
        fake_publish_generation_media_update,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    from app.services.generation_artifact_events import publish_generation_task_artifact_update

    task = SimpleNamespace(
        id=77,
        user_id=7,
        project_id=None,
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        task_type="text2image",
        status="failed",
        result_url=None,
        result_urls=None,
        progress=100,
        error_message="provider failed",
        prompt="blue banana",
        params={
            "agent_run_id": "run-failed-generation",
            "conversation_id": "conv-failed-generation",
            "artifact_ref": "artifact_ref:image-failed",
            "canvas_item": {"id": "canvas-image-failed", "status": "generating"},
        },
    )

    await publish_generation_task_artifact_update(task)

    assert [event["event_type"] for event in appended_events] == ["item_completed"]
    payload = appended_events[0]["payload"]
    assert payload["status"] == "failed"
    assert payload["error"]["summary"] == "provider failed"
    assert payload["payload"]["task_id"] == "77"
    assert payload["payload"]["canvas_item"]["status"] == "failed"


@pytest.mark.asyncio
async def test_publish_generation_task_artifact_progress_update_emits_item_updated(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    appended_events: list[dict] = []

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs.get("payload") or kwargs.get("data")}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )

    from app.services.generation_artifact_events import publish_generation_task_artifact_progress_update

    task = SimpleNamespace(
        id=88,
        user_id=7,
        project_id=65,
        provider_code="builtin",
        model_name="seedream",
        model_label="Seedream",
        task_type="text2image",
        status="processing",
        progress=42,
        result_url=None,
        result_urls=None,
        error_message=None,
        prompt="green apple",
        params={
            "agent_run_id": "run-progress-generation",
            "conversation_id": "conv-progress-generation",
            "artifact_ref": "artifact_ref:image-progress",
            "canvas_item": {"id": "canvas-image-progress", "status": "generating"},
        },
    )

    await publish_generation_task_artifact_progress_update(task)

    assert [event["event_type"] for event in appended_events] == ["item_updated"]
    payload = appended_events[0]["payload"]
    assert payload["status"] == "running"
    assert payload["payload"]["progress"] == 42
    assert payload["payload"]["canvas_item"]["status"] == "processing"


@pytest.mark.asyncio
async def test_recover_terminal_side_effects_on_startup_finalizes_crashed_terminal_task(
    db_session,
    monkeypatch,
):
    await db_session.execute(
        update(GenerationTask)
        .where(GenerationTask.status.in_(["completed", "failed"]))
        .values(terminal_side_effects_finalized_at=datetime.now(UTC))
    )
    await db_session.commit()

    user = User(
        email="poller-terminal-recovery@example.test",
        username="poller-terminal-recovery",
        hashed_password="hashed",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    task = GenerationTask(
        user_id=user.id,
        project_id=None,
        task_type="text2image",
        provider_code="builtin",
        builtin_provider_code="apimart",
        model_name="seedream",
        model_label="Seedream",
        prompt="blue banana",
        params={},
        status="completed",
        external_task_id="provider-task-terminal",
        result_url="/api/v1/uploads/generated/terminal.png",
        terminalized_at=datetime.now(UTC),
    )
    db_session.add(task)
    await db_session.commit()
    await db_session.refresh(task)

    class ExistingSessionContext:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    finalized: list[tuple[int, int | None]] = []

    class FakeTerminalizationService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def finalize_terminal_task(self, task, *, user_id=None):
            finalized.append((task.id, user_id))
            return True

    monkeypatch.setattr("app.services.task_poller.AsyncSessionLocal", lambda: ExistingSessionContext())
    monkeypatch.setattr(
        "app.services.task_poller.GenerationTerminalizationService",
        FakeTerminalizationService,
    )

    poller = TaskPoller()

    recovered = await poller.recover_terminal_side_effects_on_startup()
    await db_session.refresh(task)
    recovered_again = await poller.recover_terminal_side_effects_on_startup()

    assert recovered == 1
    assert recovered_again == 0
    assert finalized == [(task.id, None)]
    assert task.terminal_side_effects_finalized_at is not None


@pytest.mark.asyncio
async def test_poll_loop_queries_before_waiting_for_first_interval(monkeypatch):
    poller = TaskPoller()
    polled = False

    async def fake_sleep(_seconds: float):
        if not polled:
            raise AssertionError("poll loop slept before querying task status")

    async def fake_poll_once(task_id: int, user_id: int, claim_token: str) -> bool:
        assert claim_token
        nonlocal polled
        polled = True
        poller._shutdown_event.set()
        return False

    monkeypatch.setattr("app.services.task_poller.asyncio.sleep", fake_sleep)
    monkeypatch.setattr(poller, "_claim_scheduler_task", _async_value(True))
    monkeypatch.setattr(poller, "_renew_scheduler_task_claim", _async_value(True))
    monkeypatch.setattr(poller, "_release_scheduler_task_claim", _async_value(None))
    monkeypatch.setattr(poller, "_poll_once", fake_poll_once)

    await poller._poll_loop(
        task_id=1,
        user_id=1,
        provider_code="builtin",
        task_type="text2image",
        created_at=datetime.now(UTC),
    )

    assert polled is True


@pytest.mark.asyncio
async def test_poll_loop_does_not_start_next_query_until_previous_one_returns(monkeypatch):
    poller = TaskPoller()
    monkeypatch.setattr(
        "app.services.task_poller.GENERATION_TASK_ACTIVE_POLL_SECONDS",
        0.01,
        raising=False,
    )

    first_query_started = False
    release_first_query = False
    query_count = 0
    in_flight = 0
    max_in_flight = 0

    async def fake_poll_once(task_id: int, user_id: int, claim_token: str) -> bool:
        assert claim_token
        nonlocal first_query_started, release_first_query, query_count, in_flight, max_in_flight
        query_count += 1
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)

        try:
            if query_count == 1:
                first_query_started = True
                while not release_first_query:
                    await asyncio.sleep(0)
            else:
                poller._shutdown_event.set()
            return False
        finally:
            in_flight -= 1

    monkeypatch.setattr(poller, "_claim_scheduler_task", _async_value(True))
    monkeypatch.setattr(poller, "_renew_scheduler_task_claim", _async_value(True))
    monkeypatch.setattr(poller, "_release_scheduler_task_claim", _async_value(None))
    monkeypatch.setattr(poller, "_poll_once", fake_poll_once)

    task = asyncio.create_task(
        poller._poll_loop(
            task_id=1,
            user_id=1,
            provider_code="builtin",
            task_type="text2image",
            created_at=datetime.now(UTC),
        )
    )

    while not first_query_started:
        await asyncio.sleep(0)

    await asyncio.sleep(0.05)
    assert query_count == 1
    assert max_in_flight == 1

    release_first_query = True
    await asyncio.wait_for(task, timeout=1)

    assert query_count == 2
    assert max_in_flight == 1


@pytest.mark.asyncio
async def test_poll_once_renews_scheduler_claim_while_provider_query_is_running(monkeypatch):
    poller = TaskPoller()
    heartbeat_seen = asyncio.Event()
    query_can_return = asyncio.Event()
    renewals: list[tuple[int, str]] = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeGenerationTaskExecutor:
        def __init__(self, _db):
            pass

        async def execute_once(self, *, task_id, user_id, scheduler_claim_token):
            assert task_id == 91
            assert user_id == 7
            assert scheduler_claim_token == "claim-91"
            await heartbeat_seen.wait()
            query_can_return.set()
            return SimpleNamespace(status="processing")

    async def fake_renew(task_id, claim_token):
        renewals.append((task_id, claim_token))
        heartbeat_seen.set()
        return True

    monkeypatch.setattr("app.services.task_poller.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr("app.services.task_poller.GenerationTaskExecutor", FakeGenerationTaskExecutor)
    monkeypatch.setattr(poller, "_renew_scheduler_task_claim", fake_renew)
    monkeypatch.setattr(poller, "_claim_renewal_interval_seconds", lambda: 0.01)

    terminal = await poller._poll_once(91, 7, "claim-91")

    assert terminal is False
    assert query_can_return.is_set()
    assert renewals
    assert all(item == (91, "claim-91") for item in renewals)


@pytest.mark.asyncio
async def test_update_agent_usage_log_expands_elapsed_for_async_generation(monkeypatch):
    poller = TaskPoller()
    updated: dict = {}

    usage_log = SimpleNamespace(
        id=91,
        elapsed_ms=1200,
        amount_cents=1200,
        amount_cents_original=1200,
        status="pending",
        params={
            "agent_run_id": "agent-run-91",
            "agent_started_at": "2026-03-23T00:00:00+00:00",
            "timing_breakdown_ms": {"multimodal": 1200},
            "generation_tasks": [{"task_id": 42, "status": "processing", "amount_cents": 1200}],
        },
    )
    task = SimpleNamespace(
        id=42,
        status="completed",
        updated_at=datetime(2026, 3, 23, 0, 0, 8, tzinfo=UTC),
        result_url="https://example.com/video.mp4",
        error_message=None,
        params={"agent_run_id": "agent-run-91"},
    )

    class FakeUsageRepo:
        async def get_latest_agent_log_by_run_id(self, agent_run_id: str):
            assert agent_run_id == "agent-run-91"
            return usage_log

    class FakeBillingService:
        def __init__(self, _db):
            self.usage_repo = FakeUsageRepo()

        async def update_usage_log(self, log_id: int, data: dict):
            updated["log_id"] = log_id
            updated["data"] = data

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)

    await poller._update_agent_usage_log(db=object(), task=task)

    assert updated["log_id"] == 91
    assert updated["data"]["elapsed_ms"] == 8000
    assert updated["data"]["status"] == "success"
    assert updated["data"]["params"]["timing_breakdown_ms"]["async_generation"] == 8000
    assert updated["data"]["params"]["generation_tasks"][0]["status"] == "completed"
    assert updated["data"]["params"]["generation_tasks"][0]["result_url"] == "https://example.com/video.mp4"


@pytest.mark.asyncio
async def test_update_agent_usage_log_refunds_failed_agent_generation_cost(monkeypatch):
    poller = TaskPoller()
    updated: dict = {}
    refunded: list[tuple[int, int]] = []

    usage_log = SimpleNamespace(
        id=92,
        elapsed_ms=1500,
        amount_cents=1240,
        amount_cents_original=1240,
        status="pending",
        params={
            "agent_run_id": "agent-run-92",
            "agent_started_at": "2026-03-23T00:00:00+00:00",
            "total_amount_cents": 1240,
            "timing_breakdown_ms": {"multimodal": 1500},
            "generation_tasks": [
                {"task_id": 42, "status": "processing", "amount_cents": 1200},
            ],
        },
    )
    task = SimpleNamespace(
        id=42,
        status="failed",
        user_id=7,
        provider_code="builtin",
        updated_at=datetime(2026, 3, 23, 0, 0, 8, tzinfo=UTC),
        result_url=None,
        error_message="provider failed",
        params={"agent_run_id": "agent-run-92"},
    )

    class FakeUsageRepo:
        async def get_latest_agent_log_by_run_id(self, agent_run_id: str):
            assert agent_run_id == "agent-run-92"
            return usage_log

    class FakeBillingService:
        def __init__(self, _db):
            self.usage_repo = FakeUsageRepo()

        async def refund_balance(self, user_id: int, amount: int):
            refunded.append((user_id, amount))

        async def update_usage_log(self, log_id: int, data: dict):
            updated["log_id"] = log_id
            updated["data"] = data

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)

    await poller._update_agent_usage_log(db=object(), task=task)

    assert refunded == [(7, 1200)]
    assert updated["log_id"] == 92
    assert updated["data"]["amount_cents"] == 40
    assert updated["data"]["status"] == "success"
    assert updated["data"]["params"]["total_amount_cents"] == 40
    assert updated["data"]["params"]["generation_tasks"][0]["status"] == "failed"
    assert updated["data"]["params"]["generation_tasks"][0]["error_message"] == "provider failed"


@pytest.mark.asyncio
async def test_update_agent_usage_log_skips_duplicate_failed_refund_when_claim_not_won(monkeypatch):
    poller = TaskPoller()
    refunded: list[tuple[int, int]] = []
    updated: list[tuple[int, dict]] = []

    usage_log = SimpleNamespace(
        id=94,
        elapsed_ms=1500,
        amount_cents=1240,
        amount_cents_original=1240,
        status="pending",
        params={
            "agent_run_id": "agent-run-94",
            "agent_started_at": "2026-03-23T00:00:00+00:00",
            "total_amount_cents": 1240,
            "timing_breakdown_ms": {"multimodal": 1500},
            "generation_tasks": [
                {"task_id": 42, "status": "processing", "amount_cents": 1200},
            ],
        },
    )
    task = SimpleNamespace(
        id=42,
        status="failed",
        user_id=7,
        provider_code="builtin",
        updated_at=datetime(2026, 3, 23, 0, 0, 8, tzinfo=UTC),
        result_url=None,
        error_message="provider failed",
        params={"agent_run_id": "agent-run-94"},
    )

    class FakeUsageRepo:
        async def get_latest_agent_log_by_run_id(self, agent_run_id: str):
            assert agent_run_id == "agent-run-94"
            return usage_log

    class FakeBillingService:
        def __init__(self, _db):
            self.usage_repo = FakeUsageRepo()

        async def _claim_usage_log_lock(self, *_args, **_kwargs):
            return None, "lock-lost"

        async def refund_balance(self, user_id: int, amount: int):
            refunded.append((user_id, amount))

        async def update_usage_log(self, log_id: int, data: dict):
            updated.append((log_id, data))

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)

    await poller._update_agent_usage_log(db=object(), task=task)

    assert refunded == []
    assert updated == []


@pytest.mark.asyncio
async def test_update_agent_usage_log_stays_pending_until_all_generation_tasks_finish(monkeypatch):
    poller = TaskPoller()
    updated: dict = {}

    usage_log = SimpleNamespace(
        id=93,
        elapsed_ms=1200,
        amount_cents=1240,
        amount_cents_original=1240,
        status="pending",
        params={
            "agent_run_id": "agent-run-93",
            "agent_started_at": "2026-03-23T00:00:00+00:00",
            "timing_breakdown_ms": {"multimodal": 1200},
            "generation_tasks": [
                {"task_id": 42, "status": "processing", "amount_cents": 40},
                {"task_id": 43, "status": "processing", "amount_cents": 1200},
            ],
        },
    )
    task = SimpleNamespace(
        id=42,
        status="completed",
        updated_at=datetime(2026, 3, 23, 0, 0, 5, tzinfo=UTC),
        result_url="https://example.com/image.png",
        error_message=None,
        params={"agent_run_id": "agent-run-93"},
    )

    class FakeUsageRepo:
        async def get_latest_agent_log_by_run_id(self, agent_run_id: str):
            assert agent_run_id == "agent-run-93"
            return usage_log

    class FakeBillingService:
        def __init__(self, _db):
            self.usage_repo = FakeUsageRepo()

        async def update_usage_log(self, log_id: int, data: dict):
            updated["log_id"] = log_id
            updated["data"] = data

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)

    await poller._update_agent_usage_log(db=object(), task=task)

    assert updated["log_id"] == 93
    assert updated["data"]["status"] == "pending"
    assert updated["data"]["elapsed_ms"] == 5000
    assert updated["data"]["params"]["generation_tasks"][0]["status"] == "completed"
    assert updated["data"]["params"]["generation_tasks"][1]["status"] == "processing"


@pytest.mark.asyncio
async def test_update_agent_usage_log_normalizes_naive_local_time_for_parent_child_records(monkeypatch):
    poller = TaskPoller()
    updated: dict = {}
    refreshed: dict = {}

    child_log = SimpleNamespace(
        id=120,
        status="pending",
        amount_cents=42,
        amount_cents_original=42,
        elapsed_ms=0,
        params={"agent_run_id": "agent-run-120"},
        created_at=datetime(2026, 3, 25, 16, 47, 36),
    )
    task = SimpleNamespace(
        id=52,
        status="completed",
        user_id=7,
        updated_at=datetime(2026, 3, 25, 16, 48, 21),
        result_url="https://example.com/image.png",
        error_message=None,
        params={
            "agent_run_id": "agent-run-120",
            "parent_usage_log_id": 91,
            "agent_usage_log_id": 120,
            "agent_conversation_id": 33,
        },
    )

    class FakeUsageRepo:
        async def get(self, log_id: int):
            assert log_id == 120
            return child_log

    class FakeBillingService:
        def __init__(self, _db):
            self.usage_repo = FakeUsageRepo()

        async def update_usage_log(self, log_id: int, data: dict):
            updated["log_id"] = log_id
            updated["data"] = data

        async def refresh_parent_usage_log(self, log_id: int, *, finished_at, params=None):
            refreshed["log_id"] = log_id
            refreshed["finished_at"] = finished_at
            refreshed["params"] = params

    monkeypatch.setattr("app.services.task_poller.BillingService", FakeBillingService)

    await poller._update_agent_usage_log(db=object(), task=task)

    assert updated["log_id"] == 120
    assert updated["data"]["elapsed_ms"] == 45000
    assert refreshed["log_id"] == 91
    assert refreshed["finished_at"].isoformat() == "2026-03-25T08:48:21+00:00"


@pytest.mark.asyncio
async def test_recover_on_startup_resumes_lingyaai_pending_image_tasks(monkeypatch):
    poller = TaskPoller()
    task = SimpleNamespace(
        id=42,
        user_id=7,
        provider_code="builtin",
        builtin_provider_code="lingyaai",
        external_task_id="lingyaai-image-pending:42",
        status="processing",
        task_type="text2image",
        created_at=datetime.now(UTC),
        error_message=None,
    )
    claims: list[int] = []
    started: list[dict] = []

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _db):
            pass

        async def get_incomplete_tasks(self):
            return [task]

        async def claim_scheduler_task(self, **kwargs):
            assert kwargs["task_id"] == 42
            claims.append(kwargs["task_id"])
            return task

    monkeypatch.setattr("app.services.task_poller.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr("app.services.task_poller.GenerationTaskRepository", FakeRepo)
    monkeypatch.setattr(
        poller,
        "start_polling",
        lambda **kwargs: started.append(kwargs),
    )

    await poller.recover_on_startup()

    assert task.status == "processing"
    assert task.error_message is None
    assert claims == [42]
    assert len(started) == 1
    assert started[0]["task_id"] == 42
    assert started[0]["user_id"] == 7
    assert started[0]["provider_code"] == "builtin"
    assert started[0]["task_type"] == "text2image"
    assert started[0]["created_at"] == task.created_at
    assert started[0]["claim_token"]


@pytest.mark.asyncio
async def test_recover_on_startup_skips_tasks_that_fail_global_scheduler_claim(monkeypatch):
    poller = TaskPoller()
    task = SimpleNamespace(
        id=52,
        user_id=7,
        provider_code="builtin",
        builtin_provider_code="apimart",
        external_task_id="provider-task-52",
        status="processing",
        task_type="text2image",
        created_at=datetime.now(UTC),
        error_message=None,
    )

    class FakeSessionContext:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeRepo:
        def __init__(self, _db):
            pass

        async def get_incomplete_tasks(self):
            return [task]

        async def claim_scheduler_task(self, **kwargs):
            assert kwargs["task_id"] == 52
            return None

    monkeypatch.setattr("app.services.task_poller.AsyncSessionLocal", lambda: FakeSessionContext())
    monkeypatch.setattr("app.services.task_poller.GenerationTaskRepository", FakeRepo)
    monkeypatch.setattr(
        poller,
        "start_polling",
        lambda **kwargs: pytest.fail("startup recovery should not resume tasks without a global scheduler claim"),
    )

    await poller.recover_on_startup()


def _async_value(value):
    async def _wrapped(*args, **kwargs):
        return value

    return _wrapped
