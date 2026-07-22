from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .event_sink import sink_from_context

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


def enrich_harness_event_payload(
    *,
    ctx: "HarnessContext | None",
    payload: dict[str, Any] | None = None,
    tool_name: str | None = None,
    tool_call_id: str | None = None,
) -> dict[str, Any]:
    enriched: dict[str, Any] = dict(payload or {})

    if tool_name:
        enriched.setdefault("tool", tool_name)
    if tool_call_id:
        enriched.setdefault("call_id", tool_call_id)
    if ctx is not None:
        for key, value in ctx.run_output_anchor_payload().items():
            enriched.setdefault(key, value)

    return enriched


def append_harness_event(
    *,
    ctx: "HarnessContext",
    event_type: str,
    data: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    run_id: str | None = None,
    block_id: str | None = None,
    tool_call_id: str | None = None,
    artifact_id: str | None = None,
    parent_block_id: str | None = None,
    tool_name: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any] | None:
    normalized_payload = enrich_harness_event_payload(
        ctx=ctx,
        payload=payload if payload is not None else data,
        tool_name=tool_name,
        tool_call_id=tool_call_id,
    )

    resolved_run_id = run_id or ctx.subagent_run_id or ctx.run_id
    return sink_from_context(ctx).emit(
        event_type,
        data=normalized_payload,
        persist=True,
        block_id=block_id,
        tool_call_id=tool_call_id,
        artifact_id=artifact_id,
        parent_block_id=parent_block_id,
        idempotency_key=idempotency_key,
    )
