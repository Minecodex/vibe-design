from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services.agent_harness.runtime.conversation_events import load_conversation_events
from app.services.agent_harness.runtime.eventing.event_log import append_event, append_event_async, subscribe_to_events
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.snapshot import build_session_detail_snapshot_payload
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, delete_conversation
from app.services.agent_harness.workspace.session_v2.db_store import build_detail_snapshot


def _delta_payload(conversation_id: str, run_id: str, delta: str, *, block_key: str = "answer") -> dict:
    return presentation_v2.block_delta(
        conversation_id=conversation_id,
        run_id=run_id,
        block_key=block_key,
        delta=delta,
    )


def test_append_event_serializes_concurrent_user_event_sequences(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Concurrent events")

    def _append(index: int) -> int:
        record = append_event(
            7,
            conversation["id"],
            run_id="run-1",
            event_type="presentation.block.delta",
            lane="user",
            data=_delta_payload(conversation["id"], "run-1", f"chunk-{index}"),
        )
        return int(record["sequence"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        sequences = list(executor.map(_append, range(20)))

    assert sorted(sequences) == list(range(1, 21))
    stored_events = load_conversation_events(7, conversation["id"])
    assert [event["sequence"] for event in stored_events] == list(range(1, 21))


@pytest.mark.asyncio
async def test_append_event_async_presentation_delta_returns_transient_and_flushes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_transient_event_sync",
        lambda *_args, **_kwargs: None,
    )

    from app.services.agent_harness.runtime.eventing import presentation_delta_queue

    monkeypatch.setattr(
        presentation_delta_queue,
        "HARNESS_PRESENTATION_DELTA_PERSIST_FLUSH_INTERVAL_SECONDS",
        60.0,
    )
    presentation_delta_queue.reset_for_tests()
    conversation = create_conversation(7, title="Transient delta")
    received: list[dict] = []
    unsubscribe = subscribe_to_events(7, conversation["id"], received.append)
    try:
        record = await append_event_async(
            7,
            conversation["id"],
            run_id="run-1",
            event_type="presentation.block.delta",
            lane="user",
            data=_delta_payload(conversation["id"], "run-1", "live"),
        )
        assert record["transient"] is True
        assert received and received[0]["transient"] is True
        assert load_conversation_events(7, conversation["id"]) == []

        await presentation_delta_queue.flush_pending()
        stored = load_conversation_events(7, conversation["id"])
        assert len(stored) == 1
        assert stored[0]["type"] == "presentation.block.delta"
        assert stored[0]["payload"]["payload"]["delta"] == "live"
    finally:
        unsubscribe()
        await presentation_delta_queue.aclose(flush=False)


def test_append_event_raises_when_user_visible_persistence_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Durable user events")
    received: list[dict] = []
    unsubscribe = subscribe_to_events(7, conversation["id"], received.append)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.append_conversation_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    try:
        with pytest.raises(RuntimeError, match="db unavailable"):
            append_event(
                7,
                conversation["id"],
                run_id="run-1",
                event_type="presentation.block.delta",
                lane="user",
                data=_delta_payload(conversation["id"], "run-1", "hello"),
            )
    finally:
        unsubscribe()

    assert received == []
    assert load_conversation_events(7, conversation["id"]) == []


def test_append_event_drops_non_user_events_after_conversation_delete(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Deleted event target")
    received: list[dict] = []
    unsubscribe = subscribe_to_events(7, conversation["id"], received.append)

    try:
        assert delete_conversation(7, conversation["id"]) is True
        record = append_event(
            7,
            conversation["id"],
            run_id="run-1",
            event_type="heartbeat",
            lane="runtime",
            data={"status": "running"},
        )
    finally:
        unsubscribe()

    assert record["transient"] is True
    assert received == []
    assert load_conversation_events(7, conversation["id"]) == []


def test_append_event_projects_presentation_snapshot_cursor(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Presentation v2")

    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", "Hello"),
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", " world"),
    )

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["protocol_version"] == 2
    assert snapshot["projection"]["event_last_sequence"] == 2
    assert snapshot["event_stream"]["last_sequence"] == 2
    assert snapshot["messages"][0]["metadata"]["protocol_version"] == 2
    assert snapshot["messages"][0]["content"] == "Hello world"


def test_v2_rejects_legacy_transcript_rows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Presentation only")

    from app.services.agent_harness.runtime.state.store_core import append_model_message

    with pytest.raises(ValueError, match="user-visible messages must be projected"):
        append_model_message(7, conversation["id"], {"role": "user", "content": "Build a landing page"})
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="user_message",
        lane="user",
        data={"id": "user-1", "role": "user", "content": "Build a landing page", "attachments": []},
    )

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["protocol_version"] == 2
    assert [message["content"] for message in snapshot["messages"]] == ["Build a landing page"]
    assert snapshot["messages"][0]["metadata"]["render_kind"] == "presentation_v2"


def test_user_message_projection_preserves_attachments_for_snapshot_replay(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Replay attachments")
    attachments = [
        {
            "type": "image",
            "url": "references/inputs/upload_001/source.png",
            "name": "product.png",
        },
        {
            "type": "file",
            "url": "references/inputs/upload_002/source.docx",
            "name": "brief.docx",
        },
    ]

    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="user_message",
        lane="user",
        data={
            "id": "user-1",
            "role": "user",
            "content": "Use these uploads",
            "attachments": attachments,
        },
    )

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["messages"][0]["content"] == "Use these uploads"
    assert snapshot["messages"][0]["attachments"] == attachments


def test_snapshot_replay_backfills_previously_projected_user_message_attachments(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Backfill replay attachments")
    attachments = [
        {
            "type": "image",
            "url": "references/inputs/upload_001/source.png",
            "name": "product.png",
        }
    ]

    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="user_message",
        lane="user",
        data={
            "id": "user-1",
            "role": "user",
            "content": "Use this upload",
            "attachments": attachments,
        },
    )

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessMessage

    with harness_sync_session_scope() as session:
        row = session.query(HarnessMessage).filter_by(conversation_id=conversation["id"], role="user").one()
        row.attachments_json = None
        session.flush()

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["messages"][0]["content"] == "Use this upload"
    assert snapshot["messages"][0]["attachments"] == attachments


def test_interaction_submitted_projects_user_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Interaction submission")

    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="interaction_submitted",
        lane="user",
        data={
            "request_id": "quick-brief:conv:1",
            "kind": "quick_brief",
            "answer": "raw",
            "display_label": "落地页 Quick Brief",
            "answers": {"goal": "landing"},
            "approved": None,
        },
    )

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["protocol_version"] == 2
    assert snapshot["projection"]["event_last_sequence"] == 1
    assert len(snapshot["messages"]) == 1
    assert snapshot["messages"][0]["role"] == "user"
    assert snapshot["messages"][0]["content"] == "落地页 Quick Brief"
    assert snapshot["messages"][0]["metadata"]["render_kind"] == "presentation_v2"
    assert snapshot["messages"][0]["metadata"]["request_id"] == "quick-brief:conv:1"


def test_append_event_projection_is_idempotent_for_same_event(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Presentation idempotency")

    record = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", "Once"),
    )
    from app.services.agent_harness.runtime.presentation_v2.projection_store import project_committed_event

    project_committed_event(7, conversation["id"], record)
    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["messages"][0]["content"] == "Once"


def test_reconcile_backfills_shipped_critique_design_jury_child(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Backfill shipped critique")

    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.upsert",
        lane="user",
        data=presentation_v2.subagent_card(
            conversation_id=conversation["id"],
            run_id="run-1",
            payload={
                "task_id": "quality-review-1",
                "label": "Quality review",
                "purpose": "Quality review",
                "status": "running",
                "subagent_type": "QualityReview",
            },
            status="running",
        ),
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="critique.shipped",
        lane="user",
        data={
            "critique_run_id": "critique-1",
            "subagent_task_id": "quality-review-1",
            "status": "shipped",
            "round": 1,
            "score_scale": 10,
            "scores": {"critic": 8.2, "brand": 8.4},
        },
    )

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessMessage, HarnessPresentationProjectionState
    from app.services.agent_harness.runtime.presentation_v2.projection_store import reconcile_projection

    with harness_sync_session_scope() as session:
        rows = session.query(HarnessMessage).filter(HarnessMessage.conversation_id == conversation["id"]).all()
        assert len(rows) == 1
        rows[0].blocks_json[0]["children"] = []
        state = session.get(HarnessPresentationProjectionState, conversation["id"])
        assert state is not None
        state.status = "idle"
        state.lease_owner = None
        state.lease_expires_at = None

    reconcile_projection(7, conversation["id"], worker_id="test-backfill")
    snapshot = build_detail_snapshot(7, conversation["id"])
    subagent = snapshot["messages"][0]["blocks"][0]
    assert subagent["ui_kind"] == "subagent_card"
    assert subagent["children"][0]["ui_kind"] == "design_jury_card"
    assert subagent["children"][0]["status"] == "shipped"
    assert subagent["children"][0]["payload"]["scores"] == {"critic": 8.2, "brand": 8.4}


def test_selection_resolved_projection_updates_conversation_meta_without_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Selection projection")

    append_event(
        7,
        conversation["id"],
        run_id="preflight",
        event_type="selection_resolved",
        lane="user",
        data={
            "skill_id": "open-design-landing",
            "resolved_skill_id": "open-design-landing",
            "skill_selection_mode": "auto",
            "skill_resolution_source": "ai_resolved",
            "last_skill_decision_confidence": 0.95,
        },
    )

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["skill_id"] == "open-design-landing"
    assert snapshot["resolved_skill_id"] == "open-design-landing"
    assert snapshot["skill_selection_mode"] == "auto"
    assert snapshot["projection"]["event_last_sequence"] == 1
    assert snapshot["event_stream"]["last_sequence"] == 1
    assert snapshot["messages"] == []


def test_projection_failure_does_not_advance_snapshot_cursor(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection failure")
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.presentation_v2.projection_store.reduce_event_to_ops",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad reducer")),
    )

    record = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", "Saved fact"),
    )

    from app.services.agent_harness.runtime.presentation_v2.projection_store import get_projection_state

    assert record["sequence"] == 1
    stored = load_conversation_events(7, conversation["id"])[0]
    assert stored["type"] == "presentation.block.delta"
    assert stored["payload"]["payload"]["delta"] == "Saved fact"
    assert "legacy_event_type" not in stored["payload"]
    projection_state = get_projection_state(7, conversation["id"])
    assert projection_state["applied_event_sequence"] == 0
    assert projection_state["latest_observed_sequence"] == 1
    assert projection_state["status"] == "failed"


