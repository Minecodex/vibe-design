"""Feature-scoped image model overrides loaded from YAML."""

from pathlib import Path

import yaml

from app.core.default_models import DEFAULT_IMAGE_MODEL
from app.core.providers import get_active_builtin_provider_code, resolve_builtin_model_name_for_provider

_YAML_PATH = Path(__file__).with_suffix(".yaml")


def _load_feature_image_models() -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    if not _YAML_PATH.exists():
        return {}, {}

    with open(_YAML_PATH, encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    image_features = raw.get("image_features", {})
    if not isinstance(image_features, dict):
        return {}, {}

    feature_models: dict[str, str] = {}
    provider_overrides: dict[str, dict[str, str]] = {}
    for feature_name, config in image_features.items():
        if not isinstance(feature_name, str) or not isinstance(config, dict):
            continue
        model_name = config.get("model_name")
        if isinstance(model_name, str) and model_name.strip():
            feature_models[feature_name] = model_name.strip()
        raw_overrides = config.get("builtin_provider_model_names")
        if isinstance(raw_overrides, dict):
            normalized = {
                str(provider_code).strip().lower(): model.strip()
                for provider_code, model in raw_overrides.items()
                if isinstance(provider_code, str) and isinstance(model, str) and model.strip()
            }
            if normalized:
                provider_overrides[feature_name] = normalized
    return feature_models, provider_overrides


FEATURE_IMAGE_MODELS, FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES = _load_feature_image_models()


def get_feature_image_model(feature_name: str, *, builtin_provider_code: str | None = None) -> str:
    provider_code = (builtin_provider_code or get_active_builtin_provider_code()).strip().lower()
    provider_model = FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES.get(feature_name, {}).get(provider_code)
    return resolve_builtin_model_name_for_provider(
        "text2image",
        provider_model or FEATURE_IMAGE_MODELS.get(feature_name, DEFAULT_IMAGE_MODEL),
        builtin_provider_code=provider_code,
    )
