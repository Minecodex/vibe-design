from __future__ import annotations

import asyncio

import pytest

from app.services.agent_harness.runtime.eventing.conversation_stream_session import (
    stream_conversation_events,
)
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    build_turn_completed_payload,
)
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2


def _event(sequence: int, event_type: str, payload: dict | None = None) -> dict:
    payload = payload or {}
    return {
        "type": event_type,
        "event_type": event_type,
        "sequence": sequence,
        "lane": "user",
        "run_id": "run-1",
        "data": payload,
        "payload": payload,
    }


def _turn_completed(sequence: int, status: str = "completed") -> dict:
    return _event(
        sequence,
        "turn_completed",
        build_turn_completed_payload(
            conversation_id="conv-1",
            run_id="run-1",
            status=status,
            runtime_snapshot={"runtime_status": status, "run_state": status, "turn_status": status},
        ),
    )


async def _collect(chunks):
    return "".join([chunk async for chunk in chunks])


@pytest.fixture
def _no_subscription():
    queue: asyncio.Queue[dict] = asyncio.Queue()
    return queue, lambda: None


def _patch_runtime(monkeypatch, state: dict):
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_runtime_state",
        lambda _user_id, _conversation_id: state,
    )


def _patch_events(monkeypatch, events_by_call: list[list[dict]]):
    calls = {"count": 0}

    def _load(_user_id, _conversation_id, *, after_sequence=0, limit=None):
        index = min(calls["count"], len(events_by_call) - 1)
        calls["count"] += 1
        events = [
            event
            for event in events_by_call[index]
            if int(event.get("sequence") or 0) > int(after_sequence or 0)
        ]
        if limit is not None:
            return events[: max(1, int(limit))]
        return events

    monkeypatch.setattr(
        "app.services.agent_harness.runtime.conversation_events.load_conversation_events",
        _load,
    )
    return calls


@pytest.mark.asyncio
async def test_stream_with_persisted_turn_completed_closes_after_yielding_it(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "completed"})
    _patch_events(monkeypatch, [[_turn_completed(2)]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
    ))

    assert '"type": "run_preparing"' in joined
    assert '"type": "turn_completed"' in joined
    assert '"type": "protocol_error"' not in joined


@pytest.mark.asyncio
async def test_stream_runtime_completed_without_turn_completed_yields_protocol_error_only(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "completed"})
    _patch_events(monkeypatch, [[]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
        missing_turn_completed_reconcile_seconds=0,
    ))

    assert '"type": "protocol_error"' in joined
    assert '"reason": "missing_turn_completed"' in joined
    assert '"type": "turn_completed"' not in joined


@pytest.mark.asyncio
async def test_stream_runtime_completed_with_late_turn_completed_yields_terminal(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "completed"})
    calls = _patch_events(monkeypatch, [[], [_turn_completed(3)]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
        missing_turn_completed_reconcile_seconds=5,
    ))

    assert calls["count"] >= 2
    assert '"type": "turn_completed"' in joined
    assert '"type": "protocol_error"' not in joined


@pytest.mark.asyncio
async def test_stream_waiting_input_replays_interaction_then_turn_completed(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "waiting_input"})
    interaction_form_op = presentation_v2.interaction_form(
        conversation_id="conv-1",
        run_id="run-1",
        interaction={
            "request_id": "req-1",
            "kind": "ask_user",
            "question": "Continue?",
            "status": "waiting_input",
        },
    )
    _patch_events(monkeypatch, [[
        _event(1, str(interaction_form_op["type"]), interaction_form_op),
        _turn_completed(2, "waiting_input"),
    ]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
    ))

    assert joined.index('"type": "presentation.block.upsert"') < joined.index('"type": "turn_completed"')
    assert '"ui_kind": "interaction_form"' in joined
    assert '"status": "waiting_input"' in joined


@pytest.mark.asyncio
async def test_stream_after_sequence_skips_seen_events_and_closes_on_next_turn_completed(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "completed"})
    _patch_events(monkeypatch, [[
        _turn_completed(2),
    ]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        after_sequence=1,
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
    ))

    assert '"type": "turn_completed"' in joined


@pytest.mark.asyncio
async def test_stream_cursor_on_turn_completed_replays_terminal_control_event(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "completed"})
    _patch_events(monkeypatch, [[
        _turn_completed(2),
    ]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        after_sequence=2,
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
    ))

    assert '"type": "run_preparing"' in joined
    assert '"type": "turn_completed"' in joined
    assert '"type": "protocol_error"' not in joined


@pytest.mark.asyncio
async def test_stream_cursor_replays_presentation_ops_for_multi_op_event(monkeypatch, _no_subscription):
    queue, unsubscribe = _no_subscription
    _patch_runtime(monkeypatch, {"runtime_status": "completed"})
    _patch_events(monkeypatch, [[
        _event(5, "current_outline_updated", {
            "change_source": "approval_requested",
            "outline": {
                "plan_instance_id": "plan-1",
                "version": 1,
                "title": "Plan title",
                "status": "planning_ready",
                "items": [
                    {"id": "step-1", "title": "Step 1", "status": "pending"},
                ],
            },
        }),
    ]])

    joined = await _collect(stream_conversation_events(
        7,
        "conv-1",
        after_sequence=5,
        transient_queue=queue,
        unsubscribe=unsubscribe,
        status_poll_seconds=0.01,
        missing_turn_completed_reconcile_seconds=0,
    ))

    assert '"type": "presentation.conversation.patch"' in joined
    assert '"type": "presentation.block.upsert"' in joined
    assert '"type": "current_outline_updated"' not in joined
