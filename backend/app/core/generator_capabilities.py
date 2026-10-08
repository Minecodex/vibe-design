from __future__ import annotations

from typing import Any, Literal

from app.core.providers import (
    PROVIDER_REGISTRY,
    build_provider_registry,
    resolve_builtin_model_name_for_provider,
)


def _parse_duration_value(value: str | int) -> int:
    if isinstance(value, int):
        return value
    if value.endswith("s"):
        return int(value[:-1])
    return int(value)


def _build_image_model_capabilities(registry: dict[str, dict] | None = None) -> dict[str, dict[str, Any]]:
    registry = registry or PROVIDER_REGISTRY
    capabilities: dict[str, dict[str, Any]] = {}
    for model in registry["builtin"]["models"].get("text2image", []):
        config = model.get("config", {})
        if "max_reference_images" in config:
            capabilities[model["model_name"]] = {
                "max_reference_images": config["max_reference_images"],
            }
    return capabilities


def _build_video_model_capabilities(registry: dict[str, dict] | None = None) -> dict[str, dict[str, Any]]:
    registry = registry or PROVIDER_REGISTRY
    capabilities: dict[str, dict[str, Any]] = {}
    for model in registry["builtin"]["models"].get("text2video", []):
        config = model.get("config", {})
        capability: dict[str, Any] = {}

        for key in (
            "max_image_inputs",
            "disallow_manual_aspect_ratio_with_images",
            "disallow_reference_mode",
            "supports_first_frame",
            "supports_tail_frame",
            "allowed_durations_by_mode",
            "image_modes_conflict",
            "min_duration",
            "max_duration",
            "supports_audio",
            "supports_reference_video",
            "supports_reference_audio",
            "audio_allowed_sizes",
            "tail_frame_allowed_sizes",
            "requires_first_frame_for_tail_frame",
            "audio_tail_frame_mutually_exclusive",
        ):
            if key in config:
                capability[key] = config[key]

        if "allowed_durations" in config:
            capability["allowed_durations"] = [
                _parse_duration_value(value)
                for value in config["allowed_durations"]
            ]

        if capability:
            capabilities[model["model_name"]] = capability

    return capabilities


IMAGE_MODEL_CAPABILITIES: dict[str, dict[str, Any]] = _build_image_model_capabilities()
VIDEO_MODEL_CAPABILITIES: dict[str, dict[str, Any]] = _build_video_model_capabilities()


def get_image_model_capability(model_name: str, provider_code: str | None = None) -> dict[str, Any]:
    if provider_code == "builtin":
        model_name = resolve_builtin_model_name_for_provider("text2image", model_name)
        return _build_image_model_capabilities(build_provider_registry()).get(model_name, {})
    return IMAGE_MODEL_CAPABILITIES.get(model_name, {})


def get_video_model_capability(model_name: str, provider_code: str | None = None) -> dict[str, Any]:
    if provider_code == "builtin":
        model_name = resolve_builtin_model_name_for_provider("text2video", model_name)
        return _build_video_model_capabilities(build_provider_registry()).get(model_name, {})
    return VIDEO_MODEL_CAPABILITIES.get(model_name, {})


VideoInputMode = Literal["text", "image"]


def normalize_image_urls(*values: str | None) -> list[str]:
    return [value for value in values if value]


def get_video_input_mode(image_urls: list[str] | None = None) -> VideoInputMode:
    return "image" if image_urls else "text"


def get_allowed_video_durations(
    model_name: str,
    image_urls: list[str] | None = None,
    provider_code: str | None = None,
) -> list[int] | None:
    capability = get_video_model_capability(model_name, provider_code)
    mode = get_video_input_mode(image_urls)
    duration_overrides = capability.get("allowed_durations_by_mode", {})
    if duration_overrides.get(mode):
        return duration_overrides[mode]
    min_duration = capability.get("min_duration")
    max_duration = capability.get("max_duration")
    if isinstance(min_duration, int) and isinstance(max_duration, int) and min_duration <= max_duration:
        return list(range(min_duration, max_duration + 1))
    return capability.get("allowed_durations")


def normalize_video_resolution(value: str | None, default: str = "720p") -> str:
    raw = str(value or default).strip().lower()
    return raw or default


def is_audio_resolution(value: str | None) -> bool:
    return normalize_video_resolution(value).endswith("_audio")
