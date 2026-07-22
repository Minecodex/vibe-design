from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.core.config import settings
from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult
from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
from app.services.agent_harness.runtime.execution_support.harness_model_provider import create_harness_model_provider
from app.services.user_apimart_key_service import resolve_user_apimart_key_for_context
from app.services.agent_harness.core.utils import generation_store
from app.services.agent_harness.runtime.execution_support.reviewer import review_tool_result
from app.services.agent_harness.runtime.media_model_projection import is_media_generation_tool
from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_async
from app.services.agent_harness.workspace.conversation.conversation_service import load_messages
from app.services.agent_harness.workspace.session_v2.service import normalize_message_id

from .context_session import apply_context_session_to_context
from .contracts import EventSpec
from .gateway import AgentRuntimeGateway
from .records import WorkflowStepRecord
from .runtime_preparation import create_workflow_context
from .tool_gating import blocks_plan_gate_tool, build_tool_card_event, normalize_presentation_scope


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _phase_elapsed(started_ms: float) -> float:
    return max(_now_ms() - started_ms, 0.0)


def _conversation_multimodal_provider(conversation: dict[str, Any] | None) -> str | None:
    prefs = conversation.get("model_preferences") if isinstance(conversation, dict) else None
    if not isinstance(prefs, dict):
        return None
    provider = str(prefs.get("multimodal_provider") or "").strip()
    return provider or None


_MEDIA_SENSITIVE_READ_TOOLS = {
    "analyze_image",
    "glob_files",
    "grep_files",
    "list_files",
    "read_file",
    "workspace_map",
}


def _normalize_tool_name(tool_name: str | None) -> str:
    return str(tool_name or "").strip().replace("lc_", "").lower()


# Tools that should surface a Claude-Code-style inline tool row on the homepage
# (running -> completed/failed) via user-lane presentation events. Deliberately
# limited to file + command + fetch tools: workflow/interaction tools (ask_user,
# Agent, update_planning_draft, ...) already have dedicated cards, and media/search
# tools (analyze_image, generate_image/video, web_search) have their own cards too —
# emitting generic rows for those would double-render. Names are matched after
# `_normalize_tool_name` (lc_ stripped, lowercased), including the `Bash` alias.
_PLAIN_TOOL_PRESENTATION_ALLOWLIST = frozenset(
    {
        "read_file",
        "write_file",
        "edit_file",
        "list_files",
        "glob_files",
        "grep_files",
        "exec_command",
        "bash",
        "fetch_webpage",
    }
)


def _emits_plain_tool_presentation(tool_name: str | None) -> bool:
    return _normalize_tool_name(tool_name) in _PLAIN_TOOL_PRESENTATION_ALLOWLIST


def tool_presentation_message_key(
    *,
    run_id: str,
    turn: int | str | None,
    tool_call_id: str,
) -> str:
    return normalize_message_id(f"run:{run_id}:message:tool:{turn}:{tool_call_id}")


def _plain_tool_started_event(
    *,
    step: WorkflowStepRecord,
    tool_name: str,
    call_id: str,
    args: dict[str, Any],
    order: int,
    message_key: str | None,
) -> EventSpec:
    payload: dict[str, Any] = {
        "tool": tool_name,
        "tool_call_id": call_id,
        "args": args,
        "order": order,
    }
    if message_key:
        payload["message_key"] = message_key
    return EventSpec(
        event_type="tool_started",
        payload=payload,
        lane="user",
        tool_call_id=call_id,
        idempotency_key=f"run:{step.run_id}:step:{step.step_id}:tool:{call_id}:ui-started",
    )


# Cap the output we inline into the presentation event. The homepage tool row only
# renders a few preview lines, so we avoid bloating the event log with large outputs
# (e.g. full file reads); full output still lives in the persisted tool result/blob.
_PLAIN_TOOL_OUTPUT_PREVIEW_CHARS = 8000


def _truncate_tool_output(output: Any) -> str:
    text = str(output or "")
    if len(text) <= _PLAIN_TOOL_OUTPUT_PREVIEW_CHARS:
        return text
    return text[:_PLAIN_TOOL_OUTPUT_PREVIEW_CHARS] + "\n… (truncated)"