def test_detail_snapshot_reconciles_projection_from_old_cursor(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection reconcile")

    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", "First"),
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", " second"),
    )

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessMessage, HarnessPresentationProjectionState

    with harness_sync_session_scope() as session:
        session.query(HarnessMessage).filter(HarnessMessage.conversation_id == conversation["id"]).delete()
        state = session.get(HarnessPresentationProjectionState, conversation["id"])
        assert state is not None
        state.applied_event_sequence = 0
        state.status = "idle"

    snapshot = build_detail_snapshot(7, conversation["id"])

    assert snapshot["projection"]["event_last_sequence"] == 2
    assert snapshot["event_stream"]["last_sequence"] == 2
    assert snapshot["messages"][0]["content"] == "First second"


def test_projection_reconcile_respects_active_worker_lease(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection lease")

    record = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        lane="user",
        data=_delta_payload(conversation["id"], "run-1", "Blocked by lease"),
    )

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessMessage, HarnessPresentationProjectionState
    from app.services.agent_harness.runtime.presentation_v2.projection_store import reconcile_projection

    with harness_sync_session_scope() as session:
        session.query(HarnessMessage).filter(HarnessMessage.conversation_id == conversation["id"]).delete()
        state = session.get(HarnessPresentationProjectionState, conversation["id"])
        assert state is not None
        state.applied_event_sequence = 0
        state.latest_observed_sequence = int(record["sequence"])
        state.status = "running"
        state.lease_owner = "worker-a"
        state.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)

    projection_state = reconcile_projection(7, conversation["id"], worker_id="worker-b")

    assert projection_state["applied_event_sequence"] == 0
    assert projection_state["latest_observed_sequence"] == 1
    with harness_sync_session_scope() as session:
        messages = session.query(HarnessMessage).filter(HarnessMessage.conversation_id == conversation["id"]).all()
        assert messages == []


def test_presentation_snapshot_uses_projection_cursor_not_latest_event_sequence():
    snapshot = build_session_detail_snapshot_payload(
        conversation={"id": "conv-1"},
        messages_page={
            "messages": [
                {"id": "assistant", "role": "assistant", "content": "ok", "_seq": 4},
            ],
            "messages_page": {"has_more": False, "oldest_seq": 4},
        },
        workspace_files=[],
        projection_state={
            "applied_event_sequence": 4,
            "latest_observed_sequence": 9,
            "status": "idle",
        },
        latest_event_sequence=9,
        tail_limit=80,
    )

    assert snapshot["protocol_version"] == 2
    assert snapshot["projection"]["event_last_sequence"] == 4
    assert snapshot["projection"]["latest_observed_sequence"] == 9
    assert snapshot["event_stream"]["last_sequence"] == 9
    assert snapshot["messages"][0] == {"id": "assistant", "role": "assistant", "content": "ok"}
