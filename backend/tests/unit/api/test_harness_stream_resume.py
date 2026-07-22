from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import harness as harness_endpoint
from app.core.config import settings
from app.core.redis_coordination import reset_redis_coordinator_for_tests
from app.services.agent_harness.runtime.conversation_events import append_conversation_event
from app.services.agent_harness.runtime.eventing.conversation_event_fanout import (
    publish_event_notification_sync,
)
from app.services.agent_harness.runtime.eventing.conversation_stream_session import (
    stream_conversation_events,
)
from app.services.agent_harness.runtime.eventing.event_log import append_event
from app.services.agent_harness.runtime.eventing.turn_protocol import build_turn_completed_payload, build_turn_error
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    get_conversation,
)
from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state


def _presentation_delta(conversation_id: str, run_id: str, delta: str, *, block_key: str = "answer") -> dict:
    return presentation_v2.block_delta(
        conversation_id=conversation_id,
        run_id=run_id,
        block_key=block_key,
        delta=delta,
    )


def _presentation_complete(conversation_id: str, run_id: str, text: str, *, block_key: str = "answer") -> dict:
    return presentation_v2.text_block_complete(
        conversation_id=conversation_id,
        run_id=run_id,
        block_key=block_key,
        text=text,
    )


@pytest.fixture(autouse=True)
def _disable_runtime_fanout(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.conversation_event_fanout.publish_runtime_notification_sync",
        lambda *_args, **_kwargs: None,
    )


@pytest.mark.asyncio
async def test_stream_harness_events_resumes_from_durable_sequence_cursor(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS", 0.01)

    conversation = create_conversation(7, title="resume-sequence")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
        },
        touch_updated_at=False,
    )
    first = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        data=_presentation_delta(conversation["id"], "run-1", "first"),
        lane="user",
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data=build_turn_completed_payload(
            conversation_id=conversation["id"],
            run_id="run-1",
            status="failed",
            runtime_snapshot={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=build_turn_error("TestFailure", "failed"),
        ),
        lane="user",
    )

    response = await harness_endpoint.stream_harness_events(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
        after_sequence=int(first["sequence"]),
    )

    chunks = [chunk async for chunk in response.body_iterator]
    joined = "".join(chunks)

    assert '"type": "run_preparing"' in joined
    assert '"type": "turn_completed"' in joined
    assert '"delta": "first"' not in joined


