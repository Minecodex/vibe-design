from __future__ import annotations

import json

import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.execution_support.reviewer import review_tool_result
from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult
from app.services.agent_harness.capabilities.tools.fetch_webpage import (
    FetchWebpageParams,
    FetchWebpageTool,
)


class _FakeCrawlResult:
    def __init__(
        self,
        *,
        url: str = "https://example.com/final",
        markdown: str = "# Test Page\n\nHello world from crawl4ai.",
        fit_markdown: str | None = None,
        html: str = "<html><head><title>Ignored</title></head><body>Hello world from crawl4ai.</body></html>",
        success: bool = True,
        status_code: int = 200,
        response_headers: dict | None = None,
        error_message: str = "",
    ):
        self.url = url
        self.markdown = markdown
        self.fit_markdown = fit_markdown
        self.html = html
        self.success = success
        self.status_code = status_code
        self.response_headers = response_headers or {"content-type": "text/html; charset=utf-8"}
        self.error_message = error_message


class _FakeAsyncWebCrawler:
    last_init_kwargs = None
    last_url = None
    next_result = _FakeCrawlResult()

    def __init__(self, *args, **kwargs):
        type(self).last_init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def arun(self, *, url: str, **kwargs):
        type(self).last_url = url
        return type(self).next_result


class _FakeSessionFactory:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMultimodalService:
    last_call = None

    def __init__(self, db):
        self.db = db

    async def chat(
        self,
        *,
        user_id: int,
        model_name: str,
        provider_code: str | None,
        messages: list[dict],
        max_tokens: int,
        skip_usage_log: bool,
        billing_label: str,
        task_type: str,
    ) -> dict:
        type(self).last_call = {
            "user_id": user_id,
            "model_name": model_name,
            "provider_code": provider_code,
            "messages": messages,
            "max_tokens": max_tokens,
            "skip_usage_log": skip_usage_log,
            "billing_label": billing_label,
            "task_type": task_type,
        }
        return {
            "choices": [
                {
                    "message": {
                        "content": "Page summary: this is a summary of the fetched page."
                    }
                }
            ],
            "_amount_cents": 7,
            "_elapsed_ms": 18,
            "usage": {"prompt_tokens": 120, "completion_tokens": 32},
        }


