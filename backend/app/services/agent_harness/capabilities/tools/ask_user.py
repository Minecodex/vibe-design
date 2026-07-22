"""AskUserTool — interactive question to user, pauses agent loop."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ._internal.base import BaseTool, ToolResult

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


class AskUserOptionInput(BaseModel):
    label: str
    value: str
    description: str | None = None
    preview_url: str | None = None
    metadata: dict[str, Any] | None = None


class AskUserQuestionInput(BaseModel):
    id: str
    header: str
    question: str
    type: Literal["single", "multiple", "input"]
    required: bool = True
    max_selections: int | None = None
    options: list[AskUserOptionInput] = Field(default_factory=list)


class AskUserInput(BaseModel):
    """Choice-only ask_user contract.

    This intentionally does not support the legacy schema.fields form contract.
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str
    description: str | None = None
    submit_label: str
    questions: list[AskUserQuestionInput] = Field(
        default_factory=list,
        description=(
            "Choice questions to ask the user. Must contain 1-5 questions. "
            "Each question must have 2-4 concrete options. The UI automatically provides Other; do not include custom/Other options yourself."
        ),
    )
    answers: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional previously collected answers keyed by field id. "
            "Use null or omit when there are no prior answers."
        ),
    )
    @model_validator(mode="after")
    def validate_entrypoint(self) -> "AskUserInput":
        if not self.questions:
            raise ValueError("ask_user request must include 1-5 choice questions.")
        return self


