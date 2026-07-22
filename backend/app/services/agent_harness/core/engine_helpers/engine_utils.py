from __future__ import annotations

from typing import Any

from app.core.default_models import (
    get_default_multimodal_model,
    get_default_thinking_multimodal_model,
)


def resolve_harness_multimodal_model(
    conversation: dict[str, Any],
    *,
    model: str | None = None,
) -> str | None:
    if model:
        return model

    prefs = conversation.get("model_preferences") or {}
    selected_model = prefs.get("multimodal_model")
    if selected_model:
        return selected_model

    mode = str(conversation.get("mode") or "fast")
    if mode == "plan":
        return get_default_thinking_multimodal_model()
    return get_default_multimodal_model()
