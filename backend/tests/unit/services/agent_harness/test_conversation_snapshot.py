from pathlib import Path

from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, read_messages_page
from app.services.agent_harness.workspace.conversation.conversation_snapshot import (
    build_conversation_detail_snapshot,
)
from app.services.agent_harness.workspace.session_v2 import service as session_service
from app.services.agent_harness.workspace.session_v2.db_store import append_message_record
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta
from app.services.agent_harness.runtime.state.runtime_projection_store import (
    persist_outline_runtime_state,
    persist_runtime_state,
    set_runtime_projection,
)
from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
from app.services.agent_harness.runtime.eventing.event_log import append_event


def test_detail_snapshot_degrades_active_run_state_on_pool_timeout(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Active state timeout")

    from app.services.agent_harness.workspace.session_v2 import db_store

    db_store.invalidate_active_run_state_cache(conversation["id"])
    monkeypatch.setattr(
        db_store,
        "_active_run_state_from_db",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SQLAlchemyTimeoutError("pool timeout")),
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot["_active_run_state_degraded"] is True
    assert snapshot["_active_run_state_source"] == "empty_timeout"


def test_detail_snapshot_restores_rich_messages_and_snapshot_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Snapshot detail", skill_id="pptx")
    outline = {
        "artifact_type": "ppt",
        "title": "设计行业洞察",
        "summary": "四页演示文稿",
        "status": "planning_ready",
        "progress_message": "等待确认PPT大纲",
        "items": [
            {
                "id": "slide-1",
                "title": "封面",
                "summary": "展示主题与定位。",
                "order": 1,
                "status": "pending",
            },
        ],
        "constraints": [],
        "style_notes": [],
    }
    persist_outline_runtime_state(
        7,
        conversation["id"],
        current_outline=outline,
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="current_outline_updated",
        data={
            "outline": outline,
            "projection": outline,
            "execution_state": None,
            "change_source": "initial_plan",
        },
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="execution_progress_updated",
        data={
            "message": "等待确认PPT大纲",
            "completed_message": None,
            "status": "waiting_review",
        },
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["user_plan"]["title"] == "设计行业洞察"
    assert snapshot["user_progress"]["message"] == "等待确认PPT大纲"
    assert len(snapshot["messages"]) >= 2
    assert any(
        str((message.get("metadata") or {}).get("render_key") or "").startswith("home-user-plan:")
        and isinstance(message.get("blocks"), list)
        for message in snapshot["messages"]
    )


def test_detail_snapshot_exposes_latest_event_sequence_cursor(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Snapshot event cursor")
    append_event(
        7,
        conversation["id"],
        run_id="run-old",
        event_type="turn_completed",
        data={"status": "failed", "error": {"summary": "old balance error"}},
        lane="user",
    )
    latest = append_event(
        7,
        conversation["id"],
        run_id="run-new",
        event_type="turn_completed",
        data={"conversation_id": conversation["id"], "status": "completed"},
        lane="user",
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["projection"]["event_last_sequence"] == latest["sequence"]


def test_detail_snapshot_returns_design_jury_card_messages(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Design Jury card")
    append_message_record(
        7,
        conversation["id"],
        {
            "id": "critique-card-message",
            "role": "assistant",
            "content": None,
            "metadata": {
                "render_key": "critique-card:critique-1:1",
                "render_only": True,
                "message_kind": "design_jury_card",
                "critique_run_id": "critique-1",
            },
            "blocks": [
                {
                    "id": "critique:critique-1:round:1",
                    "kind": "content",
                    "order": 0,
                    "status": "completed",
                    "ui_kind": "design_jury_card",
                    "visible": True,
                    "user_visible": True,
                    "payload": {
                        "critique_run_id": "critique-1",
                        "status": "shipped",
                        "round": 1,
                        "max_rounds": 3,
                        "score_scale": 10,
                        "scores": {"critic": 8.6},
                    },
                },
            ],
        },
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])
    ui_page = session_service.read_ui_messages_page(7, conversation["id"], before_seq=None, limit=10)

    assert snapshot is not None
    assert snapshot["protocol_version"] == 2
    assert snapshot["messages"] == []
    assert ui_page["messages"] == []


def test_detail_snapshot_returns_subagent_card_messages(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Subagent card")
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
                "status": "completed",
                "anchor_message_id": "plan-execution-approved:conv:plan:v1",
            },
            status="completed",
            complete=True,
        ),
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    card_messages = [
        message
        for message in snapshot["messages"]
        if any(
            block.get("ui_kind") == "subagent_card"
            for block in (message.get("blocks") or [])
            if isinstance(block, dict)
        )
    ]
    assert len(card_messages) == 1
    assert card_messages[0]["blocks"][0]["ui_kind"] == "subagent_card"
    assert card_messages[0]["blocks"][0]["payload"]["anchor_message_id"] == "plan-execution-approved:conv:plan:v1"


def test_detail_snapshot_restores_plan_preview_without_skill_id(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Snapshot detail", artifact_mode="slides")
    persist_outline_runtime_state(
        7,
        conversation["id"],
        current_outline={
            "artifact_type": "ppt",
            "title": "设计行业洞察",
            "summary": "四页演示文稿",
            "status": "planning_ready",
            "progress_message": "等待确认PPT大纲",
            "items": [
                {
                    "id": "slide-1",
                    "title": "封面",
                    "summary": "展示主题与定位。",
                    "order": 1,
                    "status": "pending",
                },
            ],
            "constraints": [],
            "style_notes": [],
        },
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["skill_id"] is None
    assert snapshot["outline_runtime"]["current_outline"]["title"] == "设计行业洞察"
    assert snapshot["user_plan"]["title"] == "设计行业洞察"


def test_detail_snapshot_hides_internal_model_prompts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Snapshot visibility")
    append_message_record(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "系统提醒：模型准备给最终回复。",
            "metadata": {"message_kind": "internal_model_prompt"},
        },
    )
    append_message_record(
        7,
        conversation["id"],
        {
            "role": "assistant",
            "content": "这是用户可见的回复。",
        },
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="presentation.message.upsert",
        lane="user",
        data=presentation_v2.message_upsert(
            conversation_id=conversation["id"],
            run_id="run-1",
            role="assistant",
            content="这是用户可见的回复。",
            message_key="assistant:visible",
        ),
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])
    transcript_page = read_messages_page(7, conversation["id"], before_seq=None, limit=10)

    assert snapshot is not None
    assert [message["content"] for message in snapshot["messages"]] == ["这是用户可见的回复。"]
    assert [message["content"] for message in transcript_page["messages"]] == ["这是用户可见的回复。"]


def test_message_paging_hides_internal_model_prompts_and_keeps_visible_order(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Paging visibility")
    append_message_record(7, conversation["id"], {"role": "user", "content": "first visible"})
    append_message_record(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "internal prompt",
            "metadata": {"message_kind": "internal_model_prompt"},
        },
    )
    append_message_record(7, conversation["id"], {"role": "assistant", "content": "second visible"})

    page = read_messages_page(7, conversation["id"], before_seq=None, limit=2)

    assert [message["content"] for message in page["messages"]] == ["first visible", "second visible"]
    assert page["messages_page"]["has_more"] is False


def test_homepage_message_paging_does_not_let_tool_execution_tail_hide_user_history(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Homepage paging")
    append_message_record(7, conversation["id"], {"role": "user", "content": "Build the landing page"})
    append_message_record(7, conversation["id"], {"role": "assistant", "content": "I will inspect the workspace."})
    for index in range(41):
        tool_call_id = f"call-{index}"
        append_message_record(
            7,
            conversation["id"],
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": tool_call_id, "name": "read_file", "arguments": {"path": "index.html"}}],
            },
        )
        append_message_record(
            7,
            conversation["id"],
            {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "tool_name": "read_file",
                "content": "file contents",
            },
        )

    transcript_page = read_messages_page(7, conversation["id"], before_seq=None, limit=80)
    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert len(transcript_page["messages"]) == 80
    assert {message["role"] for message in transcript_page["messages"]} == {"assistant", "tool"}
    assert snapshot is not None
    assert snapshot["messages"] == []
    assert session_service.read_ui_messages_page(7, conversation["id"], before_seq=None, limit=80)["messages"] == []


def test_detail_snapshot_preserves_structured_references(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Reference snapshot")
    references = [
        {
            "id": "canvas-mark:mark-1",
            "kind": "canvas_mark",
            "media_type": "image",
            "display_name": "葡萄",
            "tool_reference": "/api/v1/uploads/canvas/88/source.png",
            "source": {
                "type": "canvas_mark",
                "mark_id": "mark-1",
                "image_item_id": "img-local-1",
                "image_source": {
                    "type": "canvas_item",
                    "item_id": "img-local-1",
                },
            },
            "mark": {
                "id": "mark-1",
                "image_item_id": "img-local-1",
                "number": 1,
                "label": "葡萄",
                "position": {"x": 0.42, "y": 0.61},
            },
        }
    ]
    append_message_record(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "只调整 #[葡萄](canvas-mark:mark-1:image:img-local-1:x:0.42:y:0.61)",
            "metadata": {"references": references},
        },
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="user_message",
        lane="user",
        data={
            "id": "user-1",
            "role": "user",
            "content": "只调整 #[葡萄](canvas-mark:mark-1:image:img-local-1:x:0.42:y:0.61)",
            "attachments": [],
            "metadata": {"references": references},
        },
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])
    page = read_messages_page(7, conversation["id"], before_seq=None, limit=10)

    assert snapshot is not None
    assert snapshot["messages"][0]["metadata"]["references"] == references
    assert page["messages"][0]["metadata"]["references"] == references


def test_detail_snapshot_turn_completed_does_not_create_progress_card_without_existing_progress(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Completed progress", skill_id="xlsx")
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data={
            "message": "已完成",
            "status": "completed",
        },
        lane="user",
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["user_progress"] is None


def test_detail_snapshot_turn_completed_marks_existing_progress_completed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Completed progress", skill_id="xlsx")
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="execution_progress_updated",
        data={
            "message": "正在完善表格内容",
            "completed_message": None,
            "status": "in_progress",
        },
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data={
            "message": "已完成",
            "status": "completed",
        },
        lane="user",
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["user_progress"]["message"] == "已完成"
    assert snapshot["user_progress"]["completed_message"] is None
    assert snapshot["user_progress"]["status"] == "completed"


def test_detail_snapshot_turn_completed_creates_completed_progress_for_planned_conversation(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Completed progress", skill_id="xlsx")
    persist_outline_runtime_state(
        7,
        conversation["id"],
        current_outline={
            "artifact_type": "excel",
            "title": "出生人口数据表",
            "summary": "整理人口数据",
            "status": "in_progress",
            "items": [{"id": "item-1", "title": "出生人口数据", "summary": "整理 1949-2024 数据", "order": 1, "status": "completed"}],
            "constraints": [],
            "style_notes": [],
        },
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="turn_completed",
        data={
            "message": "已完成",
            "status": "completed",
        },
        lane="user",
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["user_progress"]["message"] == "已完成"
    assert snapshot["user_progress"]["status"] == "completed"


def test_detail_snapshot_reads_plan_review_and_runtime_from_v2_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Unified state", skill_id="pptx")
    persist_outline_runtime_state(
        7,
        conversation["id"],
        current_outline={
            "artifact_type": "ppt",
            "title": "统一状态",
            "summary": "从单一状态文件读取",
            "status": "in_progress",
            "progress_message": "正在生成",
            "items": [],
            "constraints": [],
            "style_notes": [],
        },
    )
    set_runtime_projection(
        7,
        conversation["id"],
        phase="executing",
        runtime_status="running",
        turn_status="running",
        run_state="waiting_tool",
        last_tool="publish_output",
    )
    (ensure_harness_meta(7, conversation["id"]) / "session_state.json").unlink(missing_ok=True)

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["outline_runtime"]["current_outline"]["title"] == "统一状态"
    assert snapshot["runtime_state"]["runtime_status"] == "running"
    assert snapshot["runtime_state"]["last_tool"] == "publish_output"


def test_detail_snapshot_derives_explicit_interaction_profile_from_runtime_profile(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    home_conversation = create_conversation(7, title="Home snapshot", runtime_profile="home")
    canvas_conversation = create_conversation(7, title="Canvas snapshot", runtime_profile="canvas", project_id=42)

    home_snapshot = build_conversation_detail_snapshot(7, home_conversation["id"])
    canvas_snapshot = build_conversation_detail_snapshot(7, canvas_conversation["id"])

    assert home_snapshot is not None
    assert canvas_snapshot is not None
    assert home_snapshot["interaction_profile"] == "home_blocking_preflight"
    assert canvas_snapshot["interaction_profile"] == "canvas_live_interaction"


def test_detail_snapshot_restores_ask_user_as_interaction_form_message(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Ask user snapshot", skill_id="pptx")
    pending_interaction = {
        "request_id": "functions.ask_user:0",
        "tool_call_id": "functions.ask_user:0",
        "kind": "ask_user",
        "question": "请选择执行方向",
        "content": "### 战略简报\n\n请先阅读这段背景说明。",
        "options": [
            {"label": "方向 A", "value": "a"},
            {"label": "方向 B", "value": "b"},
        ],
    }
    set_runtime_projection(
        7,
        conversation["id"],
        runtime_status="waiting_input",
        run_state="waiting_input",
        turn_status="waiting_input",
        user_interaction=pending_interaction,
    )
    interaction_op = presentation_v2.interaction_form(
        conversation_id=conversation["id"],
        run_id="run-ask-user",
        interaction=pending_interaction,
    )
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-ask-user",
        event_type=interaction_op["type"],
        data=interaction_op,
        tool_call_id="functions.ask_user:0",
        idempotency_key="run:run-ask-user:interaction-form",
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["runtime_state"]["user_interaction"]["tool_call_id"] == "functions.ask_user:0"
    interaction_messages = [
        message
        for message in snapshot["messages"]
        if any(
            str((block or {}).get("ui_kind") or (block or {}).get("uiKind") or "") == "interaction_form"
            for block in (message.get("blocks") or [])
            if isinstance(block, dict)
        )
    ]
    assert len(interaction_messages) == 1
    interaction_block = interaction_messages[0]["blocks"][0]
    assert interaction_block["render_key"] == "interaction:functions.ask_user:0"
    assert interaction_block["payload"]["request_id"] == "functions.ask_user:0"
    assert interaction_block["payload"]["question"] == "请选择执行方向"
    assert interaction_block["payload"]["content"] == "### 战略简报\n\n请先阅读这段背景说明。"
    assert snapshot["runtime_state"]["user_interaction"]["content"] == "### 战略简报\n\n请先阅读这段背景说明。"

