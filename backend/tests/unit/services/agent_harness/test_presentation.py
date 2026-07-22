from app.services.agent_harness.runtime.eventing.presentation import build_web_search_card_for_tool


def test_build_web_search_card_uses_ui_results_for_render_payload():
    block = build_web_search_card_for_tool(
        call_id="functions.web_search:2",
        status="completed",
        result_payload={
            "query": "Friedrich Nietzsche portrait photo image",
            "search_type": "image",
            "message": "图片搜索返回了 5 条结果",
            "results": [
                {
                    "title": "sanitized result",
                    "image_url": "assets/references/web_image_001/original.jpg",
                }
            ],
            "ui_results": [
                {
                    "title": "rich ui result",
                    "image_url": "assets/references/web_image_001/original.jpg",
                    "source_url": "https://example.com/nietzsche",
                    "thumbnail_url": "https://example.com/thumb.jpg",
                }
            ],
        },
    )

    assert block["payload"]["results"] == [
        {
            "title": "rich ui result",
            "image_url": "assets/references/web_image_001/original.jpg",
            "source_url": "https://example.com/nietzsche",
            "thumbnail_url": "https://example.com/thumb.jpg",
        }
    ]
