import sys
import threading
from types import SimpleNamespace

import pytest

from app.core.config import APIMART_WRITE_TIMEOUT_SECONDS
from app.services.generation_media_resolver import (
    GenerationImageResolveBatchResult,
    GenerationMediaResolveError,
)
from app.schemas.generation import (
    GenerateContentRequest,
    GenerateImageRequest,
    GenerateVideoRequest,
)
from app.services.apimart_client import ApimartClient


def _configure_fake_tos(monkeypatch, *, prefix: str = "generation-refs/"):
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
    monkeypatch.setattr("app.core.config.settings.TOS_OBJECT_PREFIX", prefix)
    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=FakeTosClient))
    monkeypatch.setattr("app.services.generation_media_resolver._file_content_digest", lambda _path: "fixedobjectkey")
    return uploads


def test_apimart_auth_headers_reject_blank_api_key_before_httpx():
    client = ApimartClient("   ")

    with pytest.raises(ValueError, match="BUILTIN_PROVIDER_API_KEY is required"):
        client._auth_headers()


@pytest.mark.asyncio
async def test_apimart_request_uses_configured_write_timeout(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    class FakeResponse:
        status_code = 200
        text = '{"code":200,"data":[]}'

        def json(self):
            return {"code": 200, "data": []}

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json=None, headers=None):
            captured["url"] = url
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr("app.services.apimart_client.httpx.AsyncClient", FakeAsyncClient)

    await client._request("POST", "/v1/images/generations", json_data={"model": "gpt-image-2"})

    assert captured["timeout"].write == APIMART_WRITE_TIMEOUT_SECONDS


@pytest.mark.asyncio
async def test_generate_image_forwards_all_reference_urls_in_order(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["method"] = method
        captured["path"] = path
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="make it cinematic",
        model_name="gemini-3.1-flash-image-preview-official",
        resolution="1K",
        aspect_ratio="16:9",
        urls=[
            "https://example.com/ref-1.png",
            "https://example.com/ref-2.png",
        ],
    )

    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/images/generations"
    assert captured["json_data"]["image_urls"] == [
        "https://example.com/ref-1.png",
        "https://example.com/ref-2.png",
    ]


@pytest.mark.asyncio
async def test_generate_image_uploads_absolute_reference_to_object_storage_url(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    uploads = _configure_fake_tos(monkeypatch)
    reference_path = tmp_path / "uploads" / "harness" / "project" / "3" / "source.jpg"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"fake-image-bytes")
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="merge references",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="4:3",
        urls=[reference_path.resolve().as_posix()],
    )

    image_urls = captured["json_data"]["image_urls"]
    assert len(image_urls) == 1
    assert image_urls == [
        "https://design-public.tos-cn-guangzhou.volces.com/generation-refs/fixedobjectkey.jpg"
    ]
    assert uploads == [
        ("design-public", "generation-refs/fixedobjectkey.jpg", str(reference_path.resolve()))
    ]


@pytest.mark.asyncio
async def test_generate_image_uploads_reference_gallery_upload_to_object_storage_url(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _configure_fake_tos(monkeypatch)
    reference_path = tmp_path / "uploads" / "reference-gallery" / "2026-06" / "gallery_ref.jpg"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"reference-gallery-image")
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="merge references",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="4:3",
        urls=["/api/v1/uploads/reference-gallery/2026-06/gallery_ref.jpg"],
    )

    image_urls = captured["json_data"]["image_urls"]
    assert len(image_urls) == 1
    assert image_urls == [
        "https://design-public.tos-cn-guangzhou.volces.com/generation-refs/fixedobjectkey.jpg"
    ]


