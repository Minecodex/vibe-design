from app.core.providers import PROVIDER_REGISTRY
from app.core.image_constraints import resolve_image_generation_selection


def _get_builtin_image_config(model_name: str) -> dict:
    return next(
        entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2image"]
        if entry["model_name"] == model_name
    )


def test_resolve_image_generation_selection_keeps_supported_gpt_image_2_4k_ratio():
    config = _get_builtin_image_config("gpt-image-2")

    assert resolve_image_generation_selection(
        config=config,
        aspect_ratio="21:9",
        resolution="4K",
    ) == {
        "aspect_ratio": "21:9",
        "resolution": "4K",
    }


def test_resolve_image_generation_selection_keeps_square_gpt_image_2_4k_ratio():
    config = _get_builtin_image_config("gpt-image-2")

    assert resolve_image_generation_selection(
        config=config,
        aspect_ratio="1:1",
        resolution="4K",
    ) == {
        "aspect_ratio": "1:1",
        "resolution": "4K",
    }


def test_resolve_image_generation_selection_keeps_four_by_three_gpt_image_2_4k_ratio():
    config = _get_builtin_image_config("gpt-image-2")

    assert resolve_image_generation_selection(
        config=config,
        aspect_ratio="4:3",
        resolution="4K",
    ) == {
        "aspect_ratio": "4:3",
        "resolution": "4K",
    }


def test_gpt_image_2_dimension_table_matches_apimart_4k_sizes():
    config = _get_builtin_image_config("gpt-image-2")

    assert config["dimension_table"]["4K"]["1:1"] == {"width": 2880, "height": 2880}
    assert config["dimension_table"]["4K"]["16:9"] == {"width": 3840, "height": 2160}
    assert len(config["dimension_table"]["4K"]) == 15
    assert config["dimension_source"] == "apimart_docs"


def test_seedream_5_lite_dimension_table_matches_apimart_4k_sizes():
    config = _get_builtin_image_config("doubao-seedream-5-0-lite")

    assert config["allowed_sizes"] == ["2K", "3K", "4K"]
    assert config["dimension_table"]["4K"]["1:1"] == {"width": 4096, "height": 4096}
    assert config["dimension_table"]["4K"]["16:9"] == {"width": 5504, "height": 3040}
    assert len(config["dimension_table"]["4K"]) == 8
    assert config["dimension_source"] == "apimart_docs"


def test_resolve_image_generation_selection_clamps_resolution_before_ratio():
    config = _get_builtin_image_config("imagen-4.0-apimart")

    assert resolve_image_generation_selection(
        config=config,
        aspect_ratio="9:16",
        resolution="4K",
    ) == {
        "aspect_ratio": "9:16",
        "resolution": "1K",
    }
