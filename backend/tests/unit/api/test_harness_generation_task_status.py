from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import harness as harness_endpoint

@pytest.mark.asyncio
async def test_get_generation_task_status_follows_artifact_current_task_during_retry(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = {
        "id": "conv-retry-status",
        "runtime_profile": "home",
        "project_id": None,
    }
    artifact_ref = "artifact_ref:retrying-image"

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    async def _read_effective_generation_task(_ctx, task_id):
        assert task_id == "task-first"
        return {
            "task_id": "task-second",
            "artifact_ref": artifact_ref,
            "status": "processing",
            "progress": 35,
            "error": None,
            "canvas_revision": 21,
            "canvas_item_deleted": False,
            "canvas_item": {
                "id": "canvas-retry-item",
                "task_id": "task-second",
                "status": "generating",
            },
        }

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_store.read_effective_generation_task",
        _read_effective_generation_task,
    )

    response = await harness_endpoint.get_generation_task_status(
        conversation_id=conversation["id"],
        task_id="task-first",
        user=SimpleNamespace(id=7),
    )

    assert response["task_id"] == "task-second"
    assert response["artifact_ref"] == artifact_ref
    assert response["status"] == "processing"
    assert response["progress"] == 35
    assert response["error_message"] is None
    assert response["canvas_revision"] == 21
    assert response["canvas_item_deleted"] is False
    assert response["canvas_item"]["task_id"] == "task-second"


@pytest.mark.asyncio
async def test_get_generation_artifact_task_status_reads_by_artifact_ref(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = {
        "id": "conv-artifact-status",
        "runtime_profile": "home",
        "project_id": None,
    }
    artifact_ref = "artifact_ref:generated-image"

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )

    async def _read_effective_generation_task_by_artifact_ref(_ctx, value):
        assert value == artifact_ref
        return {
            "task_id": "task-image",
            "artifact_ref": artifact_ref,
            "status": "completed",
            "kind": "image",
            "result_url": "references/generated/image.png",
            "planned_result_url": "references/generated/planned.png",
            "error": None,
            "canvas_revision": 22,
            "canvas_item_deleted": False,
        }

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_store.read_effective_generation_task_by_artifact_ref",
        _read_effective_generation_task_by_artifact_ref,
    )

    response = await harness_endpoint.get_generation_artifact_task_status(
        conversation_id=conversation["id"],
        artifact_ref=artifact_ref,
        user=SimpleNamespace(id=7),
    )

    assert response["task_id"] == "task-image"
    assert response["artifact_ref"] == artifact_ref
    assert response["status"] == "completed"
    assert response["kind"] == "image"
    assert response["result_url"] == "references/generated/image.png"
    assert response["planned_result_url"] == "references/generated/planned.png"
    assert response["canvas_revision"] == 22
    assert response["canvas_item_deleted"] is False
