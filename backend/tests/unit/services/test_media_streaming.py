from __future__ import annotations

import pytest

from app.services import media_streaming


@pytest.mark.asyncio
async def test_stream_http_to_file_uses_configured_download_timeout(monkeypatch, tmp_path):
    observed: dict[str, float] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self, _chunk_size):
            yield b"image-bytes"

    class FakeStream:
        def __init__(self, *, timeout):
            observed["timeout"] = timeout

        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, *, timeout):
            observed["method"] = method
            observed["url"] = url
            return FakeStream(timeout=timeout)

    monkeypatch.setattr(media_streaming.settings, "MEDIA_DOWNLOAD_TIMEOUT_SECONDS", 180.0)
    monkeypatch.setattr(media_streaming.httpx, "AsyncClient", FakeAsyncClient)

    written = await media_streaming.stream_http_to_file(
        "https://cdn.example.test/image.png",
        tmp_path / "image.png",
    )

    assert written == len(b"image-bytes")
    assert observed == {
        "method": "GET",
        "url": "https://cdn.example.test/image.png",
        "timeout": 180.0,
    }
