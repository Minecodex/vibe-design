"""B3: characterize the reconcile hot path.

Every committed user event triggers ``project_committed_event`` ->
``reconcile_projection``. The concern was write amplification on streaming
deltas. Two facts bound it:

  * Deltas are coalesced *before* persistence (0.2s / 64 chars), so a typical
    answer is ~15-20 ``presentation.block.delta`` events, not one-per-token.
  * The projection keeps a durable cursor (``applied_event_sequence``), so each
    committed event is applied exactly once — reconcile does NOT re-replay the
    whole log on every append.

This test pins the second property (linear, not O(n^2)): applying M delta
events must invoke ``_apply_committed_event`` exactly M times in total.
"""

from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.eventing.event_log import append_event
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2 import projection_store
from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation


@pytest.fixture(autouse=True)
def _workspace_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        lambda _record: None,
    )
    yield


def test_streaming_deltas_apply_each_event_once(monkeypatch):
    user_id = 7
    conv = create_conversation(user_id, title="hotpath", runtime_profile="home")
    conversation_id = conv["id"]
    run_id = "run-1"
    message_id = "assistant:run-1"
    block_id = "answer"

    apply_calls = {"n": 0}
    real_apply = projection_store._apply_committed_event

    def _counting_apply(*args, **kwargs):
        apply_calls["n"] += 1
        return real_apply(*args, **kwargs)

    monkeypatch.setattr(projection_store, "_apply_committed_event", _counting_apply)

    delta_count = 15
    # start + N deltas + complete == delta_count + 2 user events
    append_event(
        user_id, conversation_id, run_id=run_id, event_type="presentation.block.upsert", lane="user",
        data=presentation_v2.text_block_start(conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id),
    )
    for i in range(delta_count):
        append_event(
            user_id, conversation_id, run_id=run_id, event_type="presentation.block.delta", lane="user",
            data=presentation_v2.block_delta(conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id, delta=f"tok{i} "),
        )
    append_event(
        user_id, conversation_id, run_id=run_id, event_type="presentation.block.complete", lane="user",
        data=presentation_v2.text_block_complete(conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id, text="done"),
    )

    total_events = delta_count + 2
    # Linear, not quadratic: each committed event is applied exactly once thanks
    # to the durable cursor. (A regression to re-replay would make this ~N^2/2.)
    assert apply_calls["n"] == total_events, (
        f"expected {total_events} applies (one per event), got {apply_calls['n']} "
        f"- reconcile may be re-replaying the log"
    )
