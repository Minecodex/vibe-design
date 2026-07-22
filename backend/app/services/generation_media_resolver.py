from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

from app.core.config import settings

logger = logging.getLogger(__name__)


class GenerationMediaResolveError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class GenerationMediaUploadResult:
    public_url: str
    object_key: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class GenerationImageResolveBatchResult:
    urls: list[str]
    diagnostics: dict[str, object]


def resolve_generation_image_urls(values: list[str] | tuple[str, ...] | None) -> list[str] | None:
    result = resolve_generation_image_urls_with_diagnostics(values)
    return result.urls or None


def resolve_generation_image_urls_with_diagnostics(
    values: list[str] | tuple[str, ...] | None,
) -> GenerationImageResolveBatchResult:
    clean_values = [str(value or "").strip() for value in (values or []) if str(value or "").strip()]
    resolved = [
        resolve_generation_image_url(value)
        for value in clean_values
    ]
    remote_input_count = sum(1 for value in clean_values if value.startswith(("http://", "https://")))
    object_storage_upload_count = len(resolved) - remote_input_count
    return GenerationImageResolveBatchResult(
        urls=resolved,
        diagnostics={
            "input_count": len(clean_values),
            "output_url_count": len(resolved),
            "remote_input_count": remote_input_count,
            "object_storage_upload_count": object_storage_upload_count,
            "transport_counts": {
                "remote_url": remote_input_count,
                "object_storage_url": object_storage_upload_count,
            },
        },
    )


def resolve_generation_image_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise GenerationMediaResolveError("generation_reference_empty")
    if text.startswith(("http://", "https://")):
        return text
    if text.startswith("data:"):
        raise GenerationMediaResolveError("generation_data_uri_not_allowed")

    file_path = _resolve_local_file(text)
    if file_path is None:
        raise GenerationMediaResolveError("generation_reference_file_not_found")
    return _upload_file_to_object_storage(file_path).public_url


def _resolve_local_file(value: str) -> Path | None:
    relative_upload_path = _upload_relative_path(value)
    if relative_upload_path is not None:
        return _resolve_relative_upload_file(relative_upload_path)

    candidate = Path(value)
    if candidate.is_absolute():
        return _safe_existing_generation_file(candidate)

    return None


def _resolve_relative_upload_file(relative_upload_path: str) -> Path | None:
    relative_path = Path(relative_upload_path)
    for root in _uploads_root_candidates():
        candidate = (root / _strip_overlapping_upload_root(root, relative_path)).resolve()
        safe = _safe_existing_generation_file(candidate)
        if safe is not None:
            return safe
    return None


def _upload_relative_path(value: str) -> str | None:
    parsed = urlsplit(str(value or "").strip())
    normalized = unquote(parsed.path or str(value or "")).replace("\\", "/").strip()
    if normalized.startswith("/api/v1/"):
        normalized = normalized[len("/api/v1/") :]
    elif normalized.startswith("api/v1/"):
        normalized = normalized[len("api/v1/") :]
    elif normalized.startswith("/"):
        normalized = normalized[1:]
    if not normalized.startswith("uploads/"):
        return None
    return normalized


def _uploads_root_candidates() -> list[Path]:
    harness_root = Path(getattr(settings, "HARNESS_WORKSPACE_ROOT", "uploads/harness")).resolve()
    roots = [Path("uploads").resolve(), harness_root]
    if harness_root.name == "harness" and harness_root.parent.name == "uploads":
        roots.append(harness_root.parent.resolve())

    deduped: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            seen.add(key)
            deduped.append(root)
    return deduped


def _strip_overlapping_upload_root(root: Path, relative_path: Path) -> Path:
    root_parts = root.parts[1:] if root.drive else root.parts
    overlap = 0
    max_overlap = min(len(root_parts), len(relative_path.parts))
    for size in range(max_overlap, 0, -1):
        if tuple(root_parts[-size:]) == tuple(relative_path.parts[:size]):
            overlap = size
            break
    if overlap:
        return Path(*relative_path.parts[overlap:])
    if relative_path.parts and relative_path.parts[0] == "uploads" and root.name == "uploads":
        return Path(*relative_path.parts[1:])
    return relative_path


def _safe_existing_generation_file(path: Path) -> Path | None:
    try:
        resolved = path.resolve()
    except OSError:
        return None

    if not resolved.exists() or not resolved.is_file():
        return None
    if any(_is_within_path(resolved, root) for root in _uploads_root_candidates()):
        return resolved
    return None


def _is_within_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def _upload_file_to_object_storage(file_path: Path) -> GenerationMediaUploadResult:
    ak = str(settings.TOS_AK or "").strip()
    sk = str(settings.TOS_SK or "").strip()
    endpoint = str(settings.TOS_ENDPOINT or "").strip()
    region = str(settings.TOS_REGION or "").strip()
    bucket_name = str(settings.TOS_BUCKET_NAME or "").strip()
    if not all([ak, sk, endpoint, region, bucket_name]):
        raise GenerationMediaResolveError("generation_object_storage_not_configured")

    try:
        import tos
    except Exception as exc:  # pragma: no cover - depends on deployment extras
        raise GenerationMediaResolveError("generation_object_storage_client_unavailable") from exc

    try:
        resolved = file_path.resolve()
        size_bytes = resolved.stat().st_size
        object_key = _build_object_key(resolved)
        client = tos.TosClientV2(ak, sk, endpoint, region)
        client.put_object_from_file(bucket_name, object_key, str(resolved))
        public_url = _build_public_url(bucket_name, endpoint, object_key)
        logger.info(
            "Uploaded generation reference to object storage: object_key=%s size_bytes=%s",
            object_key,
            size_bytes,
        )
        return GenerationMediaUploadResult(
            public_url=public_url,
            object_key=object_key,
            size_bytes=size_bytes,
        )
    except GenerationMediaResolveError:
        raise
    except Exception as exc:
        logger.warning(
            "Failed to upload generation reference to object storage: error_type=%s",
            type(exc).__name__,
        )
        raise GenerationMediaResolveError("generation_reference_upload_failed") from exc


def _build_object_key(file_path: Path) -> str:
    prefix = str(settings.TOS_OBJECT_PREFIX or "generation-refs/").strip().replace("\\", "/").lstrip("/")
    if prefix and not prefix.endswith("/"):
        prefix = f"{prefix}/"
    ext = os.path.splitext(file_path.name)[1]
    # Key by content digest (not a random UUID) so the same reference image maps to a
    # stable object: repeated generations / retries overwrite one object instead of
    # accumulating an unbounded number of duplicates in the bucket.
    return f"{prefix}{_file_content_digest(file_path)}{ext}"


def _file_content_digest(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _build_public_url(bucket_name: str, endpoint: str, object_key: str) -> str:
    public_base_url = str(settings.TOS_PUBLIC_BASE_URL or "").strip().rstrip("/")
    if public_base_url:
        return f"{public_base_url}/{object_key}"
    return f"https://{bucket_name}.{endpoint}/{object_key}"
