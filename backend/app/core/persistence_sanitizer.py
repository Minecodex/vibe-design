from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_BASE64_KEY_MARKERS = ("base64", "b64")
_BASE64_KEY_NAMES = {"b64_json", "source_blob", "data_uri"}


def sanitize_persistent_payload(value: Any, *, field_name: str | None = None) -> Any:
    """Remove inline base64 payloads before writing long-lived DB/file records."""
    key = str(field_name or "").strip().lower()
    if isinstance(value, str):
        if value.startswith("[omitted-base64:") or value.startswith("[omitted-data-uri:"):
            return value
        if _looks_like_data_uri(value):
            return _data_uri_redaction(value)
        if _is_base64_key(key):
            return _base64_redaction(value)
        return value

    if isinstance(value, list):
        return [sanitize_persistent_payload(item, field_name=field_name) for item in value]

    if isinstance(value, tuple):
        return [sanitize_persistent_payload(item, field_name=field_name) for item in value]

    if isinstance(value, Mapping):
        return {
            item_key: sanitize_persistent_payload(
                item_value,
                field_name=str(item_key),
            )
            for item_key, item_value in value.items()
        }

    return value


def _is_base64_key(key: str) -> bool:
    if not key:
        return False
    if key in _BASE64_KEY_NAMES:
        return True
    return any(marker in key for marker in _BASE64_KEY_MARKERS)


def _looks_like_data_uri(value: str) -> bool:
    prefix = value[:128].lower()
    return prefix.startswith("data:") and ";base64," in prefix


def _data_uri_redaction(value: str) -> str:
    header, _, payload = value.partition(",")
    mime = header[5:].split(";", 1)[0] or "application/octet-stream"
    return f"[omitted-data-uri:{mime};base64_chars={len(payload)}]"


def _base64_redaction(value: str) -> str:
    return f"[omitted-base64:chars={len(value)}]"
