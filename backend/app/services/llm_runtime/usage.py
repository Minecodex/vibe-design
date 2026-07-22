from __future__ import annotations

from typing import Any


def normalize_llm_usage(raw_usage: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    if not isinstance(raw_usage, dict) or not raw_usage:
        return None
    usage: dict[str, Any] = {
        "input_tokens": _int_token(raw_usage.get("prompt_tokens", raw_usage.get("input_tokens", 0))),
        "output_tokens": _int_token(raw_usage.get("completion_tokens", raw_usage.get("output_tokens", 0))),
    }
    cached_tokens = _first_present(
        raw_usage,
        "cached_tokens",
        "prompt_cached_tokens",
        "cache_hit_tokens",
    )
    prompt_details = raw_usage.get("prompt_tokens_details")
    if cached_tokens is None and isinstance(prompt_details, dict):
        cached_tokens = _first_present(prompt_details, "cached_tokens")
    if cached_tokens is not None:
        usage["cached_tokens"] = _int_token(cached_tokens)

    cache_read_tokens = _first_present(
        raw_usage,
        "cache_read_tokens",
        "cache_read_input_tokens",
        "prompt_cache_read_tokens",
    )
    if cache_read_tokens is not None:
        usage["cache_read_tokens"] = _int_token(cache_read_tokens)

    cache_creation_tokens = _first_present(
        raw_usage,
        "cache_creation_tokens",
        "cache_creation_input_tokens",
        "prompt_cache_creation_tokens",
    )
    if cache_creation_tokens is not None:
        usage["cache_creation_tokens"] = _int_token(cache_creation_tokens)

    if isinstance(metadata, dict):
        usage.update({key: value for key, value in metadata.items() if value is not None})
    return usage


def _first_present(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return None


def _int_token(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0
