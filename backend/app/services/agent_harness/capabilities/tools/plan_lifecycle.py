"""Plan-mode lifecycle tools for draft, approval, and execution progress."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.agent_harness.authoring.planning.outline_plan import (
    build_outline_projection,
    execution_state_from_steps,
    outline_from_user_plan,
)
from app.services.agent_harness.authoring.planning.user_plan import normalize_artifact_type, normalize_user_plan_for_storage
from app.services.agent_harness.runtime.eventing.presentation import normalize_plan_state
from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation

from ._internal.base import BaseTool, ToolResult


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _phase(conversation: dict[str, Any] | None) -> str:
    return str((conversation or {}).get("phase") or "").strip().lower()


def _previous_plan_state(conversation: dict[str, Any] | None) -> dict[str, Any] | None:
    plan = (conversation or {}).get("plan_state") if isinstance(conversation, dict) else None
    return plan if isinstance(plan, dict) else None


def _planning_draft(conversation: dict[str, Any] | None) -> dict[str, Any] | None:
    draft = (conversation or {}).get("planning_draft") if isinstance(conversation, dict) else None
    return draft if isinstance(draft, dict) else None


def _require_phase(conversation: dict[str, Any] | None, allowed: set[str], tool_name: str) -> str | None:
    phase = _phase(conversation)
    if phase not in allowed:
        return f"{tool_name} is only available in {', '.join(sorted(allowed))}; current phase is {phase or 'unknown'}."
    return None


def _non_empty_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return [text]
        return _non_empty_strings(decoded)
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_open_questions(value: Any) -> list[str]:
    if value is None:
        return []
    return _non_empty_strings(value)


def _validate_outline_summary(text: str) -> None:
    normalized = "".join(str(text or "").split())
    cjk_count = sum(1 for char in normalized if "\u4e00" <= char <= "\u9fff")
    if cjk_count < 20 and len(normalized) < 40:
        raise ValueError("outline item summary is too short; use at least 20 Chinese characters or 40 English characters")


def _infer_artifact_type(confirmed_inputs: dict[str, Any]) -> str:
    for key in ("artifact_type", "artifact", "deliverable_type", "deliverable", "type"):
        value = confirmed_inputs.get(key)
        if value:
            return normalize_artifact_type(str(value))
    return "other"


def _minimum_outline_items(artifact_type: str) -> int:
    return {
        "ppt": 2,
        "word": 2,
        "html": 2,
        "excel": 1,
    }.get(normalize_artifact_type(artifact_type), 1)


def _validate_draft_outline_items(items: list[Any], *, artifact_type: str = "other") -> None:
    outline_items = [item for item in list(items or []) if isinstance(item, dict)]
    minimum_count = _minimum_outline_items(artifact_type)
    if len(outline_items) < minimum_count:
        raise ValueError(f"draft_outline requires at least {minimum_count} item(s) for {normalize_artifact_type(artifact_type)}")
    seen_ids: set[str] = set()
    for index, item in enumerate(outline_items, start=1):
        item_id = str(item.get("id") or "").strip()
        if item_id:
            if item_id in seen_ids:
                raise ValueError("draft_outline item ids must be unique")
            seen_ids.add(item_id)
        title = str(item.get("title") or "").strip()
        if not title:
            raise ValueError(f"draft_outline item {index} requires title")
        summary = str(item.get("summary") or item.get("description") or "").strip()
        if not summary:
            raise ValueError(f"draft_outline item {index} requires summary")
        _validate_outline_summary(summary)


def _approval_user_plan_from_draft(
    *,
    params: "RequestPlanApprovalInput",
    planning_draft: dict[str, Any],
    previous_plan_state: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = params.user_plan.model_dump(exclude_none=True) if params.user_plan is not None else {}
    previous_outline = (
        previous_plan_state.get("outline_state")
        if isinstance(previous_plan_state, dict) and isinstance(previous_plan_state.get("outline_state"), dict)
        else {}
    )
    draft_outline = [
        dict(item)
        for item in list(planning_draft.get("draft_outline") or [])
        if isinstance(item, dict)
    ]
    raw_user_plan: dict[str, Any] = {
        "artifact_type": metadata.get("artifact_type") or previous_outline.get("artifact_type") or "other",
        "title": metadata.get("title") or params.title,
        "summary": metadata.get("summary") or params.summary or str(planning_draft.get("summary") or ""),
        "outline": draft_outline,
    }
    for key in ("file_path", "file_name", "progress_message", "constraints", "style_notes"):
        if metadata.get(key) is not None:
            raw_user_plan[key] = metadata[key]
    return raw_user_plan


class UserPlanOutlineItemInput(BaseModel):
    id: str | None = Field(default=None, description="Stable item id such as slide-1, section-2, or outline-3.")
    title: str = Field(..., description="User-facing outline item title.")
    summary: str | None = Field(
        default=None,
        description=(
            "1-3 concrete sentences describing the final deliverable content for this item: what it contains, "
            "why it belongs there, and the key points to present. Use at least 20 Chinese characters or 40 English characters."
        ),
    )
    description: str | None = Field(default=None, description="Legacy fallback; new outlines should use summary.")
    order: int | None = Field(default=None, description="Optional explicit order.")
    artifact_ref: str | None = Field(default=None, description="Optional artifact reference.")

    @model_validator(mode="after")
    def _validate_content(self) -> "UserPlanOutlineItemInput":
        if not self.title.strip():
            raise ValueError("outline item title cannot be empty")
        content = str(self.summary or self.description or "").strip()
        if not content:
            raise ValueError("outline items require summary or description")
        _validate_outline_summary(content)
        return self


class UserPlanInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    artifact_type: str | None = Field(default=None, description="Deliverable type such as ppt, word, excel, or html.")
    title: str | None = Field(default=None, description="User-facing plan title.")
    summary: str | None = Field(default=None, description="User-facing plan summary.")
    progress_message: str | None = Field(default=None, description="Optional user-facing progress summary.")
    outline: list[UserPlanOutlineItemInput] = Field(
        default_factory=list,
        description="Deprecated for request_plan_approval. Approval outline is derived from latest planning_draft.draft_outline.",
    )
    file_path: str | None = Field(default=None, description="Optional workspace-relative artifact path.")
    file_name: str | None = Field(default=None, description="Optional artifact filename shown to the user.")


class ExecutionStepInput(BaseModel):
    id: str = Field(..., description="Stable step identifier such as step-1.")
    title: str = Field(..., description="Short executable step title.")
    status: Literal["pending", "in_progress", "completed"] = Field(..., description="Step status.")
    description: str | None = Field(default=None, description="Optional one-line description.")
    order: int | None = Field(default=None, description="Optional explicit order.")


class PlanningDraftInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: str = Field(..., description="Current planning understanding.")
    confirmed_inputs: dict[str, Any] = Field(default_factory=dict, description="Inputs already confirmed or inferred.")
    assumptions: list[str] = Field(default_factory=list, description="Working assumptions for the draft.")
    draft_outline: list[UserPlanOutlineItemInput] = Field(
        ...,
        min_length=1,
        description=(
            "Required draft deliverable outline. This is a read-only preview, not approval-ready and not executable. "
            "Each item must include title and a detailed summary."
        ),
    )
    open_questions: list[str] = Field(default_factory=list, description="Blocking or unresolved planning questions.")

    @field_validator("open_questions", mode="before")
    @classmethod
    def _normalize_open_questions_field(cls, value: Any) -> list[str]:
        return _normalize_open_questions(value)

    @model_validator(mode="after")
    def _validate_draft_outline(self) -> "PlanningDraftInput":
        artifact_type = _infer_artifact_type(self.confirmed_inputs)
        _validate_draft_outline_items(
            [item.model_dump(exclude_none=True) for item in self.draft_outline],
            artifact_type=artifact_type,
        )
        return self


class RequestPlanApprovalInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., description="Internal execution plan title.")
    summary: str = Field(..., description="One-line approved plan summary.")
    user_plan: UserPlanInput | None = Field(
        default=None,
        description="Optional display and artifact metadata. The approved outline is derived from the latest planning draft.",
    )
    execution_steps: list[ExecutionStepInput] = Field(..., min_length=1, description="Executable steps after approval.")
    assumptions: list[str] = Field(default_factory=list, description="Defaults and assumptions to use during execution.")
    verification: list[str] = Field(default_factory=list, description="Verification checks to perform before final delivery.")
    followups: list[str] = Field(default_factory=list, description="Non-blocking follow-up items.")
    open_questions: list[str] = Field(default_factory=list, description="Must be empty before requesting approval.")

    @field_validator("open_questions", mode="before")
    @classmethod
    def _normalize_open_questions_field(cls, value: Any) -> list[str]:
        return _normalize_open_questions(value)

    @model_validator(mode="after")
    def _validate_ready(self) -> "RequestPlanApprovalInput":
        if [q for q in self.open_questions if str(q).strip()]:
            raise ValueError("request_plan_approval requires open_questions to be empty")
        step_ids = [str(step.id or "").strip() for step in self.execution_steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("request_plan_approval requires unique execution step ids")
        in_progress_steps = [step.id for step in self.execution_steps if step.status == "in_progress"]
        if in_progress_steps:
            raise ValueError("approved execution steps must be pending before the user starts execution")
        return self


class UpdateExecutionProgressInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, description="Optional execution plan title; defaults to approved plan title.")
    summary: str | None = Field(default=None, description="Optional execution summary; defaults to approved plan summary.")
    steps: list[ExecutionStepInput] = Field(..., min_length=1, description="Full execution step list.")
    current_item_id: str | None = Field(default=None, description="Current approved outline item id; never a step id.")
    progress_message: str | None = Field(default=None, description="User-facing progress message.")
    status: Literal["in_progress", "completed", "failed", "blocked"] = Field(
        default="in_progress",
        description="Overall execution status.",
    )
    explanation: str | None = Field(default=None, description="Optional progress explanation.")

    @model_validator(mode="after")
    def _validate_steps(self) -> "UpdateExecutionProgressInput":
        step_ids = [str(step.id or "").strip() for step in self.steps]
        if len(set(step_ids)) != len(step_ids):
            raise ValueError("update_execution_progress requires unique step ids")
        in_progress_steps = [step.id for step in self.steps if step.status == "in_progress"]
        if len(in_progress_steps) > 1:
            raise ValueError("update_execution_progress accepts at most one in_progress step")
        return self


class UpdatePlanningDraftTool(BaseTool):
    @property
    def name(self) -> str:
        return "update_planning_draft"

    @property
    def description(self) -> str:
        return (
            "Update the internal planning draft. This records current understanding, assumptions, draft outline, "
            "and open questions. It never requests approval, never shows a start-execution button, and never starts execution."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return PlanningDraftInput

    async def execute(self, params: PlanningDraftInput, ctx) -> ToolResult:
        conversation = get_conversation(ctx.user_id, ctx.conversation_id) if ctx is not None else None
        phase_error = _require_phase(conversation, {"planning", "revising_plan"}, self.name)
        if phase_error:
            return ToolResult(output=phase_error, is_error=True)
        draft = params.model_dump(exclude_none=True)
        draft["updated_at"] = _now_iso()
        return ToolResult(
            output=json.dumps({"message": "Updated planning draft", "open_questions": draft.get("open_questions")}, ensure_ascii=False),
            metadata={"planning_draft": draft, "status": "completed"},
        )


class RequestPlanApprovalTool(BaseTool):
    @property
    def name(self) -> str:
        return "request_plan_approval"

    @property
    def description(self) -> str:
        return (
            "Submit the latest planning draft for approval. Use only after all blocking planning questions are resolved. "
            "This derives the approved outline from planning_draft.draft_outline, creates the current outline, "
            "waits for the user to start execution, and must not be used for drafts."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return RequestPlanApprovalInput

    async def execute(self, params: RequestPlanApprovalInput, ctx) -> ToolResult:
        conversation = get_conversation(ctx.user_id, ctx.conversation_id) if ctx is not None else None
        phase_error = _require_phase(conversation, {"planning", "revising_plan"}, self.name)
        if phase_error:
            return ToolResult(output=phase_error, is_error=True)
        previous = _previous_plan_state(conversation)
        planning_draft = _planning_draft(conversation)
        if not planning_draft:
            return ToolResult(output="request_plan_approval requires an existing planning draft.", is_error=True)
        if _non_empty_strings(planning_draft.get("open_questions")):
            return ToolResult(output="request_plan_approval requires planning_draft.open_questions to be empty.", is_error=True)
        draft_outline = [item for item in list(planning_draft.get("draft_outline") or []) if isinstance(item, dict)]
        if not draft_outline:
            return ToolResult(output="request_plan_approval requires planning_draft.draft_outline.", is_error=True)
        try:
            _validate_draft_outline_items(
                draft_outline,
                artifact_type=_infer_artifact_type(
                    planning_draft.get("confirmed_inputs") if isinstance(planning_draft.get("confirmed_inputs"), dict) else {}
                ),
            )
        except ValueError as exc:
            return ToolResult(output=f"Invalid planning_draft.draft_outline: {exc}", is_error=True)
        raw_user_plan = _approval_user_plan_from_draft(
            params=params,
            planning_draft=planning_draft,
            previous_plan_state=previous,
        )
        try:
            outline_state = outline_from_user_plan(
                raw_user_plan,
                previous_outline=previous.get("outline_state") if isinstance(previous, dict) else None,
                status="draft",
            )
        except (TypeError, ValueError) as exc:
            return ToolResult(output=f"Invalid user_plan: {exc}", is_error=True)
        plan_state = normalize_plan_state(
            title=params.title,
            summary=params.summary,
            steps=[step.model_dump() for step in params.execution_steps],
            current_item_id=None,
            status="planning_ready",
            previous_plan_state=None,
        )
        execution_state = execution_state_from_steps(
            outline_state=outline_state,
            steps=plan_state.get("steps") or [],
            status="planning_ready",
            current_item_id=None,
            previous_execution=None,
        )
        projection_state = build_outline_projection(outline_state, execution_state)
        plan_state.update(
            {
                "status": "planning_ready",
                "outline_state": outline_state,
                "execution_state": execution_state,
                "projection_state": projection_state,
                "user_plan": normalize_user_plan_for_storage(
                    raw_user_plan,
                    plan_state={**plan_state, "outline_state": outline_state, "execution_state": execution_state},
                    mode=str(raw_user_plan.get("artifact_type") or "other"),
                ),
                "assumptions": list(params.assumptions or []),
                "verification": list(params.verification or []),
                "followups": list(params.followups or []),
                "approval_source": "planning_draft",
                "planning_draft_updated_at": planning_draft.get("updated_at"),
            }
        )
        return ToolResult(
            output=json.dumps({"message": "Plan submitted for approval", "status": "planning_ready"}, ensure_ascii=False),
            metadata={"plan_state": plan_state, "status": "completed", "approval_requested": True},
        )


class UpdateExecutionProgressTool(BaseTool):
    @property
    def name(self) -> str:
        return "update_execution_progress"

    @property
    def description(self) -> str:
        return (
            "Update progress for an already approved and started plan. This cannot create or revise the approved outline; "
            "it only updates execution step status, current outline item, and user-facing progress."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return UpdateExecutionProgressInput

    async def execute(self, params: UpdateExecutionProgressInput, ctx) -> ToolResult:
        conversation = get_conversation(ctx.user_id, ctx.conversation_id) if ctx is not None else None
        phase_error = _require_phase(conversation, {"executing", "finalizing", "completed"}, self.name)
        if phase_error:
            return ToolResult(output=phase_error, is_error=True)
        previous = _previous_plan_state(conversation)
        if not isinstance(previous, dict) or not isinstance(previous.get("outline_state"), dict):
            return ToolResult(output="update_execution_progress requires an approved current outline.", is_error=True)
        title = params.title or str(previous.get("title") or "")
        summary = params.summary or str(previous.get("summary") or "")
        if not title or not summary:
            return ToolResult(output="update_execution_progress requires title and summary from the approved plan.", is_error=True)
        plan_state = normalize_plan_state(
            title=title,
            summary=summary,
            steps=[step.model_dump() for step in params.steps],
            current_item_id=params.current_item_id,
            status=params.status,
            previous_plan_state=previous,
        )
        outline_state = previous["outline_state"]
        execution_state = execution_state_from_steps(
            outline_state=outline_state,
            steps=plan_state.get("steps") or [],
            status=params.status,
            current_item_id=params.current_item_id,
            previous_execution=previous.get("execution_state") if isinstance(previous.get("execution_state"), dict) else None,
        )
        projection_state = build_outline_projection(outline_state, execution_state)
        plan_state.update(
            {
                "outline_state": outline_state,
                "execution_state": execution_state,
                "projection_state": projection_state,
                "user_plan": previous.get("user_plan"),
                "assumptions": previous.get("assumptions") or [],
                "verification": previous.get("verification") or [],
                "followups": previous.get("followups") or [],
            }
        )
        if params.progress_message:
            user_plan = dict(plan_state.get("user_plan") or {})
            user_plan["progress_message"] = params.progress_message
            plan_state["user_plan"] = user_plan
        return ToolResult(
            output=json.dumps({"message": "Updated execution progress", "status": params.status}, ensure_ascii=False),
            metadata={
                "plan_state": plan_state,
                "execution_progress": True,
                "explanation": params.explanation,
                "status": "completed",
            },
        )
