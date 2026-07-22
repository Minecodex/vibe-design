from pathlib import Path
from types import SimpleNamespace

from app.services.agent_harness.core.utils.harness_generation_projection import publish_generation_media_update
from app.services.agent_harness.workflow.tool_gating import (
    build_tool_card_event,
    presentation_scope_for_interaction_response,
)


def test_tool_card_event_uses_interaction_response_scope() -> None:
    scope = presentation_scope_for_interaction_response(
        conversation_id="conv-1",
        request_id="call-ask-user",
        turn=2,
    )

    event = build_tool_card_event(
        conversation_id="conv-1",
        run_id="run-1",
        step_id="step-1",
        phase="end",
        tool_name="generate_image",
        call_id="call-image",
        result_payload={"artifact_ref": "artifact_ref:abc", "task_id": "12"},
        status="processing",
        message_key=scope["message_key"],
        parent_block_key=scope["parent_block_key"],
        order=3,
    )

    assert event is not None
    assert event.payload["message_key"] == "interaction-response:conv-1:call-ask-user:2"
    assert event.payload["parent_block_key"] is None
    assert event.payload["order"] == 3
    assert event.payload["block"]["order"] == 3


def test_generation_media_update_reuses_persisted_presentation_scope(monkeypatch, tmp_path: Path) -> None:
    published = []

    def fake_publish_presentation_event(*_args, draft, **_kwargs):
        published.append(draft)

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_presentation_event",
        fake_publish_presentation_event,
    )
    ctx = SimpleNamespace(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        conversation_dir=tmp_path,
        project_dir=tmp_path / "project",
        references_dir=tmp_path / "references",
        published_dir=tmp_path / "published",
    )
    task = {
        "kind": "image",
        "tool_call_id": "call-image",
        "artifact_ref": "artifact_ref:abc",
        "task_id": "12",
        "canvas_revision": 9,
        "canvas_item_deleted": False,
        "presentation_scope": {
            "message_key": "interaction-response:conv-1:call-ask-user:2",
            "parent_block_key": None,
        },
        "presentation_order": 3,
    }

    publish_generation_media_update(
        ctx,
        task_id="12",
        task=task,
        artifact=None,
        status="completed",
        result_url="/api/v1/uploads/canvas/1/result.png",
    )

    assert len(published) == 1
    payload = published[0].payload
    assert payload["message_key"] == "interaction-response:conv-1:call-ask-user:2"
    assert payload["parent_block_key"] is None
    assert payload["order"] == 3
    assert payload["block"]["payload"]["result_url"] == "/api/v1/uploads/canvas/1/result.png"
    assert payload["block"]["payload"]["canvas_revision"] == 9
    assert payload["block"]["payload"]["canvas_item_deleted"] is False


def test_generation_media_update_upserts_processing_blocks(monkeypatch, tmp_path: Path) -> None:
    published = []

    def fake_publish_presentation_event(*_args, draft, **_kwargs):
        published.append(draft)

    monkeypatch.setattr(
        "app.services.agent_harness.core.utils.harness_generation_projection.publish_presentation_event",
        fake_publish_presentation_event,
    )
    ctx = SimpleNamespace(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        conversation_dir=tmp_path,
        project_dir=tmp_path / "project",
        references_dir=tmp_path / "references",
        published_dir=tmp_path / "published",
    )
    task = {
        "kind": "image",
        "tool_call_id": "call-image",
        "artifact_ref": "artifact_ref:abc",
        "task_id": "12",
        "presentation_scope": {
            "message_key": "interaction-response:conv-1:call-ask-user:2",
            "parent_block_key": None,
        },
        "presentation_order": 3,
    }

    publish_generation_media_update(
        ctx,
        task_id="12",
        task=task,
        artifact=None,
        status="processing",
        result_url=None,
    )

    assert len(published) == 1
    payload = published[0].payload
    assert payload["type"] == "presentation.block.upsert"
    assert payload["block"]["status"] == "processing"
