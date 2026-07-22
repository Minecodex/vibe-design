"""Shared web search runtime for agent tools."""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

_SUPPORTED_PROVIDERS = {"duckduckgo"}
_SUPPORTED_SEARCH_TYPES = {"text", "image"}
_SEARCH_MAX_ATTEMPTS = 3
_SEARCH_RETRY_BASE_DELAY_SECONDS = 0.5


def format_search_result_message(*, search_type: str, query: str, result_count: int) -> str:
    label = "图片搜索" if _normalize_search_type(search_type) == "image" else "搜索"
    return f"{label} '{query}' 返回了 {result_count} 条结果"


def _normalize_provider(value: str | None) -> str:
    provider = str(value or "duckduckgo").strip().lower()
    if provider not in _SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported search provider '{provider}'. "
            f"Supported providers: {', '.join(sorted(_SUPPORTED_PROVIDERS))}"
        )
    return provider


def _normalize_search_type(value: str | None) -> str:
    search_type = str(value or "text").strip().lower()
    if search_type not in _SUPPORTED_SEARCH_TYPES:
        raise ValueError(
            f"Unsupported search type '{search_type}'. "
            f"Supported types: {', '.join(sorted(_SUPPORTED_SEARCH_TYPES))}"
        )
    return search_type


def _is_retryable_search_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if isinstance(exc, (ValueError, ImportError, ModuleNotFoundError)):
        return False
    retryable_markers = (
        "connect",
        "connection",
        "timeout",
        "timed out",
        "tls",
        "handshake",
        "eof",
        "temporarily unavailable",
        "temporary failure",
        "network",
        "reset by peer",
        "service unavailable",
        "too many requests",
        "rate limit",
    )
    return any(marker in name or marker in text for marker in retryable_markers)


async def _run_search_with_retries(
    runner,
    query: str,
    num_results: int,
    *,
    search_type: str,
) -> list[dict[str, Any]]:
    last_exc: Exception | None = None
    for attempt in range(1, _SEARCH_MAX_ATTEMPTS + 1):
        try:
            return await asyncio.to_thread(runner, query, num_results)
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_search_error(exc) or attempt >= _SEARCH_MAX_ATTEMPTS:
                raise
            delay = _SEARCH_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            delay += random.uniform(0, _SEARCH_RETRY_BASE_DELAY_SECONDS)
            logger.warning(
                "Search request failed via provider=duckduckgo search_type=%s on attempt %s/%s, retrying in %.2fs",
                search_type,
                attempt,
                _SEARCH_MAX_ATTEMPTS,
                delay,
                exc_info=True,
            )
            await asyncio.sleep(delay)
    assert last_exc is not None
    raise last_exc


def _run_duckduckgo_search(query: str, num_results: int) -> list[dict[str, str]]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError(
            "DuckDuckGo search dependency is not installed. Please install the 'ddgs' package."
        ) from exc

    with DDGS(timeout=settings.SEARCH_TIMEOUT_SECONDS) as client:
        raw_results = client.text(
            query,
            region=settings.DUCKDUCKGO_REGION,
            safesearch=settings.DUCKDUCKGO_SAFESEARCH,
            timelimit=settings.DUCKDUCKGO_TIME_LIMIT or None,
            max_results=num_results,
            backend=settings.DUCKDUCKGO_BACKEND,
        )

    normalized: list[dict[str, str]] = []
    for item in raw_results or []:
        title = str(item.get("title") or "").strip()
        url = str(item.get("href") or "").strip()
        snippet = str(item.get("body") or "").strip()
        if not (title or url or snippet):
            continue
        normalized.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })
    return normalized


def _run_duckduckgo_image_search(query: str, num_results: int) -> list[dict[str, Any]]:
    try:
        from ddgs import DDGS
    except ImportError as exc:
        raise RuntimeError(
            "DuckDuckGo search dependency is not installed. Please install the 'ddgs' package."
        ) from exc

    with DDGS(timeout=settings.SEARCH_TIMEOUT_SECONDS) as client:
        raw_results = client.images(
            query,
            region=settings.DUCKDUCKGO_REGION,
            safesearch=settings.DUCKDUCKGO_SAFESEARCH,
            timelimit=settings.DUCKDUCKGO_TIME_LIMIT or None,
            max_results=num_results,
            backend=settings.DUCKDUCKGO_BACKEND,
        )

    normalized: list[dict[str, Any]] = []
    for item in raw_results or []:
        title = str(item.get("title") or item.get("image_title") or "").strip()
        image_url = str(item.get("image") or item.get("image_url") or "").strip()
        source_url = str(item.get("url") or item.get("source_url") or "").strip()
        thumbnail_url = str(item.get("thumbnail") or item.get("thumbnail_url") or "").strip()
        if not (title or image_url or source_url or thumbnail_url):
            continue
        normalized_item: dict[str, Any] = {
            "title": title,
            "image_url": image_url,
            "source_url": source_url,
            "thumbnail_url": thumbnail_url,
        }
        for field in ("width", "height"):
            value = item.get(field)
            if value not in (None, ""):
                normalized_item[field] = value
        normalized.append(normalized_item)
    return normalized


async def search_web(
    query: str,
    *,
    num_results: int = 5,
    search_type: str = "text",
) -> dict[str, Any]:
    """Execute a web search through the configured provider."""
    normalized_query = str(query or "").strip()
    if not normalized_query:
        raise ValueError("Search query cannot be empty.")

    requested_results = max(1, min(int(num_results or 5), settings.SEARCH_MAX_RESULTS))
    provider = _normalize_provider(settings.SEARCH_PROVIDER)
    normalized_search_type = _normalize_search_type(search_type)

    logger.info(
        "Running web search via provider=%s search_type=%s query=%s num_results=%s",
        provider,
        normalized_search_type,
        normalized_query,
        requested_results,
    )

    if provider == "duckduckgo":
        if normalized_search_type == "image":
            results = await _run_search_with_retries(
                _run_duckduckgo_image_search,
                normalized_query,
                requested_results,
                search_type=normalized_search_type,
            )
        else:
            results = await _run_search_with_retries(
                _run_duckduckgo_search,
                normalized_query,
                requested_results,
                search_type=normalized_search_type,
            )
    else:
        raise ValueError(f"Unsupported search provider '{provider}'.")

    return {
        "provider": provider,
        "search_type": normalized_search_type,
        "query": normalized_query,
        "results": results[:requested_results],
        "message": format_search_result_message(
            search_type=normalized_search_type,
            query=normalized_query,
            result_count=len(results[:requested_results]),
        ),
    }
