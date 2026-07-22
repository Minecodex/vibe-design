"""Amount billing helpers derived from the builtin provider registry."""

from __future__ import annotations

import math

from app.core.providers import LINGYAAI_BUILTIN_MODELS, PROVIDER_REGISTRY


def _iter_builtin_models() -> list[dict]:
    builtin_models = PROVIDER_REGISTRY["builtin"]["models"]
    models: list[dict] = []
    for model_type in ("text2image", "text2video", "multimodal"):
        models.extend(builtin_models.get(model_type, []))
    return models


def _iter_builtin_label_models() -> list[dict]:
    models = _iter_builtin_models()
    for model_type in ("text2image", "text2video", "multimodal"):
        models.extend(LINGYAAI_BUILTIN_MODELS.get(model_type, []))
    return models


def _build_pricing_rules() -> dict[str, dict]:
    pricing: dict[str, dict] = {}

    for model in _iter_builtin_models():
        config = model.get("config", {})
        pricing_mode = config.get("pricing_mode")
        prices = config.get("pricing_cents")
        if pricing_mode and prices:
            pricing[model["model_name"]] = {
                "pricing_mode": pricing_mode,
                "prices": prices,
            }

    return pricing


def _build_model_labels() -> dict[str, str]:
    return {
        model["model_name"]: model["label"]
        for model in _iter_builtin_label_models()
    }


PRICING_RULES: dict[str, dict] = _build_pricing_rules()
MODEL_LABELS: dict[str, str] = _build_model_labels()


def calculate_amount_cents(
    model_name: str,
    resolution: str | None = None,
    duration: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    task_type: str | None = None,
    audio: bool | None = None,
) -> int:
    pricing = PRICING_RULES.get(model_name)
    if not pricing:
        return 0

    mode = pricing["pricing_mode"]
    prices = pricing["prices"]

    if mode == "flat":
        return int(prices.get("flat", 0) or 0)

    if mode == "per_resolution":
        if not resolution:
            return int(next(iter(prices.values()), 0) or 0)
        return int(prices.get(resolution, 0) or 0)

    if mode == "per_second":
        effective_resolution = resolution
        if model_name == "kling-v3" and resolution:
            normalized_resolution = resolution.lower()
            base_resolution = normalized_resolution.replace("_audio", "").replace("_video", "")
            if audio and f"{base_resolution}_audio" in prices:
                effective_resolution = f"{base_resolution}_audio"
            elif task_type == "image2video" and f"{base_resolution}_video" in prices:
                effective_resolution = f"{base_resolution}_video"
            elif normalized_resolution in prices:
                effective_resolution = normalized_resolution
            else:
                effective_resolution = base_resolution
        if not resolution or not duration:
            rate = int(next(iter(prices.values()), 0) or 0)
            return rate * (duration or 5)
        return int(prices.get(effective_resolution or resolution, 0) or 0) * duration

    if mode == "per_token":
        if input_tokens is None and output_tokens is None:
            return 1
        input_rate = int(prices.get("input", 0) or 0)
        output_rate = int(prices.get("output", 0) or 0)
        cost = (input_tokens or 0) / 1_000_000 * input_rate + (output_tokens or 0) / 1_000_000 * output_rate
        return max(1, math.ceil(cost))

    return 0


def get_model_label(model_name: str) -> str:
    return MODEL_LABELS.get(model_name, model_name)


def get_model_pricing(model_name: str) -> dict | None:
    return PRICING_RULES.get(model_name)