@pytest.mark.asyncio
async def test_generate_image_resolves_references_off_the_event_loop(monkeypatch):
    """Reference resolution does blocking object-storage I/O, so it must run via
    asyncio.to_thread (off the loop thread). Guards against re-introducing a synchronous
    call that would stall every other coroutine sharing the worker's event loop."""
    loop_thread_ident = threading.get_ident()
    seen: dict[str, int] = {}

    def fake_resolver(urls):
        seen["thread_ident"] = threading.get_ident()
        return GenerationImageResolveBatchResult(urls=list(urls), diagnostics={})

    monkeypatch.setattr(
        "app.services.apimart_client.resolve_generation_image_urls_with_diagnostics",
        fake_resolver,
    )

    client = ApimartClient("test-key")

    async def fake_request(method, path, params=None, json_data=None):
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="merge references",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="4:3",
        urls=["/api/v1/uploads/canvas/1/ref.png"],
    )

    assert "thread_ident" in seen  # the resolver was actually invoked
    assert seen["thread_ident"] != loop_thread_ident


@pytest.mark.asyncio
async def test_generate_image_records_reference_resolution_diagnostics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _configure_fake_tos(monkeypatch)
    reference_path = tmp_path / "uploads" / "reference-gallery" / "2026-06" / "gallery_ref.jpg"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"reference-gallery-image")
    client = ApimartClient("test-key")

    async def fake_request(method, path, params=None, json_data=None):
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    result = await client.generate_image(
        prompt="merge references",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="4:3",
        urls=["https://example.test/ref.png", "/api/v1/uploads/reference-gallery/2026-06/gallery_ref.jpg"],
    )

    assert result["_request_diagnostics"]["reference_resolution"] == {
        "input_count": 2,
        "output_url_count": 2,
        "remote_input_count": 1,
        "object_storage_upload_count": 1,
        "transport_counts": {"remote_url": 1, "object_storage_url": 1},
    }
    assert result["_request_diagnostics"]["provider_payload_has_image"] is True
    assert result["_request_diagnostics"]["provider_payload_image_count"] == 2


@pytest.mark.asyncio
async def test_generate_image_uploads_relative_upload_reference_to_object_storage_url(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _configure_fake_tos(monkeypatch)
    reference_path = tmp_path / "uploads" / "reference-gallery" / "2026-06" / "relative_ref.png"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"relative-reference-gallery-image")
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="merge references",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="4:3",
        urls=["uploads/reference-gallery/2026-06/relative_ref.png"],
    )

    image_urls = captured["json_data"]["image_urls"]
    assert len(image_urls) == 1
    assert image_urls == [
        "https://design-public.tos-cn-guangzhou.volces.com/generation-refs/fixedobjectkey.png"
    ]


@pytest.mark.asyncio
async def test_generate_image_does_not_send_mask_url_for_apimart_generation(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="merge references",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="4:3",
        urls=["https://example.test/ref.png"],
        mask_url="https://example.test/mask.png",
    )

    assert captured["json_data"]["image_urls"] == ["https://example.test/ref.png"]
    assert "mask_url" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_image_rejects_data_uri_reference(monkeypatch):
    client = ApimartClient("test-key")

    async def fake_request(*_args, **_kwargs):
        raise AssertionError("provider request should not be sent")

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(GenerationMediaResolveError) as exc:
        await client.generate_image(
            prompt="merge references",
            model_name="gpt-image-2",
            urls=["data:image/png;base64,ZmFrZQ=="],
        )

    assert exc.value.code == "generation_data_uri_not_allowed"


@pytest.mark.asyncio
async def test_generate_image_fails_before_request_when_tos_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    reference_path = tmp_path / "uploads" / "canvas" / "1" / "ref.png"
    reference_path.parent.mkdir(parents=True)
    reference_path.write_bytes(b"fake-image")
    monkeypatch.setattr("app.core.config.settings.TOS_AK", "")
    monkeypatch.setattr("app.core.config.settings.TOS_SK", "")
    monkeypatch.setattr("app.core.config.settings.TOS_ENDPOINT", "")
    monkeypatch.setattr("app.core.config.settings.TOS_REGION", "")
    monkeypatch.setattr("app.core.config.settings.TOS_BUCKET_NAME", "")
    client = ApimartClient("test-key")

    async def fake_request(*_args, **_kwargs):
        raise AssertionError("provider request should not be sent")

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(GenerationMediaResolveError) as exc:
        await client.generate_image(
            prompt="merge references",
            model_name="gpt-image-2",
            urls=["/api/v1/uploads/canvas/1/ref.png"],
        )

    assert exc.value.code == "generation_object_storage_not_configured"


