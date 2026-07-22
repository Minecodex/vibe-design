from __future__ import annotations

from pathlib import Path

from app.services.agent_harness.runtime.context_projection import mark_projection_dirty
from app.services.agent_harness.runtime.conversation_events import append_conversation_event
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
)


def test_stable_conversation_facts_mark_projection_dirty_without_jobs(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Stable dirty")

    from app.services.agent_harness.runtime.context_projection import (
        get_projection_state,
        mark_projection_dirty_for_event,
    )

    message_event = append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="assistant_message_finalized",
        payload={"message_id": "m1", "role": "user", "content": "must not be copied"},
    )
    tool_event = append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="tool_result_recorded",
        payload={"tool_call_id": "tool-1", "content": "secret tool output"},
    )

    first = mark_projection_dirty_for_event(7, conversation["id"], message_event)
    second = mark_projection_dirty_for_event(7, conversation["id"], tool_event)
    state = get_projection_state(7, conversation["id"])

    assert first is not None
    assert second is not None
    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert state["latest_observed_sequence"] == tool_event["sequence"]
    assert state["last_dirty_reason"] == "tool_result_recorded"


def test_appending_context_affecting_event_marks_projection_dirty_and_wakes_worker(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Append dirty integration")
    wakeups: list[str] = []

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.context_projection_wakeup.wake_context_projection_workers_sync",
        lambda conversation_id: wakeups.append(conversation_id),
    )

    event = append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="assistant_message_finalized",
        payload={"message_id": "m1", "role": "user", "content": "queued for projection"},
    )

    from app.services.agent_harness.runtime.context_projection import get_projection_state

    state = get_projection_state(7, conversation["id"])

    assert state is not None
    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert state["latest_observed_sequence"] == event["sequence"]
    assert wakeups == [conversation["id"]]


def test_dirty_mark_survives_redis_wakeup_failure_and_database_sweep_processes_it(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Wakeup failure fallback")

    class FakeKeys:
        def build(self, **_kwargs):
            return "context-projection:wakeup"

    class FailingCoordinator:
        keys = FakeKeys()

        async def wakeup(self, _key):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.context_projection_wakeup.get_redis_coordinator",
        lambda: FailingCoordinator(),
    )

    state = mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=9,
        reason="message_appended",
    )

    from app.services.agent_harness.runtime.context_projection import get_projection_state
    from app.services.agent_harness.runtime.context_projection_worker import (
        process_next_context_projection,
    )

    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    completed = process_next_context_projection(worker_id="projection-worker")
    refreshed = get_projection_state(7, conversation["id"])

    assert completed is not None
    assert completed["status"] == "completed"
    assert refreshed["dirty_responsibilities"] == []
    assert refreshed["latest_processed_sequence"] == 9


def test_transient_and_maintenance_events_do_not_mark_projection_dirty(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Ignored dirty")

    from app.services.agent_harness.runtime.context_projection import (
        get_projection_state,
        mark_projection_dirty_for_event,
    )

    ignored_events = [
        append_conversation_event(7, conversation["id"], run_id="run-1", event_type="message_block_delta", payload={}),
        append_conversation_event(7, conversation["id"], run_id="run-1", event_type="render_state_sync", payload={}),
        append_conversation_event(7, conversation["id"], run_id="run-1", event_type="heartbeat", payload={}),
        append_conversation_event(7, conversation["id"], run_id=None, event_type="projection_run", payload={}),
        append_conversation_event(7, conversation["id"], run_id=None, event_type="recall_sidecar_rebuilt", payload={}),
    ]

    results = [mark_projection_dirty_for_event(7, conversation["id"], event) for event in ignored_events]

    assert results == [None, None, None, None, None]
    assert get_projection_state(7, conversation["id"]) is None


def test_compaction_boundary_marks_post_boundary_projection_dirty(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Boundary dirty")

    from app.services.agent_harness.runtime.context_projection import (
        get_projection_state,
        mark_projection_dirty_for_event,
    )

    boundary_event = append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="compaction_boundary",
        payload={"boundary_id": "b1", "summary": "bounded summary"},
    )

    marked = mark_projection_dirty_for_event(7, conversation["id"], boundary_event)
    state = get_projection_state(7, conversation["id"])

    assert marked is not None
    assert state["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert state["latest_observed_sequence"] == boundary_event["sequence"]
