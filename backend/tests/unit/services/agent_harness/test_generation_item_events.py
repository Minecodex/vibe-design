import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.core.utils.generation_item_events import (
    emit_generation_item_completed,
    emit_generation_item_started,
)


@pytest.mark.asyncio
async def test_generation_item_started_payload_includes_canvas_revision_for_image_and_video(monkeypatch, tmp_path):
    appended_events: list[dict] = []

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs["payload"]}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-revision-started",
        run_id="run-revision-started",
        workspace_root=tmp_path,
        runtime_profile="canvas",
        project_id=9,
    )

    await emit_generation_item_started(
        ctx,
        {"id": "101", "provider_code": "builtin"},
        artifact_ref="artifact_ref:image-started",
        canvas_item={"id": "image-started", "type": "image_generator"},
        kind="image",
        canvas_revision=11,
        canvas_item_deleted=False,
    )
    await emit_generation_item_started(
        ctx,
        {"id": "102", "provider_code": "builtin"},
        artifact_ref="artifact_ref:video-started",
        canvas_item={"id": "video-started", "type": "video_generator"},
        kind="video",
        canvas_revision=12,
        canvas_item_deleted=False,
    )

    image_payload = appended_events[0]["payload"]["payload"]
    video_payload = appended_events[1]["payload"]["payload"]
    assert image_payload["kind"] == "image"
    assert image_payload["canvas_revision"] == 11
    assert image_payload.get("canvas_item_deleted") is not True
    assert video_payload["kind"] == "video"
    assert video_payload["canvas_revision"] == 12
    assert video_payload.get("canvas_item_deleted") is not True


@pytest.mark.asyncio
async def test_generation_item_completed_payload_includes_terminal_canvas_revision_for_image_and_video(monkeypatch, tmp_path):
    appended_events: list[dict] = []

    async def fake_append_event_async(*args, **kwargs):
        appended_events.append({"args": args, **kwargs})
        return {"sequence": len(appended_events), "type": kwargs["event_type"], "payload": kwargs["payload"]}

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.generation_item_events.append_event_async",
        fake_append_event_async,
    )
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-revision-completed",
        run_id="run-revision-completed",
        workspace_root=tmp_path,
        runtime_profile="canvas",
        project_id=9,
    )

    await emit_generation_item_completed(
        ctx,
        {"id": "201", "provider_code": "builtin"},
        artifact_ref="artifact_ref:image-completed",
        canvas_item={"id": "image-completed", "type": "image"},
        kind="image",
        status="completed",
        result_url="/api/v1/uploads/canvas/9/image-completed.png",
        canvas_revision=21,
        canvas_item_deleted=False,
    )
    await emit_generation_item_completed(
        ctx,
        {"id": "202", "provider_code": "builtin"},
        artifact_ref="artifact_ref:video-failed",
        canvas_item={"id": "video-failed", "type": "video_generator"},
        kind="video",
        status="failed",
        error="provider failed",
        canvas_revision=22,
        canvas_item_deleted=True,
    )

    image_payload = appended_events[0]["payload"]["payload"]
    video_payload = appended_events[1]["payload"]["payload"]
    assert image_payload["kind"] == "image"
    assert appended_events[0]["payload"]["status"] == "completed"
    assert image_payload["canvas_revision"] == 21
    assert image_payload.get("canvas_item_deleted") is not True
    assert video_payload["kind"] == "video"
    assert video_payload["canvas_revision"] == 22
    assert video_payload["canvas_item_deleted"] is True
    assert appended_events[1]["payload"]["status"] == "failed"
    assert appended_events[1]["payload"]["error"]["summary"] == "provider failed"
