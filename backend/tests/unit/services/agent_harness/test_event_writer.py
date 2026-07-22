from pathlib import Path

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.eventing.event_writer import (
    append_harness_event,
    enrich_harness_event_payload,
)
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.runtime.eventing.event_log import subscribe_to_events
from app.services.agent_harness.runtime.conversation_events import load_conversation_events


def test_enrich_harness_event_payload_does_not_add_legacy_subagent_context(tmp_path: Path):
    ctx = HarnessContext(
        user_id=7,
        conversation_id="conv-1",
        run_id="child-run",
        workspace_root=tmp_path,
        is_subagent=True,
        parent_run_id="parent-run",
        subagent_run_id="child-run",
        subagent_label="Visual QA",
        subagent_type="general-purpose",
        skill_id="pptx",
    )

    payload = enrich_harness_event_payload(
        ctx=ctx,
        payload={"id": "block-1"},
        tool_name="analyze_image",
        tool_call_id="call-1",
    )

    assert payload["tool"] == "analyze_image"
    assert payload["call_id"] == "call-1"
    assert "subagent_context" not in payload
    assert "subagentContext" not in payload


def test_enrich_harness_event_payload_carries_run_output_anchor(tmp_path: Path):
    ctx = HarnessContext(
        user_id=7,
        conversation_id="conv-1",
        run_id="child-run",
        workspace_root=tmp_path,
        is_subagent=True,
        parent_run_id="parent-run",
        subagent_run_id="child-run",
        subagent_label="Visual QA",
        subagent_type="general-purpose",
        skill_id="pptx",
        run_output_anchor_message_id="plan-execution-approved:conv:plan:v1",
        run_output_anchor_created_at="2026-06-04T00:00:00.000Z",
        run_output_anchor_source="plan_execution_approved",
    )

    payload = enrich_harness_event_payload(
        ctx=ctx,
        payload={"id": "block-1"},
    )

    assert payload["anchor_message_id"] == "plan-execution-approved:conv:plan:v1"
    assert "subagent_context" not in payload
    assert payload["anchor_source"] == "plan_execution_approved"


def test_context_hydrates_run_output_anchor_from_runtime_state(monkeypatch, tmp_path: Path):
    ctx = HarnessContext(
        user_id=7,
        conversation_id="conv-1",
        run_id="parent-run",
        workspace_root=tmp_path,
    )

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.state.store_core.read_runtime_state",
        lambda user_id, conversation_id: {
            "run_output_anchor": {
                "anchor_message_id": "plan-execution-approved:conv:plan:v1",
                "anchor_created_at": "2026-06-04T00:00:00.000Z",
                "anchor_source": "plan_execution_approved",
            }
        },
    )

    assert ctx.hydrate_run_output_anchor() == {
        "anchor_message_id": "plan-execution-approved:conv:plan:v1",
        "anchor_created_at": "2026-06-04T00:00:00.000Z",
        "anchor_source": "plan_execution_approved",
    }
    assert ctx.run_output_anchor_message_id == "plan-execution-approved:conv:plan:v1"


def test_append_harness_event_preserves_non_subagent_payload(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Writer contract")
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="parent-run",
        workspace_root=tmp_path,
    )

    record = append_harness_event(
        ctx=ctx,
        event_type="presentation.block.upsert",
        data={"id": "block-1", "kind": "text", "order": 0, "status": "running", "payload": {}},
        block_id="block-1",
    )

    assert record["payload"]["id"] == "block-1"
    assert "subagent_context" not in record["payload"]


def test_append_harness_event_persists_user_visible_delta_events(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Transient writer contract")
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="parent-run",
        workspace_root=tmp_path,
    )
    received: list[dict] = []
    unsubscribe = subscribe_to_events(7, conversation["id"], received.append)

    try:
        record = append_harness_event(
            ctx=ctx,
            event_type="presentation.block.delta",
            data={"block_id": "block-1", "field": "payload.text", "delta": "hello"},
            block_id="block-1",
        )
    finally:
        unsubscribe()

    assert record is not None
    assert "transient" not in record
    assert record["seq"] >= 1
    assert record["type"] == "presentation.block.delta"
    assert record["payload"]["delta"] == "hello"
    assert received == [record]


def test_append_harness_event_dedupes_explicit_presentation_idempotency_key(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Presentation event idempotency")
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="parent-run",
        workspace_root=tmp_path,
    )

    first = append_harness_event(
        ctx=ctx,
        event_type="presentation.block.upsert",
        data={"block_key": "subagent:sub-task-1", "status": "queued"},
        artifact_id="sub-task-1",
        idempotency_key="run:parent-run:subagent:sub-task-1:created",
    )
    second = append_harness_event(
        ctx=ctx,
        event_type="presentation.block.upsert",
        data={"block_key": "subagent:sub-task-1", "status": "queued"},
        artifact_id="sub-task-1",
        idempotency_key="run:parent-run:subagent:sub-task-1:created",
    )

    assert first["sequence"] == second["sequence"]
    assert first["idempotency_key"] == "run:parent-run:subagent:sub-task-1:created"

    events = load_conversation_events(7, conversation["id"])
    assert [event["event_type"] for event in events] == ["presentation.block.upsert"]


def test_transient_events_broadcast_without_authoritative_persistence(monkeypatch, tmp_path: Path):
    from app.services.agent_harness.runtime.eventing.event_sink import HarnessEventSink

    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Transient event")
    received: list[dict] = []
    unsubscribe = subscribe_to_events(7, conversation["id"], received.append)

    try:
        record = HarnessEventSink(
            user_id=7,
            conversation_id=conversation["id"],
            run_id="run-transient",
        ).emit(
            "cursor_tick",
            data={"message": "typing"},
            persist=False,
        )
    finally:
        unsubscribe()

    assert record is not None
    assert record["transient"] is True
    assert received == [record]
    assert load_conversation_events(7, conversation["id"]) == []
