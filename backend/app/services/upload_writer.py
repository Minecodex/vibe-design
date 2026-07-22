from __future__ import annotations

import os
import re
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

UPLOAD_READ_CHUNK_BYTES = 1024 * 1024

IMAGE_RASTER_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
IMAGE_VECTOR_EXTENSIONS = {".svg"}
IMAGE_FILE_EXTENSIONS = IMAGE_RASTER_EXTENSIONS | IMAGE_VECTOR_EXTENSIONS
VIDEO_FILE_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi"}


async def write_upload_with_limit(
    file: UploadFile,
    destination: Path,
    *,
    max_bytes: int,
) -> int:
    """Write an UploadFile through a bounded .part file, then atomically replace."""
    max_bytes = max(1, int(max_bytes or 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    total = 0
    try:
        with part_path.open("wb") as handle:
            while True:
                remaining = max_bytes + 1 - total
                read_size = min(UPLOAD_READ_CHUNK_BYTES, max(1, remaining))
                chunk = await file.read(read_size)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Upload exceeds maximum size of {max_bytes} bytes",
                    )
                handle.write(chunk)
        os.replace(part_path, destination)
        return total
    except Exception:
        part_path.unlink(missing_ok=True)
        raise


def verify_video_file(path: Path, *, allowed_extensions: set[str], content_type: str | None) -> None:
    suffix = path.suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported video extension: {suffix or '(none)'}")
    if content_type and not str(content_type).lower().startswith("video/"):
        raise HTTPException(status_code=400, detail=f"Unsupported video content type: {content_type}")
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except OSError as exc:
        raise HTTPException(status_code=400, detail="Invalid video file") from exc
    if not _video_header_matches(suffix, header):
        raise HTTPException(status_code=400, detail="Video file content does not match its extension")


_SVG_DANGEROUS_LOCALNAMES = {"script", "foreignobject"}
_SVG_JAVASCRIPT_URL = re.compile(r"^\s*javascript:", re.IGNORECASE)

ET.register_namespace("", "http://www.w3.org/2000/svg")
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


def sanitize_svg_file(path: Path) -> None:
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail="Invalid SVG file") from exc

    root = tree.getroot()
    if _localname(root.tag).lower() != "svg":
        raise HTTPException(status_code=400, detail="File is not an SVG document")

    for parent in list(root.iter()):
        for child in list(parent):
            if _localname(child.tag).lower() in _SVG_DANGEROUS_LOCALNAMES:
                parent.remove(child)
    for element in root.iter():
        _strip_svg_dangerous_attrs(element)

    tree.write(path, encoding="utf-8", xml_declaration=True)


def _localname(tag: str) -> str:
    return tag.split("}", 1)[1] if "}" in tag else tag


def _strip_svg_dangerous_attrs(element: ET.Element) -> None:
    for attr in list(element.attrib):
        local = _localname(attr).lower()
        if local.startswith("on"):
            del element.attrib[attr]
            continue
        if local in {"href", "src"} and _SVG_JAVASCRIPT_URL.match(element.attrib[attr] or ""):
            del element.attrib[attr]


def _video_header_matches(suffix: str, header: bytes) -> bool:
    if suffix in {".mp4", ".mov"}:
        return len(header) >= 8 and header[4:8] == b"ftyp"
    if suffix == ".webm":
        return header.startswith(b"\x1A\x45\xDF\xA3")
    if suffix == ".avi":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"AVI "
    return False


def verify_image_file(path: Path, *, allowed_extensions: set[str], content_type: str | None) -> None:
    suffix = path.suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported image extension: {suffix or '(none)'}")
    if content_type and not str(content_type).lower().startswith("image/"):
        raise HTTPException(status_code=400, detail=f"Unsupported image content type: {content_type}")
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid image file") from exc