def _plain_tool_completed_event(
    *,
    step: WorkflowStepRecord,
    tool_name: str,
    call_id: str,
    args: dict[str, Any],
    result: ToolResult,
    order: int,
    elapsed_ms: float,
    message_key: str | None,
) -> EventSpec:
    payload: dict[str, Any] = {
        "tool": tool_name,
        "tool_call_id": call_id,
        "args": args,
        "output": _truncate_tool_output(result.output),
        "is_error": bool(result.is_error),
        "error": bool(result.is_error),
        "elapsed_ms": int(max(elapsed_ms, 0.0)),
        "order": order,
    }
    if message_key:
        payload["message_key"] = message_key
    return EventSpec(
        event_type="tool_completed",
        payload=payload,
        lane="user",
        tool_call_id=call_id,
        idempotency_key=f"run:{step.run_id}:step:{step.step_id}:tool:{call_id}:ui-completed",
    )


def _tool_call_name(tool_call: Any) -> str:
    if not isinstance(tool_call, dict):
        return ""
    return _normalize_tool_name(tool_call.get("name") or tool_call.get("tool_name") or tool_call.get("tool"))


def _explicit_dependency_artifact_refs(ctx, args: dict[str, Any]) -> set[str]:
    normalized_args = generation_store.normalize_dependency_artifact_refs(ctx, args, skip_key="artifact_ref")
    return generation_store.collect_artifact_refs(normalized_args, skip_key="artifact_ref")


def _recent_tool_invocations(
    messages: list[dict[str, Any]],
    *,
    limit: int,
    exclude_call_id: str | None = None,
) -> list[str]:
    if limit <= 0:
        return []
    excluded = str(exclude_call_id or "").strip()
    seen_call_ids: set[str] = set()
    names: list[str] = []
    for message in sorted(
        [item for item in messages if isinstance(item, dict)],
        key=lambda item: int(item.get("_seq") or 0),
        reverse=True,
    ):
        role = str(message.get("role") or "").strip()
        if role == "tool":
            call_id = str(message.get("tool_call_id") or "").strip()
            if call_id and (call_id == excluded or call_id in seen_call_ids):
                continue
            metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
            name = _normalize_tool_name(message.get("tool_name") or metadata.get("tool_name"))
            if name:
                if call_id:
                    seen_call_ids.add(call_id)
                names.append(name)
        elif role == "assistant" and isinstance(message.get("tool_calls"), list):
            tool_calls = [tool_call for tool_call in (message.get("tool_calls") or []) if isinstance(tool_call, dict)]
            if excluded:
                excluded_index = next(
                    (
                        index
                        for index, tool_call in enumerate(tool_calls)
                        if str(tool_call.get("id") or "").strip() == excluded
                    ),
                    None,
                )
                if excluded_index is not None:
                    tool_calls = tool_calls[:excluded_index]
            for tool_call in reversed(tool_calls):
                if not isinstance(tool_call, dict):
                    continue
                call_id = str(tool_call.get("id") or "").strip()
                if call_id and (call_id == excluded or call_id in seen_call_ids):
                    continue
                name = _tool_call_name(tool_call)
                if name:
                    if call_id:
                        seen_call_ids.add(call_id)
                    names.append(name)
                if len(names) >= limit:
                    return names[:limit]
        if len(names) >= limit:
            return names[:limit]
    return names[:limit]


def _recent_tool_invocations_include_media_generation(
    messages: list[dict[str, Any]],
    *,
    limit: int,
    exclude_call_id: str | None = None,
) -> bool:
    return any(
        is_media_generation_tool(name)
        for name in _recent_tool_invocations(messages, limit=limit, exclude_call_id=exclude_call_id)
    )


