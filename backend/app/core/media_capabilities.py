from __future__ import annotations

from typing import Any

from app.core.media_constraints import pick_closest_aspect_ratio, pick_closest_duration, _pick_closest_resolution
from app.core.providers import build_provider_registry


def get_model_entry(provider_code: str | None, bucket: str, model_name: str | None) -> dict[str, Any] | None:
    if not provider_code or not model_name:
        return None
    provider = build_provider_registry().get(provider_code)
    if not provider:
        return None
    for entry in provider.get("models", {}).get(bucket, []):
        if entry.get("model_name") == model_name:
            return entry
    return None


def get_model_config(provider_code: str | None, bucket: str, model_name: str | None) -> dict[str, Any]:
    entry = get_model_entry(provider_code, bucket, model_name)
    return dict(entry.get("config") or {}) if entry else {}


def get_model_label(provider_code: str | None, bucket: str, model_name: str | None) -> str:
    entry = get_model_entry(provider_code, bucket, model_name)
    if entry is None:
        return str(model_name or "")
    return str(entry.get("label") or model_name or "")


def get_allowed_image_ratios_for_resolution(config: dict[str, Any] | None, resolution: str | None) -> list[str]:
    config = config or {}
    ratios_by_size = config.get("allowed_aspect_ratios_by_size") or {}
    if resolution and isinstance(ratios_by_size, dict):
        scoped = ratios_by_size.get(str(resolution))
        if isinstance(scoped, list) and scoped:
            return [str(ratio) for ratio in scoped if ratio]
    return [str(ratio) for ratio in (config.get("allowed_aspect_ratios") or []) if ratio]


def get_allowed_video_durations(config: dict[str, Any] | None, *, has_reference_image: bool = False) -> list[int]:
    config = config or {}
    mode = "image" if has_reference_image else "text"
    durations_by_mode = config.get("allowed_durations_by_mode") or {}
    source = durations_by_mode.get(mode) if isinstance(durations_by_mode, dict) else None
    source = source or config.get("allowed_durations") or []

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
    return []


def resolve_video_generation_selection(
    *,
    config: dict[str, Any] | None,
    aspect_ratio: str | None,
    resolution: str | None,
    duration: int | None,
    has_reference_image: bool = False,
    preferred_aspect_ratio: str = "16:9",
    preferred_resolution: str = "720p",
    preferred_duration: int = 5,
) -> dict[str, str | int]:
    config = config or {}
    allowed_sizes = [str(size) for size in (config.get("allowed_sizes") or []) if size]
    resolved_resolution = _pick_closest_resolution(allowed_sizes, resolution, default_to_highest=True) or preferred_resolution
    allowed_ratios = [str(ratio) for ratio in (config.get("allowed_aspect_ratios") or []) if ratio]
    resolved_aspect_ratio = pick_closest_aspect_ratio(
        allowed_ratios,
        aspect_ratio,
        preferred_ratio=preferred_aspect_ratio,
    )
    allowed_durations = get_allowed_video_durations(config, has_reference_image=has_reference_image)
    resolved_duration = pick_closest_duration(allowed_durations, duration) or preferred_duration
    return {
        "aspect_ratio": resolved_aspect_ratio,
        "resolution": resolved_resolution,
        "duration": resolved_duration,
    }


def describe_image_model_constraints(model_name: str | None, provider_code: str | None) -> str:
    config = get_model_config(provider_code, "text2image", model_name)
    label = get_model_label(provider_code, "text2image", model_name)
    if not config:
        return "工具会根据当前模型自动选择兼容的分辨率、比例和限制条件，超出范围时自动收敛到接近的可用设置。"

    parts = [f"当前图片模型为 {label}。"]
    sizes = [str(size) for size in (config.get("allowed_sizes") or []) if size]
    if sizes:
        parts.append(f"支持分辨率: {', '.join(sizes)}。")
    ratios = [str(ratio) for ratio in (config.get("allowed_aspect_ratios") or []) if ratio]
    if ratios:
        parts.append(f"支持画幅比例: {', '.join(ratios)}。")
    ratios_by_size = config.get("allowed_aspect_ratios_by_size") or {}
    if isinstance(ratios_by_size, dict):
        scoped_parts = []
        for size, scoped_ratios in ratios_by_size.items():
            if isinstance(scoped_ratios, list) and scoped_ratios:
                scoped_parts.append(f"{size} 仅支持 {', '.join(str(r) for r in scoped_ratios)}")
        if scoped_parts:
            parts.append(f"特殊限制: {'；'.join(scoped_parts)}。")
    if model_name == "gpt-image-2":
        parts.append("GPT-Image-2 的 1K/2K/4K 是模型分辨率档位，4K 不等于 4096x4096 方图。")
    max_reference_images = config.get("max_reference_images")
    if isinstance(max_reference_images, int):
        if max_reference_images > 0:
            parts.append(f"最多支持 {max_reference_images} 张参考图。")
        else:
            parts.append("不支持参考图。")
    parts.append("如果分辨率、比例或输入限制不兼容，工具会自动调整到接近的可用设置。")
    return "".join(parts)


