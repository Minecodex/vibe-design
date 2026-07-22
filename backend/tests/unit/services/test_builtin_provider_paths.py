import sys
import threading
from types import SimpleNamespace

import pytest

from app.services.builtin_provider import LingyaAiBuiltinProvider, _local_url_to_file_path
from app.services.generation_media_resolver import GenerationImageResolveBatchResult


def _configure_fake_tos(monkeypatch):
    uploads: list[tuple[str, str, str]] = []

    class FakeTosClient:
        def __init__(self, ak, sk, endpoint, region):
            assert ak == "test-ak"
            assert sk == "test-sk"
            assert endpoint == "tos-cn-guangzhou.volces.com"
            assert region == "cn-guangzhou"

        def put_object_from_file(self, bucket_name, object_key, file_path):
            uploads.append((bucket_name, object_key, file_path))

    monkeypatch.setattr("app.core.config.settings.TOS_AK", "test-ak")
    monkeypatch.setattr("app.core.config.settings.TOS_SK", "test-sk")
    monkeypatch.setattr("app.core.config.settings.TOS_ENDPOINT", "tos-cn-guangzhou.volces.com")
    monkeypatch.setattr("app.core.config.settings.TOS_REGION", "cn-guangzhou")
    monkeypatch.setattr("app.core.config.settings.TOS_BUCKET_NAME", "design-public")
    monkeypatch.setattr("app.core.config.settings.TOS_PUBLIC_BASE_URL", "")
    monkeypatch.setattr("app.core.config.settings.TOS_OBJECT_PREFIX", "generation-refs/")
    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=FakeTosClient))
    monkeypatch.setattr("app.services.generation_media_resolver._file_content_digest", lambda _path: "fixedobjectkey")
    return uploads


def test_local_url_to_file_path_keeps_canvas_upload_url_behavior(monkeypatch, tmp_path):
    image_path = tmp_path / "uploads" / "canvas" / "65" / "reference.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake-image")

    monkeypatch.chdir(tmp_path)

    assert _local_url_to_file_path("/api/v1/uploads/canvas/65/reference.png") == str(image_path)


@pytest.mark.parametrize(
    ("model_name", "expected_size_field"),
    [
        ("nano-banana-2", "image_size"),
        ("nano-banana-pro", "image_size"),
        ("gpt-image-2", "resolution"),
        ("doubao-seedream-4-5-251128", "size"),
        ("doubao-seedream-5-0-260128", "size"),
    ],
)
@pytest.mark.asyncio
async def test_lingyaai_image_models_use_profile_specific_reference_payload(
    monkeypatch,
    tmp_path,
    model_name,
    expected_size_field,
):
    image_path = tmp_path / "uploads" / "canvas" / "1" / "reference.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake-image")
    monkeypatch.chdir(tmp_path)
    _configure_fake_tos(monkeypatch)
    captured: dict[str, object] = {}

    async def fake_request(self, method, path, *, headers=None, json_data=None, timeout=None):
        captured["json_data"] = json_data
        return (
            {"data": [{"url": "https://example.test/generated.png"}]},
            {"X-Oneapi-Request-Id": "oneapi-request-1", "X-Request-Id": "provider-request-1"},
        )

    monkeypatch.setattr(LingyaAiBuiltinProvider, "_request", fake_request)

    await LingyaAiBuiltinProvider("test-key").submit_image(
        prompt="A cute monkey eating grapes",
        model_name=model_name,
        resolution="2K",
        aspect_ratio="1:1",
        image_urls=["/api/v1/uploads/canvas/1/reference.jpg"],
        image_count=1,
    )

    payload = captured["json_data"]
    assert isinstance(payload, dict)
    assert payload[expected_size_field] == "2K"
    assert payload["image"] == [
        "https://design-public.tos-cn-guangzhou.volces.com/generation-refs/fixedobjectkey.jpg"
    ]


