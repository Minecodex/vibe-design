from __future__ import annotations

from typing import Any


def render_hidden_user_context(metadata: dict[str, Any]) -> str:
    typed = metadata.get("hidden_user_context") if isinstance(metadata.get("hidden_user_context"), dict) else None
    if not typed:
        return ""

    lines = ["Hidden user context:"]
    lines.extend(_selected_file_lines(typed.get("selected_files")))
    lines.extend(_artifact_edit_lines(typed.get("artifact_edits")))
    lines.extend(_canvas_reference_lines(typed.get("canvas_references")))
    custom_lanes = typed.get("custom_lanes")
    if isinstance(custom_lanes, list):
        for item in custom_lanes:
            if not isinstance(item, dict):
                continue
            lane_type = _clean_label(item.get("type")) or "custom"
            text = str(item.get("text") or item.get("value") or "").strip()
            if text:
                lines.append(f"- {lane_type}: {text}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def hidden_user_context_text(metadata: dict[str, Any]) -> str:
    return render_hidden_user_context(metadata)


def _selected_file_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        reason = str(item.get("reason") or "").strip()
        lines.append(f"- selected_file: {path}" + (f" ({reason})" if reason else ""))
    return lines


def _artifact_edit_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "").strip()
        instruction = str(item.get("instruction") or "").strip()
        if path:
            lines.append(f"- artifact_edit: {path}" + (f" - {instruction}" if instruction else ""))
    return lines


def _canvas_reference_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    lines: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("ref") or item.get("id") or "").strip()
        label = str(item.get("label") or "").strip()
        if ref:
            lines.append(f"- canvas_reference: {ref}" + (f" ({label})" if label else ""))
    return lines


def _clean_label(value: Any) -> str:
    return "".join(ch for ch in str(value or "").strip().lower().replace("-", "_") if ch.isalnum() or ch == "_")
