import pytest
from pydantic import ValidationError

from app.core.generator_capabilities import (
    IMAGE_MODEL_CAPABILITIES,
    VIDEO_MODEL_CAPABILITIES,
    get_allowed_video_durations,
)
from app.core.providers import PROVIDER_REGISTRY
from app.schemas.generation import GenerateImageRequest, GenerateVideoRequest


def test_generate_image_request_accepts_multiple_reference_images():
    request = GenerateImageRequest(
        prompt="make it cinematic",
        model_name="gemini-3.1-flash-image-preview-official",
        provider_code="builtin",
        aspect_ratio="16:9",
        resolution="1K",
        image_urls=[
            "https://example.com/ref-1.png",
            "https://example.com/ref-2.png",
        ],
    )

    assert request.image_urls == [
        "https://example.com/ref-1.png",
        "https://example.com/ref-2.png",
    ]


def test_generate_image_request_accepts_client_request_id():
    request = GenerateImageRequest(
        prompt="make it cinematic",
        model_name="gemini-3.1-flash-image-preview-official",
        provider_code="builtin",
        client_request_id="canvas-image-request-1",
    )

    assert request.client_request_id == "canvas-image-request-1"


def test_generate_image_request_rejects_too_many_gemini_reference_images():
    with pytest.raises(ValidationError, match="14"):
        GenerateImageRequest(
            prompt="make it cinematic",
            model_name="gemini-3.1-flash-image-preview-official",
            provider_code="builtin",
            image_urls=[f"https://example.com/ref-{index}.png" for index in range(15)],
        )


def test_generate_image_request_accepts_gpt_image_2_reference_images():
    request = GenerateImageRequest(
        prompt="make it cinematic",
        model_name="gpt-image-2",
        provider_code="builtin",
        image_urls=[f"https://example.com/ref-{index}.png" for index in range(16)],
    )

    assert len(request.image_urls or []) == 16


def test_generate_image_request_rejects_too_many_gpt_image_2_reference_images():
    with pytest.raises(ValidationError, match="16"):
        GenerateImageRequest(
            prompt="make it cinematic",
            model_name="gpt-image-2",
            provider_code="builtin",
            image_urls=[f"https://example.com/ref-{index}.png" for index in range(17)],
        )


def test_generate_video_request_rejects_too_many_supported_video_images():
    with pytest.raises(ValidationError, match="2"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            duration=5,
            image_urls=[
                "https://example.com/ref-1.png",
                "https://example.com/ref-2.png",
                "https://example.com/ref-3.png",
            ],
        )


def test_generate_video_request_accepts_client_request_id():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="kling-v2-6",
        provider_code="builtin",
        client_request_id="canvas-video-request-1",
    )

    assert request.client_request_id == "canvas-video-request-1"


def test_generate_video_request_rejects_reference_video_and_audio_inputs():
    with pytest.raises(ValidationError, match="参考视频"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            reference_video_urls=["https://example.com/ref.mp4"],
        )

    with pytest.raises(ValidationError, match="参考音频"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            reference_audio_urls=["https://example.com/ref.wav"],
        )


def test_generate_video_request_uses_active_lingyaai_model_capabilities(monkeypatch):
    monkeypatch.setattr("app.core.providers.settings.BUILTIN_PROVIDER_CODE", "lingyaai")

    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="doubao-seedance-2-0-260128",
        provider_code="builtin",
        duration=15,
        image_urls=[f"https://example.com/ref-{index}.png" for index in range(9)],
    )

    assert request.duration == 15
    assert len(request.image_urls or []) == 9
    with pytest.raises(ValidationError, match="9"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="doubao-seedance-2-0-260128",
            provider_code="builtin",
            image_urls=[f"https://example.com/ref-{index}.png" for index in range(10)],
        )


def test_generate_video_request_accepts_kling_v2_6_duration_10_seconds():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="kling-v2-6",
        provider_code="builtin",
        duration=10,
    )

    assert request.duration == 10


def test_generate_video_request_accepts_kling_v3_text_duration_15_seconds():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="kling-v3",
        provider_code="builtin",
        duration=15,
    )

    assert request.duration == 15


def test_generate_video_request_accepts_kling_v3_image_duration_15_seconds():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="kling-v3",
        provider_code="builtin",
        duration=15,
        image_urls=["https://example.com/ref-1.png"],
    )

    assert request.duration == 15


def test_generate_video_request_accepts_kling_v3_image_duration_3_seconds():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="kling-v3",
        provider_code="builtin",
        duration=3,
        image_urls=["https://example.com/ref-1.png"],
    )

    assert request.duration == 3


def test_generate_video_request_rejects_kling_v2_6_duration_above_limit():
    with pytest.raises(ValidationError, match="5s, 10s"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            duration=15,
        )


