from __future__ import annotations

from typing import Any

from app.core.media_capabilities import get_allowed_image_ratios_for_resolution
from app.core.media_constraints import pick_closest_aspect_ratio, _pick_closest_resolution


def resolve_image_generation_selection(
    *,
    config: dict[str, Any] | None,
    aspect_ratio: str | None,
    resolution: str | None,
    preferred_aspect_ratio: str = "1:1",
    preferred_resolution: str = "1K",
) -> dict[str, str]:
    config = config or {}
    allowed_sizes = [str(size) for size in (config.get("allowed_sizes") or []) if size]
    resolved_resolution = _pick_closest_resolution(allowed_sizes, resolution, default_to_highest=True) or str(resolution or preferred_resolution)

    allowed_ratios = get_allowed_image_ratios_for_resolution(config, resolved_resolution)
    resolved_aspect_ratio = pick_closest_aspect_ratio(
        allowed_ratios,
        str(aspect_ratio or ""),
        preferred_ratio=preferred_aspect_ratio,
    )

    return {
        "aspect_ratio": resolved_aspect_ratio,
        "resolution": resolved_resolution,
    }
