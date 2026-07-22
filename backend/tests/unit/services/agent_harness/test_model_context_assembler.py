from __future__ import annotations

import json

import pytest

from app.services.agent_harness.runtime.conversation_events import append_conversation_event
from app.services.agent_harness.runtime.model_context.assembler import build_model_context
from app.services.agent_harness.runtime.model_context.boundary_store import append_boundary_v2
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    append_message_record,
    append_message_record as append_message,
)


def test_model_context_assembler_returns_full_history_without_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "first"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "second"})

    bundle = build_model_context(7, conversation["id"])

    assert bundle.source == "full_history"
    assert bundle.messages == [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    assert "Session memory:" not in "\n".join(str(message.get("content") or "") for message in bundle.messages)


def test_model_context_assembler_slices_after_v2_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    first = append_message(7, conversation["id"], {"role": "user", "content": "old"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "old assistant"})
    latest = append_message(7, conversation["id"], {"role": "user", "content": "new"})
    append_boundary_v2(
        7,
        conversation["id"],
        run_id="run",
        compact_type="auto_full",
        covered={"message_row_id_end": first["_seq"], "event_sequence_end": 0, "message_count": 1},
        summary_message={"role": "user", "content": "Conversation summary:\nsummary"},
        restore_messages=[{"role": "user", "content": "Post-compact restore context:\n- active_file: project/app.py"}],
        token_counts={"pre": 100, "post": 10},
        method={"source": "llm_full_compact"},
    )

    bundle = build_model_context(7, conversation["id"])

    assert bundle.source == "boundary_v2"
    assert bundle.messages == [
        {"role": "user", "content": "Conversation summary:\nsummary"},
        {"role": "user", "content": "Post-compact restore context:\n- active_file: project/app.py"},
        {"role": "assistant", "content": "old assistant"},
        {"role": "user", "content": "new"},
    ]
    assert latest["_seq"] > first["_seq"]


def test_model_context_assembler_ignores_v1_boundary(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "old"})
    append_conversation_event(
        7,
        conversation["id"],
        run_id="run",
        event_type="compaction_boundary",
        payload={"schema_version": 1, "summary": "legacy"},
        lane="system",
    )

    bundle = build_model_context(7, conversation["id"])

    assert bundle.source == "full_history"
    assert bundle.messages == [{"role": "user", "content": "old"}]


def test_model_context_assembler_appends_extra_messages(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "stored"})

    bundle = build_model_context(
        7,
        conversation["id"],
        extra_messages=[{"role": "user", "content": "transient"}],
    )

    assert bundle.messages[-1] == {"role": "user", "content": "transient"}
    assert len(bundle.persisted_messages) == 1


def test_model_context_assembler_drops_orphan_tool_results(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "start"})
    append_message(7, conversation["id"], {"role": "tool", "tool_call_id": "missing", "content": "orphan"})

    bundle = build_model_context(7, conversation["id"])

    assert bundle.messages == [{"role": "user", "content": "start"}]


def test_model_context_assembler_downgrades_incomplete_tool_call_group(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "start"})
    append_message(
        7,
        conversation["id"],
        {
            "role": "assistant",
            "content": "calling",
            "tool_calls": [
                {"id": "call-1", "name": "tool", "arguments": {}},
                {"id": "call-2", "name": "tool", "arguments": {}},
            ],
        },
    )
    append_message(7, conversation["id"], {"role": "tool", "tool_call_id": "call-1", "content": "one"})

    bundle = build_model_context(7, conversation["id"])

    assert bundle.messages[-1] == {"role": "assistant", "content": "calling"}
    assert not any(message.get("role") == "tool" for message in bundle.messages)


@pytest.mark.parametrize(
    "tool_name",
    [
        "ask_user",
        "workspace_map",
        "register_artifact",
        "fetch_webpage",
        "Agent",
        "search_harness_history",
        "edit_file",
        "exec_command",
        "read_file",
        "write_file",
        "list_files",
        "glob_files",
        "grep_files",
        "publish_output",
        "request_plan_approval",
    ],
)
def test_model_context_assembler_preserves_regular_tool_result_groups(monkeypatch, tmp_path, tool_name):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title=f"{tool_name} context")
    conversation_id = conversation["id"]
    tool_calls = [{"id": f"call-{tool_name}", "name": tool_name, "arguments": {}}]
    tool_content = json.dumps({"status": "completed", "output": f"{tool_name} done"}, ensure_ascii=False)
    append_message(7, conversation_id, {"role": "user", "content": f"use {tool_name}"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": f"call-{tool_name}",
            "tool_name": tool_name,
            "content": tool_content,
            "metadata": {"run_id": "run-1", "tool_call_id": f"call-{tool_name}", "tool_name": tool_name},
        },
    )

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": f"use {tool_name}"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": f"call-{tool_name}", "content": tool_content},
    ]


