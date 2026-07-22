import pytest

from app.api.v1.endpoints.providers import get_provider_registry
from app.core.config import settings

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


@pytest.mark.asyncio
async def test_provider_registry_endpoint_includes_gpt_image_2_dimension_table():
    registry = await get_provider_registry()

    gpt_image_2 = next(
        entry
        for entry in registry["builtin"]["models"]["text2image"]
        if entry["model_name"] == "gpt-image-2"
    )

    dimension_table = gpt_image_2["config"]["dimension_table"]
    assert dimension_table["4K"]["1:1"] == {"width": 2880, "height": 2880}
    assert dimension_table["4K"]["16:9"] == {"width": 3840, "height": 2160}
    assert len(dimension_table["4K"]) == 15
    assert gpt_image_2["config"]["dimension_source"] == "apimart_docs"


@pytest.mark.asyncio
async def test_provider_registry_endpoint_includes_seedream_5_lite_dimension_table():
    registry = await get_provider_registry()

    seedream_5 = next(
        entry
        for entry in registry["builtin"]["models"]["text2image"]
        if entry["model_name"] == "doubao-seedream-5-0-lite"
    )

    assert seedream_5["config"]["allowed_sizes"] == ["2K", "3K", "4K"]
    assert seedream_5["config"]["dimension_table"]["4K"]["16:9"] == {"width": 5504, "height": 3040}
    assert seedream_5["config"]["dimension_source"] == "apimart_docs"


@pytest.mark.asyncio
async def test_provider_registry_endpoint_marks_models_without_exact_tables_as_estimated():
    registry = await get_provider_registry()
    image_configs = {
        entry["model_name"]: entry["config"]
        for entry in registry["builtin"]["models"]["text2image"]
    }
    video_configs = {
        entry["model_name"]: entry["config"]
        for entry in registry["builtin"]["models"]["text2video"]
    }

    for model_name in [
        "doubao-seedream-4-5",
        "gemini-3.1-flash-image-preview-official",
        "gemini-3-pro-image-preview-official",
        "imagen-4.0-apimart",
    ]:
        assert image_configs[model_name]["dimension_source"] == "estimated"
        assert image_configs[model_name]["dimension_policy"] == "image_area"
        assert "dimension_table" not in image_configs[model_name]

    for model_name in [
        "kling-v2-6",
        "kling-v3",
        "doubao-seedance-1-5-pro",
        "doubao-seedance-2.0",
        "grok-imagine-1.0-video-apimart",
    ]:
        assert video_configs[model_name]["dimension_source"] == "estimated"
        assert video_configs[model_name]["dimension_policy"] == "video_short_side"


@pytest.mark.asyncio
async def test_provider_registry_endpoint_includes_ollama_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_MODEL", "gemma4:e4b")

    registry = await get_provider_registry()

    ollama_entry = registry["ollama"]["models"]["multimodal"][0]
    assert ollama_entry["model_name"] == "gemma4:e4b"
    assert ollama_entry["config"]["pricing_mode"] == "flat"
    assert ollama_entry["config"]["pricing_cents"] == {"flat": 0}


@pytest.mark.asyncio
async def test_provider_registry_endpoint_includes_ollama_image_model_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "OLLAMA_MULTIMODAL_ENABLED", False)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_ENABLED", True)
    monkeypatch.setattr(settings, "OLLAMA_IMAGE_GENERATION_MODEL", "gpt-image-2")
    monkeypatch.setattr(
        settings,
        "OLLAMA_IMAGE_GENERATION_CONFIG",
        "sizes=1K|2K|4K;ratios=1:1|16:9|9:16|2:1|1:2|4:3|3:4|3:2|2:3|5:4|4:5|21:9|9:21|3:1|1:3;reference=true;max_refs=16;response_format=url;reference_mode=edits",
    )

    registry = await get_provider_registry()

    ollama_entry = registry["ollama"]["models"]["text2image"][0]
    assert ollama_entry["model_name"] == "gpt-image-2"
    assert ollama_entry["label"] == "Ollama Image (gpt-image-2)"
    assert ollama_entry["config"]["supports_reference_image"] is True
    assert ollama_entry["config"]["max_reference_images"] == 16
    assert ollama_entry["config"]["allowed_aspect_ratios"] == GPT_IMAGE_2_RATIOS
    assert ollama_entry["config"]["allowed_sizes"] == ["1K", "2K", "4K"]
    assert ollama_entry["config"]["dimension_policy"] == "ollama_gpt_image_2"
    assert ollama_entry["config"]["dimension_source"] == "estimated"