class AskUserTool(BaseTool):

    @property
    def name(self) -> str:
        return "ask_user"

    @property
    def description(self) -> str:
        return (
            "Render choice questions beneath the assistant's current explanation. This is not a general form tool. "
            "Pass title, description(optional), submit_label, questions, and answers(optional) as normal tool arguments. "
            "Use ask_user only for the decision UI. When a decision depends on results, a brief, a proposal, a strategy, an option comparison, or rationale, the reply must follow this order: first write complete standalone assistant text with the content the user needs to judge, then call ask_user. "
            "Do not call ask_user after only a promise or lead-in such as 'I will provide the full result', 'I have prepared it', 'below is the complete content', or 'please confirm'; the assistant text must already contain the concrete summary, stage result, checklist, or comparison. "
            "The description field must be short UI helper text, not the main explanation, and must not imply there is unseen content below the card. "
            "Each question must include id, header, question, and type(single, multiple, or input). "
            "Ask 1-5 questions per call. Use single for mutually exclusive choices and multiple when several choices can apply. "
            "Use input sparingly, at most once per call, only for short factual details such as a brand name, URL, email, or one-line constraint that cannot be inferred; set required=false when the user may leave it blank. Never use input for long copy, briefs, or content writing. "
            "The UI always provides an Other option for custom text input; never include Other/custom options yourself. "
            "Do not add skip/not-needed/later/provide-text/provide-links options just to make optional information skippable; use an optional input or proceed with assumptions instead. "
            "If the user said you decide, help me write, or generate it for me, choose reasonable defaults and only ask high-impact direction questions. "
            "Do not ask users to fill long-form factual fields; infer from the request or state assumptions in the plan. "
            "The agent loop will pause until the user responds."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return AskUserInput

    def is_read_only(self, params: BaseModel) -> bool:
        return True

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        conversation = getattr(ctx, "conversation", None)
        if isinstance(conversation, dict) and conversation.get("user_plan_repair_required"):
            return "User-plan repair is pending. Call request_plan_approval first before asking the user anything else."
        phase_error = _validate_planning_ask_user_budget(ctx)
        if phase_error:
            return phase_error
        error, _payload = _build_ask_user_payload(params.model_dump(by_alias=True))
        if error:
            return error
        return None

    async def execute(self, params: AskUserInput, ctx: "HarnessContext") -> ToolResult:
        _record_planning_ask_user(ctx)
        _error, payload = _build_ask_user_payload(params.model_dump(by_alias=True))
        assert payload is not None
        # The actual pausing is handled by the engine when it detects
        # ask_user in tool calls. This just returns the question payload.
        return ToolResult(
            output=str(payload["question"]),
            metadata={"type": "ask_user", **payload},
        )


def _phase_key(phase: Any) -> str:
    return str(phase or "").strip().lower() or "executing"


def _planning_budget_phase(phase: Any) -> str | None:
    normalized = _phase_key(phase)
    return normalized if normalized in {"planning", "revising_plan"} else None


def _read_runtime_state(ctx: "HarnessContext") -> dict[str, Any]:
    conversation = getattr(ctx, "conversation", None)
    if isinstance(conversation, dict):
        runtime_state = conversation.get("runtime_state")
        if isinstance(runtime_state, dict):
            return dict(runtime_state)
        return dict(conversation)
    runtime_state_attr = getattr(ctx, "runtime_state", None)
    if isinstance(runtime_state_attr, dict):
        return dict(runtime_state_attr)
    try:
        from app.services.agent_harness.workspace.session_v2.service import get_conversation

        stored = get_conversation(int(ctx.user_id), str(ctx.conversation_id))
        runtime_state = stored.get("runtime_state") if isinstance(stored, dict) else None
        if isinstance(runtime_state, dict):
            return dict(runtime_state)
        return dict(stored or {})
    except Exception:
        return {}


def _ask_user_count_for_phase(ctx: "HarnessContext", phase: str) -> int:
    runtime_state = _read_runtime_state(ctx)
    counts = runtime_state.get("ask_user_phase_counts")
    if isinstance(counts, dict):
        try:
            return max(0, int(counts.get(phase) or 0))
        except (TypeError, ValueError):
            return 0
    if phase == _phase_key(runtime_state.get("phase")):
        try:
            from app.services.agent_harness.workspace.session_v2.service import count_successful_tool_messages_by_name

            return max(0, int(count_successful_tool_messages_by_name(int(ctx.user_id), str(ctx.conversation_id), "ask_user")))
        except Exception:
            return 0
    return 0


def _validate_planning_ask_user_budget(ctx: "HarnessContext") -> str | None:
    runtime_state = _read_runtime_state(ctx)
    phase = _planning_budget_phase(runtime_state.get("phase") or getattr(getattr(ctx, "runtime_state", None), "phase", None))
    if phase is None:
        return None
    if _ask_user_count_for_phase(ctx, phase) < 3:
        return None
    return (
        "This planning phase has already used ask_user 3 times. "
        "Stop asking clarifying questions and proceed with update_planning_draft or request_plan_approval using the information already available."
    )


def _record_planning_ask_user(ctx: "HarnessContext") -> None:
    runtime_state = _read_runtime_state(ctx)
    phase = _planning_budget_phase(runtime_state.get("phase") or getattr(getattr(ctx, "runtime_state", None), "phase", None))
    if phase is None:
        return
    counts = runtime_state.get("ask_user_phase_counts")
    next_counts = dict(counts) if isinstance(counts, dict) else {}
    next_counts[phase] = _ask_user_count_for_phase(ctx, phase) + 1
    try:
        from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

        patch_runtime_state(
            int(ctx.user_id),
            str(ctx.conversation_id),
            {"ask_user_phase_counts": next_counts},
            touch_updated_at=False,
        )
    except Exception:
        return


def _normalize_option(option: AskUserOptionInput) -> dict[str, Any]:
    label = str(option.label or "").strip()
    value = str(option.value or "").strip()
    payload: dict[str, Any] = {
        "label": label,
        "value": value,
        "description": option.description,
        "preview_url": option.preview_url,
        "metadata": option.metadata,
    }
    return payload


def _normalize_question(question: AskUserQuestionInput) -> dict[str, object]:
    question_id = str(question.id or "").strip()
    header = str(question.header or "").strip()
    question_text = str(question.question or "").strip()
    return {
        "id": question_id,
        "header": header,
        "question": question_text,
        "type": question.type,
        "required": bool(question.required),
        "max_selections": question.max_selections,
        "options": [_normalize_option(option) for option in question.options],
    }


def _build_ask_user_payload(raw_args: dict[str, Any]) -> tuple[str | None, dict[str, object] | None]:
    if not isinstance(raw_args, dict):
        return "ask_user request must be an object.", None
    if isinstance(raw_args.get("schema"), dict) or "fields" in raw_args:
        return "Unsupported legacy ask_user interaction: use top-level title, submit_label, and questions[].", None
    try:
        params = AskUserInput.model_validate(raw_args)
    except ValidationError:
        return "ask_user request must include title, submit_label, and 1-5 choice questions.", None
    title = str(params.title or "").strip()
    submit_label = str(params.submit_label or "").strip()
    if not title or not submit_label:
        return "ask_user schema must include non-empty title and submit_label.", None
    if not (1 <= len(params.questions) <= 5):
        return "ask_user questions must include 1-5 items.", None

    questions: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    input_count = 0
    for question in params.questions:
        question_id = str(question.id or "").strip()
        header = str(question.header or "").strip()
        question_text = str(question.question or "").strip()
        if not question_id or not header or not question_text:
            return "ask_user questions must include non-empty id, header, and question.", None
        if question_id in seen_ids:
            return "ask_user question ids must be unique.", None
        seen_ids.add(question_id)
        if question.type == "input":
            input_count += 1
            if input_count > 1:
                return "ask_user input questions must be used sparingly: at most one input question per call.", None
            if question.max_selections is not None:
                return "ask_user max_selections is only valid for multiple questions.", None
            if len(question.options) > 0:
                return "ask_user input questions must not include options.", None
            questions.append(_normalize_question(question))
            continue
        if not (2 <= len(question.options) <= 4):
            return "ask_user question options must include 2-4 items.", None
        if question.max_selections is not None:
            if question.type != "multiple":
                return "ask_user max_selections is only valid for multiple questions.", None
            if question.max_selections <= 0 or question.max_selections > len(question.options) + 1:
                return "ask_user max_selections must be between 1 and options length plus Other.", None
        labels: set[str] = set()
        values: set[str] = set()
        for option in question.options:
            label = str(option.label or "").strip()
            value = str(option.value or "").strip()
            if not label or not value:
                return "ask_user question options must include non-empty label and value.", None
            normalized_label = label.casefold()
            normalized_value = value.casefold()
            if normalized_label in {"other", "其他"} or normalized_value in {"other", "__ask_user_other__", "__custom_other__"}:
                return "ask_user options must not include Other; the UI provides it automatically.", None
            if normalized_label in labels or normalized_value in values:
                return "ask_user option labels and values must be unique within each question.", None
            labels.add(normalized_label)
            values.add(normalized_value)
        questions.append(_normalize_question(question))

    payload: dict[str, object] = {
        "kind": "ask_user",
        "question": title,
        "schema": {
            "title": title,
            "description": str(params.description or "").strip() or None,
            "submit_label": submit_label,
            "questions": questions,
        },
    }
    if "answers" in raw_args:
        answers = raw_args.get("answers")
        if answers is not None and not isinstance(answers, dict):
            return "ask_user answers must be an object or null when provided.", None
        if answers is not None:
            filtered_answers = {
                str(key).strip(): value
                for key, value in answers.items()
                if str(key).strip() in seen_ids
            }
            if filtered_answers:
                payload["answers"] = filtered_answers
    return None, payload
