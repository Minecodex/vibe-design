from pathlib import Path

from app.services.agent_harness.core.context import create_context
from app.services.agent_harness.workspace.conversation.conversation_store_support import workspace_root


def test_create_context_uses_canvas_conversation_directory():
    ctx = create_context(
        user_id=12,
        conversation_id="conv-canvas-1",
        run_id="run-1",
        conversation={
            "runtime_profile": "canvas",
            "project_id": 45,
            "artifact_mode": "image",
            "model_preferences": {},
        },
    )

    assert ctx.runtime_profile == "canvas"
    assert ctx.project_id == 45
    assert ctx.conversation_dir == (
        workspace_root() / "project" / "45" / "users" / "12" / "conversations" / "conv-canvas-1"
    )


def test_canvas_reference_parser_extracts_mentions_and_marks():
    from app.services.agent_harness.canvas.reference_parser import parse_canvas_references

    canvas_items = [
        {
            "id": "img-1",
            "type": "image_generator",
            "url": "https://example.com/image.png",
            "prompt": "original prompt",
        },
        {
            "id": "video-1",
            "type": "video_generator",
            "url": "https://example.com/video.mp4",
            "prompt": "video prompt",
        },
    ]

    parsed = parse_canvas_references(
        "请参考 @[主视觉](canvas:img-1) 并处理 #[瓶身](canvas-mark:mark-2:image:img-1:x:0.25:y:0.75)，再看 @[动画](canvas:video-1)",
        canvas_items,
        language="zh",
    )

    assert parsed.cleaned_content == "请参考  并处理 ，再看"
    assert [resource["type"] for resource in parsed.resources] == ["image", "mark", "video"]
    assert parsed.resources[1]["mark_id"] == "mark-2"
    assert parsed.resources[1]["mark_position"] == {"x": 0.25, "y": 0.75}
    assert "当前引用的画布资源" in parsed.prompt_context
    assert "URL: `https://example.com/image.png`" in parsed.prompt_context
    assert "标记位置: (25%, 75%)" in parsed.prompt_context


def test_canvas_generation_mapper_builds_canvas_item_for_image():
    from app.services.agent_harness.canvas.generation_mapper import build_canvas_generation_item

    item = build_canvas_generation_item(
        conversation_id="conv-canvas-1",
        kind="image",
        task_id="task-1",
        prompt="draw poster",
        model_name="gpt-image-2",
        model_label="GPT Image 2",
        provider_code="builtin",
        aspect_ratio="16:9",
        resolution="2K",
        duration=None,
        result_url="",
        status="processing",
        artifact_ref="artifact_ref:test-image",
        position={"x": 100, "y": 200},
    )

    assert item["type"] == "image_generator"
    assert item["agent_conversation_id"] == "conv-canvas-1"
    assert item["task_id"] == "task-1"
    assert item["artifact_ref"] == "artifact_ref:test-image"
    assert item["agent_media_key"] == "artifact_ref:test-image"
    assert item["id"] == "agent-generated-test-image"
    assert item["status"] == "generating"
    assert item["x"] == 100
    assert item["y"] == 200
