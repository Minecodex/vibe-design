from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.core.media_dimensions import DIMENSION_POLICY_OLLAMA_GPT_IMAGE_2, DIMENSION_SOURCE_ESTIMATED

logger = logging.getLogger(__name__)
GPT_IMAGE_2_MAX_EDGE = 3840
GPT_IMAGE_2_MAX_PIXELS = 8_294_400
GPT_IMAGE_2_MIN_PIXELS = 655_360

DEFAULT_OLLAMA_IMAGE_CONFIG: dict[str, Any] = {
    "request_profile": "ollama_openai_image",
    "allowed_sizes": ["1K"],
    "allowed_aspect_ratios": ["1:1"],
    "supports_reference_image": False,
    "max_reference_images": 0,
    "response_format": "b64_json",
    "reference_mode": "edits",
    "pricing_mode": "flat",
    "pricing_cents": {"flat": 0},
    "dimension_policy": DIMENSION_POLICY_OLLAMA_GPT_IMAGE_2,
    "dimension_source": DIMENSION_SOURCE_ESTIMATED,
}

_ALLOWED_RESPONSE_FORMATS = {"url", "b64_json"}
_ALLOWED_REFERENCE_MODES = {"edits"}
_ALLOWED_QUALITIES = {"auto", "high", "medium", "low"}
_CONFIG_KEYS = {
    "sizes",
    "ratios",
    "reference",
    "max_refs",
    "response_format",
    "reference_mode",
    "quality",
}


def _split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def _parse_bool(value: str) -> bool | None:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def parse_ollama_image_generation_config(raw_config: str | None) -> dict[str, Any]:
    config = dict(DEFAULT_OLLAMA_IMAGE_CONFIG)
    parsed: dict[str, str] = {}

    for part in (raw_config or "").split(";"):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        normalized_key = key.strip().lower()
        if normalized_key not in _CONFIG_KEYS:
            logger.warning("Ignoring unsupported Ollama image generation config key: %s", normalized_key)
            continue
        parsed[normalized_key] = value.strip()

    if sizes := _split_list(parsed.get("sizes", "")):
        config["allowed_sizes"] = sizes
    if ratios := _split_list(parsed.get("ratios", "")):
        config["allowed_aspect_ratios"] = ratios

    if "reference" in parsed:
        reference = _parse_bool(parsed["reference"])
        if reference is None:
            logger.warning("Invalid Ollama image generation reference value; disabling references")
            reference = False
        config["supports_reference_image"] = reference

    if "max_refs" in parsed:
        try:
            config["max_reference_images"] = max(0, int(parsed["max_refs"]))
        except ValueError:
            logger.warning("Invalid Ollama image generation max_refs value; using default")

    if "response_format" in parsed:
        response_format = parsed["response_format"].lower()
        if response_format in _ALLOWED_RESPONSE_FORMATS:
            config["response_format"] = response_format
        else:
            logger.warning("Invalid Ollama image generation response_format: %s", response_format)

    if "reference_mode" in parsed:
        reference_mode = parsed["reference_mode"].lower()
        if reference_mode in _ALLOWED_REFERENCE_MODES:
            config["reference_mode"] = reference_mode
        else:
            logger.warning("Unsupported Ollama image generation reference_mode: %s", reference_mode)
            config["supports_reference_image"] = False
            config["max_reference_images"] = 0

    if "quality" in parsed:
        quality = parsed["quality"].lower()
        if quality in _ALLOWED_QUALITIES:
            config["quality"] = quality
        else:
            logger.warning("Invalid Ollama image generation quality: %s", quality)

    if not config.get("supports_reference_image"):
        config["max_reference_images"] = 0
    elif int(config.get("max_reference_images") or 0) <= 0:
        config["max_reference_images"] = 1

    return config


def get_ollama_image_generation_config() -> dict[str, Any]:
    return parse_ollama_image_generation_config(settings.OLLAMA_IMAGE_GENERATION_CONFIG)


def _floor_to_multiple(value: float, multiple: int = 16) -> int:
    return max(multiple, int(value // multiple) * multiple)


def _round_to_multiple(value: float, multiple: int = 16) -> int:
    return max(multiple, int(round(value / multiple)) * multiple)


def _parse_aspect_ratio(aspect_ratio: str | None) -> tuple[int, int] | None:
    raw = str(aspect_ratio or "").strip()
    left, sep, right = raw.partition(":")
    if not sep:
        return None
    try:
        width = int(left)
        height = int(right)
    except ValueError:
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _fits_gpt_image_2_size(width: int, height: int) -> bool:
    if width % 16 != 0 or height % 16 != 0:
        return False
    if max(width, height) > GPT_IMAGE_2_MAX_EDGE:
        return False
    pixels = width * height
    if pixels < GPT_IMAGE_2_MIN_PIXELS or pixels > GPT_IMAGE_2_MAX_PIXELS:
        return False
    return max(width, height) <= min(width, height) * 3


def _size_for_short_edge(short_edge: int, ratio_width: int, ratio_height: int) -> str:
    if ratio_width >= ratio_height:
        height = short_edge
        width = _round_to_multiple(short_edge * ratio_width / ratio_height)
    else:
        width = short_edge
        height = _round_to_multiple(short_edge * ratio_height / ratio_width)
    return f"{width}x{height}"


def _size_for_long_edge(long_edge: int, ratio_width: int, ratio_height: int) -> str:
    if ratio_width >= ratio_height:
        width = long_edge
        height = _round_to_multiple(long_edge * ratio_height / ratio_width)
    else:
        width = _round_to_multiple(long_edge * ratio_width / ratio_height)
        height = long_edge
    return f"{width}x{height}"


def _largest_valid_size_for_ratio(ratio_width: int, ratio_height: int) -> str:
    if ratio_width >= ratio_height:
        for width in range(GPT_IMAGE_2_MAX_EDGE, 0, -16):
            height = _floor_to_multiple(width * ratio_height / ratio_width)
            if _fits_gpt_image_2_size(width, height):
                return f"{width}x{height}"
    else:
        for height in range(GPT_IMAGE_2_MAX_EDGE, 0, -16):
            width = _floor_to_multiple(height * ratio_width / ratio_height)
            if _fits_gpt_image_2_size(width, height):
                return f"{width}x{height}"
    return "1024x1024"


def resolve_ollama_image_size(resolution: str | None, aspect_ratio: str | None) -> str:
    requested = str(resolution or "").strip()
    if not requested:
        requested = "1K"
    if requested.lower() == "auto" or "x" in requested.lower():
        return requested

    ratio = _parse_aspect_ratio(aspect_ratio) or (1, 1)
    ratio_width, ratio_height = ratio
    tier = requested.upper()
    if tier == "1K":
        return _size_for_short_edge(1024, ratio_width, ratio_height)
    if tier == "2K":
        return _size_for_long_edge(2048, ratio_width, ratio_height)
    if tier == "4K":
        return _largest_valid_size_for_ratio(ratio_width, ratio_height)
    return requested
