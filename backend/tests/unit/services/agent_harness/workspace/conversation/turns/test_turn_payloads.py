from __future__ import annotations

from app.services.agent_harness.workspace.conversation.turns.message_turn import prepare_message_run_payload
from app.services.agent_harness.workspace.conversation.turns.plan_turn import prepare_revise_plan_payload
from app.services.agent_harness.workspace.conversation.turns.turn_preparation import build_turn_idempotency_key


def test_message_turn_payload_is_json_only_and_versioned():
    payload = prepare_message_run_payload(
        content="build it",
        attachments=[],
        base_file_versions=[],
        hidden_user_context="",
        user_message_metadata={"skill_id": "web"},
        language="zh",
        web_search_enabled=True,
        model_preferences={"model": "x"},
        effective_artifact_mode="web",
        turn_route={"activity": "executing"},
        skill_selection={"mode": "auto"},
        canvas={"references": []},
    )

    assert payload["payload_version"] == 1
    assert payload["content"] == "build it"
    assert payload["message_metadata"] == {"skill_id": "web"}
    assert payload["activity"] == "executing"


def test_revise_plan_payload_does_not_capture_conversation_object():
    conversation = {"web_search_enabled": False, "model_preferences": {"model": "x"}}

    payload = prepare_revise_plan_payload(
        conversation=conversation,
        instruction="make copy shorter",
        language="en",
        turn_route={"activity": "revising"},
    )

    assert payload == {
        "payload_version": 1,
        "instruction": "make copy shorter",
        "language": "en",
        "web_search_enabled": False,
        "model_preferences": {"model": "x"},
        "turn_route": {"activity": "revising"},
    }


def test_turn_idempotency_key_is_bounded_and_stable_for_long_payloads():
    payload = {"content": "x" * 1000, "attachments": [{"id": "a", "url": "u" * 500}]}

    first = build_turn_idempotency_key("message", "conv-1", payload)
    second = build_turn_idempotency_key("message", "conv-1", {"attachments": payload["attachments"], "content": "x" * 1000})

    assert first == second
    assert first.startswith("message:")
    assert len(first) <= 255


def test_turn_idempotency_key_distinguishes_attachment_identity():
    first = build_turn_idempotency_key("message", "conv-1", "same text", [{"id": "file-a"}])
    second = build_turn_idempotency_key("message", "conv-1", "same text", [{"id": "file-b"}])

    assert first != second
