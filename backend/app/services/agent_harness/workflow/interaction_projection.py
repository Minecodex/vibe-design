from __future__ import annotations

import json
from typing import Any

from .contracts import MessageSpec


def interaction_payload(interaction: dict[str, Any]) -> dict[str, Any]:
    request_id = str(interaction.get("request_id") or interaction.get("requestId") or "").strip()
    tool_call_id = interaction.get("tool_call_id") or interaction.get("toolCallId") or request_id
    return {
        **interaction,
        "request_id": request_id,
        "requestId": request_id,
        "tool_call_id": tool_call_id,
        "toolCallId": tool_call_id,
        "answers": interaction.get("answers"),
        "status": interaction.get("status") or "pending",
    }


def interaction_render_key(interaction: dict[str, Any]) -> str:
    render_key = str(interaction.get("render_key") or "").strip()
    if render_key:
        return render_key
    request_id = str(interaction.get("request_id") or interaction.get("requestId") or "").strip()
    return f"interaction:{request_id}"


def interaction_submission_message_spec(
    *,
    run_id: str,
    step_id: str,
    pending_interaction: dict[str, Any] | None,
    payload: dict[str, Any],
    answers: dict[str, Any],
) -> MessageSpec | None:
    pending = pending_interaction if isinstance(pending_interaction, dict) else {}
    kind = str(pending.get("kind") or payload.get("kind") or "").strip()
    request_id = str(
        payload.get("request_id")
        or payload.get("requestId")
        or pending.get("request_id")
        or pending.get("requestId")
        or ""
    ).strip()
    if not kind and not request_id:
        return None
    body = {
        "type": "interaction_submission",
        "kind": kind or None,
        "request_id": request_id or None,
        "question": str(pending.get("question") or "").strip() or None,
        "schema": _schema_summary(pending.get("schema")),
        "answers": answers if isinstance(answers, dict) else {},
        "answer": str(payload.get("answer") or ""),
        "display_label": payload.get("display_label"),
        "approved": payload.get("approved") if payload.get("approved") is not None else None,
    }
    if kind == "ecommerce_generation_options":
        if isinstance(payload, dict) and payload.get("action") is not None and "action" not in answers:
            body["action"] = payload.get("action")
        for key in (
            "action",
            "category_id",
            "category_name",
            "category_prompt",
            "style_id",
            "style_name",
            "style_prompt",
            "enable_background_reference",
            "background_reference_image_urls",
            "enable_model_reference",
            "model_reference_image_urls",
            "enable_other_main_image_reference",
            "other_main_image_reference_image_urls",
            "generation_count",
        ):
            value = answers.get(key) if isinstance(answers, dict) else None
            if value is not None and value not in ("", []):
                body[key] = value
    body = {key: value for key, value in body.items() if value not in (None, "", [])}
    stable_part = request_id or str(step_id or "").strip() or "unknown"
    return MessageSpec(
        role="user",
        content=json.dumps(body, ensure_ascii=False, sort_keys=True),
        idempotency_key=f"run:{run_id}:interaction-submission:{stable_part}",
        metadata={key: value for key, value in {
            "message_kind": "agent_context",
            "agent_context_kind": "interaction_submission",
            "interaction_kind": kind or None,
            "request_id": request_id or None,
            "model_visible": True,
            "ui_visible": False,
        }.items() if value is not None},
    )


def _schema_summary(schema_value: Any) -> dict[str, Any] | None:
    if not isinstance(schema_value, dict):
        return None
    summary: dict[str, Any] = {}
    title = str(schema_value.get("title") or "").strip()
    if title:
        summary["title"] = title
    fields = _schema_items(schema_value.get("fields"))
    if fields:
        summary["fields"] = fields
    questions = _schema_items(schema_value.get("questions"))
    if questions:
        summary["questions"] = questions
    return summary or None


def _schema_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        item_summary = {
            "id": _non_empty(item.get("id")),
            "type": _non_empty(item.get("type")),
            "label": _non_empty(item.get("label")),
            "header": _non_empty(item.get("header")),
            "question": _non_empty(item.get("question")),
            "required": item.get("required") if item.get("required") is not None else None,
            "options": _option_summaries(item.get("options")),
        }
        compact = {key: value for key, value in item_summary.items() if value not in (None, "", [])}
        if compact:
            items.append(compact)
    return items


def _option_summaries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    options: list[dict[str, Any]] = []
    for option in value:
        if isinstance(option, dict):
            option_summary = {
                "value": _non_empty(option.get("value")),
                "label": _non_empty(option.get("label")),
                "description": _non_empty(option.get("description")),
            }
            compact = {key: value for key, value in option_summary.items() if value not in (None, "", [])}
            if compact:
                options.append(compact)
        else:
            text = _non_empty(option)
            if text:
                options.append({"value": text})
    return options


def _non_empty(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None
