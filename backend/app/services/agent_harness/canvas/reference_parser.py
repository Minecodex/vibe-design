from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


MENTION_PATTERN = re.compile(r"@\[([^\]]+)\]\((canvas:[^)]+)\)")
MARK_PATTERN = re.compile(r"#\[([^\]]*)\]\((canvas-mark:[^)]*)\)")
MARK_TARGET_PATTERN = re.compile(r"^canvas-mark:([^:]+):image:([^:]+):x:([0-9.]+):y:([0-9.]+)$")


@dataclass(slots=True)
class ParsedCanvasReferences:
    cleaned_content: str
    resources: list[dict[str, Any]]
    prompt_context: str


def parse_canvas_references(
    content: str,
    canvas_items: list[dict[str, Any]],
    *,
    language: str = "zh",
) -> ParsedCanvasReferences:
    content = content or ""
    resources = _resolve_resources_in_order(content, canvas_items)
    cleaned_content = MARK_PATTERN.sub("", MENTION_PATTERN.sub("", content)).strip()
    return ParsedCanvasReferences(
        cleaned_content=cleaned_content,
        resources=resources,
        prompt_context=_build_reference_context(resources, language=language),
    )


def _resolve_resources_in_order(
    content: str,
    canvas_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    item_map = _build_canvas_item_map(canvas_items)
    resources: list[dict[str, Any]] = []
    matches: list[tuple[int, dict[str, Any]]] = []
    for match in MENTION_PATTERN.finditer(content):
        name, target = match.groups()
        item_id = _parse_canvas_mention_target(target)
        item = item_map.get(item_id or "")
        if not item:
            continue
        item_type = str(item.get("type") or "unknown")
        matches.append(
            (
                match.start(),
                {
                    "id": item_id.strip(),
                    "type": _normalize_resource_type(item_type),
                    "url": _canvas_item_tool_reference(item),
                    "name": name.strip(),
                    "prompt": item.get("prompt", ""),
                },
            )
        )
    for match in MARK_PATTERN.finditer(content):
        label, target = match.groups()
        parsed_mark = _parse_canvas_mark_target(target)
        if not parsed_mark:
            continue
        image_id = parsed_mark["image_item_id"]
        item = item_map.get(image_id)
        if not item:
            continue
        mark_number = _mark_number_from_id(parsed_mark["mark_id"])
        matches.append(
            (
                match.start(),
                {
                    "id": image_id,
                    "type": "mark",
                    "url": _canvas_item_tool_reference(item),
                    "name": f"标记{mark_number}: {label.strip()}",
                    "prompt": item.get("prompt", ""),
                    "mark_label": label.strip(),
                    "mark_id": parsed_mark["mark_id"],
                    "mark_position": {"x": parsed_mark["x"], "y": parsed_mark["y"]},
                },
            )
        )
    return [resource for _, resource in sorted(matches, key=lambda item: item[0])]


def _parse_canvas_mention_target(target: str) -> str | None:
    raw = str(target or "").strip()
    if not raw.startswith("canvas:"):
        return None
    item_id = raw.removeprefix("canvas:").strip()
    return item_id or None


def _parse_canvas_mark_target(target: str) -> dict[str, Any] | None:
    match = MARK_TARGET_PATTERN.fullmatch(str(target or "").strip())
    if not match:
        return None
    try:
        x = float(match.group(3))
        y = float(match.group(4))
    except (TypeError, ValueError):
        return None
    if x < 0 or x > 1 or y < 0 or y > 1:
        return None
    return {
        "mark_id": match.group(1).strip(),
        "image_item_id": _parse_canvas_mention_target(f"canvas:{match.group(2).strip()}") or "",
        "x": x,
        "y": y,
    }


def _canvas_item_tool_reference(item: dict[str, Any]) -> str:
    artifact_ref = str(item.get("artifact_ref") or "").strip()
    if artifact_ref.startswith("artifact_ref:"):
        return artifact_ref
    return str(item.get("url") or item.get("result_url") or "")


def _mark_number_from_id(mark_id: str) -> int:
    match = re.search(r"(\d+)$", str(mark_id or ""))
    return int(match.group(1)) if match else 0


def _build_canvas_item_map(canvas_items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id")): item
        for item in canvas_items
        if isinstance(item, dict) and item.get("id") is not None
    }


def _normalize_resource_type(item_type: str) -> str:
    if item_type == "image_generator":
        return "image"
    if item_type == "video_generator":
        return "video"
    return item_type


def _build_reference_context(resources: list[dict[str, Any]], *, language: str) -> str:
    if not resources:
        return ""
    if str(language or "").strip().lower().startswith("en"):
        return _build_reference_context_en(resources)
    return _build_reference_context_zh(resources)

def _build_reference_context_zh(resources: list[dict[str, Any]]) -> str:
    lines = ["## 当前引用的画布资源"]
    for index, resource in enumerate(resources, start=1):
        resource_type = resource.get("type", "unknown")
        name = resource.get("name", "未命名")
        lines.append(f"### 资源 {index}: {name} ({resource_type})")
        if resource.get("id"):
            lines.append(f"- ID: `{resource['id']}`")
        if resource.get("url"):
            lines.append(f"- URL: `{resource['url']}`")
        if resource.get("prompt"):
            lines.append(f"- 原始 prompt: {resource['prompt']}")
        if resource_type == "mark":
            lines.append(f"- 标记元素: {resource.get('mark_label', '')}")
            position = resource.get("mark_position", {})
            lines.append(
                f"- 标记位置: ({position.get('x', 0):.0%}, {position.get('y', 0):.0%})"
            )
        lines.append("")
    return "\n".join(lines).strip()


def _build_reference_context_en(resources: list[dict[str, Any]]) -> str:
    lines = ["## Currently Referenced Canvas Resources"]
    for index, resource in enumerate(resources, start=1):
        resource_type = resource.get("type", "unknown")
        name = resource.get("name", "unnamed")
        lines.append(f"### Resource {index}: {name} ({resource_type})")
        if resource.get("id"):
            lines.append(f"- ID: `{resource['id']}`")
        if resource.get("url"):
            lines.append(f"- URL: `{resource['url']}`")
        if resource.get("prompt"):
            lines.append(f"- Original prompt: {resource['prompt']}")
        if resource_type == "mark":
            lines.append(f"- Marked element: {resource.get('mark_label', '')}")
            position = resource.get("mark_position", {})
            lines.append(
                f"- Mark position: ({position.get('x', 0):.0%}, {position.get('y', 0):.0%})"
            )
        lines.append("")
    return "\n".join(lines).strip()
