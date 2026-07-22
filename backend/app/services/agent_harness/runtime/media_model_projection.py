from __future__ import annotations

from typing import Any


MEDIA_GENERATION_SUCCESS_MESSAGE = "媒体生成已成功。后续如需使用该媒体，请直接使用 artifact_ref。不要为了获取同一个结果重复调用生成工具。"
MEDIA_GENERATION_FAILURE_MESSAGE = "Media generation failed."
MEDIA_GENERATION_TOOLS = {"generate_image", "generate_video"}
FAILED_MEDIA_STATUSES = {"failed", "error", "cancelled", "canceled"}


def normalize_media_tool_name(tool_name: str | None) -> str:
    name = str(tool_name or "").strip().replace("lc_", "")
    if "." in name:
        name = name.rsplit(".", 1)[-1]
    return name.lower()


def is_media_generation_tool(tool_name: str | None) -> bool:
    return normalize_media_tool_name(tool_name) in MEDIA_GENERATION_TOOLS


def is_failed_media_status(status: str | None) -> bool:
    return str(status or "").strip().lower() in FAILED_MEDIA_STATUSES


def build_media_model_projection_payload(
    *,
    artifact_ref: str | None,
    status: str | None,
    error: str | None = None,
    message: str | None = None,
) -> dict[str, Any]:
    artifact = str(artifact_ref or "").strip() or None
    error_text = str(error or "").strip()
    message_text = str(message or "").strip()
    if is_failed_media_status(status):
        payload = {
            "result": "error",
            "artifact_ref": artifact,
            "message": message_text or error_text or MEDIA_GENERATION_FAILURE_MESSAGE,
        }
        if error_text:
            payload["error"] = error_text
    else:
        payload = {
            "result": "success",
            "artifact_ref": artifact,
            "message": message_text or MEDIA_GENERATION_SUCCESS_MESSAGE,
        }
    return {
        key: value
        for key, value in payload.items()
        if value is not None and value != ""
    }
