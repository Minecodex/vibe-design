"""Fetch and summarize a webpage for Home Agent."""

from __future__ import annotations

import json
import re
import time
from html import unescape
from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse, urlunparse

from pydantic import BaseModel, Field

from app.core.default_models import (
    get_default_multimodal_model,
    get_default_multimodal_provider,
)
from app.services.agent_harness.runtime.execution_support.billing import (
    get_harness_db_session_factory,
    resolve_harness_billing_label,
)
from app.services.multimodal_service import MultimodalService

from app.services.agent_harness.authoring.prompt.runtime_time import runtime_time_block
from ._internal.base import BaseTool, ToolResult

AsyncWebCrawler = None

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


_MAX_PREVIEW_CHARS = 900
_MAX_OUTPUT_TOKENS = 2000
_MAX_MODEL_SOURCE_CHARS = 6000
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class FetchWebpageParams(BaseModel):
    url: str = Field(..., description="要抓取的网页地址")
    prompt: str = Field(..., description="基于该网页内容要完成的提取或总结任务")


def _is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_fetch_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http":
        return parsed.geturl()
    hostname = (parsed.hostname or "").strip().lower()
    if hostname in _LOCAL_HOSTS:
        return parsed.geturl()
    upgraded = parsed._replace(scheme="https")
    return urlunparse(upgraded)


def _decode_html_entities(text: str) -> str:
    return unescape(text).replace("\xa0", " ").strip()


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _collapse_whitespace(_decode_html_entities(text))


def _preview_text(text: str, max_chars: int = _MAX_PREVIEW_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars].rstrip()}..."


