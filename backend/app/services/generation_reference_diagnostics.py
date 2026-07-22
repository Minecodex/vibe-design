from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def reference_value_kind(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "empty"
    lowered = text.lower()
    if lowered.startswith("artifact_ref:"):
        return "artifact_ref"
    if lowered.startswith("data:"):
        return "data_uri"
    if lowered.startswith(("http://", "https://")):
        return "remote_url"
    normalized = text.replace("\\", "/")
    if "/uploads/" in normalized or normalized.startswith(("uploads/", "/api/v1/uploads/", "api/v1/uploads/")):
        return "local_upload"
    if Path(text).is_absolute():
        return "local_file"
    return "relative_path"


def reference_transport_kind(value: str | None) -> str:
    kind = reference_value_kind(value)
    if kind == "data_uri":
        return "data_uri"
    if kind == "remote_url":
        return "url"
    if kind in {"local_upload", "local_file", "relative_path"}:
        return "local_reference"
    return kind


def reference_mime_type(value: str | None) -> str | None:
    text = str(value or "").strip()
    if text.startswith("data:"):
        media_type = text.split(";", 1)[0].removeprefix("data:").strip()
        return media_type or None
    suffix = os.path.splitext(text.split("?", 1)[0])[1].lower().lstrip(".")
    if not suffix:
        return None
    if suffix in {"jpg", "jpeg"}:
        return "image/jpeg"
    if suffix in {"png", "webp", "gif", "bmp"}:
        return f"image/{suffix}"
    return None


def redacted_reference_preview(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("data:"):
        mime = reference_mime_type(text) or "application/octet-stream"
        return f"data:{mime};base64,<redacted>"
    kind = reference_value_kind(text)
    if kind == "remote_url":
        parsed = urlsplit(text)
        filename = Path(parsed.path).name
        suffix = f"/.../{filename}" if filename else "/..."
        return f"{parsed.scheme}://{parsed.netloc}{suffix}"
    if kind in {"local_upload", "local_file", "relative_path"}:
        filename = Path(text.replace("\\", "/").split("?", 1)[0]).name
        return f"{kind}:.../{filename}" if filename else kind
    if len(text) <= 96:
        return text
    return f"{text[:48]}...{text[-32:]}"


def summarize_reference_values(values: list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    clean_values = [str(value).strip() for value in (values or []) if str(value or "").strip()]
    kinds: dict[str, int] = {}
    transports: dict[str, int] = {}
    mime_types: list[str] = []
    previews: list[dict[str, Any]] = []
    for value in clean_values:
        kind = reference_value_kind(value)
        transport = reference_transport_kind(value)
        kinds[kind] = kinds.get(kind, 0) + 1
        transports[transport] = transports.get(transport, 0) + 1
        mime_type = reference_mime_type(value)
        if mime_type and mime_type not in mime_types:
            mime_types.append(mime_type)
        previews.append(
            {
                "kind": kind,
                "transport": transport,
                "mime_type": mime_type,
                "value_preview": redacted_reference_preview(value),
            }
        )
    return {
        "count": len(clean_values),
        "kinds": kinds,
        "transports": transports,
        "mime_types": mime_types,
        "items": previews,
    }


def merge_reference_diagnostics(existing: Any, **updates: Any) -> dict[str, Any]:
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in updates.items():
        if value is not None:
            merged[key] = value
    return merged