def test_model_context_assembler_keeps_tool_result_when_legacy_projection_splits_tool_group(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Web search projection split")
    conversation_id = conversation["id"]
    tool_calls = [
        {
            "id": "call-web-1",
            "name": "web_search",
            "arguments": {"query": "尼采 生平 Friedrich Nietzsche biography", "search_type": "text"},
        }
    ]
    tool_content = json.dumps(
        {
            "status": "completed",
            "output": "{\"query\":\"尼采 生平 Friedrich Nietzsche biography\",\"results\":[{\"title\":\"Friedrich Nietzsche\"}]}",
        },
        ensure_ascii=False,
    )
    append_message(7, conversation_id, {"role": "user", "content": "网络检索下尼采的生平"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "搜索 '尼采 生平 Friedrich Nietzsche biography' 返回了 5 条结果",
            "blocks": [
                {
                    "id": "web-search-call-web-1",
                    "kind": "content",
                    "ui_kind": "web_search_card",
                    "status": "running",
                    "payload": {"query": "尼采 生平 Friedrich Nietzsche biography", "results": []},
                }
            ],
            "metadata": {"render_key": "block:web-search-call-web-1"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "call-web-1",
            "tool_name": "web_search",
            "content": tool_content,
            "metadata": {"run_id": "run-1", "tool_call_id": "call-web-1", "tool_name": "web_search"},
        },
    )

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": "网络检索下尼采的生平"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": "call-web-1", "content": tool_content},
    ]


def test_model_context_assembler_keeps_analyze_image_result_when_stream_blocks_split_tool_group(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Analyze image projection split")
    conversation_id = conversation["id"]
    tool_calls = [
        {
            "id": "call-analyze-1",
            "name": "analyze_image",
            "arguments": {"image_url": "references/source.png", "question": "describe it"},
        }
    ]
    tool_content = json.dumps(
        {
            "status": "completed",
            "output": "{\"analysis\":\"这是一张参考图。\"}",
        },
        ensure_ascii=False,
    )
    append_message(7, conversation_id, {"role": "user", "content": "分析这张图"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "图片分析",
            "blocks": [
                {
                    "id": "media-call-analyze-1",
                    "kind": "content",
                    "ui_kind": "media_card",
                    "status": "running",
                    "payload": {"tool_name": "analyze_image", "status": "running"},
                }
            ],
            "metadata": {"render_key": "block:media-call-analyze-1"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "这是一张参考图。",
            "blocks": [
                {
                    "id": "analyze-image-text-call-analyze-1",
                    "kind": "text",
                    "status": "completed",
                    "payload": {"toolName": "analyze_image", "text": "这是一张参考图。"},
                }
            ],
            "metadata": {"render_key": "block:analyze-image-text-call-analyze-1"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "call-analyze-1",
            "tool_name": "analyze_image",
            "content": tool_content,
            "metadata": {"run_id": "run-1", "tool_call_id": "call-analyze-1", "tool_name": "analyze_image"},
        },
    )

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": "分析这张图"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": "call-analyze-1", "content": tool_content},
    ]


def test_model_context_assembler_keeps_tool_result_when_projection_is_render_only(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Web search render-only projection")
    conversation_id = conversation["id"]
    tool_calls = [
        {
            "id": "call-web-1",
            "name": "web_search",
            "arguments": {"query": "尼采 生平 Friedrich Nietzsche biography", "search_type": "text"},
        }
    ]
    tool_content = json.dumps(
        {
            "status": "completed",
            "output": "{\"query\":\"尼采 生平 Friedrich Nietzsche biography\",\"results\":[{\"title\":\"Friedrich Nietzsche\"}]}",
        },
        ensure_ascii=False,
    )
    append_message(7, conversation_id, {"role": "user", "content": "网络检索下尼采的生平"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "搜索 '尼采 生平 Friedrich Nietzsche biography' 返回了 5 条结果",
            "blocks": [
                {
                    "id": "web-search-call-web-1",
                    "kind": "content",
                    "ui_kind": "web_search_card",
                    "status": "running",
                    "payload": {"query": "尼采 生平 Friedrich Nietzsche biography", "results": []},
                }
            ],
            "metadata": {"render_key": "block:web-search-call-web-1", "render_only": True},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "call-web-1",
            "tool_name": "web_search",
            "content": tool_content,
            "metadata": {"run_id": "run-1", "tool_call_id": "call-web-1", "tool_name": "web_search"},
        },
    )

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": "网络检索下尼采的生平"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": "call-web-1", "content": tool_content},
    ]


