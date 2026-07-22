from app.services.image_output_selection import select_image_output
from app.services.provider_result_urls import extract_task_result_urls


def test_select_image_output_prefers_closest_ratio_without_upscaling():
    assert select_image_output(1600, 900, feature_name="erase") == {
        "aspect_ratio": "16:9",
        "resolution": "2K",
    }


def test_select_image_output_uses_feature_model_constraints(monkeypatch):
    model_config = {
        "allowed_sizes": ["2K", "3K"],
        "allowed_aspect_ratios": ["1:1", "16:9", "3:2"],
    }
    monkeypatch.setattr(
        "app.services.image_output_selection.build_provider_registry",
        lambda: {"builtin": {"models": {"text2image": [{"model_name": "text-redraw-model", "config": model_config}]}}},
    )
    monkeypatch.setattr(
        "app.services.image_output_selection.get_feature_image_model",
        lambda feature_name: "text-redraw-model" if feature_name == "text_redraw" else "unexpected",
    )

    result = select_image_output(1200, 1000, feature_name="text_redraw")

    assert result["resolution"] in model_config["allowed_sizes"]
    assert result["aspect_ratio"] in model_config["allowed_aspect_ratios"]


def test_extract_task_result_urls_flattens_image_and_video_urls():
    result = {
        "result": {
            "images": [{"url": ["https://example.com/one.png", "https://example.com/two.png"]}],
            "videos": [{"url": "https://example.com/video.mp4"}],
        }
    }

    assert extract_task_result_urls(result) == [
        "https://example.com/one.png",
        "https://example.com/two.png",
        "https://example.com/video.mp4",
    ]
