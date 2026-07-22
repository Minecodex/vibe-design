"""Harness-local media helpers."""

from __future__ import annotations

import base64
import logging
import os
import uuid
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal

from app.core.config import settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext

class MediaProcessingError(ValueError):
    pass


def _base64_image_compress_threshold_bytes() -> int:
    return max(1, int(getattr(settings, "BASE64_IMAGE_COMPRESS_THRESHOLD_BYTES", 20 * 1024 * 1024) or 0))


def _base64_image_quality() -> int:
    return max(1, min(100, int(getattr(settings, "BASE64_IMAGE_QUALITY", 82) or 0)))


def _base64_image_output_max_bytes() -> int:
    return max(1, int(getattr(settings, "BASE64_IMAGE_OUTPUT_MAX_BYTES", 20 * 1024 * 1024) or 0))


def _workspace_root() -> Path:
    return Path(getattr(settings, "HARNESS_WORKSPACE_ROOT", "workspace"))


def _uploads_root_candidates(workspace_root: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    if workspace_root is not None:
        resolved_workspace_root = workspace_root.resolve()
        candidates.append(resolved_workspace_root)
        if resolved_workspace_root.name == "harness" and resolved_workspace_root.parent.name == "uploads":
            candidates.append(resolved_workspace_root.parent.resolve())
    candidates.append(Path("uploads").resolve())

    deduped: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _upload_relative_path(url: str) -> str | None:
    if not url:
        return None
    normalized = str(url).replace("\\", "/").strip()
    if normalized.startswith("/api/v1/"):
        normalized = normalized[len("/api/v1/") :]
    elif normalized.startswith("api/v1/"):
        normalized = normalized[len("api/v1/") :]
    elif normalized.startswith("/"):
        normalized = normalized[1:]
    if not normalized.startswith("uploads/"):
        return None
    return normalized


def _is_within_root(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _allowed_conversation_roots(ctx: "HarnessContext") -> list[Path]:
    return [
        ctx.conversation_dir.resolve(),
        ctx.code_dir.resolve(),
    ]


def _resolve_local_path(url: str, *, workspace_root: Path | None = None) -> str | None:
    """Resolve a local upload URL or absolute path to an existing file path."""
    if not url or str(url).startswith(("http://", "https://", "data:")):
        return None

    candidate = Path(str(url))
    if candidate.is_absolute():
        try:
            if candidate.exists() and candidate.is_file():
                return str(candidate)
        except OSError:
            return None

    relative_upload_path = _upload_relative_path(str(url))
    if not relative_upload_path:
        return None

    resolved_workspace_root = (workspace_root or _workspace_root()).resolve()
    relative_path_obj = Path(relative_upload_path)

    candidate_roots = _uploads_root_candidates(resolved_workspace_root)
    for root in candidate_roots:
        normalized_relative = relative_path_obj
        root_parts = root.parts[1:] if root.drive else root.parts
        overlap = 0
        max_overlap = min(len(root_parts), len(relative_path_obj.parts))
        for size in range(max_overlap, 0, -1):
            if tuple(root_parts[-size:]) == tuple(relative_path_obj.parts[:size]):
                overlap = size
                break

        if overlap:
            remaining_parts = relative_path_obj.parts[overlap:]
            normalized_relative = Path(*remaining_parts) if remaining_parts else Path()

        file_path = (root / normalized_relative).resolve()
        try:
            if not _is_within_root(file_path, root):
                continue
        except OSError:
            continue

        if file_path.exists() and file_path.is_file():
            return str(file_path)
    return None


def resolve_safe_local_media_path(url: str, ctx: "HarnessContext") -> Path | None:
    """Resolve a local media path only when it stays inside allowed Harness roots."""
    if not url or str(url).startswith(("http://", "https://", "data:")):
        return None

    candidate = Path(str(url))
    allowed_roots = _allowed_conversation_roots(ctx)

    if candidate.is_absolute():
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
        if (
            resolved.exists()
            and resolved.is_file()
            and any(_is_within_root(resolved, root) for root in allowed_roots)
        ):
            return resolved
        return None

    workspace_candidate = ctx.resolve_workspace_path(
        str(url),
        default_scope="code",
        allow_fallback_to_files=False,
    )
    if workspace_candidate is not None:
        try:
            resolved_workspace = workspace_candidate.resolve()
        except OSError:
            resolved_workspace = None
        if (
            resolved_workspace is not None
            and resolved_workspace.exists()
            and resolved_workspace.is_file()
            and any(_is_within_root(resolved_workspace, root) for root in allowed_roots)
        ):
            return resolved_workspace

    upload_resolved = _resolve_local_path(str(url), workspace_root=ctx.workspace_root)
    if upload_resolved:
        resolved_upload = Path(upload_resolved).resolve()
        if any(_is_within_root(resolved_upload, root) for root in _uploads_root_candidates(ctx.workspace_root)):
            return resolved_upload

    return None


def _get_mime_type(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
    }
    return mime_map.get(ext, "application/octet-stream")


def _prepare_image_for_base64(file_path: str) -> tuple[bytes, str, dict[str, object]]:
    from PIL import Image

    with Image.open(file_path) as image:
        processed = image.copy()
        original_size = image.size

    has_alpha = "A" in processed.getbands() or "transparency" in getattr(processed, "info", {})
    if has_alpha:
        processed = processed.convert("RGBA")
        output_format = "WEBP"
        mime_type = "image/webp"
        save_kwargs = {
            "format": output_format,
            "quality": _base64_image_quality(),
            "method": 6,
        }
    else:
        processed = processed.convert("RGB")
        output_format = "JPEG"
        mime_type = "image/jpeg"
        save_kwargs = {
            "format": output_format,
            "quality": _base64_image_quality(),
            "optimize": True,
        }

    buffer = BytesIO()
    processed.save(buffer, **save_kwargs)
    output = buffer.getvalue()
    output_max_bytes = _base64_image_output_max_bytes()
    if len(output) > output_max_bytes:
        raise MediaProcessingError(
            f"Compressed image exceeds maximum base64 source size of {output_max_bytes} bytes"
        )
    return output, mime_type, {
        "original_size": original_size,
        "processed_size": processed.size,
        "processed_bytes": len(output),
        "transcoded_format": output_format,
    }


def local_image_to_base64_parts(file_path: str) -> tuple[str, str, dict[str, object]]:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(file_path)
    mime = _get_mime_type(str(path))
    if not mime.startswith("image/"):
        raise MediaProcessingError(f"File is not an image: {file_path}")

    original_bytes = os.path.getsize(path)
    debug: dict[str, object] = {
        "source_kind": "local_path",
        "resolved_kind": "base64",
        "file_path": str(path),
        "original_bytes": original_bytes,
        "compressed": False,
    }
    if original_bytes <= _base64_image_compress_threshold_bytes():
        data = path.read_bytes()
    else:
        data, mime, image_debug = _prepare_image_for_base64(str(path))
        debug.update(image_debug)
        debug["compressed"] = True
    b64 = base64.b64encode(data).decode("utf-8")
    debug["base64_chars"] = len(b64)
    return b64, mime, debug


def local_image_to_base64_data_uri(file_path: str) -> str:
    b64, mime, _debug = local_image_to_base64_parts(file_path)
    return f"data:{mime};base64,{b64}"


def local_url_to_base64(url: str) -> tuple[str, str, dict[str, object]] | None:
    file_path = _resolve_local_path(url)
    if not file_path:
        return None

    try:
        mime = _get_mime_type(file_path)
        debug: dict[str, object] = {
            "source_kind": "local",
            "resolved_kind": "base64",
            "file_path": file_path,
            "original_bytes": os.path.getsize(file_path),
        }
        if mime.startswith("image/"):
            b64, mime, image_debug = local_image_to_base64_parts(file_path)
            debug.update(image_debug)
            debug["source_kind"] = "local"
            return b64, mime, debug
        else:
            with open(file_path, "rb") as f:
                data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        debug["base64_chars"] = len(b64)
        return b64, mime, debug
    except MediaProcessingError:
        raise
    except Exception as e:
        logger.error("[harness] Failed to read local file for base64: %s, error: %s", file_path, e)
        return None


def local_path_to_base64(file_path: str) -> tuple[str, str, dict[str, object]] | None:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None
    try:
        mime = _get_mime_type(str(path))
        debug: dict[str, object] = {
            "source_kind": "local_path",
            "resolved_kind": "base64",
            "file_path": str(path),
            "original_bytes": os.path.getsize(path),
        }
        if mime.startswith("image/"):
            b64, mime, image_debug = local_image_to_base64_parts(str(path))
            debug.update(image_debug)
            return b64, mime, debug
        else:
            with open(path, "rb") as f:
                data = f.read()
        b64 = base64.b64encode(data).decode("utf-8")
        debug["base64_chars"] = len(b64)
        return b64, mime, debug
    except MediaProcessingError:
        raise
    except Exception as e:
        logger.error("[harness] Failed to read local path for base64: %s, error: %s", file_path, e)
        return None


def local_url_to_oss(url: str) -> str | None:
    file_path = _resolve_local_path(url)
    if not file_path:
        return None

    return local_path_to_oss(file_path)


def local_path_to_oss(file_path: str) -> str | None:
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return None

    try:
        import tos

        ak = settings.TOS_AK
        sk = settings.TOS_SK
        endpoint = settings.TOS_ENDPOINT
        region = settings.TOS_REGION
        bucket_name = settings.TOS_BUCKET_NAME

        if not all([ak, sk, endpoint, bucket_name]):
            logger.warning("[harness] TOS credentials not configured, cannot upload to object storage")
            return None

        client = tos.TosClientV2(ak, sk, endpoint, region)
        ext = os.path.splitext(str(path))[1]
        object_key = f"harness-refs/{uuid.uuid4().hex}{ext}"
        client.put_object_from_file(bucket_name, object_key, str(path))
        public_url = f"https://{bucket_name}.{endpoint}/{object_key}"
        logger.info("[harness] Uploaded %s to TOS: %s", path, public_url)
        return public_url
    except Exception as e:
        logger.error("[harness] Failed to upload %s to TOS: %s", path, e)
        return None


def resolve_url_for_api(url: str, prefer: Literal["base64", "url"] = "base64") -> dict | None:
    if not url:
        return None

    if url.startswith(("http://", "https://")):
        return {
            "type": "url",
            "url": url,
            "debug": {"source_kind": "remote", "resolved_kind": "url"},
        }

    if url.startswith("data:"):
        try:
            from app.services.media_streaming import media_download_max_bytes

            header, b64_data = url.split(",", 1)
            decoded_bytes = base64.b64decode(b64_data, validate=False)
            byte_limit = media_download_max_bytes()
            if len(decoded_bytes) > byte_limit:
                raise MediaProcessingError(
                    f"Data URI payload exceeds maximum size of {byte_limit} bytes"
                )
            mime = header.split(":")[1].split(";")[0]
            return {
                "type": "base64",
                "data": b64_data,
                "mime_type": mime,
                "debug": {
                    "source_kind": "data_uri",
                    "resolved_kind": "base64",
                    "base64_chars": len(b64_data),
                    "decoded_bytes": len(decoded_bytes),
                },
            }
        except MediaProcessingError:
            raise
        except Exception:
            return {"type": "url", "url": url, "debug": {"source_kind": "data_uri", "resolved_kind": "url"}}

    if prefer == "base64":
        result = local_url_to_base64(url)
        if result:
            b64_data, mime, debug = result
            return {"type": "base64", "data": b64_data, "mime_type": mime, "debug": debug}
        tos_url = local_url_to_oss(url)
        if tos_url:
            return {
                "type": "url",
                "url": tos_url,
                "debug": {"source_kind": "local", "resolved_kind": "url", "upload_target": "tos"},
            }
    else:
        tos_url = local_url_to_oss(url)
        if tos_url:
            return {
                "type": "url",
                "url": tos_url,
                "debug": {"source_kind": "local", "resolved_kind": "url", "upload_target": "tos"},
            }
        result = local_url_to_base64(url)
        if result:
            b64_data, mime, debug = result
            return {"type": "base64", "data": b64_data, "mime_type": mime, "debug": debug}

    return None
