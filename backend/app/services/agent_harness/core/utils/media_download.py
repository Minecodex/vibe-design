from __future__ import annotations

import asyncio
import mimetypes
import os
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.services.generated_uploads import resolve_generated_upload_path
from app.services.media_streaming import (
    MEDIA_STREAM_CHUNK_BYTES,
    media_download_max_bytes,
    media_download_timeout_seconds,
)
from app.services.agent_harness.workspace.generated_content.asset_store import register_asset


def _infer_extension(file_url: str, ext_hint: str) -> str:
    parsed = urlparse(file_url)
    suffix = Path(parsed.path).suffix.lstrip(".").lower()
    if suffix:
        return suffix

    guessed_mime, _ = mimetypes.guess_type(file_url)
    if guessed_mime:
        guessed_ext = mimetypes.guess_extension(guessed_mime)
        if guessed_ext:
            return guessed_ext.lstrip(".")

    return ext_hint.lstrip(".").lower()


async def _download_http_to_file(file_url: str, destination: Path) -> int:
    limit = media_download_max_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.part")
    total = 0
    try:
        async with httpx.AsyncClient() as client:
            stream = getattr(client, "stream", None)
            if callable(stream):
                async with client.stream("GET", file_url, timeout=media_download_timeout_seconds()) as response:
                    response.raise_for_status()
                    with part_path.open("wb") as handle:
                        async for chunk in response.aiter_bytes(MEDIA_STREAM_CHUNK_BYTES):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > limit:
                                raise ValueError(f"Media download exceeds maximum size of {limit} bytes")
                            handle.write(chunk)
            else:
                response = await client.get(file_url, timeout=media_download_timeout_seconds())
                response.raise_for_status()
                content = bytes(getattr(response, "content", b"") or b"")
                total = len(content)
                if total > limit:
                    raise ValueError(f"Media download exceeds maximum size of {limit} bytes")
                part_path.write_bytes(content)
        if total <= 0:
            raise ValueError("Downloaded media is empty")
        os.replace(part_path, destination)
        return total
    except Exception:
        part_path.unlink(missing_ok=True)
        raise


async def download_media_to_workspace(
    ctx,
    file_url: str,
    *,
    ext_hint: str,
    media_kind: str,
    asset_id: str | None = None,
) -> str:
    ext = ext_hint.lstrip(".").lower() if asset_id else _infer_extension(file_url, ext_hint)
    filename = f"{media_kind}_{uuid.uuid4().hex}.{ext}"
    temp_dir = ctx.conversation_dir / ".meta" / "download_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / filename

    local_generated_path = resolve_generated_upload_path(file_url)
    if local_generated_path is not None:
        if local_generated_path.stat().st_size <= 0:
            raise ValueError("Downloaded media is empty")
        if local_generated_path.stat().st_size > media_download_max_bytes():
            raise ValueError(f"Media download exceeds maximum size of {media_download_max_bytes()} bytes")
        shutil.copy2(local_generated_path, temp_path)
    else:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                await _download_http_to_file(file_url, temp_path)
                break
            except Exception:
                if attempt >= max_attempts:
                    raise
                await asyncio.sleep(2 ** (attempt - 1))

    try:
        asset = register_asset(
            ctx.user_id,
            ctx.conversation_id,
            source_path=temp_path,
            kind="reference",
            original_name=filename,
            mime_type=mimetypes.guess_type(filename)[0],
            source=media_kind,
            source_url=file_url,
            run_id=ctx.subagent_run_id or ctx.run_id,
            asset_id=asset_id,
        )
    finally:
        temp_path.unlink(missing_ok=True)
    return str(asset["path"])
