from __future__ import annotations

import json
import time
import uuid
from typing import Any

from app.services.agent_harness.authoring.prompt.runtime_time import runtime_time_block
from app.services.agent_harness.capabilities.subagents.definitions import get_subagent_definition
from app.services.agent_harness.capabilities.subagents.types import SubagentRequest, SubagentResult, SubagentStatus
from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry
from app.services.agent_harness.core.constants import SUBAGENT_MAX_DEPTH
from app.services.agent_harness.core.context import HarnessContext, reset_current_context, set_current_context
from app.services.agent_harness.runtime.execution_support.billing_controller import record_model_usage_billing
from app.services.agent_harness.runtime.execution_support.model_stream import ModelStreamTurn
from app.services.agent_harness.runtime.execution_support.reviewer import review_tool_result
from app.services.agent_harness.runtime.model_context.prompt_cache_debug import (
    persist_prompt_cache_debug_usage_trace,
)
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.publisher import publish_presentation_event_async
from app.services.agent_harness.runtime.sidechain.artifacts import SidechainArtifactStore
from app.services.agent_harness.runtime.sidechain.tool_result_envelope import envelope_tool_result


class HarnessSubagentRunner:
    """Small in-process child loop for synchronous Agent-style subagents."""

    def __init__(
        self,
        *,
        provider: Any,
        conversation: dict[str, Any],
        parent_context: HarnessContext,
        parent_registry: ToolRegistry,
        language: str,
    ) -> None:
        self.provider = provider
        self.conversation = conversation
        self.parent_context = parent_context
        self.parent_registry = parent_registry
        self.language = language

    async def run(self, request: SubagentRequest, parent_ctx: HarnessContext) -> SubagentResult:
        definition = get_subagent_definition(request.subagent_type)
        if definition is None:
            return SubagentResult(
                task_id=f"refused-{uuid.uuid4().hex[:8]}",
                status="refused",
                summary=f"Unsupported subagent_type: {request.subagent_type}",
                result={"reason": "unsupported_subagent_type"},
            )
        if parent_ctx.subagent_depth >= SUBAGENT_MAX_DEPTH:
            return SubagentResult(
                task_id=f"refused-{uuid.uuid4().hex[:8]}",
                status="refused",
                summary="Subagent nesting limit reached.",
                result={"reason": "max_depth_exceeded", "depth": parent_ctx.subagent_depth},
            )

        parent_ctx.hydrate_run_output_anchor()
        child_ctx = self._child_context(parent_ctx, request)
        artifact_store = SidechainArtifactStore(parent_ctx)
        transcript_ref = artifact_store.start_transcript(
            request.task_id,
            metadata={
                "label": request.label,
                "description": request.spec.description,
                "subagent_type": request.subagent_type,
                "parent_run_id": parent_ctx.run_id,
                "child_run_id": child_ctx.subagent_run_id or child_ctx.run_id,
            },
        )
        child_registry = self._child_registry(request.subagent_type)
        system = self._system_prompt(definition.get_system_prompt(self.language), child_registry)
        messages: list[dict[str, Any]] = [{"role": "user", "content": request.spec.prompt}]
        model = (
            child_ctx.multimodal_model
            or child_ctx.model_preferences.get("multimodal_model")
            or (self.conversation.get("model_preferences") or {}).get("multimodal_model")
        )
        assistant_text = ""
        tool_records: list[dict[str, Any]] = []
        usage: dict[str, Any] | None = None
        tool_result_summary_chars = self._tool_result_summary_chars(definition)
        prompt_cache_key = self._prompt_cache_key(parent_ctx, child_ctx, request)

        token = set_current_context(child_ctx)
        try:
            await self._emit_started(parent_ctx, request, child_ctx)
            exhausted_after_tool_calls = False
            for turn in range(definition.max_turns):
                stream_turn = ModelStreamTurn()
                started_at = time.monotonic()
                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    system=system,
                    tools=child_registry.to_api_schemas(fmt="openai", language=self.language),
                    model=model,
                    prompt_cache_key=prompt_cache_key,
                ):
                    stream_turn.observe(chunk)
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                if stream_turn.usage:
                    usage = stream_turn.usage
                    self._persist_prompt_cache_usage(
                        child_ctx=child_ctx,
                        request=request,
                        turn=turn,
                        model=str(model or ""),
                        prompt_cache_key=prompt_cache_key,
                        usage=stream_turn.usage,
                        elapsed_ms=elapsed_ms,
                        kind="subagent_llm",
                    )
                    await record_model_usage_billing(
                        user_id=child_ctx.user_id,
                        ctx=child_ctx,
                        model_name=model,
                        usage=stream_turn.usage,
                        elapsed_ms=elapsed_ms,
                        kind="subagent_llm",
                    )
                assistant_text += stream_turn.text
                if stream_turn.text:
                    artifact_store.append_transcript(
                        request.task_id,
                        {"role": "assistant", "turn": turn, "content": stream_turn.text},
                    )
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": stream_turn.text}
                if stream_turn.tool_calls:
                    assistant_msg["tool_calls"] = stream_turn.tool_calls
                messages.append(assistant_msg)
                if not stream_turn.tool_calls:
                    break

                for raw_call in stream_turn.tool_calls:
                    tool_name = str(raw_call.get("name") or "")
                    call_id = str(raw_call.get("id") or f"{tool_name}_{uuid.uuid4().hex[:8]}")
                    args = self._parse_args(raw_call.get("arguments"))
                    canonical_tool = ToolRegistry._normalise_name(tool_name)
                    if child_registry.get(canonical_tool) is None:
                        result = self._terminal_result(
                            request=request,
                            child_ctx=child_ctx,
                            status="failed",
                            summary="Subagent attempted to use a tool outside its profile.",
                            reason_code="tool_not_available_to_subagent",
                        )
                        if not request.auto_finalize_terminal:
                            result_payload = dict(result.result) if isinstance(result.result, dict) else {"value": result.result}
                            result_payload["transcript_ref"] = transcript_ref
                            return SubagentResult(
                                task_id=result.task_id,
                                status=result.status,
                                summary=result.summary,
                                result=result_payload,
                                usage=result.usage,
                                reason_code=result.reason_code,
                            )
                        return await self.finalize_terminal_result(
                            parent_ctx=parent_ctx,
                            request=request,
                            result=result,
                            transcript_ref=transcript_ref,
                            child_ctx=child_ctx,
                        )
                    child_ctx.bind_tool_stream_scope(
                        tool_name=canonical_tool,
                        tool_call_id=call_id,
                        message_key=presentation_v2.message_key_for_run(parent_ctx.conversation_id, parent_ctx.run_id),
                        parent_block_key=f"subagent:{request.task_id}",
                    )
                    try:
                        result = await child_registry.execute(canonical_tool, args, child_ctx)
                    finally:
                        child_ctx.clear_tool_stream_scope()
                    result = envelope_tool_result(
                        ctx=child_ctx,
                        tool_name=canonical_tool,
                        tool_call_id=call_id,
                        result=result,
                    )
                    review = review_tool_result(canonical_tool, args, result)
                    record = {
                        "turn": turn,
                        "tool": canonical_tool,
                        "tool_call_id": call_id,
                        "args": args,
                        "is_error": result.is_error,
                        "metadata": result.metadata or {},
                        "review": review,
                    }
                    tool_records.append(record)
                    artifact_store.append_transcript(
                        request.task_id,
                        {
                            "role": "tool",
                            "turn": turn,
                            "tool": canonical_tool,
                            "tool_call_id": call_id,
                            "content": result.output,
                            "metadata": result.metadata or {},
                            "review": review,
                        },
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "tool_name": canonical_tool,
                            "content": json.dumps(
                                {
                                    "status": review.get("outcome"),
                                    "summary": (result.output or "")[:tool_result_summary_chars],
                                    "review": review,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                if turn == definition.max_turns - 1:
                    exhausted_after_tool_calls = True
            if exhausted_after_tool_calls:
                final_turn = definition.max_turns
                messages.append({"role": "user", "content": self._finalization_prompt(request.subagent_type)})
                stream_turn = ModelStreamTurn()
                started_at = time.monotonic()
                async for chunk in self.provider.chat_stream(
                    messages=messages,
                    system=system,
                    tools=[],
                    tool_choice="none",
                    model=model,
                    prompt_cache_key=prompt_cache_key,
                ):
                    stream_turn.observe(chunk)
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                if stream_turn.usage:
                    usage = stream_turn.usage
                    self._persist_prompt_cache_usage(
                        child_ctx=child_ctx,
                        request=request,
                        turn=final_turn,
                        model=str(model or ""),
                        prompt_cache_key=prompt_cache_key,
                        usage=stream_turn.usage,
                        elapsed_ms=elapsed_ms,
                        kind="subagent_llm_final",
                    )
                    await record_model_usage_billing(
                        user_id=child_ctx.user_id,
                        ctx=child_ctx,
                        model_name=model,
                        usage=stream_turn.usage,
                        elapsed_ms=elapsed_ms,
                        kind="subagent_llm_final",
                    )
                assistant_text += stream_turn.text
                if stream_turn.text:
                    artifact_store.append_transcript(
                        request.task_id,
                        {"role": "assistant", "turn": final_turn, "content": stream_turn.text},
                    )
                messages.append({"role": "assistant", "content": stream_turn.text})
        finally:
            reset_current_context(token)

        self._merge_child_billing(parent_ctx, child_ctx)
        status = self._status(tool_records, assistant_text=assistant_text)
        result = SubagentResult(
            task_id=child_ctx.subagent_run_id or child_ctx.run_id,
            status=status,
            summary=self._summary(assistant_text, tool_records, limit=tool_result_summary_chars),
            result={
                "assistant_text": assistant_text,
                "tool_calls": tool_records,
                "subagent_run_id": child_ctx.subagent_run_id or child_ctx.run_id,
                "task_spec": request.spec.to_dict(),
            },
            usage=usage,
        )
        if not request.auto_finalize_terminal:
            result_payload = dict(result.result) if isinstance(result.result, dict) else {"value": result.result}
            result_payload["transcript_ref"] = transcript_ref
            return SubagentResult(
                task_id=result.task_id,
                status=result.status,
                summary=result.summary,
                result=result_payload,
                usage=result.usage,
                reason_code=result.reason_code,
            )
        return await self.finalize_terminal_result(
            parent_ctx=parent_ctx,
            request=request,
            result=result,
            transcript_ref=transcript_ref,
            child_ctx=child_ctx,
        )

    def _child_context(self, parent_ctx: HarnessContext, request: SubagentRequest) -> HarnessContext:
        run_id = request.task_id
        child = HarnessContext(
            user_id=parent_ctx.user_id,
            conversation_id=parent_ctx.conversation_id,
            run_id=run_id,
            language=parent_ctx.language,
            runtime_profile=parent_ctx.runtime_profile,
            project_id=parent_ctx.project_id,
            workspace_root=parent_ctx.workspace_root,
            skill_id=parent_ctx.skill_id,
            artifact_mode=parent_ctx.artifact_mode,
            design_system_id=parent_ctx.design_system_id,
            model_preferences=dict(parent_ctx.model_preferences),
            runtime_state=parent_ctx.runtime_state,
            history_summary=dict(parent_ctx.history_summary) if isinstance(parent_ctx.history_summary, dict) else parent_ctx.history_summary,
            conversation_state=parent_ctx.conversation_state,
            image_model=parent_ctx.image_model,
            image_provider=parent_ctx.image_provider,
            video_model=parent_ctx.video_model,
            video_provider=parent_ctx.video_provider,
            multimodal_model=parent_ctx.multimodal_model,
            multimodal_provider=parent_ctx.multimodal_provider,
            parent_usage_log_id=parent_ctx.parent_usage_log_id,
            active_skill_dir=parent_ctx.active_skill_dir,
            skill_runtime_dir=parent_ctx.skill_runtime_dir,
            prepared_workspace=parent_ctx.prepared_workspace,
            workspace_runtime_session=(
                dict(parent_ctx.workspace_runtime_session)
                if isinstance(parent_ctx.workspace_runtime_session, dict)
                else parent_ctx.workspace_runtime_session
            ),
            artifact_work_root=parent_ctx.artifact_work_root,
            prepared_entry_file=parent_ctx.prepared_entry_file,
            parent_run_id=parent_ctx.run_id,
            subagent_run_id=run_id,
            subagent_label=request.label,
            subagent_type=request.subagent_type,
            is_subagent=True,
            subagent_depth=parent_ctx.subagent_depth + 1,
            run_output_anchor_message_id=parent_ctx.run_output_anchor_message_id,
            run_output_anchor_created_at=parent_ctx.run_output_anchor_created_at,
            run_output_anchor_source=parent_ctx.run_output_anchor_source,
        )
        child.event_queue = parent_ctx.event_queue
        child.runtime_gateway = parent_ctx.runtime_gateway
        child.run_subagent_handler = parent_ctx.run_subagent_handler
        quality_review_packet = getattr(parent_ctx, "quality_review_packet", None)
        if isinstance(quality_review_packet, dict):
            setattr(child, "quality_review_packet", dict(quality_review_packet))
        child._read_snapshots_cache = dict(parent_ctx._read_snapshots_cache)  # noqa: SLF001 - forked read-state cache
        read_window_cache = getattr(parent_ctx, "_read_window_snapshots_cache", None)
        if isinstance(read_window_cache, set):
            setattr(child, "_read_window_snapshots_cache", set(read_window_cache))
        return child

    @staticmethod
    def _prompt_cache_key(parent_ctx: HarnessContext, child_ctx: HarnessContext, request: SubagentRequest) -> str:
        parent_run_id = parent_ctx.run_id or child_ctx.parent_run_id or "parent"
        child_run_id = child_ctx.subagent_run_id or child_ctx.run_id or request.task_id
        return f"subagent:{child_ctx.conversation_id}:{parent_run_id}:{child_run_id}"

    def _persist_prompt_cache_usage(
        self,
        *,
        child_ctx: HarnessContext,
        request: SubagentRequest,
        turn: int,
        model: str,
        prompt_cache_key: str,
        usage: dict[str, Any],
        elapsed_ms: int,
        kind: str,
    ) -> None:
        try:
            persist_prompt_cache_debug_usage_trace(
                user_id=child_ctx.user_id,
                conversation_id=child_ctx.conversation_id,
                run_id=child_ctx.subagent_run_id or child_ctx.run_id,
                step_id=f"{child_ctx.subagent_run_id or child_ctx.run_id}-{kind}",
                turn=turn,
                model=model,
                model_provider=child_ctx.multimodal_provider,
                prompt_cache_key=prompt_cache_key,
                usage=usage,
                elapsed_ms=elapsed_ms,
                parent_run_id=child_ctx.parent_run_id,
                subagent_task_id=request.task_id,
                subagent_type=request.subagent_type,
                trace_scope="subagent",
            )
        except Exception:
            pass

    def _child_registry(self, subagent_type: str) -> ToolRegistry:
        definition = get_subagent_definition(subagent_type)
        if definition is None:
            return ToolRegistry()
        clone_for_subagent = getattr(self.parent_registry, "clone_for_subagent", None)
        if callable(clone_for_subagent):
            return clone_for_subagent(definition)
        registry = ToolRegistry()
        for tool in self.parent_registry.get_tools_for_subagent(definition):
            registry.register(tool)
        return registry

    @staticmethod
    def _merge_child_billing(parent_ctx: HarnessContext, child_ctx: HarnessContext) -> None:
        parent_ctx.absorb_billing_from(child_ctx)

    def _system_prompt(self, subagent_scope: str, registry: ToolRegistry) -> str:
        tool_names = ", ".join(tool.name for tool in registry.get_tools_for_skill(None))
        if self.language == "zh":
            base_prompt = (
                "你是一个受限同步子代理。严格执行父代理提供的任务说明。"
                "只能使用当前可用工具；如果工具失败，请根据真实错误调整策略。"
            )
            runtime_contract = (
                "路径规则：CONVERSATION_DIR 是唯一根目录；文件工具参数使用工作区相对路径，"
                "例如 `project/report.html`、`references/inputs/brief.txt`、`skill/assets/template.html`。"
            )
            scope_header = "## 子代理范围"
            return_instruction = "向父代理返回简洁结果。可用工具："
        else:
            base_prompt = (
                "You are a constrained synchronous subagent. Strictly follow the parent task prompt. "
                "Use only the tools available to you; if a tool fails, inspect the concrete error and adjust."
            )
            runtime_contract = (
                "Path rules: CONVERSATION_DIR is the only root; file-tool parameters use workspace-relative paths, "
                "for example `project/report.html`, `references/inputs/brief.txt`, and `skill/assets/template.html`."
            )
            scope_header = "## Subagent Scope"
            return_instruction = "Return a concise result to the parent agent. Available tools: "
        return (
            base_prompt
            + "\n\n"
            + runtime_time_block(self.language)
            + "\n\n"
            + runtime_contract
            + f"\n\n{scope_header}\n"
            + subagent_scope
            + "\n\n"
            + return_instruction
            + tool_names
        )

    async def _emit_started(self, parent_ctx: HarnessContext, request: SubagentRequest, child_ctx: HarnessContext) -> None:
        payload = self._event_payload(request=request, child_ctx=child_ctx, status="running")
        draft = presentation_v2.event_draft(
            presentation_v2.subagent_card(
                conversation_id=parent_ctx.conversation_id,
                run_id=parent_ctx.run_id,
                payload=payload,
                status="running",
            ),
            artifact_id=request.task_id,
            idempotency_key=f"run:{parent_ctx.run_id}:subagent:{request.task_id}:started",
        )
        if parent_ctx.runtime_gateway is not None:
            await parent_ctx.emit_workflow_event(
                draft.event_type,
                draft.payload,
                block_id=draft.block_id,
                artifact_id=request.task_id,
                idempotency_key=draft.idempotency_key,
            )
        else:
            await publish_presentation_event_async(
                parent_ctx.user_id,
                parent_ctx.conversation_id,
                run_id=parent_ctx.run_id,
                draft=draft,
            )

    @staticmethod
    def _event_payload(
        *,
        request: SubagentRequest,
        child_ctx: HarnessContext,
        status: SubagentStatus,
        result: SubagentResult | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": request.task_id,
            "label": request.spec.description,
            "purpose": request.spec.purpose,
            "description": request.spec.description,
            "status": status,
            "agent_run_id": child_ctx.subagent_run_id or child_ctx.run_id,
            "parent_run_id": child_ctx.parent_run_id,
            "subagent_type": request.spec.subagent_type,
            "skill_id": child_ctx.skill_id,
            "task_spec": request.spec.to_dict(),
            **child_ctx.run_output_anchor_payload(),
        }
        if result is not None:
            result_payload = result.result if isinstance(result.result, dict) else {}
            payload.update(
                {
                    "summary": result.summary,
                    "result": result.result,
                    "reason_code": result.reason_code,
                    "transcript_ref": result_payload.get("transcript_ref"),
                    "result_ref": result_payload.get("result_ref"),
                }
            )
        return payload

    @staticmethod
    def _persist_terminal_artifacts(
        artifact_store: SidechainArtifactStore,
        request: SubagentRequest,
        result: SubagentResult,
        transcript_ref: str,
        child_ctx: HarnessContext,
    ) -> SubagentResult:
        result_payload = dict(result.result) if isinstance(result.result, dict) else {"value": result.result}
        result_ref = artifact_store.write_result(
            request.task_id,
            status=result.status,
            summary=result.summary,
            output_refs=list(result_payload.get("output_refs") or []),
            failure_details={"reason_code": result.reason_code} if result.reason_code else {},
            usage_summary=child_ctx.build_billing_summary(),
            transcript_ref=transcript_ref,
        )
        result_payload["transcript_ref"] = transcript_ref
        result_payload["result_ref"] = result_ref
        return SubagentResult(
            task_id=result.task_id,
            status=result.status,
            summary=result.summary,
            result=result_payload,
            usage=result.usage,
            reason_code=result.reason_code,
        )

    async def _emit_terminal_event(
        self,
        parent_ctx: HarnessContext,
        request: SubagentRequest,
        result: SubagentResult,
    ) -> None:
        payload = self._event_payload(
            request=request,
            child_ctx=self._child_context(parent_ctx, request),
            status=result.status,
            result=result,
        )
        draft = presentation_v2.event_draft(
            presentation_v2.subagent_card(
                conversation_id=parent_ctx.conversation_id,
                run_id=parent_ctx.run_id,
                payload=payload,
                status=result.status,
                complete=True,
            ),
            artifact_id=request.task_id,
            idempotency_key=f"run:{parent_ctx.run_id}:subagent:{request.task_id}:{result.status}",
        )
        if parent_ctx.runtime_gateway is not None:
            await parent_ctx.emit_workflow_event(
                draft.event_type,
                draft.payload,
                block_id=draft.block_id,
                artifact_id=request.task_id,
                idempotency_key=draft.idempotency_key,
            )
        else:
            await publish_presentation_event_async(
                parent_ctx.user_id,
                parent_ctx.conversation_id,
                run_id=parent_ctx.run_id,
                draft=draft,
            )

    async def finalize_terminal_result(
        self,
        *,
        parent_ctx: HarnessContext,
        request: SubagentRequest,
        result: SubagentResult,
        transcript_ref: str | None = None,
        child_ctx: HarnessContext | None = None,
    ) -> SubagentResult:
        child_ctx = child_ctx or self._child_context(parent_ctx, request)
        artifact_store = SidechainArtifactStore(parent_ctx)
        if transcript_ref is None:
            result_payload = result.result if isinstance(result.result, dict) else {}
            transcript_ref = str(result_payload.get("transcript_ref") or artifact_store.transcript_ref(request.task_id))
        finalized = self._persist_terminal_artifacts(artifact_store, request, result, transcript_ref, child_ctx)
        await self._emit_terminal_event(parent_ctx, request, finalized)
        return finalized

    @staticmethod
    def _terminal_result(
        *,
        request: SubagentRequest,
        child_ctx: HarnessContext,
        status: SubagentStatus,
        summary: str,
        reason_code: str,
    ) -> SubagentResult:
        return SubagentResult(
            task_id=child_ctx.subagent_run_id or child_ctx.run_id,
            status=status,
            summary=summary,
            result={
                "summary": summary,
                "subagent_run_id": child_ctx.subagent_run_id or child_ctx.run_id,
                "task_spec": request.spec.to_dict(),
                "reason_code": reason_code,
            },
            reason_code=reason_code,
        )

    @staticmethod
    def _parse_args(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return {}

    @staticmethod
    def _tool_result_summary_chars(definition: dict[str, Any] | Any) -> int:
        try:
            return max(1, int(getattr(definition, "tool_result_summary_chars", 4000) or 4000))
        except (TypeError, ValueError):
            return 4000

    def _finalization_prompt(self, subagent_type: str) -> str:
        if str(subagent_type or "") == "QualityReview":
            if self.language == "zh":
                return (
                    "你已经用完内部质量评审的工具轮次。不要再调用工具。"
                    "请只基于已收集的证据，立即返回用户 prompt 要求的唯一 JSON 对象。"
                )
            return (
                "You have exhausted the internal quality-review tool turns. Do not call tools again. "
                "Return exactly the one JSON object requested by the user prompt, using only the evidence already collected."
            )
        if self.language == "zh":
            return "你已经用完子代理工具轮次。不要再调用工具；请基于已有信息返回简洁最终结果。"
        return "You have exhausted the subagent tool turns. Do not call tools again; return a concise final result from the evidence already collected."

    @staticmethod
    def _status(tool_records: list[dict[str, Any]], *, assistant_text: str = "") -> SubagentStatus:
        if not tool_records:
            return "completed"
        if str(assistant_text or "").strip():
            return "completed"
        latest = tool_records[-1]
        if latest.get("is_error"):
            return "failed"
        return "completed"

    @staticmethod
    def _summary(assistant_text: str, tool_records: list[dict[str, Any]], *, limit: int = 4000) -> str:
        summary_limit = max(1, int(limit or 4000))
        text = assistant_text.strip()
        if text:
            return text[:summary_limit]
        for record in reversed(tool_records):
            review = record.get("review") or {}
            excerpt = str(review.get("output_excerpt") or "").strip()
            if excerpt:
                return excerpt[:summary_limit]
        return "Subagent completed without a text summary."