def test_model_context_assembler_keeps_tool_result_after_web_search_card_event(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_service import load_messages

    conversation = create_conversation(7, title="Web search card event")
    conversation_id = conversation["id"]
    tool_calls = [
        {
            "id": "call-web-1",
            "name": "web_search",
            "arguments": {"query": "尼采 生平 Friedrich Nietzsche biography", "search_type": "text"},
        }
    ]
    tool_content = json.dumps(
        {
            "status": "completed",
            "output": "{\"query\":\"尼采 生平 Friedrich Nietzsche biography\",\"results\":[{\"title\":\"Friedrich Nietzsche\"}]}",
        },
        ensure_ascii=False,
    )
    append_message(7, conversation_id, {"role": "user", "content": "网络检索下尼采的生平"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2

    card_op = presentation_v2.content_block_upsert(
        conversation_id=conversation_id,
        run_id="run-1",
        block_key="web-search-call-web-1",
        ui_kind="web_search_card",
        status="completed",
        payload={
            "call_id": "call-web-1",
            "query": "尼采 生平 Friedrich Nietzsche biography",
            "results": [],
            "status": "completed",
        },
        complete=True,
    )
    publish_user_event(
        7,
        conversation_id,
        run_id="run-1",
        event_type=str(card_op["type"]),
        data=card_op,
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "call-web-1",
            "tool_name": "web_search",
            "content": tool_content,
            "metadata": {"run_id": "run-1", "tool_call_id": "call-web-1", "tool_name": "web_search"},
        },
    )

    projected_card = next(
        block
        for message in load_messages(7, conversation_id)
        for block in (message.get("blocks") or [])
        if block.get("ui_kind") == "web_search_card"
    )
    assert projected_card["block_key"] == "web-search-call-web-1"

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": "网络检索下尼采的生平"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {"role": "tool", "tool_call_id": "call-web-1", "content": tool_content},
    ]


@pytest.mark.parametrize(
    ("tool_name", "call_id"),
    [
        ("generate_image", "call-image-1"),
        ("generate_video", "call-video-1"),
    ],
)
def test_model_context_assembler_skips_media_generation_card_after_hidden_tool_result(
    monkeypatch,
    tmp_path,
    tool_name,
    call_id,
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title=f"{tool_name} card")
    conversation_id = conversation["id"]
    tool_calls = [{"id": call_id, "name": tool_name, "arguments": {"prompt": "a calm study"}}]
    append_message(7, conversation_id, {"role": "user", "content": "生成素材"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": call_id,
            "tool_name": tool_name,
            "content": json.dumps(
                {
                    "status": "completed",
                    "artifact_ref": f"artifact_ref:{call_id}",
                    "result_url": "https://example.test/generated.png",
                },
                ensure_ascii=False,
            ),
            "metadata": {
                "run_id": "run-1",
                "tool_call_id": call_id,
                "tool_name": tool_name,
                "model_visible": False,
            },
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "媒体生成",
            "blocks": [
                {
                    "id": f"media-{call_id}",
                    "kind": "content",
                    "ui_kind": "media_card",
                    "status": "completed",
                    "payload": {
                        "tool_name": tool_name,
                        "status": "completed",
                        "artifact_ref": f"artifact_ref:{call_id}",
                    },
                }
            ],
            "metadata": {"render_key": f"block:media-{call_id}"},
        },
    )

    bundle = build_model_context(7, conversation_id)

    assert len(bundle.messages) == 3
    assert bundle.messages[1] == {"role": "assistant", "content": "", "tool_calls": tool_calls}
    tool_message = bundle.messages[2]
    assert tool_message["role"] == "tool"
    assert tool_message["tool_call_id"] == call_id
    projected = json.loads(tool_message["content"])
    assert projected["result"] == "success"
    assert projected["artifact_ref"] == f"artifact_ref:{call_id}"
    assert "result_url" not in tool_message["content"]


def test_model_context_assembler_preserves_tool_result_ids_stored_in_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Tool metadata context")
    conversation_id = conversation["id"]
    tool_calls = [{"id": "call-1", "name": "workspace_map", "arguments": {}}]
    append_message(7, conversation_id, {"role": "user", "content": "build the workbook"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "status": "completed",
                    "summary": "workspace exists",
                    "output_excerpt": "workspace exists",
                },
                ensure_ascii=False,
            ),
            "metadata": {
                "run_id": "run-1",
                "tool_call_id": "call-1",
                "tool_name": "workspace_map",
                "model_visible": True,
            },
        },
    )
    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessMessage

    with harness_sync_session_scope() as session:
        row = (
            session.query(HarnessMessage)
            .filter_by(conversation_id=conversation_id, role="tool")
            .one()
        )
        row.tool_call_id = None
        row.tool_name = None

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": "build the workbook"},
        {"role": "assistant", "content": "", "tool_calls": tool_calls},
        {
            "role": "tool",
            "tool_call_id": "call-1",
            "content": json.dumps(
                {
                    "status": "completed",
                    "summary": "workspace exists",
                    "output_excerpt": "workspace exists",
                },
                ensure_ascii=False,
            ),
        },
    ]


