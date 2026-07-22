from pathlib import Path

import json

from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2


def _publish_presentation_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    payload: dict,
) -> None:
    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event

    publish_user_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=str(payload["type"]),
        data=payload,
    )


def _publish_user_message(user_id: int, conversation_id: str, content: str, *, run_id: str = "run-1") -> None:
    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event

    publish_user_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type="user_message",
        data={"content": content},
    )


def test_conversation_message_store_round_trips_messages(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages

    conversation = create_conversation(7, title="Messages")
    # User-visible messages are projected from presentation events (direct
    # transcript writes are rejected by the protocol guard).
    _publish_user_message(7, conversation["id"], "hello")

    messages = load_messages(7, conversation["id"])

    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "hello"
    assert messages[0]["metadata"]["render_kind"] == "presentation_v2"


def test_first_user_message_promotes_default_conversation_title(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        create_conversation,
        get_conversation,
    )

    conversation = create_conversation(7, title="新会话")

    _publish_user_message(7, conversation["id"], "  生成一个五页的设计行业的PPT  ")

    updated = get_conversation(7, conversation["id"])
    assert updated is not None
    assert updated["title"] == "生成一个五页的设计行业的PPT"


def test_first_user_message_does_not_overwrite_custom_conversation_title(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        create_conversation,
        get_conversation,
    )

    conversation = create_conversation(7, title="用户自定义标题")

    _publish_user_message(7, conversation["id"], "新的首条输入")

    updated = get_conversation(7, conversation["id"])
    assert updated is not None
    assert updated["title"] == "用户自定义标题"


def test_indexed_message_getters_return_targeted_rows(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Indexed getters")
    cid = conversation["id"]

    user_msg = db_store.append_message_record(7, cid, {"id": "m-user", "role": "user", "content": "hi"})
    first_assistant = db_store.append_message_record(7, cid, {"id": "m-a1", "role": "assistant", "content": "first"})
    db_store.append_message_record(7, cid, {"id": "m-tool", "role": "tool", "content": "tool output"})
    last_assistant = db_store.append_message_record(7, cid, {"id": "m-a2", "role": "assistant", "content": "second"})

    assert db_store.get_message_record(7, cid, first_assistant["id"])["content"] == "first"
    assert db_store.get_message_record(7, cid, user_msg["id"])["role"] == "user"
    assert db_store.get_message_record(7, cid, "does-not-exist") is None

    latest = db_store.get_latest_assistant_message_record(7, cid)
    assert latest["id"] == last_assistant["id"]
    assert latest["content"] == "second"

    # Wrong user has no access to the conversation's rows.
    assert db_store.get_message_record(999, cid, first_assistant["id"]) is None
    assert db_store.get_latest_assistant_message_record(999, cid) is None


def test_append_message_record_increments_message_count(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Counter")
    cid = conversation["id"]

    assert db_store.message_count(7, cid) == 0
    db_store.append_message_record(7, cid, {"id": "m-1", "role": "user", "content": "a"})
    db_store.append_message_record(7, cid, {"id": "m-2", "role": "assistant", "content": "b"})
    db_store.append_message_record(7, cid, {"id": "m-3", "role": "tool", "content": "c"})

    assert db_store.message_count(7, cid) == 3


def test_presentation_snapshot_messages_follow_source_event_sequence(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Presentation order")
    cid = conversation["id"]
    metadata = {"protocol_version": 2, "render_kind": "presentation_v2"}

    db_store.append_message_record(
        7,
        cid,
        {
            "id": "assistant-summary",
            "role": "assistant",
            "content": "出图完成",
            "metadata": {**metadata, "message_key": "summary", "source_event_sequence": 20},
        },
    )
    db_store.append_message_record(
        7,
        cid,
        {
            "id": "media-card",
            "role": "assistant",
            "content": None,
            "metadata": {**metadata, "message_key": "media-card", "source_event_sequence": 10},
            "blocks": [
                {
                    "id": "media-card",
                    "kind": "content",
                    "order": 1,
                    "status": "completed",
                    "ui_kind": "tool_card",
                    "visible": True,
                    "user_visible": True,
                    "payload": {"title": "商品图"},
                }
            ],
        },
    )

    ui_page = db_store.read_presentation_snapshot_messages_page(7, cid, before_seq=None, limit=10)
    transcript_page = db_store.read_messages_page(7, cid, before_seq=None, limit=10)

    assert [message["id"] for message in ui_page["messages"]] == ["media-card", "assistant-summary"]
    assert transcript_page["messages"] == []


def test_presentation_snapshot_messages_prefer_stable_display_source_sequence(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Stable presentation order")
    cid = conversation["id"]
    metadata = {"protocol_version": 2, "render_kind": "presentation_v2"}

    db_store.append_message_record(
        7,
        cid,
        {
            "id": "assistant-summary",
            "role": "assistant",
            "content": "出图完成",
            "metadata": {**metadata, "message_key": "summary", "source_event_sequence": 35},
        },
    )
    db_store.append_message_record(
        7,
        cid,
        {
            "id": "media-card",
            "role": "assistant",
            "content": None,
            "metadata": {
                **metadata,
                "message_key": "media-card",
                "display_source_event_sequence": 25,
                "source_event_sequence": 40,
            },
            "blocks": [
                {
                    "id": "media-card",
                    "kind": "content",
                    "order": 1,
                    "status": "completed",
                    "ui_kind": "media_card",
                    "visible": True,
                    "user_visible": True,
                    "payload": {"tool_name": "generate_image", "status": "completed"},
                }
            ],
        },
    )

    ui_page = db_store.read_presentation_snapshot_messages_page(7, cid, before_seq=None, limit=10)

    assert [message["id"] for message in ui_page["messages"]] == ["media-card", "assistant-summary"]


def test_presentation_projection_keeps_render_card_display_anchor_on_completion(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.event_log import append_event
    from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Media display anchor")
    cid = conversation["id"]
    run_id = "run-media-anchor"
    media_message_key = "assistant-media"
    media_block_key = "media-card"

    append_event(
        7,
        cid,
        run_id=run_id,
        event_type="presentation.block.upsert",
        payload=presentation_v2.content_block_upsert(
            conversation_id=cid,
            run_id=run_id,
            message_key=media_message_key,
            block_key=media_block_key,
            ui_kind="media_card",
            status="processing",
            payload={"tool_name": "generate_image", "status": "processing"},
            order=1,
        ),
    )
    append_event(
        7,
        cid,
        run_id=run_id,
        event_type="presentation.block.complete",
        payload=presentation_v2.text_block_complete(
            conversation_id=cid,
            run_id=run_id,
            message_key="assistant-final",
            block_key="assistant-final-text",
            text="已生成一张图片。",
            order=0,
        ),
    )
    append_event(
        7,
        cid,
        run_id=run_id,
        event_type="presentation.block.complete",
        payload=presentation_v2.content_block_upsert(
            conversation_id=cid,
            run_id=run_id,
            message_key=media_message_key,
            block_key=media_block_key,
            ui_kind="media_card",
            status="completed",
            payload={"tool_name": "generate_image", "status": "completed"},
            order=1,
            complete=True,
        ),
    )

    ui_page = db_store.read_presentation_snapshot_messages_page(7, cid, before_seq=None, limit=10)
    messages = ui_page["messages"]
    media = next(message for message in messages if message["metadata"]["message_key"] == media_message_key)

    assert [message["metadata"]["message_key"] for message in messages] == [media_message_key, "assistant-final"]
    assert media["metadata"]["display_source_event_sequence"] == 1
    assert media["metadata"]["source_event_sequence"] == 3
    assert media["blocks"][0]["status"] == "completed"


def test_successful_tool_message_count_ignores_failed_ask_user_attempts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Ask budget")
    cid = conversation["id"]

    db_store.append_message_record(
        7,
        cid,
        {
            "id": "m-assistant",
            "role": "assistant",
            "tool_calls": [
                {"id": "call_failed", "type": "function", "function": {"name": "ask_user", "arguments": "{}"}},
                {"id": "call_success", "type": "function", "function": {"name": "ask_user", "arguments": "{}"}},
            ],
        },
    )
    db_store.append_message_record(
        7,
        cid,
        {
            "id": "m-tool-failed",
            "role": "tool",
            "tool_name": "ask_user",
            "tool_call_id": "call_failed",
            "content": json.dumps({"status": "failed", "output": "invalid parameters"}),
            "metadata": {"failure_kind": "invalid_parameters"},
        },
    )
    db_store.append_message_record(
        7,
        cid,
        {
            "id": "m-tool-success",
            "role": "tool",
            "tool_name": "ask_user",
            "tool_call_id": "call_success",
            "content": json.dumps({"status": "completed", "output": "Question title"}),
        },
    )

    assert db_store.count_assistant_tool_calls_by_name(7, cid, "ask_user") == 2
    assert db_store.count_successful_tool_messages_by_name(7, cid, "ask_user") == 1


def test_get_latest_assistant_message_record_returns_none_without_assistant(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="No assistant yet")
    cid = conversation["id"]
    db_store.append_message_record(7, cid, {"id": "m-user", "role": "user", "content": "hi"})

    assert db_store.get_latest_assistant_message_record(7, cid) is None


def test_presentation_block_complete_is_projected_before_live_subscribers_observe_snapshot(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.event_log import subscribe_to_events
    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages

    conversation = create_conversation(7, title="Subscriber ordering")
    observed: dict[str, object] = {}

    unsubscribe = subscribe_to_events(
        7,
        conversation["id"],
        lambda _event: observed.setdefault("messages", load_messages(7, conversation["id"])),
    )
    try:
        _publish_presentation_event(
            7,
            conversation["id"],
            run_id="run-1",
            payload=presentation_v2.text_block_complete(
                conversation_id=conversation["id"],
                run_id="run-1",
                block_key="assistant-final-1",
                text="已发布的最终结果",
                ui_kind="assistant_final_answer",
                payload_extra={"message_kind": "final_answer"},
            ),
        )
    finally:
        unsubscribe()

    observed_messages = observed.get("messages")
    assert isinstance(observed_messages, list)
    assert observed_messages[0]["content"] == "已发布的最终结果"
    assert observed_messages[0]["metadata"]["protocol_version"] == 2
    assert observed_messages[0]["metadata"]["render_kind"] == "presentation_v2"
    assert observed_messages[0]["blocks"][0]["ui_kind"] == "assistant_final_answer"


def test_pending_interaction_event_projects_pending_interaction_block(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(7, title="Pending interaction")

    # The interaction form is projected from the presentation interaction_form
    # event emitted by the workflow (not the legacy `user_interaction_requested`).
    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.interaction_form(
            conversation_id=conversation["id"],
            run_id="run-1",
            interaction={
                "request_id": "quick-brief:conv-1:abc",
                "kind": "quick_brief",
                "question": "Quick brief",
                "schema": {
                    "title": "Quick brief",
                    "submit_label": "Continue",
                    "fields": [
                        {"id": "output", "label": "Output", "type": "text", "required": True},
                    ],
                },
                "status": "pending",
                "answers": None,
            },
        ),
    )

    messages = load_messages(7, conversation["id"])
    interaction_block = messages[0]["blocks"][0]
    assert interaction_block["ui_kind"] == "interaction_form"
    assert interaction_block["status"] == "pending"
    assert interaction_block["payload"]["status"] == "pending"


def test_subagent_events_project_v2_subagent_card(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(7, title="Subagent card")

    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.subagent_card(
            conversation_id=conversation["id"],
            run_id="run-1",
            payload={
                "task_id": "task-review-1",
                "label": "Quality review",
                "purpose": "Review the generated page",
                "status": "queued",
                "subagent_type": "QualityReview",
                "skill_id": "web",
                "task_spec": {"objective": "Check the UI before publishing"},
            },
            status="queued",
        ),
    )
    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.subagent_card(
            conversation_id=conversation["id"],
            run_id="run-1",
            payload={
                "task_id": "task-review-1",
                "label": "Quality review",
                "purpose": "Review the generated page",
                "status": "completed",
                "summary": "The review passed.",
                "subagent_type": "QualityReview",
                "result_ref": "sidechain/task-review-1/result.json",
            },
            status="completed",
            complete=True,
        ),
    )

    messages = load_messages(7, conversation["id"])
    assert len(messages) == 1
    assert messages[0]["metadata"]["protocol_version"] == 2
    assert messages[0]["metadata"]["render_kind"] == "presentation_v2"
    # Subagent cards are grouped into a stable per-subagent message keyed by
    # task id so each renders at its own time on the home timeline instead of
    # collapsing into the single run-level assistant message.
    assert messages[0]["metadata"]["message_key"].endswith(":subagent:task-review-1")
    block = messages[0]["blocks"][0]
    assert block["ui_kind"] == "subagent_card"
    assert block["task_id"] == "task-review-1"
    assert block["status"] == "completed"
    assert block["payload"]["status"] == "completed"
    assert block["payload"]["summary"] == "The review passed."
    assert block["payload"]["result_ref"] == "sidechain/task-review-1/result.json"


def test_shipped_critique_event_persists_design_jury_child(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(7, title="Design Jury child")

    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.subagent_card(
            conversation_id=conversation["id"],
            run_id="run-1",
            payload={
                "task_id": "task-jury-1",
                "label": "Design Jury",
                "purpose": "Review the artifact",
                "status": "queued",
                "subagent_type": "QualityReview",
            },
            status="queued",
        ),
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="critique.shipped",
        data={
            "critique_run_id": "review-1",
            "subagent_task_id": "task-jury-1",
            "status": "shipped",
            "round": 1,
            "scores": {"visual": 0.92},
            "composite": 0.92,
        },
    )

    messages = load_messages(7, conversation["id"])
    assert len(messages) == 1
    assert messages[0]["blocks"][0]["ui_kind"] == "subagent_card"
    children = messages[0]["blocks"][0].get("children")
    assert len(children) == 1
    assert children[0]["ui_kind"] == "design_jury_card"
    assert children[0]["status"] == "shipped"
    assert children[0]["payload"]["scores"] == {"visual": 0.92}


def test_subagent_block_projection_persists_children_without_outer_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(7, title="Subagent child block")
    context = {
        "task_id": "task-jury-1",
        "label": "Design Jury",
        "purpose": "Design Jury",
        "status": "running",
        "subagent_type": "QualityReview",
        "anchor_message_id": "plan-execution-approved:conv:plan:v1",
        "anchor_source": "plan_execution_approved",
    }

    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.subagent_card(
            conversation_id=conversation["id"],
            run_id="run-1",
            payload=context,
            status="running",
        ),
    )
    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.block_delta(
            conversation_id=conversation["id"],
            run_id="run-1",
            block_key="analyze-image-text-call-1",
            parent_block_key="subagent:task-jury-1",
            delta="Looks ",
        ),
    )
    _publish_presentation_event(
        7,
        conversation["id"],
        run_id="run-1",
        payload=presentation_v2.text_block_complete(
            conversation_id=conversation["id"],
            run_id="run-1",
            block_key="analyze-image-text-call-1",
            parent_block_key="subagent:task-jury-1",
            text="Looks good",
            payload_extra={
                "toolName": "analyze_image",
                "anchor_message_id": "plan-execution-approved:conv:plan:v1",
                "anchor_source": "plan_execution_approved",
            },
        ),
    )

    messages = load_messages(7, conversation["id"])
    assert len(messages) == 1
    assert messages[0]["metadata"]["protocol_version"] == 2
    assert messages[0]["metadata"]["render_kind"] == "presentation_v2"
    block = messages[0]["blocks"][0]
    assert block["ui_kind"] == "subagent_card"
    assert block["payload"]["status"] == "running"
    assert block["children"][0]["id"] == "analyze-image-text-call-1"
    assert block["children"][0]["payload"]["anchor_message_id"] == "plan-execution-approved:conv:plan:v1"
    assert block["children"][0]["payload"]["text"] == "Looks good"


def test_event_sink_legacy_subagent_event_no_longer_creates_v2_projection(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.event_sink import HarnessEventSink
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(7, title="Event sink projection")
    sink = HarnessEventSink(user_id=7, conversation_id=conversation["id"], run_id="run-1")

    sink.emit(
        "subagent_created",
        data={
            "task_id": "task-sink-1",
            "label": "Research helper",
            "purpose": "Collect supporting facts",
            "status": "queued",
        },
        artifact_id="task-sink-1",
    )

    messages = load_messages(7, conversation["id"])
    assert messages == []


def test_current_outline_projects_v2_plan_card_summary(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(7, title="Plan card")

    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="current_outline_updated",
        data={
            "change_source": "approval_requested",
            "outline": {
                "artifact_type": "html",
                "title": "Landing page",
                "summary": "Approved plan summary",
                "status": "planning_ready",
                "snapshot_status": "active",
                "plan_instance_id": "plan-1",
                "version": 1,
                "items": [
                    {"id": "item-1", "title": "Hero", "summary": "Build hero"},
                ],
            },
            "projection": {
                "status": "planning_ready",
                "snapshot_status": "active",
                "plan_instance_id": "plan-1",
            },
            "execution_state": {"status": "planning_ready", "steps": []},
        },
    )

    messages = load_messages(7, conversation["id"])
    assert len(messages) == 1
    # v2 contract: render cards carry their data in `payload`, not in the message
    # `content` field (which is reserved for text blocks). The frontend renders the
    # plan card from payload.summary; message content stays None for card-only
    # messages, consistently on both the live stream and a snapshot reload.
    assert messages[0]["content"] is None
    assert messages[0]["metadata"]["protocol_version"] == 2
    assert messages[0]["metadata"]["render_kind"] == "presentation_v2"
    assert messages[0]["blocks"][0]["ui_kind"] == "user_plan_card"
    assert messages[0]["blocks"][0]["payload"]["summary"] == "Approved plan summary"


def test_internal_recovery_prompt_skips_default_trace_and_visible_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation
    from app.services.agent_harness.workspace.conversation.conversation_message_store import load_messages
    from app.services.agent_harness.runtime.eventing.persistence import record_internal_recovery_prompt, trace_path

    conversation = create_conversation(7, title="Recovery trace")
    record_internal_recovery_prompt(
        7,
        conversation["id"],
        run_id="run-1",
        decision="retry",
        prompt={"role": "user", "content": "Continue executing without asking the user."},
        review={"root_cause_hint": "The tool failed.", "output_excerpt": "stderr: boom"},
        hint="Fix the specific issue using the smallest reliable action.",
    )

    messages = load_messages(7, conversation["id"])
    assert messages == []
    assert not trace_path(7, conversation["id"]).exists()


