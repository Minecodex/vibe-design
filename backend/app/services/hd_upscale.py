from __future__ import annotations

from typing import Any

from app.core.feature_models import get_feature_image_model
from app.core.providers import build_provider_registry

DEFAULT_IMAGE_PROVIDER = "builtin"
DEFAULT_IMAGE_RESOLUTIONS = ("1K", "2K", "4K")
DEFAULT_IMAGE_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9")

_RESOLUTION_BASE = {
    "0.5K": 512,
    "1K": 1024,
    "2K": 2048,
    "3K": 3072,
    "4K": 4096,
}

def _get_default_image_model_name() -> str:
    return get_feature_image_model("hd_upscale")

def _get_default_image_model_constraints() -> tuple[tuple[str, ...], tuple[str, ...]]:
    provider = build_provider_registry().get(DEFAULT_IMAGE_PROVIDER, {})
    text2image_models = provider.get("models", {}).get("text2image", [])
    model_name = _get_default_image_model_name()

    for model in text2image_models:
        if model.get("model_name") != model_name:
            continue

        config = model.get("config", {})
        allowed_sizes = tuple(
            size for size in config.get("allowed_sizes", []) if isinstance(size, str) and size in _RESOLUTION_BASE
        )
        allowed_ratios = tuple(
            ratio for ratio in config.get("allowed_aspect_ratios", []) if isinstance(ratio, str) and ":" in ratio
        )
        return allowed_sizes or DEFAULT_IMAGE_RESOLUTIONS, allowed_ratios or DEFAULT_IMAGE_RATIOS

    return DEFAULT_IMAGE_RESOLUTIONS, DEFAULT_IMAGE_RATIOS

def _build_area_scaled_dimensions(base: int, ratio: str) -> tuple[int, int]:
    raw_width, raw_height = (int(part) for part in ratio.split(":"))
    ratio_value = raw_width / raw_height
    width = round((base * base * ratio_value) ** 0.5)
    height = round(width / ratio_value)
    return width, height

def select_hd_upscale_output(source_width: int, source_height: int) -> dict[str, Any]:
    allowed_resolutions, allowed_ratios = _get_default_image_model_constraints()
    safe_width = max(1, int(source_width))
    safe_height = max(1, int(source_height))
    source_ratio = safe_width / safe_height

    aspect_ratio = min(
        allowed_ratios,
        key=lambda candidate: abs((int(candidate.split(":")[0]) / int(candidate.split(":")[1])) - source_ratio),
    )
    
    max_res_value = max([_RESOLUTION_BASE[r] for r in allowed_resolutions])
    resolution = [r for r in allowed_resolutions if _RESOLUTION_BASE[r] == max_res_value][0]
    
    # But if source is close to 4k already, maybe we just use 4k. 
    # Requirement: "Nano banana2支持的4k分辨率和尺寸"
    width, height = _build_area_scaled_dimensions(_RESOLUTION_BASE[resolution], aspect_ratio)

    return {
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "width": width,
        "height": height
    }

def build_hd_upscale_prompt() -> str:
    return "upscale, 4k, hd, highly detailed, masterpieces, high resolution, original image content unchanged"