def test_model_context_assembler_projects_hidden_media_generation_as_success(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Media context")
    conversation_id = conversation["id"]
    tool_calls = [{"id": "call-image", "name": "generate_image", "arguments": {}}]
    append_message(7, conversation_id, {"role": "user", "content": "generate and analyze"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": tool_calls,
            "metadata": {"run_id": "run-1", "finish_reason": "tool_calls"},
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "status": "completed",
                    "artifact_ref": "artifact_ref:abc123",
                },
                ensure_ascii=False,
            ),
            "metadata": {
                "run_id": "run-1",
                "tool_call_id": "call-image",
                "tool_name": "generate_image",
                "model_visible": False,
            },
        },
    )

    bundle = build_model_context(7, conversation_id)

    projected = json.loads(bundle.messages[-1]["content"])
    assert bundle.messages[-1]["role"] == "tool"
    assert bundle.messages[-1]["tool_call_id"] == "call-image"
    assert projected["result"] == "success"
    assert projected["artifact_ref"] == "artifact_ref:abc123"
    assert "processing" not in bundle.messages[-1]["content"]


def test_model_context_assembler_preserves_hidden_user_context(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "continue here",
            "metadata": {
                "hidden_user_context": {
                    "selected_files": [{"path": "backend/app/demo.py", "reason": "user selected"}],
                    "artifact_edits": [{"path": "project/index.html", "instruction": "tighten copy"}],
                    "canvas_references": [{"ref": "canvas-node-1", "label": "hero"}],
                }
            },
        },
    )

    bundle = build_model_context(7, conversation["id"])

    content = bundle.messages[0]["content"]
    assert "Hidden user context:" in content
    assert "selected_file: backend/app/demo.py" in content
    assert "artifact_edit: project/index.html" in content
    assert "canvas_reference: canvas-node-1" in content


def test_model_context_assembler_preserves_attachment_context(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "use this file",
            "attachments": [
                {
                    "type": "image",
                    "url": "references/inputs/upload_001/source.png",
                    "name": "source.png",
                }
            ],
        },
    )

    bundle = build_model_context(7, conversation["id"])

    content = bundle.messages[0]["content"]
    assert "Attached files:" in content
    assert "source.png" in content
    assert "type=image" in content
    assert "references/inputs/upload_001/source.png" in content
    assert "$HARNESS_REFERENCES_DIR/inputs/upload_001/source.png" in content


def test_model_context_assembler_preserves_structured_media_references(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Context")
    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "use this reference",
            "metadata": {
                "references": [
                    {
                        "id": "ref-upload-1",
                        "kind": "upload_attachment",
                        "media_type": "image",
                        "display_name": "reference.png",
                        "tool_reference": "references/inputs/upload_001/source.png",
                        "source": {
                            "type": "harness_input",
                            "path": "references/inputs/upload_001/source.png",
                        },
                    }
                ]
            },
        },
    )

    bundle = build_model_context(7, conversation["id"])

    content = bundle.messages[0]["content"]
    assert "Structured media references (JSON):" in content
    assert '"tool_reference":"references/inputs/upload_001/source.png"' in content
    assert '"type":"harness_input"' in content
    assert '"path":"references/inputs/upload_001/source.png"' in content


