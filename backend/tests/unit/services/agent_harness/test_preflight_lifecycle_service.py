from __future__ import annotations

import json

from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    get_conversation,
    load_messages,
)
from app.services.agent_harness.runtime.eventing.persistence import trace_path
from app.services.agent_harness.runtime.state.store_core import read_runtime_state

from app.services.agent_harness.workspace.conversation.preflight_lifecycle_service import (
    has_preflight_billing_key,
    mark_preflight_billing_key,
    persist_interaction_request,
    persist_interaction_submission,
    persist_skill_resolution,
)


def test_persist_skill_resolution_updates_skill_state_without_writing_message():
    user_id = 9301
    conversation = create_conversation(
        user_id,
        title="Preflight lifecycle",
        artifact_mode="slides",
        skill_selection_mode="auto",
    )
    conversation_id = str(conversation["id"])

    persist_skill_resolution(
        user_id=user_id,
        conversation_id=conversation_id,
        previous_skill_id=None,
        next_skill_id="html-ppt",
        artifact_mode="slides",
        model_preferences={"model": "test"},
        reason="slides requested",
        confidence=0.91,
        language="zh",
    )
    persist_skill_resolution(
        user_id=user_id,
        conversation_id=conversation_id,
        previous_skill_id=None,
        next_skill_id="html-ppt",
        artifact_mode="slides",
        model_preferences={"model": "test"},
        reason="slides requested",
        confidence=0.91,
        language="zh",
    )

    stored = get_conversation(user_id, conversation_id) or {}
    assert stored["skill_id"] == "html-ppt"
    assert stored["resolved_skill_id"] == "html-ppt"
    assert stored["skill_resolution_source"] == "auto"
    assert stored["last_skill_decision_reason"] == "slides requested"
    assert stored["last_skill_decision_confidence"] == 0.91
    assert stored["artifact_mode"] == "slides"
    assert stored["model_preferences"] == {"model": "test"}

    assert load_messages(user_id, conversation_id) == []


def test_persist_skill_resolution_recomputes_phase_for_plan_first_modes():
    user_id = 9305
    conversation = create_conversation(
        user_id,
        title="Spreadsheet preflight lifecycle",
        artifact_mode="web",
        skill_selection_mode="auto",
    )
    conversation_id = str(conversation["id"])

    persist_skill_resolution(
        user_id=user_id,
        conversation_id=conversation_id,
        previous_skill_id=None,
        next_skill_id="xlsx",
        artifact_mode="spreadsheet",
        model_preferences={"model": "test"},
        reason="spreadsheet requested",
        confidence=0.95,
        language="zh",
    )

    stored = get_conversation(user_id, conversation_id) or {}
    assert stored["skill_id"] == "xlsx"
    assert stored["resolved_skill_id"] == "xlsx"
    assert stored["artifact_mode"] == "spreadsheet"
    assert stored["phase"] == "planning"

    assert not trace_path(user_id, conversation_id).exists()


def test_persist_interaction_request_updates_runtime_without_writing_messages():
    user_id = 9302
    conversation = create_conversation(user_id, title="Quick brief", artifact_mode="ppt")
    conversation_id = str(conversation["id"])
    request_id = f"quick-brief:{conversation_id}"

    interaction = {
        "request_id": request_id,
        "kind": "quick_brief",
        "question": "Design industry PPT quick brief",
        "schema": {"title": "Quick brief", "fields": []},
        "status": "pending",
    }

    persist_interaction_request(
        user_id=user_id,
        conversation_id=conversation_id,
        interaction=interaction,
        run_state="briefing",
    )
    persist_interaction_request(
        user_id=user_id,
        conversation_id=conversation_id,
        interaction=interaction,
        run_state="briefing",
    )

    assert load_messages(user_id, conversation_id) == []

    runtime = read_runtime_state(user_id, conversation_id)
    assert runtime["runtime_status"] == "waiting_input"
    assert runtime["turn_status"] == "waiting_input"
    assert runtime["run_state"] == "briefing"
    assert runtime["user_interaction"]["request_id"] == request_id


