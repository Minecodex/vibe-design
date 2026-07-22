"""Helpers for resolving harness agent default media generation parameters."""

from __future__ import annotations

from typing import Any

from app.core.image_constraints import resolve_image_generation_selection
from app.core.providers import build_provider_registry

IMAGE_PROVIDER_FALLBACKS: dict[str, dict[str, Any]] = {
    "kling": {
        "allowed_sizes": ["1K", "2K"],
        "allowed_aspect_ratios": ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"],
    },
    "jimeng": {
        "allowed_sizes": ["1K", "2K", "4K"],
        "allowed_aspect_ratios": ["1:1", "4:3", "3:2", "16:9", "21:9"],
    },
    "volcark": {
        "allowed_sizes": ["2K", "3K"],
        "allowed_aspect_ratios": ["1:1", "4:3", "3:4", "3:2", "2:3", "16:9", "9:16", "21:9"],
    },
}

VIDEO_PROVIDER_FALLBACKS: dict[str, dict[str, Any]] = {
    "kling": {
        "allowed_sizes": ["720p", "1080p"],
        "allowed_aspect_ratios": ["16:9", "9:16", "1:1"],
        "allowed_durations": ["5s", "10s"],
    },
    "jimeng": {
        "allowed_sizes": ["1080p"],
        "allowed_aspect_ratios": ["16:9", "9:16"],
        "allowed_durations": ["5s"],
    },
    "volcark": {
        "allowed_sizes": ["720p", "1080p"],
        "allowed_aspect_ratios": ["16:9", "9:16"],
        "allowed_durations": ["5s"],
    },
}


def _normalize_aspect_ratios(config: dict[str, Any]) -> list[str]:
    ratios = config.get("allowed_aspect_ratios") or []
    return [str(ratio) for ratio in ratios if ratio]


def _normalize_sizes(config: dict[str, Any]) -> list[str]:
    sizes = config.get("allowed_sizes") or []
    return [str(size) for size in sizes if size]


def _normalize_durations(config: dict[str, Any], mode: str) -> list[int]:
    durations_by_mode = config.get("allowed_durations_by_mode") or {}
    mode_durations = durations_by_mode.get(mode) if isinstance(durations_by_mode, dict) else None
    source = mode_durations or config.get("allowed_durations") or []

    normalized: list[int] = []
    for value in source:
        if isinstance(value, int):
            normalized.append(value)
            continue
        raw = str(value).strip().lower()
        if raw.endswith("s"):
            raw = raw[:-1]
        if raw.isdigit():
            normalized.append(int(raw))

    if normalized:
        return normalized

    min_duration = config.get("min_duration")
    max_duration = config.get("max_duration")
    if isinstance(min_duration, int) and isinstance(max_duration, int) and min_duration <= max_duration:
        return list(range(min_duration, max_duration + 1))

    return normalized


def _resolution_rank(value: str) -> float:
    normalized = str(value).strip().lower()
    if normalized.endswith("k"):
        try:
            return float(normalized[:-1]) * 1000
        except ValueError:
            return -1
    if normalized.endswith("p"):
        digits = "".join(ch for ch in normalized if ch.isdigit())
        return float(digits) if digits else -1
    return -1


def _find_model_config(provider_code: str | None, model_name: str, media_type: str) -> dict[str, Any]:
    model_buckets = {
        "image": "text2image",
        "video": "text2video",
    }
    bucket = model_buckets[media_type]

    registry = build_provider_registry()
    providers_to_check: list[dict[str, Any]] = []
    if provider_code and provider_code in registry:
        providers_to_check.append(registry[provider_code])
    providers_to_check.extend(
        provider
        for code, provider in registry.items()
        if code != provider_code
    )

    for provider in providers_to_check:
        for model in provider.get("models", {}).get(bucket, []):
            if model.get("model_name") == model_name:
                return dict(model.get("config") or {})

    if media_type == "image":
        return dict(IMAGE_PROVIDER_FALLBACKS.get(provider_code or "", {}))
    return dict(VIDEO_PROVIDER_FALLBACKS.get(provider_code or "", {}))


def _preferred_aspect_ratio(allowed_ratios: list[str], preferred: str) -> str:
    if preferred in allowed_ratios:
        return preferred
    if allowed_ratios:
        return allowed_ratios[0]
    return preferred


def resolve_harness_image_defaults(model_name: str, provider_code: str | None) -> dict[str, str]:
    config = _find_model_config(provider_code, model_name, "image")
    return resolve_image_generation_selection(
        config=config,
        aspect_ratio="1:1",
        resolution=max(_normalize_sizes(config), key=_resolution_rank) if _normalize_sizes(config) else "1K",
        preferred_aspect_ratio="1:1",
        preferred_resolution="1K",
    )


def resolve_harness_video_defaults(
    model_name: str,
    provider_code: str | None,
    *,
    has_reference_image: bool = False,
) -> dict[str, str | int]:
    config = _find_model_config(provider_code, model_name, "video")
    sizes = _normalize_sizes(config)
    allowed_ratios = _normalize_aspect_ratios(config)
    durations = _normalize_durations(config, "image" if has_reference_image else "text")

    resolution = max(sizes, key=_resolution_rank) if sizes else "720p"
    aspect_ratio = _preferred_aspect_ratio(allowed_ratios, "16:9")
    duration = min(durations) if durations else 5

    return {
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "duration": duration,
    }