def test_model_context_assembler_adds_canvas_media_rules_for_canvas_marks(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Canvas mark context")
    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "把#[葡萄](canvas-mark:mark-1:image:img-1:x:0.42:y:0.61)换成桃子",
            "metadata": {
                "references": [
                    {
                        "id": "canvas-mark:mark-1",
                        "kind": "canvas_mark",
                        "media_type": "image",
                        "display_name": "葡萄",
                        "tool_reference": "/api/v1/uploads/canvas/88/source.png",
                        "source": {
                            "type": "canvas_mark",
                            "mark_id": "mark-1",
                            "image_item_id": "img-1",
                        },
                        "mark": {
                            "id": "mark-1",
                            "image_item_id": "img-1",
                            "number": 1,
                            "label": "葡萄",
                            "position": {"x": 0.42, "y": 0.61},
                        },
                    }
                ]
            },
        },
    )

    bundle = build_model_context(7, conversation["id"])

    content = bundle.messages[0]["content"]
    assert "Structured media references (JSON):" in content
    assert "Canvas media reference rules:" in content
    assert "canvas_mark" in content
    assert "generate_image.reference_image_urls" in content
    assert "保持其余画面不变" in content


def test_model_context_assembler_adds_media_rules_for_uploaded_image_attachments(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Attachment reference context")
    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "参考这张图生成一张新图",
            "attachments": [
                {
                    "type": "image",
                    "url": "references/inputs/upload_001/source.png",
                    "name": "source.png",
                }
            ],
        },
    )

    bundle = build_model_context(7, conversation["id"])

    content = bundle.messages[0]["content"]
    assert "Media reference rules:" in content
    assert "User-uploaded image attachments" in content
    assert "generate_image.reference_image_urls" in content
    assert "analyze_image.image_url" in content


def test_model_context_assembler_substitutes_media_projection_for_hidden_tool_result(monkeypatch, tmp_path):
    """Regression: assembler must convert ``model_visible=False`` media tool
    results into the canonical success projection rather than dropping them.

    Dropping causes the loop bug: with no tool result in context, the
    sanitize pass strips the assistant's ``tool_calls`` too, leaving the
    model with no memory of having called ``generate_image`` — so it just
    re-issues the same calls turn after turn.
    """
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Hidden media projection")
    conversation_id = conversation["id"]

    append_message(7, conversation_id, {"role": "user", "content": "draw a logo"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "functions.generate_image:0",
                    "name": "generate_image",
                    "arguments": {"prompt": "coffee"},
                }
            ],
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "functions.generate_image:0",
            "tool_name": "generate_image",
            "content": json.dumps(
                {
                    "artifact_ref": "artifact_ref:abc",
                    "task_id": "internal-task-id",
                    "status": "processing",
                    "result_url": "https://example.test/internal.png",
                    "async_execution": True,
                }
            ),
            "metadata": {"model_visible": False},
        },
    )

    bundle = build_model_context(7, conversation_id)

    # Assistant tool_calls must survive (matching tool result is present).
    assistant_message = next(
        message for message in bundle.messages if message.get("role") == "assistant"
    )
    assert assistant_message.get("tool_calls"), "tool_calls were stripped — sanitize would loop the model"
    assert assistant_message["tool_calls"][0]["id"] == "functions.generate_image:0"

    # Tool message must carry the success projection, not the raw payload.
    tool_message = next(
        message for message in bundle.messages if message.get("role") == "tool"
    )
    summary = json.loads(tool_message["content"])
    assert summary == {
        "result": "success",
        "artifact_ref": "artifact_ref:abc",
        "message": "媒体生成已成功。后续如需使用该媒体，请直接使用 artifact_ref。不要为了获取同一个结果重复调用生成工具。",
    }
    rendered = json.dumps(bundle.messages, ensure_ascii=False)
    assert "processing" not in rendered
    assert "internal-task-id" not in rendered
    assert "result_url" not in rendered
    assert "async_execution" not in rendered


