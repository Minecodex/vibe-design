from __future__ import annotations

from typing import Any

from app.services.agent_harness.runtime.eventing.live_event_publisher import (
    publish_user_event,
    publish_user_event_async,
)
from app.services.agent_harness.runtime.presentation_v2.builder import PresentationEventDraft


def publish_presentation_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    draft: PresentationEventDraft,
) -> dict[str, Any] | None:
    return publish_user_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=draft.event_type,
        data=draft.payload,
        lane=draft.lane,
        block_id=draft.block_id,
        tool_call_id=draft.tool_call_id,
        artifact_id=draft.artifact_id,
        parent_block_id=draft.parent_block_id,
        idempotency_key=draft.idempotency_key,
    )


async def publish_presentation_event_async(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    draft: PresentationEventDraft,
) -> dict[str, Any] | None:
    return await publish_user_event_async(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=draft.event_type,
        data=draft.payload,
        lane=draft.lane,
        block_id=draft.block_id,
        tool_call_id=draft.tool_call_id,
        artifact_id=draft.artifact_id,
        parent_block_id=draft.parent_block_id,
        idempotency_key=draft.idempotency_key,
    )
