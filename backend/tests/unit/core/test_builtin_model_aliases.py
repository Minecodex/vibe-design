"""Canonical model IDs must remain usable by defaults and stored legacy tasks."""
import pytest

from app.core.billing_pricing import calculate_amount_cents, get_model_pricing
from app.core.default_models import DEFAULT_IMAGE_MODEL
from app.core.feature_models import get_feature_image_model
from app.core.providers import (
    BUILTIN_PROVIDER_MODEL_NAME_ALIASES,
    PROVIDER_REGISTRY,
    resolve_builtin_model_name_for_provider,
)


def test_default_and_feature_models_exist_in_the_builtin_registry():
    supported = {
        entry["model_name"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2image"]
    }
    assert DEFAULT_IMAGE_MODEL in supported
    for feature in ("erase", "text_redraw", "element_edit", "hd_upscale", "spatial_angle"):
        assert get_feature_image_model(feature) in supported


def test_apimart_aliases_all_resolve_to_supported_models():
    for bucket, aliases in BUILTIN_PROVIDER_MODEL_NAME_ALIASES["apimart"].items():
        supported = {
            entry["model_name"]
            for entry in PROVIDER_REGISTRY["builtin"]["models"][bucket]
        }
        for alias in aliases:
            assert resolve_builtin_model_name_for_provider(bucket, alias) in supported


@pytest.mark.parametrize("alias,canonical", [
    ("gemini-3.1-flash-image-preview-official", "gemini-3.1-flash-image-preview"),
    ("nano-banana-2", "gemini-3.1-flash-image-preview"),
    ("gemini-3-pro-image-preview-official", "gemini-3-pro-image-preview"),
])
def test_legacy_image_ids_keep_the_canonical_price(alias, canonical):
    assert get_model_pricing(alias) == get_model_pricing(canonical)
    assert calculate_amount_cents(alias, resolution="4K") == calculate_amount_cents(
        canonical, resolution="4K",
    )
