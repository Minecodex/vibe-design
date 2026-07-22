from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .event_log import append_event, publish_transient_event

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


@dataclass(slots=True)
class HarnessEventSink:
    """Single write path for harness UI events.

    The sink keeps callers away from the details of persistent vs transient
    records, which makes the engine easier to split without changing event
    semantics at every call site.
    """

    user_id: int
    conversation_id: str
    run_id: str
    ctx: "HarnessContext | None" = None

    def emit(
        self,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        lane: str = "user",
        persist: bool = True,
        block_id: str | None = None,
        agent_id: str | None = None,
        tool_call_id: str | None = None,
        artifact_id: str | None = None,
        parent_block_id: str | None = None,
        idempotency_key: str | None = None,
        tool_name: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_payload = _enrich_payload(
            ctx=self.ctx,
            payload=payload if payload is not None else data,
            tool_name=tool_name,
            tool_call_id=tool_call_id,
        )

        kwargs = {
            "run_id": self.run_id,
            "event_type": event_type,
            "data": normalized_payload,
            "lane": lane,
            "block_id": block_id,
            "agent_id": agent_id,
            "tool_call_id": tool_call_id,
            "artifact_id": artifact_id,
            "parent_block_id": parent_block_id,
            "idempotency_key": idempotency_key,
        }
        if persist:
            if str(lane or "user") == "user":
                from .live_event_publisher import publish_user_event

                record = publish_user_event(self.user_id, self.conversation_id, **kwargs)
            else:
                record = append_event(self.user_id, self.conversation_id, **kwargs)
            if record is not None:
                return record

        return publish_transient_event(self.user_id, self.conversation_id, **kwargs)


def sink_from_context(ctx: "HarnessContext") -> HarnessEventSink:
    return HarnessEventSink(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        run_id=ctx.subagent_run_id or ctx.run_id,
        ctx=ctx,
    )


def _enrich_payload(
    *,
    ctx: "HarnessContext | None",
    payload: dict[str, Any] | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    enriched = dict(payload or {})
    if tool_name:
        enriched.setdefault("tool", tool_name)
    if tool_call_id:
        enriched.setdefault("call_id", tool_call_id)
    if ctx is not None:
        for key, value in ctx.run_output_anchor_payload().items():
            enriched.setdefault(key, value)
    return enriched
