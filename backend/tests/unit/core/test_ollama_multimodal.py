from app.core import default_models
from app.core.config import settings
from app.core.ollama_image_config import (
    parse_ollama_image_generation_config,
    resolve_ollama_image_size,
)
from app.core.ollama_credentials import (
    get_ollama_image_api_key,
    get_ollama_multimodal_api_key,
)
from app.core.providers import build_provider_registry

GPT_IMAGE_2_RATIOS = [
    "1:1",
    "16:9",
    "9:16",
    "2:1",
    "1:2",
    "4:3",
    "3:4",
    "3:2",
    "2:3",
    "5:4",
    "4:5",
    "21:9",
    "9:21",
    "3:1",
    "1:3",
]
from app.services.multimodal_service import get_multimodal_model_config


def test_build_provider_registry_omits_ollama_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_ENABLED", False)

    registry = build_provider_registry()

    assert "ollama" not in registry


def test_ollama_api_keys_use_dedicated_image_key_then_ollama_api_key_fallback(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "legacy-key")
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_API_KEY", "image-key")

    assert get_ollama_multimodal_api_key() == "legacy-key"
    assert get_ollama_image_api_key() == "image-key"

    monkeypatch.setattr(settings, "OLLAMA_IMAGE_API_KEY", "")

    assert get_ollama_image_api_key() == "legacy-key"


def test_ollama_multimodal_key_preserves_legacy_api_key_fallback(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_API_KEY", "legacy-key")
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_API_KEY", "")

    assert get_ollama_multimodal_api_key() == "legacy-key"
    assert get_ollama_image_api_key() == "legacy-key"


def test_build_provider_registry_injects_ollama_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr(settings, "OLLAMA_MAX_INPUT_TOKENS", 123456)
    monkeypatch.setattr(settings, "OLLAMA_MAX_OUTPUT_TOKENS", 4096)

    registry = build_provider_registry()

    assert registry["ollama"]["is_builtin"] is True
    assert registry["ollama"]["models"]["multimodal"] == [
        {
            "model_name": "gemma4:e4b",
            "label": "Ollama (gemma4:e4b)",
            "config": {
                "pricing_mode": "flat",
                "pricing_cents": {"flat": 0},
                "max_input_tokens": 123456,
                "max_output_tokens": 4096,
                "supports_fast_mode": True,
                "supports_thinking_mode": True,
            },
        }
    ]


def test_build_provider_registry_injects_ollama_text2image_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_MODEL", "gpt-image-2")
    monkeypatch.setattr(
        settings,
        "OLLAMA_IMAGE_GENERATION_CONFIG",
        "sizes=1K|2K|4K;ratios=1:1|16:9|9:16|2:1|1:2|4:3|3:4|3:2|2:3|5:4|4:5|21:9|9:21|3:1|1:3;reference=true;max_refs=16;response_format=url;reference_mode=edits",
    )

    registry = build_provider_registry()

    assert registry["ollama"]["is_builtin"] is True
    assert registry["ollama"]["tags"] == ["TEXT2IMAGE"]
    assert registry["ollama"]["models"]["text2image"] == [
        {
            "model_name": "gpt-image-2",
            "label": "Ollama Image (gpt-image-2)",
            "config": {
                "request_profile": "ollama_openai_image",
                "allowed_sizes": ["1K", "2K", "4K"],
                "allowed_aspect_ratios": GPT_IMAGE_2_RATIOS,
                "supports_reference_image": True,
                "max_reference_images": 16,
                "response_format": "url",
                "reference_mode": "edits",
                "pricing_mode": "flat",
                "pricing_cents": {"flat": 0},
                "dimension_policy": "ollama_gpt_image_2",
                "dimension_source": "estimated",
            },
        }
    ]


def test_parse_ollama_image_generation_config_rejects_unsupported_reference_mode():
    config = parse_ollama_image_generation_config(
        "sizes=1K|2K;ratios=1:1;reference=true;max_refs=4;response_format=url;reference_mode=generations_reference_images;unknown=value"
    )

    assert config["allowed_sizes"] == ["1K", "2K"]
    assert config["allowed_aspect_ratios"] == ["1:1"]
    assert config["response_format"] == "url"
    assert config["reference_mode"] == "edits"
    assert config["supports_reference_image"] is False
    assert config["max_reference_images"] == 0


def test_parse_ollama_image_generation_config_invalid_values_fall_back():
    config = parse_ollama_image_generation_config(
        "reference=maybe;max_refs=lots;response_format=jpeg;quality=ultra"
    )

    assert config["supports_reference_image"] is False
    assert config["max_reference_images"] == 0
    assert config["response_format"] == "b64_json"
    assert "quality" not in config


def test_resolve_ollama_image_size_converts_k_tiers_to_gpt_image_2_pixel_sizes():
    assert resolve_ollama_image_size("1K", "16:9") == "1824x1024"
    assert resolve_ollama_image_size("2K", "16:9") == "2048x1152"
    assert resolve_ollama_image_size("2K", "9:16") == "1152x2048"
    assert resolve_ollama_image_size("4K", "16:9") == "3840x2160"
    assert resolve_ollama_image_size("4K", "1:1") == "2880x2880"
    assert resolve_ollama_image_size("1K", "4:3") == "1360x1024"
    assert resolve_ollama_image_size("1K", "3:4") == "1024x1360"
    assert resolve_ollama_image_size("2K", "4:3") == "2048x1536"
    assert resolve_ollama_image_size("2K", "3:4") == "1536x2048"
    assert resolve_ollama_image_size("4K", "4:3") == "3312x2480"
    assert resolve_ollama_image_size("4K", "3:4") == "2480x3312"
    assert resolve_ollama_image_size("1024x1024", "1:1") == "1024x1024"
    assert resolve_ollama_image_size("auto", "1:1") == "auto"


def test_default_multimodal_helpers_switch_to_ollama_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_ANALYSIS_ENABLED", False)

    assert default_models.get_default_multimodal_provider() == "ollama"
    assert default_models.get_default_multimodal_model() == "gemma4:e4b"
    assert default_models.get_default_thinking_multimodal_model() == "gemma4:e4b"
    assert default_models.get_default_image_analysis_model() == "gemini-3.1-pro-preview"
    assert default_models.get_default_image_analysis_provider() == "builtin"


def test_default_image_analysis_helpers_switch_to_ollama_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_ANALYSIS_ENABLED", True)

    assert default_models.get_default_image_analysis_model() == "gemma4:e4b"
    assert default_models.get_default_image_analysis_provider() == "ollama"
    assert default_models.get_default_mark_recognition_model() == "gemma4:e4b"
    assert default_models.get_default_mark_recognition_provider() == "ollama"


def test_get_multimodal_model_config_returns_ollama_token_limits(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")
    monkeypatch.setattr(settings, "OLLAMA_MAX_INPUT_TOKENS", 65536)
    monkeypatch.setattr(settings, "OLLAMA_MAX_OUTPUT_TOKENS", 8192)

    assert get_multimodal_model_config("gemma4:e4b", "ollama") == {
        "max_input_tokens": 65536,
        "max_output_tokens": 8192,
        "supports_fast_mode": True,
        "supports_thinking_mode": True,
    }
