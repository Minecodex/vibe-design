from __future__ import annotations

from app.core.feature_models import get_feature_image_model
from app.core.providers import build_provider_registry

DEFAULT_IMAGE_PROVIDER = "builtin"
DEFAULT_IMAGE_RESOLUTIONS = ("2K", "3K")
DEFAULT_IMAGE_RATIOS = ("1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "21:9")
_RESOLUTION_BASE = {
    "2K": 2048,
    "3K": 3072,
    "4K": 4096,
}


def _get_image_model_constraints(feature_name: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    provider = build_provider_registry().get(DEFAULT_IMAGE_PROVIDER, {})
    text2image_models = provider.get("models", {}).get("text2image", [])
    model_name = get_feature_image_model(feature_name)

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


def select_image_output(source_width: int, source_height: int, *, feature_name: str) -> dict[str, str]:
    allowed_resolutions, allowed_ratios = _get_image_model_constraints(feature_name)
    safe_width = max(1, int(source_width))
    safe_height = max(1, int(source_height))
    source_ratio = safe_width / safe_height
    source_long_edge = max(safe_width, safe_height)

    aspect_ratio = min(
        allowed_ratios,
        key=lambda candidate: abs((int(candidate.split(":")[0]) / int(candidate.split(":")[1])) - source_ratio),
    )
    candidates = []
    for resolution in allowed_resolutions:
        width, height = _build_area_scaled_dimensions(_RESOLUTION_BASE[resolution], aspect_ratio)
        candidates.append((resolution, max(width, height)))

    non_upscaled = [candidate for candidate in candidates if candidate[1] <= source_long_edge]
    resolution_pool = non_upscaled or [min(candidates, key=lambda candidate: candidate[1])]
    resolution = min(resolution_pool, key=lambda candidate: abs(candidate[1] - source_long_edge))[0]
    return {"aspect_ratio": aspect_ratio, "resolution": resolution}
