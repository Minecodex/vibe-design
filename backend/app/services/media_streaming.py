from __future__ import annotations

import base64
import os
import uuid
from pathlib import Path

import httpx

from app.core.config import settings

MEDIA_STREAM_CHUNK_BYTES = 1024 * 1024


def media_download_max_bytes() -> int:
    return max(1, int(getattr(settings, "MEDIA_DOWNLOAD_MAX_BYTES", 200 * 1024 * 1024) or 0))


def media_download_timeout_seconds() -> float:
    return max(1.0, float(getattr(settings, "MEDIA_DOWNLOAD_TIMEOUT_SECONDS", 180.0) or 0))


async def stream_http_to_file(url: str, destination: Path, *, max_bytes: int | None = None) -> int:
    limit = media_download_max_bytes() if max_bytes is None else max(1, int(max_bytes or 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    total = 0
    try:
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", url, timeout=media_download_timeout_seconds()) as response:
                response.raise_for_status()
                with part_path.open("wb") as handle:
                    async for chunk in response.aiter_bytes(MEDIA_STREAM_CHUNK_BYTES):
                        if not chunk:
                            continue
                        total += len(chunk)
                        if total > limit:
                            raise ValueError(f"Media download exceeds maximum size of {limit} bytes")
                        handle.write(chunk)
        if total <= 0:
            raise ValueError("Downloaded media is empty")
        os.replace(part_path, destination)
        return total
    except Exception:
        part_path.unlink(missing_ok=True)
        raise


def write_data_uri_to_file(data_uri: str, destination: Path, *, max_bytes: int | None = None) -> int:
    byte_limit = media_download_max_bytes() if max_bytes is None else max(1, int(max_bytes or 0))
    destination.parent.mkdir(parents=True, exist_ok=True)
    _header, _separator, payload = data_uri.partition(",")
    if not payload:
        raise ValueError("Data URI payload is empty")
    part_path = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    try:
        data = base64.b64decode(payload, validate=False)
        if len(data) > byte_limit:
            raise ValueError(f"Data URI payload exceeds maximum size of {byte_limit} bytes")
        part_path.write_bytes(data)
        os.replace(part_path, destination)
        return len(data)
    except Exception:
        part_path.unlink(missing_ok=True)
        raise