def _model_source_text(text: str, max_chars: int = _MAX_MODEL_SOURCE_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip()


def _status_text(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except Exception:
        return "Unknown"


def _result_value(result: Any, *names: str) -> Any:
    for name in names:
        if isinstance(result, dict) and name in result:
            return result[name]
        if hasattr(result, name):
            return getattr(result, name)
    return None


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _extract_main_content(result: Any) -> str:
    fit_markdown = _string_value(_result_value(result, "fit_markdown"))
    if fit_markdown.strip():
        return fit_markdown.strip()

    markdown = _string_value(_result_value(result, "markdown"))
    if markdown.strip():
        return markdown.strip()

    cleaned_html = _string_value(_result_value(result, "cleaned_html"))
    if cleaned_html.strip():
        return _html_to_text(cleaned_html)

    html = _string_value(_result_value(result, "html"))
    if html.strip():
        return _html_to_text(html)

    return ""


def _extract_raw_html(result: Any) -> str:
    html = _string_value(_result_value(result, "html"))
    if html:
        return html
    cleaned_html = _string_value(_result_value(result, "cleaned_html"))
    return cleaned_html


def _extract_title(content: str, raw_html: str) -> str | None:
    if raw_html:
        match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
        if match:
            title = _collapse_whitespace(_decode_html_entities(match.group(1)))
            if title:
                return title

    for line in content.splitlines():
        trimmed = line.strip().lstrip("#").strip()
        if trimmed:
            return trimmed
    return None


def _summarize_web_fetch(*, url: str, prompt: str, content: str, title: str | None) -> str:
    lowered_prompt = prompt.lower()
    compact = _collapse_whitespace(content)

    if "title" in lowered_prompt:
        detail = f"Title: {title}" if title else _preview_text(compact, 600)
    elif "summary" in lowered_prompt or "summarize" in lowered_prompt:
        detail = _preview_text(compact, 900)
    else:
        detail = f"Prompt: {prompt}\nContent preview:\n{_preview_text(compact, 900)}"

    return f"Fetched {url}\n{detail}"


def _extract_chat_text(result: dict) -> str:
    choices = result.get("choices") or []
    if not choices:
        raise ValueError("Webpage summary returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        text = "\n".join(
            part.get("text", "").strip()
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ).strip()
    else:
        text = ""

    if not text:
        raise ValueError("Webpage summary returned empty content")
    return text


async def _summarize_with_model(
    *,
    ctx: "HarnessContext",
    page_url: str,
    title: str | None,
    prompt: str,
    content_preview: str,
) -> tuple[str, dict]:
    model_name = ctx.multimodal_model or get_default_multimodal_model()
    provider_code = ctx.multimodal_provider or get_default_multimodal_provider()
    session_factory = get_harness_db_session_factory()
    system_prompt = (
        "You summarize webpage content for a tool call. "
        "Answer only from the supplied webpage content preview. "
        "Stay focused on the user's task. "
        "If the preview does not contain the requested information, say so clearly. "
        "Keep the answer concise and factual."
    )
    user_prompt = (
        f"{runtime_time_block(ctx.language)}\n\n"
        f"URL: {page_url}\n"
        f"Title: {title or '(untitled)'}\n"
        f"Task: {prompt}\n\n"
        "Webpage content preview:\n"
        f"{content_preview}"
    )

    async with session_factory() as db:
        service = MultimodalService(db)
        response = await service.chat(
            user_id=ctx.user_id,
            model_name=model_name,
            provider_code=provider_code,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=_MAX_OUTPUT_TOKENS,
            skip_usage_log=True,
            billing_label=resolve_harness_billing_label(mode="web"),
            task_type="web_fetch",
        )

    usage = response.get("usage") or {}
    summary = _extract_chat_text(response)
    detail = {
        "model_name": model_name,
        "provider_code": provider_code,
        "kind": "fetch_webpage",
        "input_tokens": int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0),
        "output_tokens": int(usage.get("completion_tokens") or usage.get("output_tokens") or 0),
        "elapsed_ms": int(response.get("_elapsed_ms") or 0),
    }
    cost = int(response.get("_amount_cents") or 0)
    if cost > 0:
        ctx.record_billing("multimodal", cost, detail=detail)
    return summary, detail


def _blocked_reason(*, status_code: int, body: str, error_message: str) -> str | None:
    lowered = f"{body}\n{error_message}".lower()
    if status_code == 403:
        if "robot policy" in lowered:
            return "robot_policy_blocked"
        if "captcha" in lowered or "verify" in lowered or "安全验证" in lowered:
            return "captcha_blocked"
        return "forbidden"
    if status_code == 429:
        return "rate_limited"
    if "captcha" in lowered or "安全验证" in lowered:
        return "captcha_blocked"
    return None


def _crawl_success(result: Any) -> bool:
    value = _result_value(result, "success")
    if value is None:
        return True
    return bool(value)


async def _run_crawler(url: str) -> Any:
    crawler_cls = AsyncWebCrawler
    if crawler_cls is None:
        try:
            from crawl4ai import AsyncWebCrawler as crawler_cls  # type: ignore
        except Exception as exc:  # pragma: no cover - exercised through runtime error path
            raise RuntimeError("crawl4ai is not installed") from exc
    async with crawler_cls(verbose=False) as crawler:
        return await crawler.arun(url=url)


class FetchWebpageTool(BaseTool):
    @property
    def name(self) -> str:
        return "fetch_webpage"

    @property
    def description(self) -> str:
        return (
            "抓取指定网页并根据给定提示提炼结果。"
            "当 web_search 的摘要不足以回答问题时，用它读取具体 URL 的页面内容。"
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return FetchWebpageParams

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        return True

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        if not _is_http_url(params.url):
            return "fetch_webpage 仅支持 http 或 https 网页地址"
        if not str(params.prompt or "").strip():
            return "fetch_webpage 需要提供 prompt"
        return None

    async def execute(self, params: FetchWebpageParams, ctx: "HarnessContext") -> ToolResult:
        started = time.perf_counter()
        request_url = _normalize_fetch_url(params.url)

        try:
            crawl_result = await _run_crawler(request_url)
        except Exception as exc:
            payload = {
                "url": request_url,
                "code": 500,
                "codeText": "Crawler Error",
                "bytes": 0,
                "durationMs": int((time.perf_counter() - started) * 1000),
                "result": f"网页正文抓取失败：{type(exc).__name__}: {exc}",
            }
            return ToolResult(
                output=json.dumps(payload, ensure_ascii=False),
                is_error=True,
                metadata={
                    **payload,
                    "semantic_error_type": "web_fetch_runtime_error",
                    "failure_kind": "crawler_runtime_error",
                },
            )

        page_url = _string_value(_result_value(crawl_result, "url")) or request_url
        status_code = int(_result_value(crawl_result, "status_code", "status", "response_status_code") or 200)
        content = _extract_main_content(crawl_result)
        raw_html = _extract_raw_html(crawl_result)
        response_headers = _result_value(crawl_result, "response_headers", "headers") or {}
        error_message = _string_value(_result_value(crawl_result, "error_message", "error"))
        title = _extract_title(content, raw_html)
        fetch_preview = _summarize_web_fetch(
            url=page_url,
            prompt=params.prompt,
            content=content or error_message,
            title=title,
        )

        blocked_reason = _blocked_reason(
            status_code=status_code,
            body=content or raw_html,
            error_message=error_message,
        )
        is_success = _crawl_success(crawl_result)

        if blocked_reason or not is_success or not (content or raw_html):
            error_code = status_code if status_code > 0 else 500
            payload = {
                "url": page_url,
                "code": error_code,
                "codeText": _status_text(error_code),
                "bytes": len((raw_html or content or error_message).encode("utf-8", errors="ignore")),
                "durationMs": int((time.perf_counter() - started) * 1000),
                "result": "网页正文抓取失败：页面返回了反爬虫、限制访问或无可用正文内容的响应。",
            }
            failure_kind = "bot_protected_page" if blocked_reason else "empty_or_failed_page"
            semantic_error_type = "web_fetch_blocked" if blocked_reason else "web_fetch_failed"
            metadata = {
                **payload,
                "fetchPreview": fetch_preview,
                "semantic_error_type": semantic_error_type,
                "failure_kind": failure_kind,
            }
            if blocked_reason:
                metadata["blocked_reason"] = blocked_reason
            if error_message:
                metadata["error_message"] = error_message
            if response_headers:
                metadata["response_headers"] = response_headers
            return ToolResult(
                output=json.dumps(payload, ensure_ascii=False),
                is_error=True,
                metadata=metadata,
            )

        model_result, model_detail = await _summarize_with_model(
            ctx=ctx,
            page_url=page_url,
            title=title,
            prompt=params.prompt,
            content_preview=_model_source_text(content or fetch_preview),
        )

        payload = {
            "url": page_url,
            "code": status_code,
            "codeText": _status_text(status_code),
            "bytes": len((raw_html or content).encode("utf-8", errors="ignore")),
            "durationMs": int((time.perf_counter() - started) * 1000),
            "result": model_result,
        }
        return ToolResult(
            output=json.dumps(payload, ensure_ascii=False),
            metadata={
                **payload,
                "fetchPreview": fetch_preview,
                "model": model_detail,
            },
        )

