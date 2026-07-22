from __future__ import annotations

from app.services.agent_harness.workflow.repositories import get_active_run_for_conversation


def has_active_agent_run(conversation_id: str) -> bool:
    return get_active_run_for_conversation(conversation_id) is not None
