from datetime import datetime

import pytest

from app.services.chat_uploads import build_chat_upload


def test_build_chat_upload_places_file_under_year_month(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    upload = build_chat_upload("photo.png", now=datetime(2026, 4, 29, 12, 30))

    assert upload.path == tmp_path / "uploads" / "chat" / "2026-04" / "photo.png"
    assert upload.url == "/api/v1/uploads/chat/2026-04/photo.png"
    assert upload.path.parent.exists()


def test_build_chat_upload_preserves_existing_extension(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    upload = build_chat_upload("archive.tar.gz", now=datetime(2026, 11, 1))

    assert upload.path.name.endswith(".gz")
    assert upload.url.endswith(".gz")


@pytest.mark.parametrize("filename", ["../photo.png", "nested\\photo.png"])
def test_build_chat_upload_rejects_nested_filename(filename):
    with pytest.raises(ValueError):
        build_chat_upload(filename, now=datetime(2026, 4, 29))
