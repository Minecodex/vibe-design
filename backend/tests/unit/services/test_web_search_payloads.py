from app.services.web_search_payloads import (
    build_web_search_payloads,
    sanitize_tool_result_for_model,
)


def test_build_web_search_payloads_keeps_remote_urls_out_of_model_payload():
    results = [
        {
            "title": "Portrait of Kant",
            "image_url": "https://images.example.com/kant.jpg",
            "thumbnail_url": "https://thumbs.example.com/kant.jpg",
            "source_url": "https://source.example.com/kant",
            "network_image_url": "https://images.example.com/kant.jpg",
            "local_image_path": "generated/web_search_image_kant.jpg",
            "width": 1024,
            "height": 1536,
        }
    ]

    model_payload, ui_payload = build_web_search_payloads(
        provider="duckduckgo",
        search_type="image",
        query="Immanuel Kant portrait painting",
        results=results,
        message="ok",
    )

    assert model_payload["results"] == [
        {
            "title": "Portrait of Kant",
            "image_url": "generated/web_search_image_kant.jpg",
            "local_image_path": "generated/web_search_image_kant.jpg",
            "source_url": "https://source.example.com/kant",
            "width": 1024,
            "height": 1536,
        }
    ]
    assert "ui_results" not in model_payload
    assert ui_payload["ui_results"][0]["source_url"] == "https://source.example.com/kant"
    assert ui_payload["ui_results"][0]["network_image_url"] == "https://images.example.com/kant.jpg"


def test_sanitize_tool_result_for_model_uses_ui_results_when_present():
    result = {
        "provider": "duckduckgo",
        "search_type": "image",
        "query": "Hegel portrait",
        "results": [{"title": "stale"}],
        "ui_results": [
            {
                "title": "Hegel portrait",
                "source_url": "https://source.example.com/hegel",
                "local_image_path": "generated/web_search_image_hegel.jpg",
            }
        ],
        "message": "ok",
    }

    sanitized = sanitize_tool_result_for_model("lc_search_web", result)

    assert "ui_results" not in sanitized
    assert sanitized["results"] == [
        {
            "title": "Hegel portrait",
            "image_url": "generated/web_search_image_hegel.jpg",
            "local_image_path": "generated/web_search_image_hegel.jpg",
            "source_url": "https://source.example.com/hegel",
        }
    ]


def test_sanitize_tool_result_for_model_summarizes_async_generation_without_ui_message():
    result = {
        "task_id": 42,
        "canvas_item_id": "canvas-42",
        "status": "processing",
        "result_url": None,
        "message": "图片生成任务 #42 状态为 processing。",
        "canvas_item": {
            "id": "canvas-42",
            "type": "image_generator",
            "task_id": 42,
            "status": "generating",
            "url": "",
            "prompt": "Logo design",
            "model_name": "hidden-model",
        },
    }

    sanitized = sanitize_tool_result_for_model("lc_generate_image", result)

    assert {key: value for key, value in sanitized.items() if key != "instruction"} == {
        "type": "async_generation_started",
        "media_type": "image",
        "task_id": 42,
        "canvas_item_id": "canvas-42",
        "status": "processing",
        "result_url": None,
        "ui_already_shows_progress": True,
        "async_execution": True,
        "do_not_repeat_same_generation": True,
    }
    assert "Do not call the same generation tool again" in sanitized["instruction"]
    assert "artifact_ref" in sanitized["instruction"]
