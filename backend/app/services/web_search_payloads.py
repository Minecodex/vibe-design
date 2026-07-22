from __future__ import annotations

from typing import Any


_VISIBLE_RESULT_KEYS = {
    "title",
    "url",
    "snippet",
    "message",
    "width",
    "height",
    "source_url",
}


def sanitize_web_search_result_for_model(item: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}

    for key in _VISIBLE_RESULT_KEYS:
        value = item.get(key)
        if value not in (None, ""):
            sanitized[key] = value

    local_path = str(
        item.get("local_image_path")
        or item.get("localImagePath")
        or ""
    ).strip()
    if local_path:
        sanitized["local_image_path"] = local_path
        sanitized["image_url"] = local_path

    return sanitized


def sanitize_web_search_results_for_model(results: list[dict[str, Any]] | Any) -> list[dict[str, Any]]:
    if not isinstance(results, list):
        return []
    sanitized_results: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        sanitized_results.append(sanitize_web_search_result_for_model(item))
    return sanitized_results


def build_web_search_payloads(
    *,
    provider: str,
    search_type: str,
    query: str,
    results: list[dict[str, Any]],
    message: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    model_payload = {
        "provider": provider,
        "search_type": search_type,
        "query": query,
        "results": sanitize_web_search_results_for_model(results),
        "message": message,
    }
    ui_payload = {
        **model_payload,
        "ui_results": results,
    }
    return model_payload, ui_payload


def sanitize_tool_result_for_model(tool_name: str, result: Any) -> Any:
    if not isinstance(result, dict):
        return result

    normalized_name = tool_name.replace("lc_", "")
    if normalized_name in {"generate_image", "generate_video"}:
        media_type = "video" if normalized_name == "generate_video" else "image"
        canvas_item = result.get("canvas_item")
        canvas_item_id = result.get("canvas_item_id")
        if not canvas_item_id and isinstance(canvas_item, dict):
            canvas_item_id = canvas_item.get("id")
        status = result.get("status")
        sanitized = {
            "type": "async_generation_started",
            "media_type": media_type,
            "task_id": result.get("task_id") or result.get("id"),
            "canvas_item_id": canvas_item_id,
            "status": status,
            "result_url": result.get("result_url"),
            "ui_already_shows_progress": True,
            "instruction": (
                "The UI already shows this generation task. The task is running asynchronously. "
                "Do not call the same generation tool again just to wait or create a duplicate. "
                "Use artifact_ref only in downstream dependency arguments when another tool needs this media, "
                "and continue with the next substantive action."
            ),
        }
        if result.get("artifact_ref") is not None:
            sanitized["artifact_ref"] = result.get("artifact_ref")
        if result.get("auto_retry_count") is not None:
            sanitized["auto_retry_count"] = result.get("auto_retry_count")
        if result.get("auto_retry_max") is not None:
            sanitized["auto_retry_max"] = result.get("auto_retry_max")
        if result.get("manual_retry_count") is not None:
            sanitized["manual_retry_count"] = result.get("manual_retry_count")
        if status in {"processing", "running", "pending"}:
            sanitized["async_execution"] = True
            sanitized["do_not_repeat_same_generation"] = True
        if result.get("duplicate_generation_blocked"):
            sanitized["duplicate_generation_blocked"] = True
        if result.get("next_action_hint"):
            sanitized["next_action_hint"] = result.get("next_action_hint")
        return sanitized

    if normalized_name not in {"search_web", "web_search"}:
        return result

    source_results = result.get("ui_results")
    if not isinstance(source_results, list):
        source_results = result.get("results")

    sanitized = dict(result)
    sanitized.pop("ui_results", None)
    sanitized["results"] = sanitize_web_search_results_for_model(source_results)
    return sanitized
