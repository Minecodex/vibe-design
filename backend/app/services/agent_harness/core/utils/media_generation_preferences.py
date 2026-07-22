from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImageGenerationPreferences:
    resolution: str | None = None
    aspect_ratio: str | None = None


@dataclass(frozen=True)
class VideoGenerationPreferences:
    resolution: str | None = None
    aspect_ratio: str | None = None
    duration: int | None = None


def media_generation_model_key(provider_code: str | None, model_name: str | None) -> str | None:
    normalized_model = str(model_name or "").strip()
    if not normalized_model:
        return None
    normalized_provider = str(provider_code or "builtin").strip() or "builtin"
    return f"{normalized_provider}:{normalized_model}"


def resolve_image_generation_preferences(
    model_preferences: dict[str, Any] | None,
    *,
    provider_code: str | None,
    model_name: str | None,
) -> ImageGenerationPreferences:
    settings = _get_model_settings(model_preferences, "image", provider_code, model_name)
    return ImageGenerationPreferences(
        resolution=_clean_string(settings.get("resolution")),
        aspect_ratio=_clean_string(settings.get("aspect_ratio")),
    )


def resolve_video_generation_preferences(
    model_preferences: dict[str, Any] | None,
    *,
    provider_code: str | None,
    model_name: str | None,
) -> VideoGenerationPreferences:
    settings = _get_model_settings(model_preferences, "video", provider_code, model_name)
    return VideoGenerationPreferences(
        resolution=_clean_string(settings.get("resolution")),
        aspect_ratio=_clean_string(settings.get("aspect_ratio")),
        duration=_clean_duration(settings.get("duration")),
    )


def _get_model_settings(
    model_preferences: dict[str, Any] | None,
    media_type: str,
    provider_code: str | None,
    model_name: str | None,
) -> dict[str, Any]:
    if not isinstance(model_preferences, dict):
        return {}
    all_settings = model_preferences.get("media_generation_settings")
    if not isinstance(all_settings, dict):
        return {}
    typed_settings = all_settings.get(media_type)
    if not isinstance(typed_settings, dict):
        return {}
    model_key = media_generation_model_key(provider_code, model_name)
    if not model_key:
        return {}
    settings = typed_settings.get(model_key)
    return dict(settings) if isinstance(settings, dict) else {}


def _clean_string(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _clean_duration(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    raw = str(value or "").strip().lower()
    if raw.endswith("s"):
        raw = raw[:-1].strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except ValueError:
        return None
    return parsed if parsed > 0 else None