@pytest.mark.asyncio
async def test_fetch_webpage_returns_prompt_aware_summary(monkeypatch, tmp_path):
    _FakeAsyncWebCrawler.next_result = _FakeCrawlResult(
        markdown="# Test Page\n\nHello world from crawl4ai.",
        fit_markdown="Test Page\n\nHello world from crawl4ai.",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.AsyncWebCrawler",
        _FakeAsyncWebCrawler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.get_harness_db_session_factory",
        lambda: _FakeSessionFactory,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.MultimodalService",
        _FakeMultimodalService,
    )

    ctx = HarnessContext(
        user_id=9,
        conversation_id="fetch-webpage",
        run_id="run-fetch-webpage",
        workspace_root=tmp_path,
        multimodal_model="test-model",
        multimodal_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await FetchWebpageTool().execute(
        FetchWebpageParams(
            url="http://example.com/source",
            prompt="Summarize this page",
        ),
        ctx,
    )

    assert result.is_error is False
    payload = json.loads(result.output)
    assert payload["url"] == "https://example.com/final"
    assert payload["code"] == 200
    assert payload["codeText"] == "OK"
    assert payload["bytes"] > 0
    assert payload["durationMs"] >= 0
    assert payload["result"] == "Page summary: this is a summary of the fetched page."
    assert result.metadata["code"] == 200
    assert result.metadata["url"] == "https://example.com/final"
    assert _FakeAsyncWebCrawler.last_url == "https://example.com/source"
    assert _FakeMultimodalService.last_call["user_id"] == 9
    assert _FakeMultimodalService.last_call["model_name"] == "test-model"
    assert _FakeMultimodalService.last_call["provider_code"] == "builtin"
    assert _FakeMultimodalService.last_call["skip_usage_log"] is True
    assert _FakeMultimodalService.last_call["billing_label"] == "billing.labels.web_generate"
    assert _FakeMultimodalService.last_call["task_type"] == "web_fetch"
    user_message = _FakeMultimodalService.last_call["messages"][1]["content"]
    assert "Summarize this page" in user_message
    assert "Hello world from crawl4ai" in user_message
    assert "Current runtime time:" in user_message
    assert "UTC" in user_message
    assert payload["result"]


@pytest.mark.asyncio
async def test_fetch_webpage_uses_expanded_summary_token_budget(monkeypatch, tmp_path):
    _FakeAsyncWebCrawler.next_result = _FakeCrawlResult(
        markdown="# Test Page\n\nHello world from crawl4ai.",
        fit_markdown="Test Page\n\nHello world from crawl4ai.",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.AsyncWebCrawler",
        _FakeAsyncWebCrawler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.get_harness_db_session_factory",
        lambda: _FakeSessionFactory,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.MultimodalService",
        _FakeMultimodalService,
    )

    ctx = HarnessContext(
        user_id=9,
        conversation_id="fetch-webpage-budget",
        run_id="run-fetch-webpage-budget",
        workspace_root=tmp_path,
        multimodal_model="test-model",
        multimodal_provider="builtin",
    )
    ctx.ensure_dirs()

    result = await FetchWebpageTool().execute(
        FetchWebpageParams(
            url="http://example.com/source",
            prompt="Summarize this page",
        ),
        ctx,
    )

    assert result.is_error is False
    assert _FakeMultimodalService.last_call["max_tokens"] == 2000


@pytest.mark.asyncio
async def test_fetch_webpage_prefers_title_for_title_prompts(monkeypatch):
    _FakeAsyncWebCrawler.next_result = _FakeCrawlResult(
        markdown="# Test Page\n\nHello world from crawl4ai.",
        html="<html><head><title>Ignored</title></head><body>Hello world from crawl4ai.</body></html>",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.AsyncWebCrawler",
        _FakeAsyncWebCrawler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.get_harness_db_session_factory",
        lambda: _FakeSessionFactory,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.MultimodalService",
        _FakeMultimodalService,
    )

    result = await FetchWebpageTool().execute(
        FetchWebpageParams(
            url="https://example.com/source",
            prompt="What is the page title?",
        ),
        HarnessContext(user_id=1, conversation_id="c", run_id="r"),
    )

    assert result.is_error is False
    user_message = _FakeMultimodalService.last_call["messages"][1]["content"]
    assert "Title: Ignored" in user_message


@pytest.mark.asyncio
async def test_fetch_webpage_supports_plain_text(monkeypatch):
    _FakeAsyncWebCrawler.next_result = _FakeCrawlResult(
        url="http://127.0.0.1/plain",
        markdown="plain text response",
        fit_markdown="plain text response",
        html="plain text response",
        response_headers={"content-type": "text/plain"},
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.AsyncWebCrawler",
        _FakeAsyncWebCrawler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.get_harness_db_session_factory",
        lambda: _FakeSessionFactory,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.MultimodalService",
        _FakeMultimodalService,
    )

    result = await FetchWebpageTool().execute(
        FetchWebpageParams(
            url="http://127.0.0.1/plain",
            prompt="Show me the content",
        ),
        HarnessContext(user_id=1, conversation_id="c", run_id="r"),
    )

    assert result.is_error is False
    payload = json.loads(result.output)
    assert payload["url"] == "http://127.0.0.1/plain"
    assert payload["result"] == "Page summary: this is a summary of the fetched page."
    assert "plain text response" in _FakeMultimodalService.last_call["messages"][1]["content"]


@pytest.mark.asyncio
async def test_fetch_webpage_returns_blocked_crawl_errors(monkeypatch):
    _FakeAsyncWebCrawler.next_result = _FakeCrawlResult(
        url="https://example.com/blocked",
        markdown="Please respect our robot policy",
        fit_markdown="Please respect our robot policy",
        html="Please respect our robot policy",
        success=False,
        status_code=403,
        response_headers={"content-type": "text/plain"},
        error_message="Please respect our robot policy",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.AsyncWebCrawler",
        _FakeAsyncWebCrawler,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.get_harness_db_session_factory",
        lambda: _FakeSessionFactory,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.fetch_webpage.MultimodalService",
        _FakeMultimodalService,
    )

    result = await FetchWebpageTool().execute(
        FetchWebpageParams(
            url="https://example.com/blocked",
            prompt="Summarize this page",
        ),
        HarnessContext(user_id=1, conversation_id="c", run_id="r"),
    )

    assert result.is_error is True
    payload = json.loads(result.output)
    assert payload["code"] == 403
    assert payload["codeText"] == "Forbidden"
    assert "抓取失败" in payload["result"]
    assert result.metadata["semantic_error_type"] == "web_fetch_blocked"
    assert result.metadata["failure_kind"] == "bot_protected_page"


def test_fetch_webpage_reviewer_excerpt_keeps_full_url():
    result = ToolResult(
        output="{}",
        is_error=True,
        metadata={
            "url": "https://example.com/blocked",
            "code": 403,
            "codeText": "Forbidden",
            "blocked_reason": "robot_policy_blocked",
            "result": "Webpage fetch failed due to access restrictions.",
            "semantic_error_type": "web_fetch_blocked",
            "failure_kind": "bot_protected_page",
        },
    )

    review = review_tool_result(
        "fetch_webpage",
        {"url": "https://example.com/blocked"},
        result,
    )

    assert "https://example.com/blocked" in review["output_excerpt"]


def test_web_search_reviewer_excerpt_keeps_full_urls():
    result = ToolResult(
        output="{}",
        metadata={
            "query": "Nietzsche biography",
            "results": [
                {
                    "title": "A",
                    "url": "https://example.com/full/path",
                    "snippet": "x" * 300,
                }
            ],
        },
    )

    review = review_tool_result(
        "web_search",
        {"query": "Nietzsche biography"},
        result,
    )

    assert "https://example.com/full/path" in review["output_excerpt"]


def test_fetch_webpage_rejects_invalid_url():
    tool = FetchWebpageTool()

    error = tool.validate_input(
        FetchWebpageParams(url="https://example.com", prompt="ok"),
        object(),
    )
    assert error is None

    invalid = tool.validate_input(
        FetchWebpageParams.model_construct(url="not a url", prompt="Summarize"),
        object(),
    )
    assert invalid == "fetch_webpage 仅支持 http 或 https 网页地址"


def test_fetch_webpage_tool_is_registered_by_default():
    registry = create_harness_registry()

    assert registry.get("fetch_webpage") is not None