@pytest.mark.asyncio
async def test_generate_imagen_4_image_omits_resolution_field(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="make it cinematic",
        model_name="imagen-4.0-apimart",
        resolution="1K",
        aspect_ratio="16:9",
    )

    assert captured["json_data"]["size"] == "16:9"
    assert "resolution" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_gpt_image_2_normalizes_resolution_to_lowercase(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_image(
        prompt="make it cinematic",
        model_name="gpt-image-2",
        resolution="2K",
        aspect_ratio="16:9",
    )

    assert captured["json_data"]["resolution"] == "2k"
    assert captured["json_data"]["size"] == "16:9"


@pytest.mark.asyncio
async def test_generate_video_forwards_ordered_image_urls(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="animate it",
        model_name="kling-v2-6",
        duration=8,
        resolution="1080p",
        urls=[
            "https://example.com/first.png",
            "https://example.com/last.png",
        ],
    )

    assert captured["json_data"]["image_urls"] == [
        "https://example.com/first.png",
        "https://example.com/last.png",
    ]
    assert captured["json_data"]["mode"] == "pro"
    assert "resolution" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_video_resolves_local_references_off_the_event_loop(monkeypatch):
    """Local reference uploads are blocking object-storage I/O, so video reference
    resolution must run via asyncio.to_thread (off the loop thread) just like images.
    Guards against re-introducing a synchronous upload that stalls the worker loop."""
    loop_thread_ident = threading.get_ident()
    seen: dict[str, int] = {}

    client = ApimartClient("test-key")

    def fake_local_to_absolute(url):
        seen["thread_ident"] = threading.get_ident()
        return f"https://cdn.test/{url.rsplit('/', 1)[-1]}"

    monkeypatch.setattr(client, "_local_url_to_absolute", fake_local_to_absolute)

    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="animate it",
        model_name="kling-v2-6",
        duration=8,
        resolution="1080p",
        urls=["/api/v1/uploads/canvas/1/ref.png"],
    )

    assert "thread_ident" in seen  # resolution actually happened
    assert seen["thread_ident"] != loop_thread_ident
    assert captured["json_data"]["image_urls"] == ["https://cdn.test/ref.png"]


@pytest.mark.asyncio
async def test_generate_video_uploads_local_reference_with_content_addressed_key(monkeypatch, tmp_path):
    """Local video references upload under a content digest key so repeated generations of
    the same file reuse one object instead of accumulating unbounded duplicates."""
    monkeypatch.chdir(tmp_path)
    uploads = _configure_fake_tos(monkeypatch)
    reference = tmp_path / "uploads" / "canvas" / "1" / "ref.png"
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b"same-bytes")

    client = ApimartClient("test-key")
    captured: dict = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(prompt="x", model_name="kling-v2-6", urls=["/uploads/canvas/1/ref.png"])
    await client.generate_video(prompt="x", model_name="kling-v2-6", urls=["/uploads/canvas/1/ref.png"])

    object_keys = {object_key for _bucket, object_key, _path in uploads}
    assert len(uploads) == 2
    assert len(object_keys) == 1  # content-addressed: same file -> same object key
    assert captured["json_data"]["image_urls"] == [f"https://design-public.tos-cn-guangzhou.volces.com/{object_keys.pop()}"]


