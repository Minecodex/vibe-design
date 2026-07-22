from __future__ import annotations

from pathlib import Path

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import ContextProjectionState
from app.services.agent_harness.runtime.model_context.boundary_store import append_boundary_v2
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    load_messages,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    append_message_record as append_message,
)


def test_conversation_event_log_is_authoritative_while_messages_remain_projection(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event

    conversation = create_conversation(7, title="Events")
    # The durable conversation event log is authoritative; user-visible messages
    # are a projection of presentation events (not a direct message_appended write).
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="user_message",
        data={"content": "build the context pipeline"},
    )

    from app.services.agent_harness.runtime.conversation_events import load_conversation_events

    events = load_conversation_events(7, conversation["id"])
    messages = load_messages(7, conversation["id"])

    assert [event["type"] for event in events] == ["user_message"]
    assert events[0]["sequence"] == 1
    assert events[0]["payload"]["content"] == "build the context pipeline"
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "build the context pipeline"
    assert messages[0]["metadata"]["render_kind"] == "presentation_v2"


def test_context_projection_state_uses_recall_sidecar_responsibility(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Projection")

    from app.services.agent_harness.runtime.context_projection import (
        claim_next_projection,
        complete_projection,
        mark_projection_dirty,
    )

    first = mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=1,
        reason="message_appended",
    )
    second = mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=2,
        reason="tool_result_recorded",
    )
    claimed = claim_next_projection(worker_id="worker-1")

    assert first["conversation_id"] == second["conversation_id"]
    assert second["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert claimed is not None
    assert claimed["conversation_id"] == conversation["id"]
    assert claimed["lease_owner"] == "worker-1"

    completed = complete_projection(
        conversation["id"],
        worker_id="worker-1",
        lease_token=claimed["lease_token"],
        processed_sequence=2,
        completed_responsibilities=["recall_sidecar_refresh"],
        result={"artifact": "recall_sidecar"},
    )

    assert completed["dirty_responsibilities"] == []
    assert completed["last_result"]["artifact"] == "recall_sidecar"

    with harness_sync_session_scope() as session:
        assert session.get(ContextProjectionState, conversation["id"]) is not None


def test_large_tool_result_promotes_to_blob_and_keeps_preview(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Blob")

    from app.services.agent_harness.runtime.blob_artifacts import promote_large_tool_result

    promoted = promote_large_tool_result(
        7,
        conversation["id"],
        tool_call_id="call-1",
        tool_name="exec_command",
        content="needle " + ("x" * 10_000),
        threshold_chars=1024,
    )

    assert promoted["promoted"] is True
    assert promoted["content"] != "needle " + ("x" * 10_000)
    assert promoted["artifact"]["ref"].startswith(".meta/tool_blobs/")
    assert "needle" in promoted["preview"]
    assert (tmp_path / "users" / "7" / "conversations" / conversation["id"] / promoted["artifact"]["ref"]).exists()


def test_compaction_boundary_marks_only_recall_sidecar_dirty(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Boundary")
    message = append_message(7, conversation["id"], {"role": "user", "content": "old"})
    boundary = append_boundary_v2(
        7,
        conversation["id"],
        run_id="run-1",
        compact_type="auto_full",
        covered={"message_row_id_end": int(message["_seq"]), "event_sequence_end": 1, "message_count": 1},
        summary_message={"role": "user", "content": "Conversation summary:\nold"},
        restore_messages=[],
        token_counts={"pre": 100, "post": 10, "effective_window": 1000, "auto_threshold": 800},
        method={"source": "llm_full_compact", "levels_applied": ["full_summary"]},
    )

    from app.services.agent_harness.runtime.context_projection import get_projection_state

    state = get_projection_state(7, conversation["id"])

    assert boundary.payload["schema_version"] == 2
    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]