def test_generate_video_request_rejects_kling_v2_6_audio_without_pro_resolution():
    with pytest.raises(ValidationError, match="pro"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            duration=5,
            resolution="720p",
            audio=True,
        )


def test_generate_video_request_rejects_kling_v2_6_tail_frame_without_first_frame():
    with pytest.raises(ValidationError, match="首帧"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            duration=5,
            resolution="1080p",
            tail_frame_image="https://example.com/last.png",
        )


def test_generate_video_request_rejects_kling_v2_6_tail_frame_without_pro_resolution():
    with pytest.raises(ValidationError, match="pro"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            duration=5,
            resolution="720p",
            first_frame_image="https://example.com/first.png",
            tail_frame_image="https://example.com/last.png",
        )


def test_generate_video_request_rejects_kling_v2_6_tail_frame_with_audio():
    with pytest.raises(ValidationError, match="互斥"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="kling-v2-6",
            provider_code="builtin",
            duration=5,
            resolution="1080p_audio",
            audio=True,
            first_frame_image="https://example.com/first.png",
            tail_frame_image="https://example.com/last.png",
        )


def test_generate_video_request_accepts_seedance_duration_within_range():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="doubao-seedance-1-5-pro",
        provider_code="builtin",
        duration=4,
    )

    assert request.duration == 4


def test_generate_video_request_rejects_seedance_duration_above_limit():
    with pytest.raises(ValidationError, match="4s, 5s, 6s, 7s, 8s, 9s, 10s, 11s, 12s"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="doubao-seedance-1-5-pro",
            provider_code="builtin",
            duration=13,
        )


def test_generate_video_request_accepts_seedance_2_duration_within_range():
    request = GenerateVideoRequest(
        prompt="animate this",
        model_name="doubao-seedance-2.0",
        provider_code="builtin",
        duration=8,
    )

    assert request.duration == 8


def test_generate_video_request_rejects_seedance_2_duration_above_limit():
    with pytest.raises(ValidationError, match="5s, 6s, 7s, 8s, 9s, 10s, 11s, 12s, 13s, 14s, 15s"):
        GenerateVideoRequest(
            prompt="animate this",
            model_name="doubao-seedance-2.0",
            provider_code="builtin",
            duration=16,
        )


def test_generator_capabilities_are_derived_from_builtin_registry():
    image_configs = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2image"]
    }
    video_configs = {
        entry["model_name"]: entry["config"]
        for entry in PROVIDER_REGISTRY["builtin"]["models"]["text2video"]
    }

    assert image_configs["gemini-3.1-flash-image-preview-official"]["max_reference_images"] == 14
    assert image_configs["gpt-image-2"]["max_reference_images"] == 16
    assert image_configs["doubao-seedream-5-0-lite"]["max_reference_images"] == 10
    assert video_configs["kling-v2-6"]["max_image_inputs"] == 2
    assert video_configs["kling-v3"]["max_image_inputs"] == 2
    assert video_configs["doubao-seedance-1-5-pro"]["max_image_inputs"] == 2
    assert video_configs["kling-v2-6"]["requires_first_frame_for_tail_frame"] is True
    assert video_configs["kling-v2-6"]["audio_tail_frame_mutually_exclusive"] is True
    assert video_configs["doubao-seedance-2.0"]["max_image_inputs"] == 9
    assert IMAGE_MODEL_CAPABILITIES["gemini-3.1-flash-image-preview-official"]["max_reference_images"] == 14
    assert IMAGE_MODEL_CAPABILITIES["gpt-image-2"]["max_reference_images"] == 16
    assert VIDEO_MODEL_CAPABILITIES["kling-v2-6"]["max_image_inputs"] == 2
    assert VIDEO_MODEL_CAPABILITIES["kling-v3"]["max_image_inputs"] == 2
    assert VIDEO_MODEL_CAPABILITIES["kling-v2-6"]["requires_first_frame_for_tail_frame"] is True
    assert VIDEO_MODEL_CAPABILITIES["kling-v2-6"]["audio_tail_frame_mutually_exclusive"] is True


def test_get_allowed_video_durations_uses_supported_registry_values():
    assert get_allowed_video_durations("kling-v2-6") == [5, 10]
    assert get_allowed_video_durations("kling-v2-6", ["https://example.com/ref-1.png"]) == [5, 10]
    assert get_allowed_video_durations("kling-v3") == list(range(3, 16))
    assert get_allowed_video_durations("kling-v3", ["https://example.com/ref-1.png"]) == list(range(3, 16))
    assert get_allowed_video_durations("doubao-seedance-1-5-pro") == [4, 5, 6, 7, 8, 9, 10, 11, 12]
    assert get_allowed_video_durations("doubao-seedance-2.0") == [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