@pytest.mark.asyncio
async def test_generate_kling_v2_6_video_maps_resolution_to_mode_without_resolution_field(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="stormy sea",
        model_name="kling-v2-6",
        duration=5,
        resolution="1080p",
        aspect_ratio="16:9",
    )

    assert captured["json_data"]["mode"] == "pro"
    assert captured["json_data"]["aspect_ratio"] == "16:9"
    assert "resolution" not in captured["json_data"]
    assert "audio" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_kling_v2_6_video_maps_audio_resolution_to_pro_audio(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="stormy sea",
        model_name="kling-v2-6",
        duration=10,
        resolution="1080p_audio",
        aspect_ratio="16:9",
    )

    assert captured["json_data"]["mode"] == "pro"
    assert captured["json_data"]["audio"] is True
    assert "resolution" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_kling_v3_video_forwards_audio_and_std_mode(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="concert stage",
        model_name="kling-v3",
        duration=5,
        resolution="720p_audio",
        aspect_ratio="16:9",
        audio=True,
    )

    assert captured["json_data"]["mode"] == "std"
    assert captured["json_data"]["audio"] is True
    assert "resolution" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_kling_v3_4k_video_uses_4k_mode_without_resolution_field(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="snow mountain sunrise",
        model_name="kling-v3",
        duration=5,
        resolution="4k_audio",
        aspect_ratio="16:9",
        audio=True,
    )

    assert captured["json_data"]["mode"] == "4k"
    assert captured["json_data"]["audio"] is True
    assert "resolution" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_seedance_2_video_uses_size_field(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="animate it",
        model_name="doubao-seedance-2.0",
        aspect_ratio="16:9",
        duration=5,
        resolution="720p",
    )

    assert captured["json_data"]["size"] == "16:9"
    assert "aspect_ratio" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_seedance_2_video_uses_image_with_roles_for_frame_mode(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="animate it",
        model_name="doubao-seedance-2.0",
        duration=5,
        resolution="720p",
        first_frame_url="https://example.com/first.png",
        tail_frame_url="https://example.com/last.png",
    )

    assert captured["json_data"]["image_with_roles"] == [
        {"url": "https://example.com/first.png", "role": "first_frame"},
        {"url": "https://example.com/last.png", "role": "last_frame"},
    ]
    assert "image_urls" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_seedance_1_5_video_uses_image_with_roles_for_tail_frame(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="animate it",
        model_name="doubao-seedance-1-5-pro",
        duration=5,
        resolution="720p",
        first_frame_url="https://example.com/first.png",
        tail_frame_url="https://example.com/last.png",
    )

    assert captured["json_data"]["image_with_roles"] == [
        {"url": "https://example.com/first.png", "role": "first_frame"},
        {"url": "https://example.com/last.png", "role": "last_frame"},
    ]
    assert "image_urls" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_seedance_2_video_uses_generate_audio_flag(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="animate it",
        model_name="doubao-seedance-2.0",
        aspect_ratio="16:9",
        duration=5,
        resolution="720p",
        audio=True,
    )

    assert captured["json_data"]["generate_audio"] is True
    assert "audio" not in captured["json_data"]


@pytest.mark.asyncio
async def test_generate_seedance_2_video_forwards_multimodal_reference_inputs(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": [{"task_id": "task-1"}]}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="immersive tea commercial",
        model_name="doubao-seedance-2.0",
        aspect_ratio="16:9",
        duration=5,
        resolution="720p",
        audio=True,
        reference_image_urls=[
            "https://example.com/ref-1.png",
            "https://example.com/ref-2.png",
        ],
        reference_video_urls=["https://example.com/ref.mp4"],
        reference_audio_urls=["https://example.com/ref.wav"],
        return_last_frame=True,
    )

    assert captured["json_data"]["image_urls"] == [
        "https://example.com/ref-1.png",
        "https://example.com/ref-2.png",
    ]
    assert captured["json_data"]["video_urls"] == ["https://example.com/ref.mp4"]
    assert captured["json_data"]["audio_urls"] == ["https://example.com/ref.wav"]
    assert captured["json_data"]["return_last_frame"] is True
    assert captured["json_data"]["generate_audio"] is True


