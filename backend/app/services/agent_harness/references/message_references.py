from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Callable
from urllib.parse import unquote, urlsplit


class InvalidMessageReferenceError(ValueError):
    pass


def resolve_upload_attachment_references(
    references: Any,
    *,
    attachments: list[dict] | None,
) -> list[dict[str, Any]]:
    return resolve_message_references(references, attachments=attachments)


def resolve_message_references(
    references: Any,
    *,
    attachments: list[dict] | None = None,
    canvas_items: list[dict[str, Any]] | None = None,
    project_id: int | None = None,
    content: str | None = None,
    is_artifact_reference_available: Callable[[str], bool] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(references, list):
        return []
    content_mark_keys = _parse_canvas_mark_content_keys(content) if content is not None else None
    attachment_paths = {
        normalized
        for attachment in (attachments or [])
        if isinstance(attachment, dict)
        for normalized in [_normalize_reference_input_path(attachment.get("url") or attachment.get("path"))]
        if normalized
    }
    attached_reference_values = {
        normalized
        for attachment in (attachments or [])
        if isinstance(attachment, dict)
        for normalized in [_normalize_attached_reference_value(attachment.get("url") or attachment.get("path"))]
        if normalized
    }
    canvas_item_map = {
        str(item.get("id")): item
        for item in (canvas_items or [])
        if isinstance(item, dict) and item.get("id") is not None
    }
    resolved: list[dict[str, Any]] = []
    for index, item in enumerate(references, start=1):
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        if kind == "upload_attachment":
            resolved.append(_resolve_upload_attachment_reference(item, index=index, attachment_paths=attachment_paths))
            continue
        if kind == "canvas_item":
            resolved.append(
                _resolve_canvas_item_reference(
                    item,
                    index=index,
                    canvas_item_map=canvas_item_map,
                    project_id=project_id,
                    is_artifact_reference_available=is_artifact_reference_available,
                )
            )
            continue
        if kind == "home_asset":
            resolved.append(
                _resolve_home_asset_reference(
                    item,
                    index=index,
                    attached_reference_values=attached_reference_values,
                )
            )
            continue
        if kind == "workspace_file":
            resolved.append(
                _resolve_workspace_file_reference(
                    item,
                    index=index,
                    attached_reference_values=attached_reference_values,
                )
            )
            continue
        if kind == "canvas_mark":
            resolved.append(
                _resolve_canvas_mark_reference(
                    item,
                    index=index,
                    canvas_item_map=canvas_item_map,
                    project_id=project_id,
                    content_mark_keys=content_mark_keys,
                    is_artifact_reference_available=is_artifact_reference_available,
                )
            )
            continue
    return resolved


def _resolve_upload_attachment_reference(
    item: dict[str, Any],
    *,
    index: int,
    attachment_paths: set[str],
) -> dict[str, Any]:
    path = _reference_source_path(item)
    normalized_path = _normalize_reference_input_path(path)
    if not normalized_path:
        reference_id = str(item.get("id") or f"upload-{index}")
        raise InvalidMessageReferenceError(f"Invalid upload reference path: {reference_id}")
    if attachment_paths and normalized_path not in attachment_paths:
        reference_id = str(item.get("id") or f"upload-{index}")
        raise InvalidMessageReferenceError(f"Upload reference is not attached to this message: {reference_id}")
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    return {
        "id": str(item.get("id") or f"upload-{index}"),
        "kind": "upload_attachment",
        "media_type": str(item.get("media_type") or "image"),
        "display_name": str(item.get("display_name") or item.get("name") or PurePosixPath(normalized_path).name),
        "tool_reference": normalized_path,
        "source": {
            "type": str(source.get("type") or "harness_input"),
            "path": normalized_path,
        },
    }


def _resolve_home_asset_reference(
    item: dict[str, Any],
    *,
    index: int,
    attached_reference_values: set[str],
) -> dict[str, Any]:
    reference_id = str(item.get("id") or f"home-asset-{index}")
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    url = _normalize_home_asset_url(source.get("url") or item.get("tool_reference") or item.get("url"))
    if not url:
        raise InvalidMessageReferenceError(f"Invalid home asset reference URL: {reference_id}")
    if attached_reference_values and url not in attached_reference_values:
        raise InvalidMessageReferenceError(f"Home asset reference is not attached to this message: {reference_id}")
    return {
        "id": reference_id,
        "kind": "home_asset",
        "media_type": str(item.get("media_type") or "image"),
        "display_name": str(item.get("display_name") or PurePosixPath(urlsplit(url).path).name or "image"),
        "tool_reference": url,
        "source": {
            "type": "home_asset",
            "url": url,
        },
    }


def _resolve_workspace_file_reference(
    item: dict[str, Any],
    *,
    index: int,
    attached_reference_values: set[str],
) -> dict[str, Any]:
    reference_id = str(item.get("id") or f"workspace-file-{index}")
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    path = _normalize_workspace_reference_path(source.get("path") or item.get("tool_reference") or item.get("path"))
    if not path:
        raise InvalidMessageReferenceError(f"Invalid workspace file reference path: {reference_id}")
    if attached_reference_values and path not in attached_reference_values:
        raise InvalidMessageReferenceError(f"Workspace file reference is not attached to this message: {reference_id}")
    return {
        "id": reference_id,
        "kind": "workspace_file",
        "media_type": str(item.get("media_type") or "image"),
        "display_name": str(item.get("display_name") or PurePosixPath(path).name),
        "tool_reference": path,
        "source": {
            "type": "workspace_file",
            "path": path,
        },
    }


def _resolve_canvas_item_reference(
    item: dict[str, Any],
    *,
    index: int,
    canvas_item_map: dict[str, dict[str, Any]],
    project_id: int | None,
    is_artifact_reference_available: Callable[[str], bool] | None,
) -> dict[str, Any]:
    reference_id = str(item.get("id") or f"canvas-{index}")
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    item_id = _normalize_canvas_item_id(source.get("item_id") or item.get("item_id"))
    if not item_id:
        raise InvalidMessageReferenceError(f"Canvas reference is missing item_id: {reference_id}")
    canvas_item = canvas_item_map.get(item_id)
    if canvas_item is None:
        raise InvalidMessageReferenceError(f"Canvas item reference was not found: {reference_id}")
    tool_reference, source_snapshot = _resolve_canvas_item_tool_reference(
        canvas_item,
        item_id=item_id,
        project_id=project_id,
        is_artifact_reference_available=is_artifact_reference_available,
    )
    if not tool_reference:
        raise InvalidMessageReferenceError(f"Invalid canvas upload reference: {reference_id}")
    media_type = str(item.get("media_type") or _canvas_media_type(canvas_item) or "image")
    return {
        "id": reference_id,
        "kind": "canvas_item",
        "media_type": media_type,
        "display_name": str(item.get("display_name") or canvas_item.get("name") or PurePosixPath(tool_reference).name),
        "tool_reference": tool_reference,
        "source": source_snapshot,
    }


def _resolve_canvas_mark_reference(
    item: dict[str, Any],
    *,
    index: int,
    canvas_item_map: dict[str, dict[str, Any]],
    project_id: int | None,
    content_mark_keys: set[tuple[str, str, int, int]] | None,
    is_artifact_reference_available: Callable[[str], bool] | None,
) -> dict[str, Any]:
    reference_id = str(item.get("id") or f"canvas-mark-{index}")
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    mark = item.get("mark") if isinstance(item.get("mark"), dict) else {}
    parsed_source_token = _parse_canvas_mark_token(source.get("mark_id") or item.get("id"))
    mark_id = str(
        (parsed_source_token or {}).get("mark_id")
        or source.get("mark_id")
        or mark.get("id")
        or ""
    ).strip()
    image_item_id = _normalize_canvas_item_id(
        (parsed_source_token or {}).get("image_item_id")
        or source.get("image_item_id")
        or mark.get("image_item_id")
    )
    mark_image_item_id = _normalize_canvas_item_id(mark.get("image_item_id") or image_item_id)
    if not mark_id or not image_item_id:
        raise InvalidMessageReferenceError(f"Canvas mark reference is missing mark or image id: {reference_id}")
    if mark_image_item_id != image_item_id:
        raise InvalidMessageReferenceError(f"Canvas mark reference does not belong to source image: {reference_id}")
    canvas_item = canvas_item_map.get(image_item_id)
    if canvas_item is None:
        raise InvalidMessageReferenceError(f"Canvas mark source item was not found: {reference_id}")
    position = mark.get("position") if isinstance(mark.get("position"), dict) else {}
    x = _normalized_coordinate(position.get("x"))
    y = _normalized_coordinate(position.get("y"))
    if x is None or y is None:
        raise InvalidMessageReferenceError(f"Invalid canvas mark position: {reference_id}")
    try:
        mark_number = int(mark.get("number") or 0)
    except (TypeError, ValueError):
        mark_number = 0
    if mark_number <= 0:
        raise InvalidMessageReferenceError(f"Invalid canvas mark number: {reference_id}")
    if content_mark_keys is not None and (mark_id, image_item_id, _coordinate_key(x), _coordinate_key(y)) not in content_mark_keys:
        raise InvalidMessageReferenceError(f"Canvas mark reference is not present in message content: {reference_id}")
    tool_reference, image_source = _resolve_canvas_item_tool_reference(
        canvas_item,
        item_id=image_item_id,
        project_id=project_id,
        is_artifact_reference_available=is_artifact_reference_available,
    )
    if not tool_reference:
        raise InvalidMessageReferenceError(f"Invalid canvas mark source reference: {reference_id}")
    label = str(item.get("display_name") or mark.get("label") or f"mark {mark_number}")
    return {
        "id": reference_id,
        "kind": "canvas_mark",
        "media_type": str(item.get("media_type") or "image"),
        "display_name": label,
        "tool_reference": tool_reference,
        "source": {
            "type": "canvas_mark",
            "mark_id": mark_id,
            "image_item_id": image_item_id,
            "image_source": image_source,
        },
        "mark": {
            "id": mark_id,
            "image_item_id": image_item_id,
            "number": mark_number,
            "label": label,
            "position": {"x": x, "y": y},
        },
    }


def _resolve_canvas_item_tool_reference(
    canvas_item: dict[str, Any],
    *,
    item_id: str,
    project_id: int | None,
    is_artifact_reference_available: Callable[[str], bool] | None,
) -> tuple[str | None, dict[str, Any]]:
    artifact_ref = _normalize_artifact_ref(canvas_item.get("artifact_ref"))
    if artifact_ref and (
        is_artifact_reference_available is None
        or is_artifact_reference_available(artifact_ref)
    ):
        return artifact_ref, {
            "type": "canvas_item",
            "item_id": item_id,
            "origin": "generated_artifact",
            "artifact_ref": artifact_ref,
        }
    url = str(canvas_item.get("url") or canvas_item.get("result_url") or "").strip()
    source_snapshot: dict[str, Any] = {
        "type": "canvas_item",
        "item_id": item_id,
    }
    if artifact_ref:
        source_snapshot["origin"] = "canvas_url_fallback"
    return _normalize_canvas_upload_reference(url, project_id=project_id), source_snapshot


def _reference_source_path(item: dict[str, Any]) -> Any:
    source = item.get("source")
    if isinstance(source, dict):
        path = source.get("path") or source.get("url")
        if path:
            return path
    return item.get("tool_reference") or item.get("url") or item.get("path")


def _normalize_reference_input_path(value: Any) -> str | None:
    raw = unquote(str(value or "").strip()).replace("\\", "/")
    if not raw:
        return None
    raw = raw.lstrip("./")
    path = PurePosixPath(raw)
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    normalized = path.as_posix()
    if not normalized.startswith("references/inputs/"):
        return None
    return normalized


def _normalize_attached_reference_value(value: Any) -> str | None:
    return (
        _normalize_reference_input_path(value)
        or _normalize_workspace_reference_path(value)
        or _normalize_home_asset_url(value)
    )


def _normalize_workspace_reference_path(value: Any) -> str | None:
    raw = unquote(str(value or "").strip()).replace("\\", "/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc:
        return None
    raw = raw.lstrip("./").lstrip("/")
    path = PurePosixPath(raw)
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        return None
    normalized = path.as_posix()
    allowed_prefixes = (
        "published/",
        "project/",
        "references/sources/",
        "references/generated/",
    )
    if not normalized.startswith(allowed_prefixes):
        return None
    return normalized


def _normalize_home_asset_url(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or any(ch.isspace() for ch in raw):
        return None
    parsed = urlsplit(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    if raw.startswith("/api/v1/"):
        return raw
    return None


def _normalize_canvas_upload_reference(value: Any, *, project_id: int | None) -> str | None:
    raw = str(value or "").strip().replace("\\", "/")
    if not raw:
        return None
    parsed = urlsplit(raw)
    path_value = parsed.path if parsed.scheme or parsed.netloc else raw
    decoded = unquote(path_value).replace("\\", "/")
    if not decoded.startswith("/api/v1/uploads/canvas/"):
        return None
    path = PurePosixPath(decoded)
    parts = path.parts
    if any(part in {"", ".", ".."} for part in parts):
        return None
    expected_parts_prefix = ("/", "api", "v1", "uploads", "canvas")
    if parts[:5] != expected_parts_prefix or len(parts) < 7:
        return None
    if project_id is not None and parts[5] != str(project_id):
        return None
    return path.as_posix()


def _normalize_artifact_ref(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw.startswith("artifact_ref:"):
        return None
    artifact_id = raw.removeprefix("artifact_ref:")
    if not artifact_id or any(ch.isspace() for ch in raw) or "/" in artifact_id or "\\" in artifact_id:
        return None
    return raw


def _normalized_coordinate(value: Any) -> float | None:
    try:
        coordinate = float(value)
    except (TypeError, ValueError):
        return None
    if coordinate < 0 or coordinate > 1:
        return None
    return coordinate


def _coordinate_key(value: float) -> int:
    return int(round(value * 10000))


def _normalize_canvas_item_id(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("canvas:"):
        raw = raw.removeprefix("canvas:").strip()
    return raw


def _parse_canvas_mark_token(value: Any) -> dict[str, Any] | None:
    raw = str(value or "").strip()
    match = re.fullmatch(r"canvas-mark:([^:]+):image:([^:]+):x:([0-9.]+):y:([0-9.]+)", raw)
    if not match:
        return None
    x = _normalized_coordinate(match.group(3))
    y = _normalized_coordinate(match.group(4))
    if x is None or y is None:
        return None
    return {
        "mark_id": match.group(1).strip(),
        "image_item_id": _normalize_canvas_item_id(match.group(2)),
        "x": x,
        "y": y,
    }


def _parse_canvas_mark_content_keys(content: str | None) -> set[tuple[str, str, int, int]]:
    keys: set[tuple[str, str, int, int]] = set()
    if not content:
        return keys
    pattern = re.compile(r"#\[([^\]]*)\]\((canvas-mark:[^)]*)\)")
    for match in pattern.finditer(content):
        parsed = _parse_canvas_mark_token(match.group(2))
        if not parsed:
            continue
        mark_id = str(parsed.get("mark_id") or "").strip()
        image_item_id = str(parsed.get("image_item_id") or "").strip()
        x = parsed.get("x")
        y = parsed.get("y")
        if not mark_id or not image_item_id or x is None or y is None:
            continue
        keys.add((mark_id, image_item_id, _coordinate_key(float(x)), _coordinate_key(float(y))))
    return keys


def _canvas_media_type(item: dict[str, Any]) -> str | None:
    item_type = str(item.get("type") or "").strip()
    if item_type in {"image", "image_generator"}:
        return "image"
    if item_type in {"video", "video_generator"}:
        return "video"
    return None
