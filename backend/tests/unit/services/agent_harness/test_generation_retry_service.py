from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.agent_harness.capabilities.tools.generate_image import GenerateImageParams, GenerateImageTool
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.core.utils import generation_store
from app.services.agent_harness.generation_retry_service import retry_generation_artifact
from app.repositories.generation_repository import GenerationTaskRepository


class FakeRetryKeys:
    def __init__(self) -> None:
        self.resource_parts: list[tuple[str, ...]] = []

    def build(self, *, domain, purpose, resource_parts=()):
        parts = tuple(str(part) for part in resource_parts)
        self.resource_parts.append(parts)
        digest = abs(hash(parts))
        return f"{domain}:{purpose}:{digest}"


class FakeRetryCoordinator:
    def __init__(self) -> None:
        self.keys = FakeRetryKeys()
        self.leases: set[str] = set()
        self.snapshots: dict[str, dict] = {}

    async def try_acquire_lease(self, key, *, owner, ttl_seconds):
        if key in self.leases:
            return {"acquired": False, "owner": "other-worker"}
        self.leases.add(key)
        return {"acquired": True, "owner": owner}

    async def release_lease(self, key, *, owner):
        self.leases.discard(key)
        return True

    async def set_snapshot(self, key, value, *, ttl_seconds):
        self.snapshots[key] = dict(value)

    async def get_snapshot(self, key):
        return self.snapshots.get(key)


@pytest.mark.asyncio
async def test_retry_generation_artifact_reuses_canvas_placeholder_and_saved_reference_input(
    monkeypatch,
    tmp_path: Path,
    client,
    db_session,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_API_KEY", "test-key")

    provider_calls: list[dict] = []
    started_task_ids: list[str] = []

    class FakeApimartClient:
        def __init__(self, api_key: str):
            self.api_key = api_key

        async def generate_image(self, **kwargs):
            provider_calls.append(kwargs)
            remote_id = f"remote-image-task-{len(provider_calls)}"
            return {"code": 200, "data": [{"task_id": remote_id}]}

    monkeypatch.setattr("app.services.apimart_client.ApimartClient", FakeApimartClient)
    monkeypatch.setattr("app.services.builtin_provider.ApimartClient", FakeApimartClient)
    async def fake_enqueue_task(task_id, *_args, **_kwargs):
        started_task_ids.append(str(task_id))

    monkeypatch.setattr(
        "app.services.task_poller.task_poller.enqueue_task",
        fake_enqueue_task,
    )

    conversation = {
        "id": "conv-canvas-retry",
        "runtime_profile": "canvas",
        "project_id": 64,
        "model_preferences": {
            "image_model": "gemini-3.1-flash-image-preview-official",
            "image_provider": "builtin",
        },
    }
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-image",
        workspace_root=tmp_path,
        runtime_profile="canvas",
        project_id=64,
        image_model="gemini-3.1-flash-image-preview-official",
        image_provider="builtin",
    )
    ctx.ensure_dirs()
    (ctx.conversation_dir / "ref.png").write_bytes(b"fake-image")

    first = await GenerateImageTool().execute(
        GenerateImageParams(
            prompt="A coffee ad layout",
            reference_image_urls=["ref.png"],
        ),
        ctx,
    )

    first_task_id = first.metadata["task_id"]
    artifact_ref = first.metadata["artifact_ref"]
    placeholder_id = first.metadata["canvas_item"]["id"]

    repo = GenerationTaskRepository(db_session)
    first_task = await repo.get(int(first_task_id))
    await repo.update(
        first_task,
        {
            "status": "failed",
            "error_message": "provider failed",
        },
    )
    generation_store.update_artifact(
        ctx,
        artifact_ref,
        {
            "status": "failed",
            "error": "provider failed",
            "current_task_id": first_task_id,
            "canvas_item": {
                **first.metadata["canvas_item"],
                "status": "failed",
                "task_id": first_task_id,
            },
        },
    )

    retried = await retry_generation_artifact(
        user_id=7,
        conversation_id=conversation["id"],
        artifact_ref=artifact_ref,
    )

    assert started_task_ids == []
    assert provider_calls == []
    assert retried.artifact_ref == artifact_ref
    assert retried.task_id != first_task_id
    assert retried.auto_retry_count == 0
    assert retried.auto_retry_max == 3
    assert retried.manual_retry_count == 1
    assert retried.canvas_item["id"] == placeholder_id
    assert retried.canvas_item["task_id"] == retried.task_id
    assert retried.canvas_item["status"] == "generating"
    retried_task = await generation_store.read_generation_task(ctx, str(retried.task_id))
    assert retried_task["reference_image_urls"] == ["ref.png"]
    assert retried_task["retry_source"] == "manual"
    stored_retried_task = await repo.get(int(retried.task_id))
    assert stored_retried_task.workflow_stage == "provider_operation"


@pytest.mark.asyncio
async def test_retry_generation_artifact_returns_running_status_for_duplicate_manual_retry(
    monkeypatch,
    tmp_path: Path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = {
        "id": "conv-retry-duplicate",
        "runtime_profile": "home",
    }
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-image",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    artifact_ref = "artifact_ref:duplicate_retry"
    generation_store.create_or_read_artifact(
        ctx,
        kind="image",
        planned_result_url="agent://generated/duplicate.png",
        artifact_ref=artifact_ref,
    )
    generation_store.update_artifact(
        ctx,
        artifact_ref,
        {
            "status": "failed",
            "error": "provider failed",
            "current_task_id": "123",
            "manual_retry_count": 0,
        },
    )

    coordinator = FakeRetryCoordinator()
    release_gate = asyncio.Event()
    retry_calls = 0

    async def fake_retry_artifact(ctx, artifact_ref, *, source):
        nonlocal retry_calls
        retry_calls += 1
        await release_gate.wait()
        return SimpleNamespace(
            metadata={
                "task_id": "124",
                "artifact_ref": artifact_ref,
                "manual_retry_count": 1,
                "status": "processing",
            }
        )

    monkeypatch.setattr(
        "app.services.ephemeral_task_coordinator.get_redis_coordinator",
        lambda: coordinator,
    )
    monkeypatch.setattr(generation_store, "retry_artifact", fake_retry_artifact)

    first = asyncio.create_task(
        retry_generation_artifact(
            user_id=7,
            conversation_id=conversation["id"],
            artifact_ref=artifact_ref,
        )
    )
    await asyncio.sleep(0)

    duplicate = await retry_generation_artifact(
        user_id=7,
        conversation_id=conversation["id"],
        artifact_ref=artifact_ref,
    )
    release_gate.set()
    completed = await first

    assert retry_calls == 1
    assert completed.status == "processing"
    assert duplicate.status == "already_running"
    assert duplicate.task_id == "123"
    assert duplicate.error_message == "generation_retry_already_running"
    assert all(str(tmp_path) not in ":".join(parts) for parts in coordinator.keys.resource_parts)