@pytest.mark.asyncio
async def test_generate_grok_video_uses_size_and_quality_fields(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None):
        captured["json_data"] = json_data
        return {"code": 200, "data": {"id": "task-1"}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.generate_video(
        prompt="neon city chase",
        model_name="grok-imagine-1.0-video-apimart",
        aspect_ratio="3:2",
        duration=6,
        resolution="720p",
        urls=["https://example.com/ref-1.png"],
    )

    assert captured["json_data"]["size"] == "3:2"
    assert captured["json_data"]["quality"] == "720p"
    assert captured["json_data"]["duration"] == 6
    assert captured["json_data"]["image_urls"] == ["https://example.com/ref-1.png"]
    assert "aspect_ratio" not in captured["json_data"]
    assert "resolution" not in captured["json_data"]


def test_generate_image_request_normalizes_legacy_single_image_field():
    request = GenerateImageRequest(
        prompt="make it cinematic",
        model_name="gemini-3.1-flash-image-preview-official",
        provider_code="builtin",
        image_url="https://example.com/ref-1.png",
    )

    assert request.image_urls == ["https://example.com/ref-1.png"]


def test_generate_video_request_normalizes_legacy_first_and_tail_fields():
    request = GenerateVideoRequest(
        prompt="animate it",
        model_name="doubao-seedance-1-5-pro",
        provider_code="builtin",
        image_url="https://example.com/first.png",
        image_tail_url="https://example.com/last.png",
    )

    assert request.image_urls == [
        "https://example.com/first.png",
        "https://example.com/last.png",
    ]


def test_generate_video_request_preserves_explicit_frame_fields():
    request = GenerateVideoRequest(
        prompt="animate it",
        model_name="doubao-seedance-2.0",
        provider_code="builtin",
        first_frame_image="https://example.com/first.png",
        tail_frame_image="https://example.com/last.png",
    )

    assert request.first_frame_image == "https://example.com/first.png"
    assert request.tail_frame_image == "https://example.com/last.png"
    assert request.image_urls is None


def test_generate_video_request_accepts_audio_for_kling_v3():
    request = GenerateVideoRequest(
        prompt="concert stage",
        model_name="kling-v3",
        provider_code="builtin",
        duration=5,
        resolution="720p_audio",
        audio=True,
    )

    assert request.audio is True


def test_generate_content_request_defaults_max_tokens_to_zero():
    request = GenerateContentRequest(
        model_name="gemini-3.1-pro-preview",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert request.max_tokens == 0


@pytest.mark.asyncio
async def test_chat_completions_defaults_max_tokens_for_gemini_when_zero(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None, timeout=60):
        captured["json_data"] = json_data
        return {"code": 200, "data": {"choices": []}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.chat_completions(
        model_name="gemini-3.1-pro-preview",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=0,
    )

    assert captured["json_data"]["max_tokens"] == 65536


@pytest.mark.asyncio
async def test_chat_completions_defaults_max_tokens_for_claude_when_zero(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None, timeout=60):
        captured["json_data"] = json_data
        return {"code": 200, "data": {"choices": []}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.chat_completions(
        model_name="claude-opus-4-8",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=0,
    )

    assert captured["json_data"]["max_tokens"] == 128000


@pytest.mark.asyncio
async def test_messages_defaults_max_tokens_for_claude_when_zero(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None, timeout=60):
        captured["json_data"] = json_data
        return {"code": 200, "data": {"content": []}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.messages(
        model="claude-opus-4-8",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=0,
    )

    assert captured["json_data"]["max_tokens"] == 128000


@pytest.mark.asyncio
async def test_chat_completions_stream_events_defaults_max_tokens_for_gemini_when_zero(monkeypatch):
    client = ApimartClient("test-key")
    captured: dict[str, object] = {}

    class _FakeStreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def aiter_lines(self):
            yield "data: [DONE]"

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            del args, kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def stream(self, method, url, json=None, headers=None):
            captured["method"] = method
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _FakeStreamResponse()

    monkeypatch.setattr("app.services.apimart_client.httpx.AsyncClient", _FakeAsyncClient)

    events = [
        event
        async for event in client.chat_completions_stream_events(
            model_name="gemini-3.1-pro-preview",
            messages=[{"role": "user", "content": "hello"}],
            max_tokens=0,
        )
    ]

    assert events == []
    assert captured["json"]["max_tokens"] == 65536


@pytest.mark.asyncio
async def test_chat_completions_forwards_positive_max_tokens_without_threshold(monkeypatch):
    client = ApimartClient("test-key")
    captured = {}

    async def fake_request(method, path, params=None, json_data=None, timeout=60):
        captured["json_data"] = json_data
        return {"code": 200, "data": {"choices": []}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.chat_completions(
        model_name="glm-5.1",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=4096,
    )

    assert captured["json_data"]["max_tokens"] == 4096