@pytest.mark.asyncio
async def test_live_streaming_response_resumes_post_stream_from_sequence_cursor(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS", 0.01)

    conversation = create_conversation(7, title="post-resume-sequence")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
        },
        touch_updated_at=False,
    )
    first = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data=build_turn_completed_payload(
            conversation_id=conversation["id"],
            run_id="run-1",
            status="failed",
            runtime_snapshot={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=build_turn_error("TestFailure", "old balance error"),
        ),
        lane="user",
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-2",
        event_type="presentation.block.complete",
        data=_presentation_complete(conversation["id"], "run-2", "new output", block_key="block-1"),
        lane="user",
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-2",
        event_type="turn_completed",
        data=build_turn_completed_payload(
            conversation_id=conversation["id"],
            run_id="run-2",
            status="failed",
            runtime_snapshot={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=build_turn_error("TestFailure", "failed"),
        ),
        lane="user",
    )

    response = harness_endpoint._build_live_streaming_response(
        7,
        conversation["id"],
        after_sequence=int(first["sequence"]),
    )

    chunks = [chunk async for chunk in response.body_iterator]
    joined = "".join(chunks)

    assert "old balance error" not in joined
    assert "new output" in joined


@pytest.mark.asyncio
async def test_stream_harness_events_emits_selection_resolved_as_conversation_patch(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="selection-meta")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
        },
        touch_updated_at=False,
    )
    append_event(
        7,
        conversation["id"],
        run_id="preflight",
        event_type="selection_resolved",
        data={
            "skill_id": "open-design-landing",
            "resolved_skill_id": "open-design-landing",
            "skill_selection_mode": "auto",
            "skill_resolution_source": "ai_resolved",
            "last_skill_decision_confidence": 0.95,
        },
        lane="user",
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data=build_turn_completed_payload(
            conversation_id=conversation["id"],
            run_id="run-1",
            status="failed",
            runtime_snapshot={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            error=build_turn_error("TestFailure", "done"),
        ),
        lane="user",
    )

    response = await harness_endpoint.stream_harness_events(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
        after_sequence=0,
    )

    chunks = [chunk async for chunk in response.body_iterator]
    joined = "".join(chunks)

    assert '"type": "presentation.conversation.patch"' in joined
    assert '"skill_id": "open-design-landing"' in joined
    assert '"source_sequence": 1' in joined


@pytest.mark.asyncio
async def test_stream_harness_events_replays_pending_interaction_from_durable_log(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS", 0.01)

    conversation = create_conversation(7, title="pending-interaction")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "kind": "ask_user",
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )
    interaction_form_op = presentation_v2.interaction_form(
        conversation_id=conversation["id"],
        run_id="run-1",
        interaction={
            "request_id": "req-1",
            "kind": "ask_user",
            "question": "Need approval",
            "status": "pending",
        },
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type=str(interaction_form_op["type"]),
        data=interaction_form_op,
        lane="user",
    )

    response = await harness_endpoint.stream_harness_events(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
        after_sequence=0,
    )

    chunks = [chunk async for chunk in response.body_iterator]
    joined = "".join(chunks)

    assert '"type": "run_preparing"' in joined
    assert '"type": "presentation.block.upsert"' in joined
    assert '"ui_kind": "interaction_form"' in joined
    assert '"request_id": "req-1"' in joined
    stored = get_conversation(7, conversation["id"])
    assert stored is not None
    assert stored["runtime_status"] == "waiting_input"


@pytest.mark.asyncio
async def test_stream_harness_events_open_path_does_not_reconcile_running_conversation(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="observe-open-read-only")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )

    response = await harness_endpoint.stream_harness_events(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
        after_sequence=0,
    )

    body_iterator = response.body_iterator
    first_chunk = await body_iterator.__anext__()
    assert '"type": "run_preparing"' in first_chunk
    await body_iterator.aclose()


@pytest.mark.asyncio
async def test_stream_live_events_polling_path_does_not_reconcile_running_conversation(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS", 0.01)

    conversation = create_conversation(7, title="observe-poll-read-only")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )

    generator = harness_endpoint._stream_live_events(7, conversation["id"])
    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk
    await generator.aclose()


@pytest.mark.asyncio
async def test_append_event_keeps_durable_event_when_fanout_publish_fails(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="fanout-failure")

    def _boom(_record):
        raise RuntimeError("redis publish failed")

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        _boom,
    )

    record = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        data=_presentation_delta(conversation["id"], "run-1", "still durable"),
        lane="user",
    )

    assert record["sequence"] == 1
    assert record["type"] == "presentation.block.delta"
    assert record["payload"]["payload"]["delta"] == "still durable"


