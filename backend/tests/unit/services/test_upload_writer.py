from __future__ import annotations

from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

from app.services.upload_writer import (
    sanitize_svg_file,
    verify_video_file,
    write_upload_with_limit,
)


@pytest.mark.asyncio
async def test_write_upload_with_limit_cleans_part_file_on_oversize(tmp_path):
    destination = tmp_path / "uploads" / "sample.bin"
    upload = UploadFile(filename="sample.bin", file=BytesIO(b"abcdef"))

    with pytest.raises(HTTPException) as exc_info:
        await write_upload_with_limit(upload, destination, max_bytes=3)

    assert exc_info.value.status_code == 413
    assert not destination.exists()
    assert list(destination.parent.glob("*.part")) == []


@pytest.mark.asyncio
async def test_write_upload_with_limit_replaces_destination_atomically(tmp_path):
    destination = tmp_path / "uploads" / "sample.bin"
    upload = UploadFile(filename="sample.bin", file=BytesIO(b"abc"))

    written = await write_upload_with_limit(upload, destination, max_bytes=3)

    assert written == 3
    assert destination.read_bytes() == b"abc"
    assert list(destination.parent.glob("*.part")) == []


def test_verify_video_file_accepts_mp4_ftyp_header(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 16)

    verify_video_file(video, allowed_extensions={".mp4"}, content_type="video/mp4")


def test_verify_video_file_rejects_extension_mismatch(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"<?php system($_GET['c']); ?>")

    with pytest.raises(HTTPException) as exc_info:
        verify_video_file(video, allowed_extensions={".mp4"}, content_type="video/mp4")
    assert exc_info.value.status_code == 400


def test_verify_video_file_rejects_unsupported_extension(tmp_path):
    video = tmp_path / "clip.exe"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42")

    with pytest.raises(HTTPException):
        verify_video_file(video, allowed_extensions={".mp4"}, content_type="video/mp4")


def test_verify_video_file_accepts_webm_ebml_header(tmp_path):
    video = tmp_path / "clip.webm"
    video.write_bytes(b"\x1A\x45\xDF\xA3" + b"\x00" * 12)

    verify_video_file(video, allowed_extensions={".webm"}, content_type="video/webm")


def test_sanitize_svg_strips_script_and_event_attrs(tmp_path):
    svg = tmp_path / "evil.svg"
    svg.write_bytes(
        b'<?xml version="1.0"?>'
        b'<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)">'
        b'<script>alert(1)</script>'
        b'<a href="javascript:alert(1)">x</a>'
        b'<rect width="10" height="10"/>'
        b'</svg>'
    )

    sanitize_svg_file(svg)
    out = svg.read_text(encoding="utf-8")

    assert "<script" not in out.lower()
    assert "onload" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "<rect" in out.lower()


def test_sanitize_svg_rejects_non_svg_root(tmp_path):
    svg = tmp_path / "bad.svg"
    svg.write_bytes(b'<?xml version="1.0"?><html><body/></html>')

    with pytest.raises(HTTPException) as exc_info:
        sanitize_svg_file(svg)
    assert exc_info.value.status_code == 400
