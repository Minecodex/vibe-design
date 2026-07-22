"""B2 reproduction: does the presentation-v2 projection produce duplicate
content rows in ``harness_messages``?

These drive the *real* persistence pipeline (``create_conversation`` +
``append_event`` -> ``project_committed_event`` -> ``reconcile_projection``)
plus the legacy direct-append path (``session_service.append_message``) so we
can observe whether the same assistant text ends up duplicated across rows.

Run:
    cd backend && python -m pytest \
      tests/unit/services/agent_harness/runtime/eventing/test_projection_dedup.py -q
"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.agent_harness.runtime.eventing.event_log import append_event
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
    create_conversation,
)
from app.services.agent_harness.workspace.session_v2 import service as session_service
from app.services.agent_harness.workspace.session_v2.service import normalize_message_id


@pytest.fixture(autouse=True)
def _workspace_root(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    # Projection fanout to SSE subscribers is irrelevant for persistence assertions.
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.eventing.event_log.publish_event_notification_sync",
        lambda _record: None,
    )
    yield


def _emit_presentation(user_id: int, conversation_id: str, run_id: str, op_payload: dict[str, Any]) -> None:
    append_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=str(op_payload["type"]),
        lane="user",
        data=op_payload,
    )


def _non_empty_contents(messages: list[dict[str, Any]]) -> list[str]:
    return [str(m.get("content") or "") for m in messages if str(m.get("content") or "").strip()]


def test_assistant_stream_does_not_duplicate_content_rows():
    """Mirror handlers `_ensure_stream_message_started`: the legacy path writes an
    agent_context (ui_visible=False) assistant row, and the presentation path
    projects the same assistant text under the SAME message_key. Assert this does
    not yield two rows carrying identical visible content."""
    user_id = 7
    conv = create_conversation(user_id, title="dup-stream", runtime_profile="home")
    conversation_id = conv["id"]
    run_id = "run-dup-1"
    message_id = normalize_message_id(f"run:{run_id}:message:assistant:1")
    block_id = f"run:{run_id}:model:1:assistant-text"
    final_text = "Hello world from the assistant."

    # 1) Legacy/direct path: model-context assistant message (ui_visible=False).
    session_service.append_message(
        user_id,
        conversation_id,
        {
            "id": message_id,
            "role": "assistant",
            "content": final_text,
            "streaming": False,
            "metadata": {
                "message_kind": "agent_context",
                "model_visible": True,
                "ui_visible": False,
                "run_id": run_id,
            },
        },
    )

    # 2) Presentation path: same assistant text streamed under the same message_key.
    _emit_presentation(
        user_id,
        conversation_id,
        run_id,
        presentation_v2.text_block_start(
            conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id
        ),
    )
    _emit_presentation(
        user_id,
        conversation_id,
        run_id,
        presentation_v2.block_delta(
            conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id, delta=final_text
        ),
    )
    _emit_presentation(
        user_id,
        conversation_id,
        run_id,
        presentation_v2.text_block_complete(
            conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id, text=final_text
        ),
    )

    messages = session_service.load_messages(user_id, conversation_id)
    ids = [m["id"] for m in messages]
    contents = _non_empty_contents(messages)

    # Diagnostic dump (visible with -s) to characterize what actually lands.
    print("\n[dup-stream] rows:")
    for m in messages:
        md = m.get("metadata") or {}
        print(f"  id={m['id']!r} content={str(m.get('content'))[:40]!r} ui_visible={md.get('ui_visible')} render_kind={md.get('render_kind')}")

    assert len(ids) == len(set(ids)), f"duplicate message_id rows: {ids}"
    assert contents.count(final_text) <= 1, f"assistant text duplicated across rows: {contents}"


def test_projected_assistant_text_clears_model_context_visibility_metadata():
    """When the presentation projection reuses a model-context assistant row, the
    resulting presentation snapshot must be UI replayable."""
    user_id = 7
    conv = create_conversation(user_id, title="projection-visible", runtime_profile="home")
    conversation_id = conv["id"]
    run_id = "run-visible-1"
    message_id = normalize_message_id(f"run:{run_id}:message:assistant:1")
    block_id = f"run:{run_id}:model:1:assistant-text"
    final_text = "Image generated. You can keep refining this result."

    session_service.append_message(
        user_id,
        conversation_id,
        {
            "id": message_id,
            "role": "assistant",
            "content": "",
            "streaming": False,
            "metadata": {
                "message_kind": "agent_context",
                "model_visible": True,
                "ui_visible": False,
                "run_id": run_id,
            },
        },
    )

    _emit_presentation(
        user_id,
        conversation_id,
        run_id,
        presentation_v2.text_block_complete(
            conversation_id=conversation_id,
            run_id=run_id,
            block_key=block_id,
            message_key=message_id,
            text=final_text,
        ),
    )

    messages = session_service.load_messages(user_id, conversation_id)
    assistant = next(message for message in messages if message["id"] == message_id)
    metadata = assistant.get("metadata") or {}

    assert assistant["content"] == final_text
    assert metadata["render_kind"] == "presentation_v2"
    assert "ui_visible" not in metadata
    assert "model_visible" not in metadata
    assert metadata.get("message_kind") != "agent_context"


def test_repeated_presentation_op_is_idempotent():
    """Re-appending the same logical text-complete op (same op identity) must not
    duplicate the block / message."""
    user_id = 7
    conv = create_conversation(user_id, title="dup-idem", runtime_profile="home")
    conversation_id = conv["id"]
    run_id = "run-idem-1"
    message_id = normalize_message_id(f"run:{run_id}:message:assistant:1")
    block_id = f"run:{run_id}:model:1:assistant-text"
    text = "Idempotent answer."

    for _ in range(3):
        _emit_presentation(
            user_id,
            conversation_id,
            run_id,
            presentation_v2.text_block_complete(
                conversation_id=conversation_id, run_id=run_id, block_key=block_id, message_key=message_id, text=text
            ),
        )

    messages = session_service.load_messages(user_id, conversation_id)
    assistant_rows = [m for m in messages if m.get("role") == "assistant"]
    print("\n[dup-idem] assistant rows:", [(m["id"], str(m.get("content"))[:30]) for m in assistant_rows])

    assert len(assistant_rows) == 1, f"expected one assistant row, got {len(assistant_rows)}"
    blocks = assistant_rows[0].get("blocks") or []
    text_blocks = [b for b in blocks if str(b.get("ui_kind") or b.get("uiKind") or "") == "text"]
    assert len(text_blocks) == 1, f"text block duplicated: {text_blocks}"


def test_direct_ui_visible_append_is_rejected():
    """Regression guard for the root cause of the historical double-write: a
    *UI-visible* message must never be persisted via the legacy direct-append
    path. Only model-context / internal / ui_visible=False rows may be written
    directly; everything else must be projected from presentation events.

    (This `ValueError` guard is why post-fix conversations stopped accumulating
    duplicate old-format + presentation_v2 twins.)"""
    user_id = 7
    conv = create_conversation(user_id, title="guard", runtime_profile="home")
    conversation_id = conv["id"]

    with pytest.raises(ValueError):
        session_service.append_message(
            user_id,
            conversation_id,
            {"id": "ui-msg-1", "role": "assistant", "content": "visible answer"},
        )

    # model-context / ui_visible=False rows are still allowed (model transcript).
    allowed = session_service.append_message(
        user_id,
        conversation_id,
        {
            "id": "ctx-msg-1",
            "role": "assistant",
            "content": "model only",
            "metadata": {"message_kind": "agent_context", "model_visible": True, "ui_visible": False},
        },
    )
    assert allowed["id"] == "ctx-msg-1"