@pytest.mark.asyncio
async def test_stream_live_events_wakes_from_redis_fanout_notification(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.api.v1.endpoints.harness._STREAM_STATUS_POLL_SECONDS", 60)
    monkeypatch.setattr(settings, "REDIS_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "REDIS_REQUIRED", False, raising=False)
    monkeypatch.setattr(settings, "REDIS_CONNECT_TIMEOUT_SECONDS", 0.01, raising=False)
    monkeypatch.setattr(settings, "REDIS_OPERATION_TIMEOUT_SECONDS", 0.01, raising=False)
    reset_redis_coordinator_for_tests()

    conversation = create_conversation(7, title="redis-fanout-wakeup")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    generator = harness_endpoint._stream_live_events(7, conversation["id"], after_sequence=0)
    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk

    record = append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        payload=_presentation_delta(conversation["id"], "run-1", "from durable log"),
        lane="user",
    )
    task = publish_event_notification_sync(record)
    if task is not None:
        await task

    next_chunk = await asyncio.wait_for(generator.__anext__(), timeout=1)
    assert '"delta": "from durable log"' in next_chunk
    await generator.aclose()
    reset_redis_coordinator_for_tests()


@pytest.mark.asyncio
@pytest.mark.parametrize("lane", ["internal", "projection", "system"])
async def test_stream_session_ignores_non_user_redis_fanout_lanes(monkeypatch, tmp_path, lane):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title=f"ignore-{lane}-fanout")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    callbacks: list = []
    load_calls: list[int] = []

    async def fake_subscribe_event_notifications(_user_id, _conversation_id, callback):
        callbacks.append(callback)
        return lambda: None

    async def fake_subscribe_runtime_notifications(*_args, **_kwargs):
        return lambda: None

    def fake_load_events(*_args, **_kwargs):
        load_calls.append(1)
        return []

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.conversation_stream_session.subscribe_event_notifications",
        fake_subscribe_event_notifications,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.conversation_stream_session.subscribe_runtime_notifications",
        fake_subscribe_runtime_notifications,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.conversation_events.load_conversation_events",
        fake_load_events,
    )

    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        status_poll_seconds=60,
    )
    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk
    assert callbacks

    next_chunk_task = asyncio.create_task(generator.__anext__())
    await asyncio.sleep(0)
    assert load_calls == [1]

    callbacks[0]({"metadata": {"lane": lane}})
    await asyncio.sleep(0.02)

    assert load_calls == [1]
    assert not next_chunk_task.done()
    next_chunk_task.cancel()
    await asyncio.gather(next_chunk_task, return_exceptions=True)
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_session_wakes_from_user_redis_fanout_lane(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="user-lane-fanout")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    callbacks: list = []
    events: list[dict] = []

    async def fake_subscribe_event_notifications(_user_id, _conversation_id, callback):
        callbacks.append(callback)
        return lambda: None

    async def fake_subscribe_runtime_notifications(*_args, **_kwargs):
        return lambda: None

    def fake_load_events(*_args, **_kwargs):
        return list(events)

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.conversation_stream_session.subscribe_event_notifications",
        fake_subscribe_event_notifications,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.conversation_stream_session.subscribe_runtime_notifications",
        fake_subscribe_runtime_notifications,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.conversation_events.load_conversation_events",
        fake_load_events,
    )

    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        status_poll_seconds=60,
    )
    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk
    assert callbacks

    next_chunk_task = asyncio.create_task(generator.__anext__())
    await asyncio.sleep(0)
    events.append(
        {
            "conversation_id": conversation["id"],
            "sequence": 1,
            "type": "presentation.block.delta",
            "event_type": "presentation.block.delta",
            "lane": "user",
            "payload": _presentation_delta(conversation["id"], "run-1", "from user lane"),
        }
    )
    callbacks[0]({"metadata": {"lane": "user"}})

    next_chunk = await asyncio.wait_for(next_chunk_task, timeout=1)
    assert "from user lane" in next_chunk
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_session_duplicate_notifications_do_not_duplicate_persisted_frames(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="duplicate-notifications")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    transient_queue: asyncio.Queue[dict] = asyncio.Queue()
    cleanup_calls: list[str] = []
    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        transient_queue=transient_queue,
        unsubscribe=lambda: cleanup_calls.append("local"),
        status_poll_seconds=60,
    )

    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk

    append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        payload=_presentation_delta(conversation["id"], "run-1", "emit once"),
        lane="user",
    )
    transient_queue.put_nowait({"lane": "user"})
    transient_queue.put_nowait({"lane": "user"})

    next_chunk = await asyncio.wait_for(generator.__anext__(), timeout=1)
    assert next_chunk.count("emit once") == 1

    await generator.aclose()
    assert cleanup_calls == ["local"]