def describe_video_model_constraints(model_name: str | None, provider_code: str | None) -> str:
    config = get_model_config(provider_code, "text2video", model_name)
    label = get_model_label(provider_code, "text2video", model_name)
    if not config:
        return "工具会根据当前模型自动选择兼容的视频分辨率、比例、时长和输入限制，超出范围时自动收敛到接近的可用设置。"

    parts = [f"当前视频模型为 {label}。"]
    sizes = [str(size) for size in (config.get("allowed_sizes") or []) if size]
    if sizes:
        parts.append(f"支持分辨率: {', '.join(sizes)}。")
    ratios = [str(ratio) for ratio in (config.get("allowed_aspect_ratios") or []) if ratio]
    if ratios:
        parts.append(f"支持画幅比例: {', '.join(ratios)}。")
    durations = get_allowed_video_durations(config)
    if durations:
        parts.append(f"支持时长: {', '.join(f'{duration}s' for duration in durations)}。")
    max_image_inputs = config.get("max_image_inputs")
    if isinstance(max_image_inputs, int):
        if max_image_inputs > 0:
            parts.append(f"最多支持 {max_image_inputs} 张图片输入。")
        else:
            parts.append("不支持图片输入。")
    if config.get("supports_first_frame"):
        parts.append("支持首帧控制。")
    if config.get("supports_tail_frame"):
        parts.append("支持尾帧控制。")
    if config.get("supports_audio"):
        parts.append("支持音频生成。")
    if config.get("image_modes_conflict"):
        parts.append("参考图模式与首尾帧模式不能同时使用。")
    if config.get("disallow_manual_aspect_ratio_with_images"):
        parts.append("使用图片输入时会自动处理画幅比例。")
    parts.append("如果分辨率、比例、时长或输入限制不兼容，工具会自动调整到接近的可用设置。")
    return "".join(parts)


def build_image_tool_schema(provider_code: str | None, model_name: str | None) -> dict[str, Any]:
    config = get_model_config(provider_code, "text2image", model_name)
    return {
        "aspect_ratios": [str(ratio) for ratio in (config.get("allowed_aspect_ratios") or []) if ratio],
        "resolutions": [str(size) for size in (config.get("allowed_sizes") or []) if size],
        "description": describe_image_model_constraints(model_name, provider_code),
    }


def build_video_tool_schema(provider_code: str | None, model_name: str | None) -> dict[str, Any]:
    config = get_model_config(provider_code, "text2video", model_name)
    return {
        "aspect_ratios": [str(ratio) for ratio in (config.get("allowed_aspect_ratios") or []) if ratio],
        "resolutions": [str(size) for size in (config.get("allowed_sizes") or []) if size],
        "durations": [str(duration) for duration in get_allowed_video_durations(config)],
        "description": describe_video_model_constraints(model_name, provider_code),
        "supports_frame_images": bool(config.get("supports_first_frame") or config.get("supports_tail_frame")),
        "supports_reference_image_list": bool(config.get("supports_reference_image_list")),
        "supports_reference_video": bool(config.get("supports_reference_video")),
        "supports_reference_audio": bool(config.get("supports_reference_audio")),
        "supports_return_last_frame": bool(config.get("supports_return_last_frame")),
        "supports_generate_audio": bool(config.get("supports_audio")),
        "supports_kling_mode": bool(config.get("supports_kling_mode")),
        "supports_multi_shot": bool(config.get("supports_multi_shot")),
        "supports_element_list": bool(config.get("supports_element_list")),
    }
