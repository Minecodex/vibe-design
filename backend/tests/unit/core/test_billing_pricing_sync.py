import pytest

from app.api.v1.endpoints.providers import _inject_pricing, get_provider_registry
from app.core.billing_pricing import calculate_amount_cents, get_model_label, get_model_pricing
from app.core.providers import PROVIDER_REGISTRY

EXPECTED_PRICED_BUILTIN_MODELS = {
    "gemini-3.1-flash-image-preview-official",
    "gemini-3-pro-image-preview-official",
    "imagen-4.0-apimart",
    "gpt-image-2",
    "doubao-seedream-4-5",
    "doubao-seedream-5-0-lite",
    "kling-v2-6",
    "kling-v3",
    "doubao-seedance-1-5-pro",
    "doubao-seedance-2.0",
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview-thinking",
    "claude-opus-4-8",
    "claude-opus-4-6-thinking",
    "deepseek-v4-pro",
}


def test_all_approved_builtin_models_have_pricing_cents():
    missing = [
        model_name
        for model_name in sorted(EXPECTED_PRICED_BUILTIN_MODELS)
        if get_model_pricing(model_name) is None
    ]

    assert missing == []


def test_representative_builtin_models_expose_expected_pricing_modes():
    assert get_model_pricing("gemini-3.1-flash-image-preview-official")["pricing_mode"] == "per_resolution"
    assert get_model_pricing("gemini-3-pro-image-preview-official")["pricing_mode"] == "per_resolution"
    assert get_model_pricing("imagen-4.0-apimart")["pricing_mode"] == "flat"
    assert get_model_pricing("gpt-image-2")["pricing_mode"] == "per_resolution"
    assert get_model_pricing("kling-v2-6")["pricing_mode"] == "per_second"
    assert get_model_pricing("kling-v3")["pricing_mode"] == "per_second"
    assert get_model_pricing("doubao-seedance-2.0")["pricing_mode"] == "per_second"
    assert get_model_pricing("gemini-3.1-pro-preview")["pricing_mode"] == "per_token"
    assert get_model_pricing("deepseek-v4-pro")["pricing_mode"] == "per_token"


def test_lingyaai_builtin_model_ids_resolve_to_display_labels():
    assert get_model_label("doubao-seedream-4-5-251128") == "Seedream 4.5"
    assert get_model_label("doubao-seedance-2-0-260128") == "Seedance 2.0"


def test_builtin_registry_embeds_pricing_for_all_generation_models():
    missing = []
    for model_type in ("text2image", "text2video"):
        for entry in PROVIDER_REGISTRY["builtin"]["models"][model_type]:
            config = entry.get("config", {})
            if "pricing_cents" not in config or "pricing_mode" not in config:
                missing.append(entry["model_name"])

    assert missing == []


def test_inject_pricing_is_a_no_op_for_builtin_models():
    builtin_models = PROVIDER_REGISTRY["builtin"]["models"]

    assert _inject_pricing(builtin_models) == builtin_models


def test_multimodal_builtin_registry_embeds_pricing_cents():
    multimodal_configs = {
        entry["model_name"]: entry.get("config", {})
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["multimodal"]
    }

    assert multimodal_configs["gemini-3.1-pro-preview"]["pricing_mode"] == "per_token"
    assert multimodal_configs["gemini-3.1-pro-preview"]["pricing_cents"] == {
        "input": 1120,
        "output": 6720,
    }
    assert multimodal_configs["gemini-3-pro-preview-thinking"]["pricing_mode"] == "per_token"


def test_supported_claude_pricing_is_exposed_via_pricing_cents():
    assert get_model_pricing("claude-opus-4-8") == {
        "pricing_mode": "per_token",
        "prices": {"input": 2800, "output": 14000},
    }
    assert get_model_pricing("claude-opus-4-6-thinking") == {
        "pricing_mode": "per_token",
        "prices": {"input": 2800, "output": 14000},
    }


def test_deepseek_v4_pro_pricing_is_exposed_via_pricing_cents():
    assert get_model_pricing("deepseek-v4-pro") == {
        "pricing_mode": "per_token",
        "prices": {"input": 960, "output": 1920},
    }


