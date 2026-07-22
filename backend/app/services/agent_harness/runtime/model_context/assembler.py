from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.agent_harness.authoring.prompt.hidden_user_context import render_hidden_user_context
from app.services.agent_harness.runtime.media_model_projection import (
    build_media_model_projection_payload,
    is_failed_media_status,
    is_media_generation_tool,
)
from app.services.agent_harness.runtime.message_visibility import is_model_session_message, message_metadata
from app.services.agent_harness.runtime.model_context.boundary_store import load_latest_boundary_v2
from app.services.agent_harness.runtime.model_context.models import ModelContextBundle
from app.services.agent_harness.runtime.conversation_events import latest_conversation_event_sequence
from app.services.agent_harness.workspace.conversation.conversation_service import load_messages, load_messages_after_seq


def build_model_context(
    user_id: int,
    conversation_id: str,
    *,
    extra_messages: list[dict[str, Any]] | None = None,
    transcript_messages: list[dict[str, Any]] | None = None,
) -> ModelContextBundle:
    boundary = load_latest_boundary_v2(user_id, conversation_id)
    all_messages = [
        message
        for message in (transcript_messages if transcript_messages is not None else load_messages(user_id, conversation_id))
        if isinstance(message, dict)
    ]
    if boundary is not None:
        row_id_end = int(boundary.covered.get("message_row_id_end") or 0)
        persisted_source = [
            message
            for message in all_messages
            if int(message.get("_seq") or 0) > row_id_end
        ]
        source = "boundary_v2"
        prefix = [boundary.summary_message, *boundary.restore_messages]
    else:
        persisted_source = all_messages
        source = "full_history"
        prefix = []
    provider_persisted = _provider_messages(persisted_source)
    transient = _provider_messages([message for message in (extra_messages or []) if isinstance(message, dict)])
    compact_messages = _sanitize_message_sequence([*prefix, *provider_persisted])
    messages = [*compact_messages, *_sanitize_message_sequence(transient)]
    return ModelContextBundle(
        messages=messages,
        compact_messages=compact_messages,
        persisted_messages=persisted_source,
        boundary=boundary,
        message_row_id_end=max((int(message.get("_seq") or 0) for message in all_messages), default=0),
        event_sequence_end=_latest_event_sequence(user_id, conversation_id),
        source=source,
    )


def build_model_context_from_checkpoint(
    user_id: int,
    conversation_id: str,
    *,
    previous_checkpoint: dict[str, Any] | None,
    extra_messages: list[dict[str, Any]] | None = None,
) -> ModelContextBundle:
    checkpoint = previous_checkpoint if isinstance(previous_checkpoint, dict) else {}
    checkpoint_seq = int(checkpoint.get("message_seq_end") or 0)
    boundary = load_latest_boundary_v2(user_id, conversation_id)
    if boundary is not None and int(boundary.covered.get("message_row_id_end") or 0) >= checkpoint_seq:
        boundary_seq = int(boundary.covered.get("message_row_id_end") or 0)
        return _build_model_context_from_prefix(
            user_id,
            conversation_id,
            after_seq=boundary_seq,
            prefix=[boundary.summary_message, *boundary.restore_messages],
            source="boundary_v2",
            extra_messages=extra_messages,
            boundary=boundary,
        )
    prefix = _checkpoint_prefix_messages(checkpoint)
    if checkpoint_seq <= 0 or not prefix:
        return build_model_context(user_id, conversation_id, extra_messages=extra_messages)
    return _build_model_context_from_prefix(
        user_id,
        conversation_id,
        after_seq=checkpoint_seq,
        prefix=prefix,
        source="render_checkpoint",
        extra_messages=extra_messages,
        boundary=boundary,
    )


def _checkpoint_prefix_messages(checkpoint: dict[str, Any]) -> list[dict[str, Any]]:
    summary = checkpoint.get("summary_message")
    if not isinstance(summary, dict) or not str(summary.get("content") or "").strip():
        return []
    restore_messages = checkpoint.get("restore_messages")
    return [
        deepcopy(summary),
        *[
            deepcopy(message)
            for message in (restore_messages if isinstance(restore_messages, list) else [])
            if isinstance(message, dict)
        ],
    ]