async def _maybe_wait_for_recent_media_barrier(
    *,
    ctx,
    tool_name: str,
    parsed_args: dict[str, Any],
    call_id: str,
) -> dict[str, Any] | None:
    if _normalize_tool_name(tool_name) not in _MEDIA_SENSITIVE_READ_TOOLS:
        return None
    if _explicit_dependency_artifact_refs(ctx, parsed_args):
        return None

    window = max(0, int(getattr(settings, "HARNESS_MEDIA_BARRIER_RECENT_TOOL_WINDOW", 5) or 0))
    if window <= 0:
        return None
    try:
        messages = load_messages(ctx.user_id, ctx.conversation_id)
    except Exception:
        return None
    if not _recent_tool_invocations_include_media_generation(messages, limit=window, exclude_call_id=call_id):
        return None
    return await generation_store.wait_for_pending_conversation_media_artifacts(ctx)


async def execute_tool_invocation(
    *,
    step: WorkflowStepRecord,
    gateway: AgentRuntimeGateway,
    activity_gateway: AgentRuntimeGateway,
    scheduler_loop: asyncio.AbstractEventLoop,
    payload: dict[str, Any],
    turn: int,
    tool_call: dict[str, Any],
    absolute_tool_index: int,
    context_session: dict[str, Any] | None,
) -> dict[str, Any]:
    timings: dict[str, float] = {}
    conversation = await get_conversation_async(step.user_id, step.conversation_id) or {"id": step.conversation_id}
    phase_started = _now_ms()
    ctx = create_workflow_context(
        user_id=step.user_id,
        conversation_id=step.conversation_id,
        run_id=step.run_id,
        language=str(payload.get("language") or conversation.get("language") or "zh"),
        conversation=conversation,
    )
    ctx.runtime_gateway = activity_gateway
    apply_context_session_to_context(ctx, context_session or {})
    ctx.ensure_dirs()
    timings["context_setup_ms"] = _phase_elapsed(phase_started)

    phase_started = _now_ms()
    registry = create_harness_registry(web_search_enabled=bool(payload.get("web_search_enabled", True)))
    provider = create_harness_model_provider(
        api_key=await resolve_user_apimart_key_for_context(step.user_id),
        multimodal_provider=_conversation_multimodal_provider(conversation),
    )
    ctx.run_subagent_handler = HarnessSubagentRunner(
        provider=provider,
        conversation=conversation,
        parent_context=ctx,
        parent_registry=registry,
        language=ctx.language,
    ).run
    tool_name = str(tool_call.get("name") or "")
    call_id = str(tool_call.get("id") or f"tool-index:{absolute_tool_index}")
    raw_args = tool_call.get("arguments")
    if isinstance(raw_args, str):
        try:
            parsed_args = json.loads(raw_args) if raw_args.strip() else {}
        except Exception:
            parsed_args = {"raw": raw_args}
    elif isinstance(raw_args, dict):
        parsed_args = dict(raw_args)
    else:
        parsed_args = {}
    timings["registry_args_ms"] = _phase_elapsed(phase_started)

    phase_started = _now_ms()
    effective_args = parsed_args
    presentation_scope = normalize_presentation_scope(step.input.get("presentation_scope") or payload.get("presentation_scope"))
    scoped_message_key = presentation_scope.get("message_key")
    scoped_parent_block_key = presentation_scope.get("parent_block_key")
    # Tool cards need their own chronological message row. Falling back to the
    # shared "{conv}:{run}:assistant" bucket lets later media updates jump back
    # above assistant text emitted after the tool call.
    resolved_tool_presentation_message_key = scoped_message_key or tool_presentation_message_key(
        run_id=step.run_id,
        turn=turn,
        tool_call_id=call_id,
    )
    presentation_order = absolute_tool_index + 1
    ctx.bind_tool_stream_scope(
        tool_name=tool_name,
        tool_call_id=call_id,
        message_key=resolved_tool_presentation_message_key,
        parent_block_key=scoped_parent_block_key,
        order=presentation_order,
    )
    try:
        plan_gate_blocked = blocks_plan_gate_tool(conversation=conversation, tool_name=tool_name)
        dependency_error = None
        if not plan_gate_blocked:
            dependency_error = await _maybe_wait_for_recent_media_barrier(
                ctx=ctx,
                tool_name=tool_name,
                parsed_args=parsed_args,
                call_id=call_id,
            )
            if dependency_error is None:
                resolved_args, dependency_error = await generation_store.resolve_artifact_dependencies(ctx, parsed_args)
                if resolved_args is not None:
                    effective_args = resolved_args
        timings["dependency_resolution_ms"] = _phase_elapsed(phase_started)

        phase_started = _now_ms()
        await gateway.append_event(
            EventSpec(
                event_type="tool_call_started",
                payload={"tool": tool_name, "tool_call_id": call_id},
                tool_call_id=call_id,
                idempotency_key=f"run:{step.run_id}:step:{step.step_id}:tool:{call_id}:started",
            )
        )
        if _emits_plain_tool_presentation(tool_name):
            # User-lane running row (Claude-Code-style). Same block_key=tool:{call_id}
            # is upgraded to completed by the tool_completed event emitted below.
            await gateway.append_event(
                _plain_tool_started_event(
                    step=step,
                    tool_name=tool_name,
                    call_id=call_id,
                    args=effective_args if isinstance(effective_args, dict) else {},
                    order=presentation_order,
                    message_key=resolved_tool_presentation_message_key,
                )
            )
        if step.claim_token:
            await gateway.update_step_checkpoint(
                claim_token=step.claim_token,
                patch={
                    "tool_segment": {
                        "started": True,
                        "latest_tool_name": tool_name,
                        "latest_tool_call_id": call_id,
                        "latest_tool_index": absolute_tool_index,
                    }
                },
            )
        timings["tool_start_persist_ms"] = _phase_elapsed(phase_started)

        phase_started = _now_ms()
        if plan_gate_blocked:
            result = ToolResult(
                output=(
                    "Plan approval is required before executing deliverable tools. "
                    "Wait for the user to start the plan before continuing."
                ),
                is_error=True,
                metadata={
                    "plan_gate_blocked": True,
                    "blocked_phase": str(conversation.get("phase") or ""),
                },
            )
        else:
            start_card_event = build_tool_card_event(
                conversation_id=step.conversation_id,
                run_id=step.run_id,
                step_id=step.step_id,
                phase="start",
                tool_name=tool_name,
                call_id=call_id,
                result_payload=effective_args,
                status="running",
                message_key=resolved_tool_presentation_message_key,
                parent_block_key=scoped_parent_block_key,
                order=presentation_order,
            )
            if start_card_event is not None:
                await gateway.append_event(start_card_event)
            if dependency_error is not None:
                result = ToolResult(
                    output=json.dumps(dependency_error, ensure_ascii=False),
                    is_error=True,
                    metadata=dependency_error,
                )
            else:
                result = await registry.execute(tool_name, effective_args, ctx)
    finally:
        ctx.clear_tool_stream_scope()

    timings["tool_execute_ms"] = _phase_elapsed(phase_started)
    phase_started = _now_ms()
    review = review_tool_result(tool_name, effective_args, result)
    timings["tool_review_ms"] = _phase_elapsed(phase_started)
    result_payload = {
        "tool": tool_name,
        "tool_call_id": call_id,
        "args": effective_args,
        "output": result.output,
        "is_error": bool(result.is_error),
        "metadata": result.metadata or {},
        "review": review,
    }
    if _emits_plain_tool_presentation(tool_name):
        # User-lane completed/failed row; upgrades the running block in place.
        await gateway.append_event(
            _plain_tool_completed_event(
                step=step,
                tool_name=tool_name,
                call_id=call_id,
                args=effective_args if isinstance(effective_args, dict) else {},
                result=result,
                order=presentation_order,
                elapsed_ms=timings.get("tool_execute_ms", 0.0),
                message_key=resolved_tool_presentation_message_key,
            )
        )
    return {
        "tool_index": int(absolute_tool_index),
        "tool_name": tool_name,
        "call_id": call_id,
        "raw_args": effective_args,
        "status": "failed" if result.is_error else "completed",
        "is_error": bool(result.is_error),
        "result_payload": result_payload,
        "review": review,
        "billing_breakdown": list(ctx.billing_breakdown),
        "timings": timings,
        "presentation_scope": {
            "message_key": resolved_tool_presentation_message_key,
            "parent_block_key": scoped_parent_block_key,
        },
        "presentation_order": presentation_order,
    }
