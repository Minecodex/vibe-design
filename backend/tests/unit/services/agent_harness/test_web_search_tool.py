from __future__ import annotations

import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.capabilities.tools.web_search import WebSearchParams, WebSearchTool
from app.services.web_search_payloads import build_web_search_payloads


@pytest.mark.asyncio
async def test_web_search_image_results_skip_failed_cache(monkeypatch, tmp_path):
    ctx = HarnessContext(
        user_id=7,
        conversation_id="web-search-images",
        run_id="run-web-search-images",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()

    async def fake_search_web(query: str, *, num_results: int, search_type: str):
        return {
            "provider": "test",
            "search_type": "image",
            "query": query,
            "message": "图片搜索 'hegel' 返回了 2 条结果",
            "results": [
                {"title": "bad", "image_url": "https://example.com/empty.jpg"},
                {"title": "good", "image_url": "https://example.com/good.jpg"},
            ],
        }

    async def fake_download(ctx, url: str, *, ext_hint: str, media_kind: str):
        if "empty" in url:
            raise ValueError("Downloaded media is empty")
        return "assets/references/web_image_001/original.jpg"

    monkeypatch.setattr("app.services.agent_harness.capabilities.tools.web_search.search_web", fake_search_web)
    monkeypatch.setattr("app.services.agent_harness.capabilities.tools.web_search.download_media_to_workspace", fake_download)

    result = await WebSearchTool().execute(
        WebSearchParams(query="hegel", search_type="image", num_results=2),
        ctx,
    )

    assert result.is_error is False
    assert result.metadata["message"] == "图片搜索 'hegel' 返回了 1 条结果"
    assert [item["title"] for item in result.metadata["ui_results"]] == ["good"]
    assert result.metadata["results"] == [
        {
            "title": "good",
            "local_image_path": "assets/references/web_image_001/original.jpg",
            "image_url": "assets/references/web_image_001/original.jpg",
        }
    ]


def test_web_search_model_payload_keeps_result_urls():
    model_payload, ui_payload = build_web_search_payloads(
        provider="test",
        search_type="text",
        query="japan births by year",
        results=[
            {
                "title": "Vital Statistics",
                "url": "https://example.com/vital",
                "snippet": "Annual births by year.",
            }
        ],
        message="ok",
    )

    assert model_payload["results"] == [
        {
            "title": "Vital Statistics",
            "url": "https://example.com/vital",
            "snippet": "Annual births by year.",
        }
    ]
    assert ui_payload["ui_results"][0]["url"] == "https://example.com/vital"
