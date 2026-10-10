from app.core.default_models import DEFAULT_IMAGE_MODEL


def test_get_feature_image_model_returns_configured_override():
    from app.core import feature_models

    original = feature_models.FEATURE_IMAGE_MODELS.copy()
    try:
        feature_models.FEATURE_IMAGE_MODELS.clear()
        feature_models.FEATURE_IMAGE_MODELS.update(
            {
                "erase": "erase-model",
                "text_redraw": "redraw-model",
                "element_edit": "element-model",
            }
        )

        assert feature_models.get_feature_image_model("erase") == "erase-model"
        assert feature_models.get_feature_image_model("text_redraw") == "redraw-model"
        assert feature_models.get_feature_image_model("element_edit") == "element-model"
    finally:
        feature_models.FEATURE_IMAGE_MODELS.clear()
        feature_models.FEATURE_IMAGE_MODELS.update(original)


def test_get_feature_image_model_falls_back_to_default():
    from app.core import feature_models

    original = feature_models.FEATURE_IMAGE_MODELS.copy()
    try:
        feature_models.FEATURE_IMAGE_MODELS.clear()

        assert feature_models.get_feature_image_model("erase") == DEFAULT_IMAGE_MODEL
        assert feature_models.get_feature_image_model("unknown_feature") == DEFAULT_IMAGE_MODEL
    finally:
        feature_models.FEATURE_IMAGE_MODELS.clear()
        feature_models.FEATURE_IMAGE_MODELS.update(original)


def test_get_feature_image_model_uses_builtin_provider_override():
    from app.core import feature_models

    original_models = feature_models.FEATURE_IMAGE_MODELS.copy()
    original_overrides = {
        feature_name: overrides.copy()
        for feature_name, overrides in feature_models.FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES.items()
    }
    try:
        feature_models.FEATURE_IMAGE_MODELS.clear()
        feature_models.FEATURE_IMAGE_MODELS.update({"hd_upscale": "apimart-image-model"})
        feature_models.FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES.clear()
        feature_models.FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES.update(
            {"hd_upscale": {"lingyaai": "nano-banana-2"}}
        )

        assert feature_models.get_feature_image_model("hd_upscale") == "apimart-image-model"
        assert (
            feature_models.get_feature_image_model("hd_upscale", builtin_provider_code="lingyaai")
            == "nano-banana-2"
        )
    finally:
        feature_models.FEATURE_IMAGE_MODELS.clear()
        feature_models.FEATURE_IMAGE_MODELS.update(original_models)
        feature_models.FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES.clear()
        feature_models.FEATURE_IMAGE_MODEL_PROVIDER_OVERRIDES.update(original_overrides)


def test_configured_lingyaai_feature_models_use_native_image_model():
    from app.core import feature_models

    for feature_name in ["erase", "text_redraw", "element_edit", "hd_upscale", "spatial_angle"]:
        assert (
            feature_models.get_feature_image_model(feature_name, builtin_provider_code="lingyaai")
            == "nano-banana-2"
        )


def test_builtin_model_aliases_resolve_between_apimart_and_lingyaai():
    from app.core.providers import resolve_builtin_model_name_for_provider

    assert (
        resolve_builtin_model_name_for_provider(
            "text2image",
            "gemini-3.1-flash-image-preview",
            builtin_provider_code="lingyaai",
        )
        == "nano-banana-2"
    )
    assert (
        resolve_builtin_model_name_for_provider(
            "text2image",
            "nano-banana-2",
            builtin_provider_code="apimart",
        )
        == "gemini-3.1-flash-image-preview"
    )
    assert (
        resolve_builtin_model_name_for_provider(
            "text2video",
            "kling-v3",
            builtin_provider_code="lingyaai",
        )
        == "kling-v3-video-generation"
    )
    assert (
        resolve_builtin_model_name_for_provider(
            "multimodal",
            "kimi-k2.5",
            builtin_provider_code="lingyaai",
        )
        == "kimi-k2.6"
    )