def test_persist_structured_interaction_submission_updates_runtime_without_writing_messages():
    user_id = 9303
    conversation = create_conversation(user_id, title="Quick brief", artifact_mode="ppt")
    conversation_id = str(conversation["id"])
    request_id = f"quick-brief:{conversation_id}"

    persist_interaction_request(
        user_id=user_id,
        conversation_id=conversation_id,
        interaction={
            "request_id": request_id,
            "kind": "quick_brief",
            "question": "Quick brief",
            "schema": {"title": "Quick brief", "fields": []},
            "status": "pending",
        },
        run_state="briefing",
    )

    answers = {"presentation_topic": "2026 design trends"}
    persist_interaction_submission(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        kind="quick_brief",
        answer="submitted",
        display_label="已提交快速简报",
        answers=answers,
    )
    persist_interaction_submission(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        kind="quick_brief",
        answer="submitted",
        display_label="已提交快速简报",
        answers=answers,
    )

    assert load_messages(user_id, conversation_id) == []

    runtime = read_runtime_state(user_id, conversation_id)
    assert runtime.get("user_interaction") is None
    assert runtime["runtime_status"] == "running"


def test_persist_structured_interaction_submission_does_not_update_legacy_cards():
    user_id = 9307
    conversation = create_conversation(user_id, title="Legacy interaction card", artifact_mode="ppt")
    conversation_id = str(conversation["id"])
    request_id = f"legacy-ask-user:{conversation_id}"

    persist_interaction_request(
        user_id=user_id,
        conversation_id=conversation_id,
        interaction={
            "request_id": request_id,
            "kind": "ask_user",
            "question": "补充品牌信息",
            "schema": {"title": "补充品牌信息", "fields": []},
            "status": "pending",
        },
        run_state="executing",
    )
    answers = {"brand_stage": "0-1 新建品牌"}
    persist_interaction_submission(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        kind="ask_user",
        answer="0-1 新建品牌",
        display_label="0-1 新建品牌",
        answers=answers,
    )

    assert load_messages(user_id, conversation_id) == []
    runtime = read_runtime_state(user_id, conversation_id)
    assert runtime.get("user_interaction") is None
    assert runtime["runtime_status"] == "running"


def test_persist_freeform_ask_user_submission_updates_runtime_without_writing_messages():
    user_id = 9306
    conversation = create_conversation(user_id, title="Ask user", artifact_mode="ppt")
    conversation_id = str(conversation["id"])
    request_id = "functions.ask_user:9306"

    persist_interaction_request(
        user_id=user_id,
        conversation_id=conversation_id,
        interaction={
            "request_id": request_id,
            "tool_call_id": request_id,
            "kind": "ask_user",
            "question": "继续吗？",
            "schema": {"title": "继续吗？", "fields": []},
            "status": "pending",
        },
        run_state="executing",
    )

    persist_interaction_submission(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        kind="ask_user",
        answer="继续执行",
        display_label="继续执行",
        answers={"answer": "继续执行"},
    )
    persist_interaction_submission(
        user_id=user_id,
        conversation_id=conversation_id,
        request_id=request_id,
        kind="ask_user",
        answer="继续执行",
        display_label="继续执行",
        answers={"answer": "继续执行"},
    )

    assert load_messages(user_id, conversation_id) == []
    runtime = read_runtime_state(user_id, conversation_id)
    assert runtime.get("user_interaction") is None
    assert runtime["runtime_status"] == "running"


def test_preflight_billing_ledger_survives_message_replay():
    user_id = 9304
    conversation = create_conversation(user_id, title="Billing ledger", artifact_mode="ppt")
    conversation_id = str(conversation["id"])
    key = f"quick_brief:{conversation_id}:request-1"

    assert has_preflight_billing_key(user_id, conversation_id, key) is False

    mark_preflight_billing_key(
        user_id,
        conversation_id,
        key,
        detail={"request_id": "request-1"},
    )
    mark_preflight_billing_key(
        user_id,
        conversation_id,
        key,
        detail={"request_id": "request-1"},
    )

    assert has_preflight_billing_key(user_id, conversation_id, key) is True
