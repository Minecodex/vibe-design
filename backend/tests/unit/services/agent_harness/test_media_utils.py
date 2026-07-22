from __future__ import annotations

import base64
from io import BytesIO

import pytest
from PIL import Image

from app.services.agent_harness.core.utils.media_utils import (
    MediaProcessingError,
    local_image_to_base64_parts,
    resolve_url_for_api,
)


def _write_png(path, *, size=(8, 8), color=(255, 0, 0)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    data = buffer.getvalue()
    path.write_bytes(data)
    return data


def test_local_image_to_base64_keeps_small_image_bytes_and_mime(tmp_path, monkeypatch):
    image_path = tmp_path / "small.png"
    original = _write_png(image_path)
    monkeypatch.setattr(
        "app.core.config.settings.BASE64_IMAGE_COMPRESS_THRESHOLD_BYTES",
        len(original),
        raising=False,
    )

    b64, mime, debug = local_image_to_base64_parts(str(image_path))

    assert mime == "image/png"
    assert base64.b64decode(b64) == original
    assert debug["compressed"] is False


def test_local_image_to_base64_compresses_only_when_file_bytes_exceed_threshold(tmp_path, monkeypatch):
    image_path = tmp_path / "large.png"
    original = _write_png(image_path, size=(64, 64))
    monkeypatch.setattr("app.core.config.settings.BASE64_IMAGE_COMPRESS_THRESHOLD_BYTES", 1, raising=False)
    monkeypatch.setattr("app.core.config.settings.BASE64_IMAGE_OUTPUT_MAX_BYTES", 1024 * 1024, raising=False)

    b64, mime, debug = local_image_to_base64_parts(str(image_path))

    assert mime == "image/jpeg"
    assert base64.b64decode(b64) != original
    assert debug["compressed"] is True


def test_local_image_to_base64_rejects_compressed_output_over_limit(tmp_path, monkeypatch):
    image_path = tmp_path / "large.png"
    _write_png(image_path, size=(64, 64))
    monkeypatch.setattr("app.core.config.settings.BASE64_IMAGE_COMPRESS_THRESHOLD_BYTES", 1, raising=False)
    monkeypatch.setattr("app.core.config.settings.BASE64_IMAGE_OUTPUT_MAX_BYTES", 1, raising=False)

    with pytest.raises(MediaProcessingError):
        local_image_to_base64_parts(str(image_path))


def test_resolve_url_for_api_rejects_large_data_uri(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.MEDIA_DOWNLOAD_MAX_BYTES", 1, raising=False)

    with pytest.raises(MediaProcessingError):
        resolve_url_for_api("data:image/png;base64,YWJjZGVmZ2g=")