def _build_model_context_from_prefix(
    user_id: int,
    conversation_id: str,
    *,
    after_seq: int,
    prefix: list[dict[str, Any]],
    source: str,
    extra_messages: list[dict[str, Any]] | None,
    boundary,
) -> ModelContextBundle:
    persisted_source = load_messages_after_seq(user_id, conversation_id, after_seq=int(after_seq or 0))
    provider_persisted = _provider_messages(persisted_source)
    transient = _provider_messages([message for message in (extra_messages or []) if isinstance(message, dict)])
    compact_messages = _sanitize_message_sequence([*prefix, *provider_persisted])
    messages = [*compact_messages, *_sanitize_message_sequence(transient)]
    return ModelContextBundle(
        messages=messages,
        compact_messages=compact_messages,
        persisted_messages=persisted_source,
        boundary=boundary,
        message_row_id_end=max((int(message.get("_seq") or 0) for message in persisted_source), default=int(after_seq or 0)),
        event_sequence_end=_latest_event_sequence(user_id, conversation_id),
        source=source,
    )


def _hidden_media_tool_projection_message(message: dict[str, Any]) -> dict[str, Any] | None:
    tool_name = str(message.get("tool_name") or "")
    if not is_media_generation_tool(tool_name):
        return None
    raw_payload = _parse_json_object(message.get("content"))
    nested_output = _parse_json_object(raw_payload.get("output"))
    status = str(raw_payload.get("status") or "")
    error = str(
        raw_payload.get("error")
        or raw_payload.get("error_message")
        or nested_output.get("error")
        or nested_output.get("error_message")
        or ""
    ).strip() or None
    payload = build_media_model_projection_payload(
        artifact_ref=str(raw_payload.get("artifact_ref") or nested_output.get("artifact_ref") or "").strip() or None,
        status=status,
        error=error,
        message=error if is_failed_media_status(status) else None,
    )
    return {
        "role": "tool",
        "tool_call_id": str(message.get("tool_call_id") or ""),
        "content": json.dumps(payload, ensure_ascii=False),
    }


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _provider_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rendered: list[dict[str, Any]] = []
    for message in messages:
        rendered_message = _normalize_message(message)
        if rendered_message is not None:
            rendered.append(rendered_message)
    return rendered


def _normalize_message(message: dict[str, Any]) -> dict[str, Any] | None:
    metadata = message_metadata(message)
    if metadata.get("render_only"):
        return None
    if _is_render_projection_message(message, metadata):
        return None
    role = str(message.get("role") or "").strip()
    # Media-generation tools are persisted with model_visible=False (so the
    # raw payload — task_id / result_url / status=processing — never leaks
    # into the LLM prompt) but the model still needs *some* trace of the
    # call, otherwise it forgets it called generate_image and re-fires the
    # same prompt forever. Substitute with the canonical success projection
    # (see media_model_projection.MEDIA_GENERATION_SUCCESS_MESSAGE) — the
    # "code-side blocks downstream tools when the asset isn't actually
    # ready" contract still holds because reference_image_urls / analyze_image
    # resolve the artifact_ref and wait for completion.
    if role == "tool" and _is_duplicate_media_generation_reuse_message(message):
        return _hidden_media_tool_projection_message(message)
    if role == "tool" and not is_model_session_message(message):
        return _hidden_media_tool_projection_message(message)
    if role == "assistant" and _is_presentation_model_tool_call_message(message, metadata):
        return _assistant_provider_message(message, metadata)
    if not is_model_session_message(message):
        return None
    if role == "tool":
        return _with_debug_metadata({
            "role": "tool",
            "tool_call_id": str(message.get("tool_call_id") or ""),
            "content": str(message.get("content") or ""),
        }, metadata)
    if role == "assistant":
        return _assistant_provider_message(message, metadata)
    if role == "user":
        content = str(message.get("content") or "")
        hidden_context = render_hidden_user_context(metadata)
        if hidden_context:
            content = f"{content}\n\n{hidden_context}" if content else hidden_context
        reference_context = _structured_reference_context(metadata.get("references"))
        if reference_context:
            content = f"{content}\n\n{reference_context}" if content else reference_context
        media_rules_context = _media_reference_rules_context(
            metadata.get("references"),
            message.get("attachments"),
        )
        if media_rules_context:
            content = f"{content}\n\n{media_rules_context}" if content else media_rules_context
        attachment_context = _attachment_context(message.get("attachments"))
        if attachment_context:
            content = f"{content}\n\n{attachment_context}" if content else attachment_context
        return _with_debug_metadata({"role": "user", "content": content}, metadata)
    if role == "system":
        return _with_debug_metadata({"role": "system", "content": str(message.get("content") or "")}, metadata)
    return None