@pytest.mark.asyncio
async def test_stream_session_polling_recovers_when_live_notifications_are_dropped(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="dropped-notification-poll")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        transient_queue=asyncio.Queue(),
        unsubscribe=lambda: None,
        status_poll_seconds=0.01,
        reconcile_interval_seconds=0.01,
    )

    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk

    append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.block.delta",
        payload=_presentation_delta(conversation["id"], "run-1", "poll fallback"),
        lane="user",
    )

    next_chunk = await asyncio.wait_for(generator.__anext__(), timeout=1)
    assert "poll fallback" in next_chunk
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_session_timeout_keepalive_does_not_poll_persisted_events(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="timeout-keepalive")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    load_calls: list[int] = []

    def fake_load_events(*_args, **_kwargs):
        load_calls.append(1)
        return []

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.conversation_events.load_conversation_events",
        fake_load_events,
    )
    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        transient_queue=asyncio.Queue(),
        unsubscribe=lambda: None,
        status_poll_seconds=0.01,
        reconcile_interval_seconds=60,
    )

    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk
    keepalive = await asyncio.wait_for(generator.__anext__(), timeout=1)

    assert keepalive == ": keepalive\n\n"
    assert len(load_calls) == 1
    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_session_misses_durable_event_until_reconcile_when_notifications_drop(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="missed-notification-delay")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
        },
        touch_updated_at=False,
    )
    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        transient_queue=asyncio.Queue(),
        unsubscribe=lambda: None,
        status_poll_seconds=0.01,
        reconcile_interval_seconds=60,
    )

    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk

    next_chunk_task = asyncio.create_task(generator.__anext__())
    await asyncio.sleep(0)

    append_conversation_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="current_outline_updated",
        payload={"outline": {"title": "durable plan already stored"}},
        lane="user",
    )

    next_chunk = await asyncio.wait_for(next_chunk_task, timeout=1)
    assert next_chunk == ": keepalive\n\n"
    assert "durable plan already stored" not in next_chunk
    await generator.aclose()


@pytest.mark.asyncio
async def test_run_preparing_payload_reports_actual_runtime_status_on_completed_conversation(monkeypatch, tmp_path):
    """Regression: run_preparing must not advertise runtime_status='running' on a completed run.

    The synthetic handshake event used to hardcode "running" in its payload.
    On a GET /stream subscription opened against an already-completed
    conversation (a race that happens during run-end transitions) the
    payload would lie about the runtime status. The client projection would
    then flip session.runStatus back to 'running', the server would close
    the stream because the actual runtime_status is not in RUNNING, and the
    client would reconnect — looping forever and showing "thinking" in the
    UI. Reading the true runtime_status before emitting the handshake
    prevents the lie at the source.
    """
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="completed-handshake")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "completed",
            "run_state": "completed",
            "turn_status": "completed",
        },
        touch_updated_at=False,
    )

    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=0,
        transient_queue=asyncio.Queue(),
        unsubscribe=lambda: None,
        status_poll_seconds=60,
        missing_turn_completed_reconcile_seconds=0.01,
    )

    first_chunk = await generator.__anext__()
    assert '"type": "run_preparing"' in first_chunk
    assert '"runtime_status": "completed"' in first_chunk
    assert '"runtime_status": "running"' not in first_chunk

    await generator.aclose()


@pytest.mark.asyncio
async def test_stream_cursor_after_waiting_input_turn_completed_closes_without_protocol_error(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="waiting-input-cursor-terminal")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "kind": "design_system_picker",
                "request_id": "design-system:req-1",
                "status": "pending",
            },
        },
        touch_updated_at=False,
    )
    terminal = append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data=build_turn_completed_payload(
            conversation_id=conversation["id"],
            run_id="run-1",
            status="waiting_input",
            runtime_snapshot={
                "runtime_status": "waiting_input",
                "run_state": "waiting_input",
                "turn_status": "waiting_input",
                "user_interaction": {
                    "kind": "design_system_picker",
                    "request_id": "design-system:req-1",
                    "status": "pending",
                },
            },
        ),
        lane="user",
    )

    generator = stream_conversation_events(
        7,
        conversation["id"],
        after_sequence=int(terminal["sequence"]),
        transient_queue=asyncio.Queue(),
        unsubscribe=lambda: None,
        status_poll_seconds=60,
        missing_turn_completed_reconcile_seconds=0.01,
    )

    chunks = [chunk async for chunk in generator]
    joined = "".join(chunks)

    assert '"type": "run_preparing"' in joined
    assert '"runtime_status": "waiting_input"' in joined
    assert '"type": "protocol_error"' not in joined
    assert '"missing_turn_completed"' not in joined