def test_model_context_assembler_keeps_media_projection_after_presentation_tool_call_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Presentation media tool projection")
    conversation_id = conversation["id"]
    tool_calls = [
        {
            "id": "call-image-1",
            "name": "generate_image",
            "arguments": {"prompt": "product photo"},
        }
    ]

    append_message(7, conversation_id, {"role": "user", "content": "生成商品图"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "我将生成商品图。",
            "tool_calls": tool_calls,
            "metadata": {
                "render_kind": "presentation_v2",
                "finish_reason": "tool_calls",
                "source_run_id": "run-1",
            },
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "call-image-1",
            "tool_name": "generate_image",
            "content": json.dumps(
                {
                    "artifact_ref": "artifact_ref:product",
                    "task_id": "task-1",
                    "status": "processing",
                    "result_url": None,
                }
            ),
            "metadata": {
                "message_kind": "agent_context",
                "model_visible": False,
                "ui_visible": False,
                "tool_name": "generate_image",
            },
        },
    )

    bundle = build_model_context(7, conversation_id)

    assert bundle.messages == [
        {"role": "user", "content": "生成商品图"},
        {"role": "assistant", "content": "我将生成商品图。", "tool_calls": tool_calls},
        {
            "role": "tool",
            "tool_call_id": "call-image-1",
            "content": json.dumps(
                {
                    "result": "success",
                    "artifact_ref": "artifact_ref:product",
                    "message": "媒体生成已成功。后续如需使用该媒体，请直接使用 artifact_ref。不要为了获取同一个结果重复调用生成工具。",
                },
                ensure_ascii=False,
            ),
        },
    ]
    rendered = json.dumps(bundle.messages, ensure_ascii=False)
    assert "task-1" not in rendered
    assert "processing" not in rendered


def test_model_context_assembler_projects_duplicate_media_reuse_even_if_model_visible(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Duplicate media projection")
    conversation_id = conversation["id"]

    append_message(7, conversation_id, {"role": "user", "content": "draw a product"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "I will generate it.",
            "tool_calls": [
                {
                    "id": "call-repeat",
                    "name": "generate_image",
                    "arguments": {"prompt": "same prompt"},
                }
            ],
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "call-repeat",
            "tool_name": "generate_image",
            "content": json.dumps(
                {
                    "status": "completed",
                    "output": json.dumps(
                        {
                            "artifact_ref": "artifact_ref:abc",
                            "status": "completed",
                            "result_url": "/api/v1/uploads/generated/image.png",
                            "duplicate_generation_blocked": True,
                            "emit_media_card": False,
                        }
                    ),
                },
                ensure_ascii=False,
            ),
            "metadata": {"model_visible": True},
        },
    )

    bundle = build_model_context(7, conversation_id)

    tool_message = next(message for message in bundle.messages if message.get("role") == "tool")
    summary = json.loads(tool_message["content"])
    assert summary == {
        "result": "success",
        "artifact_ref": "artifact_ref:abc",
        "message": "媒体生成已成功。后续如需使用该媒体，请直接使用 artifact_ref。不要为了获取同一个结果重复调用生成工具。",
    }
    rendered = json.dumps(bundle.messages, ensure_ascii=False)
    assert "duplicate_generation_blocked" not in rendered
    assert "result_url" not in rendered


def test_model_context_assembler_substitutes_failed_media_projection(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Failed media")
    conversation_id = conversation["id"]

    append_message(7, conversation_id, {"role": "user", "content": "draw"})
    append_message_record(
        7,
        conversation_id,
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "functions.generate_video:9", "name": "generate_video", "arguments": {"prompt": "x"}}
            ],
        },
    )
    append_message_record(
        7,
        conversation_id,
        {
            "role": "tool",
            "tool_call_id": "functions.generate_video:9",
            "tool_name": "generate_video",
            "content": json.dumps(
                {
                    "artifact_ref": "artifact_ref:video-9",
                    "status": "failed",
                    "error": "provider failed",
                }
            ),
            "metadata": {"model_visible": False},
        },
    )

    bundle = build_model_context(7, conversation_id)
    tool_message = next(message for message in bundle.messages if message.get("role") == "tool")
    summary = json.loads(tool_message["content"])
    assert summary["result"] == "error"
    assert summary["artifact_ref"] == "artifact_ref:video-9"
    assert "provider failed" in summary["message"]
