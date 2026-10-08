from app.core.providers import PROVIDER_REGISTRY, build_provider_registry


EXPECTED_BUILTIN_IMAGE_MODELS = {
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
    "imagen-4.0-apimart",
    "gpt-image-2",
    "doubao-seedream-4-5",
    "doubao-seedream-5-0-lite",
}

EXPECTED_BUILTIN_VIDEO_MODELS = {
    "kling-v2-6",
    "kling-v3",
    "doubao-seedance-1-5-pro",
    "doubao-seedance-2.0",
    "grok-imagine-1.0-video-apimart",
}

EXPECTED_BUILTIN_MULTIMODAL_MODELS = {
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview-thinking",
    "claude-opus-4-8",
    "claude-opus-4-6-thinking",
    "deepseek-v4-pro",
    "glm-5.1",
    "kimi-k2.5",
}


def test_builtin_registry_matches_approved_image_models():
    builtin_models = {
        entry["model_name"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2image"]
    }

    assert builtin_models == EXPECTED_BUILTIN_IMAGE_MODELS


def test_builtin_registry_matches_approved_video_models():
    builtin_models = {
        entry["model_name"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2video"]
    }

    assert builtin_models == EXPECTED_BUILTIN_VIDEO_MODELS


def test_builtin_registry_includes_grok_video_capability_config():
    by_model = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2video"]
    }

    grok_config = by_model["grok-imagine-1.0-video-apimart"]
    expected_grok_config = {
        "min_duration": 6,
        "max_duration": 30,
        "allowed_aspect_ratios": ["16:9", "9:16", "1:1", "3:2", "2:3"],
        "allowed_sizes": ["480p", "720p"],
        "supports_reference_image": True,
        "supports_reference_image_list": True,
        "supports_reference_video": False,
        "supports_reference_audio": False,
        "pricing_mode": "per_second",
        "pricing_cents": {"480p": 5, "720p": 10},
        "max_image_inputs": 7,
    }
    for key, value in expected_grok_config.items():
        assert grok_config[key] == value
    assert grok_config["dimension_policy"] == "video_short_side"
    assert grok_config["dimension_source"] == "estimated"


def test_builtin_registry_matches_approved_multimodal_models():
    builtin_models = {
        entry["model_name"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert builtin_models == EXPECTED_BUILTIN_MULTIMODAL_MODELS


def test_builtin_multimodal_registry_includes_token_limits_and_mode_capabilities():
    for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]:
        config = entry.get("config", {})
        assert isinstance(config.get("max_input_tokens"), int)
        assert config["max_input_tokens"] > 0
        assert isinstance(config.get("max_output_tokens"), int)
        assert config["max_output_tokens"] > 0
        assert isinstance(config.get("supports_fast_mode"), bool)
        assert isinstance(config.get("supports_thinking_mode"), bool)


def test_builtin_multimodal_registry_marks_glm_and_kimi_as_fast_only():
    by_model = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert by_model["glm-5.1"]["max_input_tokens"] == 204800
    assert by_model["glm-5.1"]["max_output_tokens"] == 128000
    assert by_model["glm-5.1"]["supports_fast_mode"] is True
    assert by_model["glm-5.1"]["supports_thinking_mode"] is False

    assert by_model["kimi-k2.5"]["max_input_tokens"] == 262144
    assert by_model["kimi-k2.5"]["max_output_tokens"] == 98304
    assert by_model["kimi-k2.5"]["supports_fast_mode"] is True
    assert by_model["kimi-k2.5"]["supports_thinking_mode"] is False


def test_builtin_multimodal_registry_marks_deepseek_v4_pro_as_fast_only():
    by_model = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert by_model["deepseek-v4-pro"]["max_input_tokens"] == 1_048_576
    assert by_model["deepseek-v4-pro"]["max_output_tokens"] == 128_000
    assert by_model["deepseek-v4-pro"]["supports_fast_mode"] is True
    assert by_model["deepseek-v4-pro"]["supports_thinking_mode"] is False
    assert "thinking_variant_of" not in by_model["deepseek-v4-pro"]


def test_builtin_multimodal_registry_marks_thinking_variants_as_plan_only():
    by_model = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert by_model["gemini-3-pro-preview-thinking"]["supports_fast_mode"] is False
    assert by_model["gemini-3-pro-preview-thinking"]["supports_thinking_mode"] is True

    assert by_model["claude-opus-4-6-thinking"]["supports_fast_mode"] is False
    assert by_model["claude-opus-4-6-thinking"]["supports_thinking_mode"] is True


def test_builtin_multimodal_registry_exposes_thinking_variant_links():
    by_model = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert by_model["gemini-3-pro-preview-thinking"]["thinking_variant_of"] == "gemini-3.1-pro-preview"
    assert by_model["claude-opus-4-6-thinking"]["thinking_variant_of"] == "claude-opus-4-8"


def test_builtin_registry_hides_requested_models():
    hidden_models = {
        "flux-2-flex",
        "flux-2-pro",
        "gpt-4o-image",
        "gemini-2.5-flash-image-preview",
        "gemini-2.5-pro",
        "gemini-2.5-pro-thinking",
        "flux-kontext-pro",
        "flux-kontext-max",
        "doubao-seedance-4-0",
        "veo3.1-fast",
        "veo3.1-quality",
        "sora-2",
        "sora-2-vip",
        "sora-2-preview",
        "sora-2-pro",
        "sora-2-pro-preview",
        "kling-v3-omni",
        "viduq3-pro",
        "MiniMax-Hailuo-2.3",
        "MiniMax-Hailuo-02",
        "wan2.6",
        "doubao-seedance-1-0-pro-fast",
        "doubao-seedance-1-0-pro-quality",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gpt-5-mini",
        "gpt-5-nano",
        "claude-haiku-4-5-20251001",
    }
    builtin_models = {
        entry["model_name"]
        for model_type in ("text2image", "text2video", "multimodal")
        for entry in PROVIDER_REGISTRY["builtin"]["models"][model_type]
    }

    assert hidden_models.isdisjoint(builtin_models)


def test_legacy_lingyaai_registry_keeps_native_model_contracts():
    from app.core import providers

    builtin = providers.LINGYAAI_BUILTIN_MODELS

    assert {
        entry["model_name"] for entry in builtin["text2image"]
    } == {
        "nano-banana-2",
        "nano-banana-pro",
        "gpt-image-2",
        "doubao-seedream-4-5-251128",
        "doubao-seedream-5-0-260128",
    }
    assert {
        entry["model_name"] for entry in builtin["text2video"]
    } == {
        "doubao-seedance-2-0-260128",
        "doubao-seedance-1-5-pro-251215",
        "kling-v3-video-generation",
    }
    assert {
        entry["model_name"] for entry in builtin["multimodal"]
    } == {
        "gemini-3.1-pro-preview",
        "gemini-3.1-pro-preview-thinking",
        "claude-opus-4-7",
        "claude-opus-4-6-thinking",
        "deepseek-v4-pro",
        "glm-5.1",
        "glm-5-thinking",
        "kimi-k2.6",
        "kimi-k2.6-thinking",
    }
    seedream_configs = {
        entry["model_name"]: entry["config"]
        for entry in builtin["text2image"]
        if entry["model_name"] in {"doubao-seedream-4-5-251128", "doubao-seedream-5-0-260128"}
    }
    assert seedream_configs["doubao-seedream-4-5-251128"]["allowed_aspect_ratios"] == []
    assert seedream_configs["doubao-seedream-5-0-260128"]["allowed_aspect_ratios"] == []
    assert all(
        entry.get("config", {}).get("request_profile")
        for bucket in builtin.values()
        for entry in bucket
    )


def test_legacy_lingyaai_chat_registry_marks_models_that_must_omit_temperature():
    from app.core import providers

    by_model = {
        entry["model_name"]: entry["config"]
        for entry in providers.LINGYAAI_BUILTIN_MODELS["multimodal"]
    }

    assert by_model["gemini-3.1-pro-preview"]["omit_temperature"] is True
    assert by_model["gemini-3.1-pro-preview-thinking"]["omit_temperature"] is True
    assert by_model["claude-opus-4-7"]["omit_temperature"] is True
    assert by_model["claude-opus-4-6-thinking"]["omit_temperature"] is True
    assert "omit_temperature" not in by_model["deepseek-v4-pro"]
