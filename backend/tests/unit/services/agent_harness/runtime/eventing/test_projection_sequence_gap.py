"""B4: a hole in the committed event sequence must not permanently stall the
presentation projection.

A gap can arise from a deleted/never-written sequence number (sequence is
assigned as ``max(sequence)+1`` with a unique constraint + retry, so concurrent
appends never leave a *transient* hole — a hole is therefore permanent). The
projection must skip forward over such a hole instead of refusing to advance.

Run:
    cd backend && python -m pytest \
      tests/unit/services/agent_harness/runtime/eventing/test_projection_sequence_gap.py -q
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import ConversationEvent
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.projection_store import (
    get_projection_state,
    reconcile_projection,
)
from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
from app.services.agent_harness.workspace.session_v2 import service as session_service


@pytest.fixture(autouse=True)
def _workspace_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    yield


def _insert_text_event(conversation_id: str, user_id: int, sequence: int, *, block_key: str, text: str) -> None:
    op = presentation_v2.text_block_complete(
        conversation_id=conversation_id,
        run_id="run-1",
        block_key=block_key,
        message_key="assistant:run-1",
        text=text,
    )
    with harness_sync_session_scope() as session:
        session.add(
            ConversationEvent(
                conversation_id=conversation_id,
                user_id=int(user_id),
                sequence=sequence,
                run_id="run-1",
                event_type=str(op["type"]),
                lane="user",
                payload_json=op,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )


def test_reconcile_skips_a_permanent_sequence_gap():
    user_id = 7
    conv = create_conversation(user_id, title="gap", runtime_profile="home")
    conversation_id = conv["id"]

    # Sequences 1 and 3 exist; sequence 2 is permanently missing (a hole).
    _insert_text_event(conversation_id, user_id, 1, block_key="blk-a", text="first")
    _insert_text_event(conversation_id, user_id, 3, block_key="blk-b", text="third")

    reconcile_projection(user_id, conversation_id)

    state = get_projection_state(user_id, conversation_id)
    assert state["applied_event_sequence"] == 3, f"projection stalled at the gap: {state}"

    messages = session_service.load_messages(user_id, conversation_id)
    assistant = next((m for m in messages if m.get("role") == "assistant"), None)
    assert assistant is not None, "assistant message was never projected"
    block_keys = {
        str(b.get("block_key") or b.get("id") or "")
        for b in (assistant.get("blocks") or [])
    }
    assert {"blk-a", "blk-b"} <= block_keys, f"event after the gap was not applied: {block_keys}"
