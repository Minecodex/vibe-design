from __future__ import annotations

from app.services.agent_harness.runtime.presentation_v2.builder import PresentationEventDraft

from .contracts import EventSpec


def event_spec_from_presentation_draft(draft: PresentationEventDraft) -> EventSpec:
    return EventSpec(
        event_type=draft.event_type,
        payload=draft.payload,
        lane=draft.lane,
        idempotency_key=draft.idempotency_key,
        block_id=draft.block_id,
        tool_call_id=draft.tool_call_id,
        artifact_id=draft.artifact_id,
        parent_block_id=draft.parent_block_id,
    )
