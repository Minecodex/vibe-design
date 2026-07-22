from datetime import datetime

import pytest

from app.services.generated_uploads import (
    build_generated_upload,
    resolve_generated_upload_path,
)


def test_build_generated_upload_places_file_under_year_month(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    upload = build_generated_upload("image.png", now=datetime(2026, 4, 29, 12, 30))

    assert upload.path == tmp_path / "uploads" / "generated" / "2026-04" / "image.png"
    assert upload.url == "/api/v1/uploads/generated/2026-04/image.png"
    assert upload.path.parent.exists()


def test_resolve_generated_upload_path_supports_nested_and_legacy_urls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    nested = tmp_path / "uploads" / "generated" / "2026-04" / "image.png"
    legacy = tmp_path / "uploads" / "generated" / "legacy.png"
    nested.parent.mkdir(parents=True)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    nested.write_bytes(b"nested")
    legacy.write_bytes(b"legacy")

    assert resolve_generated_upload_path("/api/v1/uploads/generated/2026-04/image.png") == nested
    assert resolve_generated_upload_path("/api/v1/uploads/generated/legacy.png") == legacy


def test_generated_upload_rejects_nested_filename():
    with pytest.raises(ValueError):
        build_generated_upload("../image.png", now=datetime(2026, 4, 29))
