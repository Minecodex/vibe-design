from __future__ import annotations

from app.services.agent_harness.runtime.eventing.persistence import append_trace

from .models import RenderedPromptBundle


def persist_prompt_bundle_trace(
    *,
    user_id: int | None,
    conversation_id: str | None,
    run_id: str | None,
    bundle: RenderedPromptBundle,
    summary: str | None = None,
) -> None:
    if user_id is None or not conversation_id:
        return
    append_trace(
        user_id,
        conversation_id,
        trace_type="prompt_bundle_assembled",
        summary=summary or f"Prompt bundle assembled ({bundle.mode.value})",
        payload=bundle.trace,
        run_id=run_id,
    )
