from __future__ import annotations

import uuid
from typing import Any


def build_canvas_generation_item(
    *,
    conversation_id: str | int | None,
    kind: str,
    task_id: str | int,
    prompt: str,
    model_name: str | None,
    model_label: str | None,
    provider_code: str | None,
    aspect_ratio: str | None,
    resolution: str | None,
    duration: int | None,
    result_url: str | None,
    status: str | None,
    artifact_ref: str | None = None,
    agent_group_key: str | None = None,
    position: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_kind = str(kind or "image").strip().lower()
    position = position or {}
    normalized_artifact_ref = str(artifact_ref or "").strip() or None
    task_id_text = str(task_id)
    agent_media_key = normalized_artifact_ref or task_id_text
    return {
        "id": _stable_canvas_item_id(agent_media_key),
        "type": "video_generator" if normalized_kind == "video" else "image_generator",
        "task_id": task_id_text,
        "artifact_ref": normalized_artifact_ref,
        "agent_conversation_id": conversation_id,
        "agent_media_key": agent_media_key,
        "agent_group_key": str(agent_group_key or "").strip() or None,
        "prompt": prompt,
        "x": position.get("x", 0),
        "y": position.get("y", 0),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration": duration,
        "model_name": model_name,
        "model_label": model_label,
        "provider_code": provider_code,
        "status": _normalize_canvas_status(status),
        "url": result_url or "",
    }


def _stable_canvas_item_id(agent_media_key: str) -> str:
    normalized = str(agent_media_key or "").strip()
    if not normalized:
        return str(uuid.uuid4())
    stable = (
        normalized
        .replace("artifact_ref:", "")
        .replace(":", "-")
        .replace("/", "-")
        .replace("\\", "-")
    )
    stable = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in stable).strip("-")
    return f"agent-generated-{stable or uuid.uuid4().hex}"


def _normalize_canvas_status(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"processing", "running", "pending"}:
        return "generating"
    if normalized == "completed":
        return "completed"
    if normalized == "failed":
        return "failed"
    return "generating"
