"""AgentTool - synchronously delegate a task to a built-in subagent."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from pydantic import BaseModel, Field, model_validator

from app.services.agent_harness.capabilities.subagents import (
    SubagentRequest,
    SubagentResult,
    SubagentTaskSpec,
    list_public_subagent_definitions,
)
from app.services.agent_harness.runtime.presentation_v2 import builder as presentation_v2
from app.services.agent_harness.runtime.presentation_v2.publisher import publish_presentation_event_async

from ._internal.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


def _supported_subagent_types() -> list[str]:
    return [definition.name for definition in list_public_subagent_definitions()]


class AgentInput(BaseModel):
    description: str = Field(
        ...,
        min_length=1,
        description="A short (3-5 word) description of the task.",
    )
    prompt: str = Field(
        ...,
        min_length=1,
        description="The complete task for the agent to perform.",
    )
    subagent_type: str = Field(
        default="general-purpose",
        description="The built-in subagent profile to use.",
        json_schema_extra={"enum": _supported_subagent_types()},
    )

    @model_validator(mode="after")
    def _validate_agent_task(self) -> "AgentInput":
        if not str(self.description or "").strip():
            raise ValueError("description is required")
        if not str(self.prompt or "").strip():
            raise ValueError("prompt is required")
        return self


class AgentTool(BaseTool):
    @property
    def name(self) -> str:
        return "Agent"

    @property
    def description(self) -> str:
        return (
            "Delegate a focused task to a built-in synchronous subagent. "
            "Use this when a separate agent should investigate, plan, or complete a bounded task."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return AgentInput

    def to_api_schema(self, fmt: str = "openai", language: str = "zh") -> dict:
        schema = super().to_api_schema(fmt, language=language)
        target = schema["function"]["parameters"] if fmt == "openai" else schema["input_schema"]
        target["properties"]["subagent_type"]["enum"] = _supported_subagent_types()
        return schema

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, AgentInput)
        if str(params.subagent_type or "general-purpose").strip() not in set(_supported_subagent_types()):
            supported = ", ".join(_supported_subagent_types())
            return f"Unsupported subagent_type '{params.subagent_type}'. Supported types: {supported}."
        conversation = getattr(ctx, "conversation", None)
        if isinstance(conversation, dict):
            phase = str(conversation.get("phase") or "").strip().lower()
            if phase in {"planning", "planning_ready", "revising_plan"}:
                return "Agent is unavailable before plan approval. Create or revise the structured plan first."
            if conversation.get("user_plan_repair_required"):
                return "User-plan repair is pending. Call request_plan_approval with a valid user_plan before delegating work."
        return None

    async def execute(self, params: AgentInput, ctx: "HarnessContext") -> ToolResult:
        spec = SubagentTaskSpec(
            description=str(params.description).strip(),
            prompt=str(params.prompt).strip(),
            subagent_type=str(params.subagent_type or "general-purpose").strip() or "general-purpose",
        )
        task_id = f"sub-{uuid.uuid4().hex[:12]}"
        request = SubagentRequest(task_id=task_id, spec=spec)
        handler = self._get_handler(ctx)
        if handler is None:
            return ToolResult(
                output="Subagent execution is not configured for this harness run yet.",
                is_error=True,
                metadata={
                    "task_id": request.task_id,
                    "task_spec": spec.to_dict(),
                    "label": request.label,
                    "subagent_type": request.subagent_type,
                },
            )

        created_payload = {
            "task_id": request.task_id,
            "label": request.label,
            "purpose": spec.purpose,
            "description": spec.description,
            "status": "queued",
            "subagent_type": spec.subagent_type,
            "skill_id": ctx.skill_id,
            "parent_run_id": ctx.run_id,
            "task_spec": spec.to_dict(),
        }
        created_draft = presentation_v2.event_draft(
            presentation_v2.subagent_card(
                conversation_id=ctx.conversation_id,
                run_id=ctx.run_id,
                payload=created_payload,
                status="queued",
            ),
            artifact_id=request.task_id,
            idempotency_key=f"run:{ctx.run_id}:subagent:{request.task_id}:created",
        )
        if ctx.runtime_gateway is not None:
            await ctx.emit_workflow_event(
                created_draft.event_type,
                created_draft.payload,
                block_id=created_draft.block_id,
                artifact_id=request.task_id,
                idempotency_key=created_draft.idempotency_key,
            )
        else:
            await publish_presentation_event_async(
                ctx.user_id,
                ctx.conversation_id,
                run_id=ctx.run_id,
                draft=created_draft,
            )

        result = await handler(request, ctx)
        if isinstance(result, ToolResult):
            return result
        if isinstance(result, SubagentResult):
            failed_statuses = {"degraded", "failed", "refused", "cancelled"}
            return ToolResult(
                output=result.summary,
                is_error=result.status in failed_statuses,
                metadata={
                    "task": request.task,
                    "task_id": result.task_id,
                    "task_spec": spec.to_dict(),
                    "label": request.label,
                    "purpose": spec.purpose,
                    "description": spec.description,
                    "status": result.status,
                    "task_created": True,
                    "task_completed": result.status == "completed",
                    "lifecycle_phase": "terminal",
                    "summary": result.summary,
                    "reason_code": result.reason_code,
                    "result": result.result,
                    "usage": result.usage,
                    "subagent_type": request.subagent_type,
                    "skill_id": ctx.skill_id,
                },
            )
        return ToolResult(output=str(result))

    @staticmethod
    def _get_handler(
        ctx: "HarnessContext",
    ) -> Callable[[SubagentRequest, "HarnessContext"], Awaitable[SubagentResult | ToolResult | Any]] | None:
        handler = ctx.run_subagent_handler
        return handler if callable(handler) else None
