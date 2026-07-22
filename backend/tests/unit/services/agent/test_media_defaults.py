from app.services.agent_harness.core.utils.media_defaults import (
    resolve_harness_image_defaults,
    resolve_harness_video_defaults,
)
from app.services.agent_harness.core.utils.model_labels import resolve_model_label


def test_seedance_2_video_defaults_use_highest_resolution_and_shortest_duration():
    defaults = resolve_harness_video_defaults("doubao-seedance-2.0", "builtin")

    assert defaults == {
        "resolution": "1080p",
        "aspect_ratio": "16:9",
        "duration": 5,
    }


def test_lingyaai_image_defaults_use_active_builtin_registry(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_CODE", "lingyaai", raising=False)

    defaults = resolve_harness_image_defaults("nano-banana-2", "builtin")

    assert defaults == {
        "resolution": "4K",
        "aspect_ratio": "1:1",
    }


def test_lingyaai_model_label_uses_active_builtin_registry(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.BUILTIN_PROVIDER_CODE", "lingyaai", raising=False)

    assert resolve_model_label("nano-banana-2", provider_code="builtin", bucket="text2image") == "NanoBanana2"