def _is_duplicate_media_generation_reuse_message(message: dict[str, Any]) -> bool:
    if str(message.get("role") or "").strip() != "tool":
        return False
    if not is_media_generation_tool(str(message.get("tool_name") or "")):
        return False
    raw_payload = _parse_json_object(message.get("content"))
    if raw_payload.get("duplicate_generation_blocked") is True:
        return True
    output_payload = _parse_json_object(raw_payload.get("output"))
    return output_payload.get("duplicate_generation_blocked") is True


def _is_presentation_model_tool_call_message(message: dict[str, Any], metadata: dict[str, Any]) -> bool:
    if str(metadata.get("render_kind") or "").strip() != "presentation_v2":
        return False
    tool_calls = message.get("tool_calls")
    return isinstance(tool_calls, list) and bool(tool_calls)


def _assistant_provider_message(message: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    content = str(message.get("content") or "")
    model_session_content = str(metadata.get("model_session_content") or "").strip()
    if model_session_content:
        content = model_session_content
    entry: dict[str, Any] = {"role": "assistant", "content": content}
    if isinstance(message.get("tool_calls"), list):
        entry["tool_calls"] = deepcopy(message["tool_calls"])
    return _with_debug_metadata(entry, metadata)


def _with_debug_metadata(entry: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    debug_metadata = {
        key: metadata.get(key)
        for key in (
            "message_kind",
            "agent_context_kind",
            "cache_policy",
            "context_hash",
            "idempotency_key",
            "ledger_turn_key",
        )
        if metadata.get(key) is not None
    }
    if debug_metadata:
        return {**entry, "metadata": deepcopy(debug_metadata)}
    return entry


def _is_render_projection_message(message: dict[str, Any], metadata: dict[str, Any]) -> bool:
    render_key = str(metadata.get("render_key") or "").strip()
    if not render_key.startswith("block:"):
        return False
    if str(message.get("role") or "").strip() != "assistant":
        return False
    blocks = message.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        return False
    for block in blocks:
        if not isinstance(block, dict):
            return False
        ui_kind = str(block.get("ui_kind") or block.get("uiKind") or "").strip()
        if ui_kind in {"assistant_text", "assistant_final_answer"}:
            return False
    return True


def _sanitize_message_sequence(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [message for group in _message_groups(messages) for message in group]


def _message_groups(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    i = 0
    while i < len(messages):
        message = messages[i]
        if message.get("role") == "assistant" and message.get("tool_calls"):
            tool_call_ids = {
                str(call.get("id") or "")
                for call in message.get("tool_calls") or []
                if isinstance(call, dict)
            }
            group = [message]
            i += 1
            while (
                i < len(messages)
                and messages[i].get("role") == "tool"
                and str(messages[i].get("tool_call_id") or "") in tool_call_ids
            ):
                group.append(messages[i])
                i += 1
            result_ids = {
                str(entry.get("tool_call_id") or "")
                for entry in group[1:]
                if entry.get("role") == "tool"
            }
            if result_ids != tool_call_ids:
                groups.append([{"role": "assistant", "content": str(message.get("content") or "")}])
                continue
            groups.append(group)
            continue
        if message.get("role") == "tool":
            i += 1
            continue
        groups.append([message])
        i += 1
    return groups


def _structured_reference_context(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    references: list[dict[str, Any]] = []
    allowed_keys = {
        "id",
        "kind",
        "media_type",
        "display_name",
        "tool_reference",
        "source",
        "mark",
    }
    for item in value:
        if not isinstance(item, dict):
            continue
        reference = {key: item[key] for key in allowed_keys if key in item}
        if not str(reference.get("tool_reference") or "").strip():
            continue
        references.append(reference)
    if not references:
        return ""
    payload = {
        "references": references,
        "usage": {
            "tool_reference": "Copy the exact tool_reference value into image/video tool fields when using that media.",
        },
    }
    return "Structured media references (JSON):\n" + json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _media_reference_rules_context(references_value: Any, attachments_value: Any) -> str:
    references = (
        [item for item in references_value if isinstance(item, dict)]
        if isinstance(references_value, list)
        else []
    )
    image_attachments = (
        [
            item
            for item in attachments_value
            if isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "image"
        ]
        if isinstance(attachments_value, list)
        else []
    )
    if not references and not image_attachments:
        return ""

    has_canvas_reference = any(
        str(item.get("kind") or "").strip() in {"canvas_item", "canvas_mark"}
        or str((item.get("source") if isinstance(item.get("source"), dict) else {}).get("type") or "").strip()
        in {"canvas_item", "canvas_mark"}
        for item in references
    )
    has_canvas_mark = any(str(item.get("kind") or "").strip() == "canvas_mark" for item in references)
    has_structured_references = bool(references)

    lines = [
        "Canvas media reference rules:" if has_canvas_reference else "Media reference rules:",
        (
            "- When the user asks to generate from, edit, replace, remove, repair, restyle, "
            "or make a variant of a referenced image, copy the relevant tool_reference exactly "
            "into generate_image.reference_image_urls."
        ),
        "- If a referenced source provides artifact_ref, prefer artifact_ref; otherwise use the provided URL or path.",
        "- Do not ignore referenced images or regenerate only from a text description.",
        (
            "- Do not add visual attributes that the user did not request when writing image/video prompts "
            "from referenced media. Keep the user's wording and intent; do not invent colors, materials, "
            "styles, lighting, composition, or object details from assumptions about the reference."
        ),
        (
            "- If the user has clearly requested replacement, removal, modification, repair, "
            "or generation, call the appropriate image tool instead of only explaining."
        ),
    ]
    if has_structured_references:
        lines.insert(
            1,
            (
                "- Use Structured media references (JSON) as the source of truth for media inputs; "
                "do not invent reference ids or tool fields."
            ),
        )
    if has_canvas_reference:
        lines.extend(
            [
                "- @[name](canvas:itemId) means the user referenced a canvas media item.",
                "- For canvas media references, use the relevant tool_reference in image or video tool inputs.",
            ]
        )
    if has_canvas_mark:
        lines.extend(
            [
                "- kind=canvas_mark means the user selected a local element inside the source image, not a new standalone subject.",
                (
                    "- For canvas_mark edits, include the mark label and normalized position in the prompt, "
                    "describe the local edit target, and ask to keep the rest of the image unchanged / "
                    "保持其余画面不变."
                ),
            ]
        )
    if image_attachments:
        lines.append(
            (
                "- User-uploaded image attachments can be used as reference images; for image edits "
                "or image-to-image generation, pass their path or URL to generate_image.reference_image_urls, "
                "and for analysis pass it to analyze_image.image_url."
            )
        )
    return "\n".join(lines)


def _attachment_context(value: Any) -> str:
    if not isinstance(value, list):
        return ""
    lines: list[str] = []
    for index, attachment in enumerate(value, start=1):
        if not isinstance(attachment, dict):
            continue
        path = str(attachment.get("url") or attachment.get("path") or "").strip()
        name = str(attachment.get("name") or "").strip()
        attachment_type = str(attachment.get("type") or "file").strip() or "file"
        if not path:
            continue
        label = name or Path(path.replace("\\", "/")).name or f"attachment-{index}"
        normalized_path = path.replace("\\", "/")
        parts = [f"- {label}: type={attachment_type}", f"path={path}"]
        references_index = normalized_path.find("references/")
        if references_index >= 0:
            asset_suffix = normalized_path[references_index + len("references/") :].lstrip("/")
            parts.append(f"asset_path=$HARNESS_REFERENCES_DIR/{asset_suffix}")
        lines.append(", ".join(parts))
    if not lines:
        return ""
    return "Attached files:\n" + "\n".join(lines)


def _latest_event_sequence(user_id: int, conversation_id: str) -> int:
    return latest_conversation_event_sequence(user_id, conversation_id)
