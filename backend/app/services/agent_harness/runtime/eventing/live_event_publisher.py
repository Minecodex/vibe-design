from __future__ import annotations

from typing import Any

from app.services.agent_harness.runtime.eventing.event_log import append_event, append_event_async


def publish_user_event(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    lane: str = "user",
    **kwargs: Any,
) -> dict[str, Any] | None:
    return append_event(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=event_type,
        data=data or {},
        lane=lane,
        **kwargs,
    )


async def publish_user_event_async(
    user_id: int,
    conversation_id: str,
    *,
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    lane: str = "user",
    **kwargs: Any,
) -> dict[str, Any] | None:
    return await append_event_async(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=event_type,
        data=data or {},
        lane=lane,
        **kwargs,
    )
