from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.generation_reference_diagnostics import summarize_reference_values

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


def message_reference_diagnostics(
    ctx: "HarnessContext",
    *,
    used_reference_image_count: int,
    used_reference_image_urls: list[str] | None = None,
) -> dict[str, object] | None:
    messages = []
    try:
        from app.services.agent_harness.workspace.conversation.conversation_service import load_recent_messages

        messages = load_recent_messages(ctx.user_id, ctx.conversation_id, limit=6)
    except Exception:
        messages = []

    references: list[dict] = []
    for message in reversed(messages or []):
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        metadata = message.get("metadata")
        if not isinstance(metadata, dict):
            continue
        raw_refs = metadata.get("references")
        if isinstance(raw_refs, list):
            references = [item for item in raw_refs if isinstance(item, dict)]
            break

    image_reference_ids = [
        str(item.get("id") or "").strip()
        for item in references
        if str(item.get("media_type") or "").strip() == "image" and str(item.get("id") or "").strip()
    ]
    if not image_reference_ids and not used_reference_image_urls:
        return None

    diagnostic: dict[str, object] = {
        "available_reference_count": len(image_reference_ids),
        "available_reference_ids": image_reference_ids,
        "used_reference_image_count": used_reference_image_count,
    }
    if used_reference_image_urls is not None:
        diagnostic["tool_reference_images"] = summarize_reference_values(used_reference_image_urls)
    if used_reference_image_count == 0:
        diagnostic["warning"] = "message_has_image_references_but_tool_has_no_image_inputs"
    return diagnostic
