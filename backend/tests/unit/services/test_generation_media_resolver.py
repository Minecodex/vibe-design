import hashlib
import sys
from types import SimpleNamespace

import pytest

from app.services.generation_media_resolver import (
    GenerationMediaResolveError,
    resolve_generation_image_url,
    resolve_generation_image_urls,
    resolve_generation_image_urls_with_diagnostics,
)


# Reference objects are content-addressed (sha256 of the file bytes), so the object key is
# deterministic for a given payload instead of a random UUID.
def _expected_key(ext: str, *, content: bytes = b"fake") -> str:
    return f"generation-refs/{hashlib.sha256(content).hexdigest()}{ext}"


def _expected_url(ext: str, *, base: str = "https://design-public.tos-cn-guangzhou.volces.com", content: bytes = b"fake") -> str:
    return f"{base}/{_expected_key(ext, content=content)}"


def _configure_fake_tos(monkeypatch, *, public_base_url: str = ""):
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
    monkeypatch.setattr("app.core.config.settings.TOS_PUBLIC_BASE_URL", public_base_url)
    monkeypatch.setattr("app.core.config.settings.TOS_OBJECT_PREFIX", "generation-refs/")
    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=FakeTosClient))
    return uploads


def test_resolve_generation_image_url_passes_remote_urls_through():
    assert resolve_generation_image_url("https://example.test/ref.png") == "https://example.test/ref.png"
    assert resolve_generation_image_urls(["https://example.test/ref.png"]) == ["https://example.test/ref.png"]


def test_resolve_generation_image_url_rejects_data_uri():
    with pytest.raises(GenerationMediaResolveError) as exc:
        resolve_generation_image_url("data:image/png;base64,ZmFrZQ==")

    assert exc.value.code == "generation_data_uri_not_allowed"


def test_resolve_generation_image_url_uploads_local_reference(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "uploads" / "canvas" / "1" / "ref.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")
    uploads = _configure_fake_tos(monkeypatch)

    result = resolve_generation_image_url("/api/v1/uploads/canvas/1/ref.png")

    assert result == _expected_url(".png")
    assert uploads == [
        ("design-public", _expected_key(".png"), str(image_path.resolve()))
    ]


def test_resolve_generation_image_url_treats_api_upload_as_url_path_on_posix(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "uploads" / "canvas" / "3" / "ref.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")
    uploads = _configure_fake_tos(monkeypatch)

    result = resolve_generation_image_url("/api/v1/uploads/canvas/3/ref.jpg")

    assert result == _expected_url(".jpg")
    assert uploads == [
        ("design-public", _expected_key(".jpg"), str(image_path.resolve()))
    ]


def test_resolve_generation_image_url_ignores_upload_url_query(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "uploads" / "canvas" / "3" / "ref.webp"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")
    _configure_fake_tos(monkeypatch)

    result = resolve_generation_image_url("/api/v1/uploads/canvas/3/ref.webp?v=123#preview")

    assert result == _expected_url(".webp")


def test_resolve_generation_image_urls_reports_transport_diagnostics(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "uploads" / "canvas" / "1" / "ref.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")
    _configure_fake_tos(monkeypatch)

    result = resolve_generation_image_urls_with_diagnostics(
        ["https://example.test/ref.jpg", "/api/v1/uploads/canvas/1/ref.png"]
    )

    assert result.urls == [
        "https://example.test/ref.jpg",
        _expected_url(".png"),
    ]
    assert result.diagnostics == {
        "input_count": 2,
        "output_url_count": 2,
        "remote_input_count": 1,
        "object_storage_upload_count": 1,
        "transport_counts": {"remote_url": 1, "object_storage_url": 1},
    }


def test_resolve_generation_image_url_uses_public_base_url(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "uploads" / "canvas" / "1" / "ref.jpg"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")
    _configure_fake_tos(monkeypatch, public_base_url="https://cdn.example.test/assets/")

    result = resolve_generation_image_url("uploads/canvas/1/ref.jpg")

    assert result == _expected_url(".jpg", base="https://cdn.example.test/assets")


def test_object_key_is_content_addressed_and_deduplicates(monkeypatch, tmp_path):
    """Same bytes -> same object key (idempotent overwrite); different bytes -> different key.

    Guards the fix that replaced random-UUID keys with a content digest so repeated
    references do not accumulate unbounded duplicate objects in the bucket.
    """
    monkeypatch.chdir(tmp_path)
    first = tmp_path / "uploads" / "canvas" / "1" / "a.png"
    second = tmp_path / "uploads" / "canvas" / "2" / "b.png"  # different path/name, same bytes
    third = tmp_path / "uploads" / "canvas" / "3" / "c.png"  # different bytes
    for path in (first, second, third):
        path.parent.mkdir(parents=True)
    first.write_bytes(b"same-bytes")
    second.write_bytes(b"same-bytes")
    third.write_bytes(b"other-bytes")
    uploads = _configure_fake_tos(monkeypatch)

    first_url = resolve_generation_image_url("/api/v1/uploads/canvas/1/a.png")
    second_url = resolve_generation_image_url("/api/v1/uploads/canvas/2/b.png")
    third_url = resolve_generation_image_url("/api/v1/uploads/canvas/3/c.png")

    # Identical content -> identical object key, regardless of source filename/path.
    assert first_url == second_url
    assert first_url == _expected_url(".png", content=b"same-bytes")
    # Distinct content -> distinct object key.
    assert third_url != first_url
    assert third_url == _expected_url(".png", content=b"other-bytes")
    # The object key set has exactly two distinct keys (the duplicate collapses).
    assert len({key for _bucket, key, _file in uploads}) == 2


def test_resolve_generation_image_url_fails_when_object_storage_is_not_configured(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "uploads" / "canvas" / "1" / "ref.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"fake")
    monkeypatch.setattr("app.core.config.settings.TOS_AK", "")
    monkeypatch.setattr("app.core.config.settings.TOS_SK", "")
    monkeypatch.setattr("app.core.config.settings.TOS_ENDPOINT", "")
    monkeypatch.setattr("app.core.config.settings.TOS_REGION", "")
    monkeypatch.setattr("app.core.config.settings.TOS_BUCKET_NAME", "")

    with pytest.raises(GenerationMediaResolveError) as exc:
        resolve_generation_image_url("/api/v1/uploads/canvas/1/ref.png")

    assert exc.value.code == "generation_object_storage_not_configured"