def test_calculate_amount_cents_supports_representative_pricing_modes():
    assert calculate_amount_cents("imagen-4.0-apimart") == 28
    assert calculate_amount_cents("gpt-image-2", resolution="1K") == 4
    assert calculate_amount_cents("gpt-image-2", resolution="2K") == 8
    assert calculate_amount_cents("gpt-image-2", resolution="4K") == 13
    assert calculate_amount_cents("gemini-3-pro-image-preview-official", resolution="1K") == 75
    assert calculate_amount_cents("gemini-3-pro-image-preview-official", resolution="2K") == 75
    assert calculate_amount_cents("gemini-3-pro-image-preview-official", resolution="4K") == 134
    assert calculate_amount_cents("gemini-3.1-flash-image-preview-official", resolution="0.5K") == 38
    assert calculate_amount_cents("gemini-3.1-flash-image-preview-official", resolution="1K") == 38
    assert calculate_amount_cents("gemini-3.1-flash-image-preview-official", resolution="2K") == 56
    assert calculate_amount_cents("gemini-3.1-flash-image-preview-official", resolution="4K") == 84
    assert calculate_amount_cents("kling-v2-6", resolution="720p", duration=5) == 130
    assert calculate_amount_cents("kling-v2-6", resolution="1080p_audio", duration=5) == 525
    assert calculate_amount_cents("kling-v3", resolution="720p", duration=5) == 235
    assert calculate_amount_cents("kling-v3", resolution="1080p", duration=10) == 630
    assert calculate_amount_cents("kling-v3", resolution="1080p_audio", duration=5) == 470
    assert calculate_amount_cents("kling-v3", resolution="4k", duration=5) == 1500
    assert calculate_amount_cents("kling-v3", resolution="4k_audio", duration=5) == 1500
    assert calculate_amount_cents("kling-v3", resolution="720p", duration=5, task_type="image2video") == 235
    assert calculate_amount_cents("doubao-seedance-1-5-pro", resolution="480p", duration=5) == 70
    assert calculate_amount_cents("doubao-seedance-1-5-pro", resolution="720p", duration=5) == 155
    assert calculate_amount_cents("doubao-seedance-1-5-pro", resolution="1080p", duration=5) == 380
    assert calculate_amount_cents("doubao-seedance-2.0", resolution="480p", duration=5) == 255
    assert calculate_amount_cents("doubao-seedance-2.0", resolution="720p", duration=5) == 545
    assert calculate_amount_cents("doubao-seedance-2.0", resolution="1080p", duration=5) == 1230
    assert calculate_amount_cents("grok-imagine-1.0-video-apimart", resolution="480p", duration=5) == 25
    assert (
        calculate_amount_cents(
            "gemini-3.1-pro-preview",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        == 7840
    )
    assert (
        calculate_amount_cents(
            "deepseek-v4-pro",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
        )
        == 2880
    )


@pytest.mark.asyncio
async def test_provider_registry_endpoint_preserves_builtin_pricing_fields():
    registry = await get_provider_registry()
    imagen_entry = next(
        entry
        for entry in registry["builtin"]["models"]["text2image"]
        if entry["model_name"] == "imagen-4.0-apimart"
    )
    gpt_image_entry = next(
        entry
        for entry in registry["builtin"]["models"]["text2image"]
        if entry["model_name"] == "gpt-image-2"
    )
    image_entry = next(
        entry
        for entry in registry["builtin"]["models"]["text2image"]
        if entry["model_name"] == "gemini-3-pro-image-preview-official"
    )
    video_entry = next(
        entry
        for entry in registry["builtin"]["models"]["text2video"]
        if entry["model_name"] == "kling-v2-6"
    )
    kling_v3_entry = next(
        entry
        for entry in registry["builtin"]["models"]["text2video"]
        if entry["model_name"] == "kling-v3"
    )
    seedance_2_entry = next(
        entry
        for entry in registry["builtin"]["models"]["text2video"]
        if entry["model_name"] == "doubao-seedance-2.0"
    )
    multimodal_entry = next(
        entry
        for entry in registry["builtin"]["models"]["multimodal"]
        if entry["model_name"] == "gemini-3.1-pro-preview"
    )

    assert imagen_entry["config"]["pricing_mode"] == "flat"
    assert imagen_entry["config"]["pricing_cents"] == {"flat": 28}
    assert gpt_image_entry["config"]["pricing_mode"] == "per_resolution"
    assert gpt_image_entry["config"]["pricing_cents"] == {"1K": 4, "2K": 8, "4K": 13}
    assert image_entry["config"]["pricing_mode"] == "per_resolution"
    assert image_entry["config"]["pricing_cents"] == {"1K": 75, "2K": 75, "4K": 134}
    assert video_entry["config"]["pricing_mode"] == "per_second"
    assert video_entry["config"]["pricing_cents"]["720p"] == 26
    assert video_entry["config"]["pricing_cents"]["1080p_audio"] == 105
    assert kling_v3_entry["config"]["pricing_mode"] == "per_second"
    assert kling_v3_entry["config"]["allowed_sizes"] == [
        "720p",
        "720p_audio",
        "1080p",
        "1080p_audio",
        "4k",
        "4k_audio",
    ]
    assert kling_v3_entry["config"]["pricing_cents"] == {
        "720p": 47,
        "720p_audio": 71,
        "1080p": 63,
        "1080p_audio": 94,
        "4k": 300,
        "4k_audio": 300,
    }
    assert seedance_2_entry["config"]["pricing_mode"] == "per_second"
    assert seedance_2_entry["config"]["allowed_sizes"] == ["480p", "720p", "1080p"]
    assert seedance_2_entry["config"]["pricing_cents"] == {"480p": 51, "720p": 109, "1080p": 246}
    assert seedance_2_entry["config"]["uploaded_video_pricing_cents"] == {"480p": 28, "720p": 61}
    assert multimodal_entry["config"]["pricing_mode"] == "per_token"
    assert multimodal_entry["config"]["pricing_cents"]["input"] == 1120


@pytest.mark.asyncio
async def test_provider_registry_endpoint_exposes_deepseek_v4_pro_builtin_fields():
    registry = await get_provider_registry()
    deepseek_entry = next(
        entry
        for entry in registry["builtin"]["models"]["multimodal"]
        if entry["model_name"] == "deepseek-v4-pro"
    )

    assert deepseek_entry["config"]["pricing_mode"] == "per_token"
    assert deepseek_entry["config"]["pricing_cents"] == {"input": 960, "output": 1920}
    assert deepseek_entry["config"]["max_input_tokens"] == 1_000_000
    assert deepseek_entry["config"]["max_output_tokens"] == 384_000
    assert deepseek_entry["config"]["supports_fast_mode"] is True
    assert deepseek_entry["config"]["supports_thinking_mode"] is False