@pytest.mark.asyncio
async def test_lingyaai_seedream_payload_uploads_canvas_reference_to_object_storage_url(monkeypatch, tmp_path):
    image_path = tmp_path / "uploads" / "canvas" / "1" / "2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake-image")
    monkeypatch.chdir(tmp_path)
    _configure_fake_tos(monkeypatch)

    captured: dict[str, object] = {}

    async def fake_request(self, method, path, *, headers=None, json_data=None, timeout=None):
        captured["method"] = method
        captured["path"] = path
        captured["json_data"] = json_data
        return (
            {
                "data": [
                    {
                        "url": "https://example.test/generated.png",
                    }
                ]
            },
            {"X-Oneapi-Request-Id": "oneapi-request-1", "X-Request-Id": "provider-request-1"},
        )

    monkeypatch.setattr(LingyaAiBuiltinProvider, "_request", fake_request)

    result = await LingyaAiBuiltinProvider("test-key").submit_image(
        prompt="A cute monkey eating grapes",
        model_name="doubao-seedream-5-0-260128",
        resolution="2K",
        aspect_ratio="1:1",
        image_urls=["/api/v1/uploads/canvas/1/2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg"],
        image_count=1,
    )

    payload = captured["json_data"]
    assert result.status == "completed"
    assert isinstance(payload, dict)
    assert payload["model"] == "doubao-seedream-5-0-260128"
    assert payload["size"] == "2K"
    assert payload["image"] == [
        "https://design-public.tos-cn-guangzhou.volces.com/generation-refs/fixedobjectkey.jpg"
    ]
    assert result.request_diagnostics == {
        "provider": "lingyaai",
        "operation": "image_submit",
        "model_name": "doubao-seedream-5-0-260128",
        "request_profile": "lingyaai_seedream_image",
        "reference_inputs": {
            "count": 1,
            "kinds": {"local_upload": 1},
            "transports": {"local_reference": 1},
            "mime_types": ["image/jpeg"],
            "items": [
                {
                    "kind": "local_upload",
                    "transport": "local_reference",
                    "mime_type": "image/jpeg",
                    "value_preview": "local_upload:.../2aec01ac-7f21-44eb-93ef-87cc202f7c27.jpg",
                }
            ],
        },
        "provider_payload_has_image": True,
        "provider_payload_image_count": 1,
        "provider_payload_images": {
            "count": 1,
            "kinds": {"remote_url": 1},
            "transports": {"url": 1},
            "mime_types": ["image/jpeg"],
            "items": [
                {
                    "kind": "remote_url",
                    "transport": "url",
                    "mime_type": "image/jpeg",
                    "value_preview": "https://design-public.tos-cn-guangzhou.volces.com/.../fixedobjectkey.jpg",
                }
            ],
        },
        "reference_resolution": {
            "input_count": 1,
            "output_url_count": 1,
            "remote_input_count": 0,
            "object_storage_upload_count": 1,
            "transport_counts": {"remote_url": 0, "object_storage_url": 1},
        },
    }


@pytest.mark.asyncio
async def test_submit_image_resolves_references_off_the_event_loop(monkeypatch):
    """Reference resolution does blocking object-storage I/O, so it must run via
    asyncio.to_thread (off the loop thread) and not stall the shared worker event loop."""
    loop_thread_ident = threading.get_ident()
    seen: dict[str, int] = {}

    def fake_resolver(urls):
        seen["thread_ident"] = threading.get_ident()
        return GenerationImageResolveBatchResult(urls=list(urls), diagnostics={})

    monkeypatch.setattr(
        "app.services.builtin_provider.resolve_generation_image_urls_with_diagnostics",
        fake_resolver,
    )

    async def fake_request(self, method, path, *, headers=None, json_data=None, timeout=None):
        return (
            {"data": [{"url": "https://example.test/generated.png"}]},
            {"X-Oneapi-Request-Id": "oneapi-request-1", "X-Request-Id": "provider-request-1"},
        )

    monkeypatch.setattr(LingyaAiBuiltinProvider, "_request", fake_request)

    await LingyaAiBuiltinProvider("test-key").submit_image(
        prompt="A cute monkey eating grapes",
        model_name="doubao-seedream-5-0-260128",
        resolution="2K",
        aspect_ratio="1:1",
        image_urls=["/api/v1/uploads/canvas/1/ref.jpg"],
        image_count=1,
    )

    assert "thread_ident" in seen  # the resolver was actually invoked
    assert seen["thread_ident"] != loop_thread_ident


def test_lingyaai_seedance_2_video_model_uses_seedance_content_payload():
    payload = LingyaAiBuiltinProvider("test-key")._build_video_payload(
        prompt="make it move",
        model_name="doubao-seedance-2-0-260128",
        resolution="1080p",
        aspect_ratio="16:9",
        duration=5,
        image_urls=["https://example.test/reference.png"],
        audio=True,
    )

    assert payload["model"] == "doubao-seedance-2-0-260128"
    assert payload["resolution"] == "1080p"
    assert payload["ratio"] == "16:9"
    assert payload["generate_audio"] is True
    assert payload["content"] == [
        {"type": "text", "text": "make it move"},
        {
            "type": "image_url",
            "image_url": {"url": "https://example.test/reference.png"},
            "role": "reference_image",
        },
    ]
    assert "input" not in payload


def test_lingyaai_seedance_15_video_model_uses_images_payload():
    payload = LingyaAiBuiltinProvider("test-key")._build_video_payload(
        prompt="make it move",
        model_name="doubao-seedance-1-5-pro-251215",
        resolution="1080p",
        aspect_ratio="9:16",
        duration=6,
        image_urls=[
            "https://example.test/reference-1.png",
            "https://example.test/reference-2.png",
            "https://example.test/reference-3.png",
        ],
    )

    assert payload["model"] == "doubao-seedance-1-5-pro-251215"
    assert payload["resolution"] == "1080p"
    assert payload["aspect_ratio"] == "9:16"
    assert payload["images"] == [
        "https://example.test/reference-1.png",
        "https://example.test/reference-2.png",
    ]
    assert "input" not in payload
