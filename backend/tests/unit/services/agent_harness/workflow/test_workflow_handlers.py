from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.services.agent_harness.workflow.contracts import BillingSpec, BlobSpec, EventSpec, MessageSpec
from app.services.agent_harness.runtime.open_design.contracts import ArtifactCaptureResult
from app.services.agent_harness.workflow.handlers import (
    _apply_user_input,
    _current_user_message_from_payload,
    _discovery_schema,
    _execute_tool,
    _finalize,
    _finalize_step_idempotency_key,
    _model_turn,
    _persist_tool_result,
    _prepare_skill,
    _render_context,
    _plan_lifecycle,
    _wait_user_input,
)
from app.services.agent_harness.workflow.records import WorkflowStepRecord
from app.services.agent_harness.workflow.status import (
    RUN_KIND_REVISE_PLAN,
    RUN_KIND_START_PLAN,
    STEP_APPLY_USER_INPUT,
    STEP_DISCOVERY_SCHEMA,
    STEP_EXECUTE_TOOL,
    STEP_FINALIZE,
    STEP_MODEL_TURN,
    STEP_PERSIST_TOOL_RESULT,
    STEP_PREPARE_CONTEXT_SESSION,
    STEP_PREPARE_SKILL,
    STEP_RENDER_CONTEXT,
    STEP_PLAN_LIFECYCLE,
    STEP_WAIT_USER_INPUT,
    STEP_STATUS_FAILED,
    STEP_STATUS_SUCCEEDED,
    STEP_STATUS_WAITING_INPUT,
)
from app.services.agent_harness.workflow.tool_execution import (
    _recent_tool_invocations_include_media_generation,
    execute_tool_invocation,
)


def _step(*, input_payload: dict) -> WorkflowStepRecord:
    return WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_PERSIST_TOOL_RESULT,
        status="running",
        input=input_payload,
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-1:persist-result",
    )


def _tool_outcome(
    *,
    index: int,
    tool_name: str,
    call_id: str,
    output: str = "ok",
    is_error: bool = False,
    metadata: dict | None = None,
) -> dict:
    return {
        "tool_index": index,
        "tool_name": tool_name,
        "call_id": call_id,
        "status": "failed" if is_error else "completed",
        "is_error": is_error,
        "result_payload": {
            "tool": tool_name,
            "tool_call_id": call_id,
            "output": output,
            "metadata": metadata or {},
            "review": {"summary": output, "output_excerpt": output},
        },
        "billing_breakdown": [],
        "timings": {},
    }


class _Gateway:
    def __init__(self) -> None:
        self.activities: list[dict] = []
        self.billings: list[BillingSpec] = []
        self.blobs: list[BlobSpec] = []
        self.events: list[EventSpec] = []
        self.messages: dict[str, dict] = {}
        self.refreshed_statuses: list[str] = []
        self.checkpoints: list[dict] = []

    async def write_blob(self, spec: BlobSpec) -> dict:
        self.blobs.append(spec)
        return {"promoted": False, "artifact": None}

    async def record_activity(self, **kwargs) -> None:
        self.activities.append(kwargs)

    async def record_billing(self, spec: BillingSpec) -> dict:
        self.billings.append(spec)
        return {"id": len(self.billings), "status": spec.task_status}

    async def append_event(self, spec: EventSpec) -> dict:
        self.events.append(spec)
        return {"event_type": spec.event_type, "payload": spec.payload}

    async def append_message(self, spec: MessageSpec) -> dict:
        message_id = spec.idempotency_key or f"message-{len(self.messages) + 1}"
        message = {
            "id": message_id,
            "role": spec.role,
            "content": spec.content,
            "tool_calls": spec.tool_calls or [],
            "metadata": spec.metadata or {},
            "streaming": spec.streaming,
        }
        self.messages[message_id] = message
        return message

    async def update_message(self, *, message_id: str, **kwargs) -> dict | None:
        message = self.messages.get(message_id)
        if message is None:
            return None
        message.update(kwargs)
        return message

    async def update_step_checkpoint(self, *, claim_token: str, patch: dict) -> dict:
        self.checkpoints.append({"claim_token": claim_token, "patch": patch})
        return patch

    async def get_message(self, message_id: str) -> dict | None:
        return self.messages.get(message_id)

    async def get_latest_assistant_message(self) -> dict | None:
        for message in reversed(list(self.messages.values())):
            if message.get("role") == "assistant":
                return message
        return None

    async def refresh_parent_usage_log(self, *, status: str = "success") -> None:
        self.refreshed_statuses.append(status)


def _interaction_submission_message(result) -> tuple[MessageSpec, dict]:
    assert len(result.messages) == 1
    message = result.messages[0]
    assert message.role == "user"
    assert (message.metadata or {})["message_kind"] == "agent_context"
    assert (message.metadata or {})["agent_context_kind"] == "interaction_submission"
    assert (message.metadata or {})["model_visible"] is True
    assert (message.metadata or {})["ui_visible"] is False
    return message, json.loads(message.content or "{}")


def test_current_user_message_uses_plan_revision_instruction():
    message = _current_user_message_from_payload(
        {"instruction": "把第二步改成先做数据清洗"},
        run_id="run-1",
    )

    assert message is not None
    assert message["role"] == "user"
    assert message["content"] == "把第二步改成先做数据清洗"
    assert message["metadata"]["idempotency_key"] == "run:run-1:user-message"


@pytest.mark.asyncio
async def test_discovery_schema_records_quick_brief_model_billing(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "slides",
            "skill_id": "html-ppt",
            "language": "zh",
            "parent_usage_log_id": 123,
        }

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_build_quick_brief_interaction(**kwargs):
        await kwargs["on_model_call"](
            "GPT-5.4",
            {"input_tokens": 11, "output_tokens": 7, "request_id": "quick-req"},
            321,
        )
        return {
            "kind": "quick_brief",
            "request_id": "quick-brief:conv-1:abc",
            "status": "pending",
            "schema": {"title": "Brief", "fields": []},
        }

    billing_calls: list[dict] = []

    async def fake_record_turn_preflight_model_calls(**kwargs):
        billing_calls.append(kwargs)
        return 123

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_skill", lambda _skill_id: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_artifact_family", lambda **_kwargs: "slides")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.conversation_has_reference_attachments", lambda **_kwargs: False)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.build_quick_brief_interaction",
        fake_build_quick_brief_interaction,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.record_turn_preflight_model_calls",
        fake_record_turn_preflight_model_calls,
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-discovery",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_DISCOVERY_SCHEMA,
        status="running",
        input={"kind": "message", "payload": {"language": "zh"}, "artifact_family": "slides"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:discovery_schema:0",
    )

    result = await _discovery_schema(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert len(billing_calls) == 1
    assert billing_calls[0]["conversation"]["parent_usage_log_id"] == 123
    assert billing_calls[0]["run_id"] == "run-1"
    assert billing_calls[0]["turn_idempotency_key"] == "run:run-1:step:discovery_schema:0"
    assert billing_calls[0]["preflight_model_calls"] == [
        {
            "kind": "quick_brief_schema",
            "model_name": "GPT-5.4",
            "usage": {"input_tokens": 11, "output_tokens": 7, "request_id": "quick-req"},
            "elapsed_ms": 321,
        }
    ]


@pytest.mark.asyncio
async def test_apply_quick_brief_for_plan_first_spreadsheet_routes_to_plan_creation(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "spreadsheet",
            "skill_id": "xlsx",
            "phase": "discovery",
            "runtime_state": {
                "user_interaction": {
                    "kind": "quick_brief",
                    "request_id": "quick-brief:conv-1:abc",
                    "status": "pending",
                    "schema": {
                        "title": "Spreadsheet brief",
                        "fields": [
                            {"id": "output_goal", "type": "text", "label": "Goal", "required": True},
                        ],
                    },
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "quick-brief:conv-1:abc",
                "answer": "{\"output_goal\":\"clean_and_structure\"}",
                "answers": {"output_goal": "clean_and_structure"},
                "display_label": "整理为结构化表格",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:quick-brief",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "planning"
    assert result.runtime_patch["activity"] == "planning_outline"
    assert result.next_steps[0].step_type == STEP_PLAN_LIFECYCLE
    message, body = _interaction_submission_message(result)
    assert message.idempotency_key == "run:run-1:interaction-submission:quick-brief:conv-1:abc"
    assert body["kind"] == "quick_brief"
    assert body["request_id"] == "quick-brief:conv-1:abc"
    assert body["schema"]["title"] == "Spreadsheet brief"
    assert body["answers"]["output_goal"] == "clean_and_structure"


@pytest.mark.asyncio
async def test_apply_quick_brief_for_slides_prompts_design_system_id_before_plan(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "slides",
            "skill_id": "html-ppt",
            "phase": "discovery",
            "design_system_id": None,
            "runtime_state": {
                "user_interaction": {
                    "kind": "quick_brief",
                    "request_id": "quick-brief:conv-1:abc",
                    "status": "pending",
                    "schema": {"title": "Brief", "fields": []},
                },
            },
        }

    async def _design_system_interaction(**kwargs):
        assert kwargs["artifact_family"] == "slides"
        assert kwargs["discovery_brief"]["output"] == "Deck"
        await kwargs["on_model_call"](
            "GPT-5.4",
            {"input_tokens": 13, "output_tokens": 5, "request_id": "visual-req"},
            654,
        )
        return {
            "kind": "design_system_picker",
            "request_id": "design-system:conv-1:def",
            "status": "pending",
            "schema": {"title": "Choose", "fields": [{"id": "design_system_id", "options": []}]},
        }

    billing_calls: list[dict] = []

    async def fake_record_turn_preflight_model_calls(**kwargs):
        billing_calls.append(kwargs)
        return 456

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_skill", lambda _skill_id: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.conversation_has_reference_attachments", lambda **_kwargs: False)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.build_design_system_interaction", _design_system_interaction)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.record_turn_preflight_model_calls",
        fake_record_turn_preflight_model_calls,
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "quick-brief:conv-1:abc",
                "answer": '{"output":"Deck"}',
                "answers": {"output": "Deck"},
                "display_label": "Deck",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:quick-brief",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["runtime_status"] == "waiting_input"
    assert result.runtime_patch["user_interaction"]["kind"] == "design_system_picker"
    _, body = _interaction_submission_message(result)
    assert body["kind"] == "quick_brief"
    assert body["answers"]["output"] == "Deck"
    assert result.next_steps[0].step_type == STEP_WAIT_USER_INPUT
    assert result.next_steps[0].input["interaction"]["kind"] == "design_system_picker"
    assert len(billing_calls) == 1
    assert billing_calls[0]["run_id"] == "run-1"
    assert billing_calls[0]["turn_idempotency_key"] == "run:run-1:step:apply_user_input:quick-brief:design_system"
    assert billing_calls[0]["preflight_model_calls"] == [
        {
            "kind": "design_system_selection",
            "model_name": "GPT-5.4",
            "usage": {"input_tokens": 13, "output_tokens": 5, "request_id": "visual-req"},
            "elapsed_ms": 654,
        }
    ]


@pytest.mark.asyncio
async def test_wait_user_input_turn_completed_idempotency_key_is_step_scoped():
    def make_step(step_id: str, request_id: str) -> WorkflowStepRecord:
        return WorkflowStepRecord(
            id=1,
            step_id=step_id,
            run_id="run-1",
            conversation_id="conv-1",
            user_id=7,
            step_type=STEP_WAIT_USER_INPUT,
            status="running",
            input={
                "interaction": {
                    "kind": "design_system_picker",
                    "request_id": request_id,
                    "question": "Choose a design system",
                    "status": "pending",
                    "schema": {"title": "Design system", "fields": []},
                },
                "started_at": "2026-06-02T00:00:00Z",
            },
            attempts=1,
            max_attempts=1,
            priority=0,
            claim_owner="worker-a",
            claim_token="token-1",
            claim_expires_at=None,
            idempotency_key=f"run:run-1:step:wait_user_input:{request_id}",
        )

    first = await _wait_user_input(make_step("step-wait-1", "quick-brief:conv-1:abc"), _Gateway())  # type: ignore[arg-type]
    second = await _wait_user_input(make_step("step-wait-2", "design-system:conv-1:def"), _Gateway())  # type: ignore[arg-type]

    first_terminal = first.events[-1]
    second_terminal = second.events[-1]

    assert first_terminal.event_type == "turn_completed"
    assert second_terminal.event_type == "turn_completed"
    assert first_terminal.idempotency_key != second_terminal.idempotency_key
    assert first_terminal.idempotency_key == "run:run-1:step:step-wait-1:turn-completed:waiting_input"
    assert second_terminal.idempotency_key == "run:run-1:step:step-wait-2:turn-completed:waiting_input"



@pytest.mark.asyncio
async def test_apply_quick_brief_skips_design_system_when_design_system_already_selected(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "document",
            "skill_id": "doc",
            "phase": "discovery",
            "design_system_id": "manual",
            "runtime_state": {
                "user_interaction": {
                    "kind": "quick_brief",
                    "request_id": "quick-brief:conv-1:abc",
                    "status": "pending",
                    "schema": {"title": "Brief", "fields": []},
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "quick-brief:conv-1:abc",
                "answer": '{"output":"Doc"}',
                "answers": {"output": "Doc"},
                "display_label": "Doc",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:quick-brief",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "planning"
    assert result.next_steps[0].step_type == STEP_PLAN_LIFECYCLE


@pytest.mark.asyncio
async def test_apply_design_system_selection_persists_design_system_id_before_plan(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "slides",
            "skill_id": "html-ppt",
            "phase": "discovery",
            "design_system_id": None,
            "runtime_state": {
                "runtime_contract": {
                    "discovery_brief": {"answers": {"output": "Deck"}},
                },
                "user_interaction": {
                    "kind": "design_system_picker",
                    "request_id": "design-system:conv-1:def",
                    "status": "pending",
                    "schema": {"title": "Choose", "fields": []},
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "design-system:conv-1:def",
                "answer": "Design",
                "answers": {"design_system_id": "aurora"},
                "display_label": "Aurora",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:design-system",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["design_system_id"] == "aurora"
    assert result.next_steps[0].step_type == STEP_PLAN_LIFECYCLE
    message, body = _interaction_submission_message(result)
    assert message.idempotency_key == "run:run-1:interaction-submission:design-system:conv-1:def"
    assert body["kind"] == "design_system_picker"
    assert body["answers"]["design_system_id"] == "aurora"


@pytest.mark.asyncio
async def test_apply_ask_user_during_execution_resumes_context_session(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "spreadsheet",
            "skill_id": "xlsx",
            "phase": "executing",
            "plan_state": {"title": "Existing plan"},
            "runtime_state": {
                "user_interaction": {
                    "kind": "ask_user",
                    "request_id": "ask-user:conv-1:abc",
                    "resume_turn": 7,
                    "status": "pending",
                    "question": "Continue?",
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ask-user:conv-1:abc",
                "answer": "continue",
                "display_label": "Continue",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ask-user",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "executing"
    assert result.runtime_patch["activity"] == "executing"
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["turn"] == 7
    _, body = _interaction_submission_message(result)
    assert body["kind"] == "ask_user"
    assert body["request_id"] == "ask-user:conv-1:abc"
    assert body["question"] == "Continue?"
    assert result.next_steps[0].idempotency_key == (
        "run:run-1:step:prepare_context_session:after-interaction:ask-user:conv-1:abc"
    )


def test_apply_ask_user_during_initial_planning_resumes_plan_update(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "spreadsheet",
            "skill_id": "xlsx",
            "phase": "planning",
            "runtime_state": {
                "runtime_contract": {
                    "active_skill_context": {"skill_id": "xlsx"},
                },
                "user_interaction": {
                    "kind": "ask_user",
                    "request_id": "ask-user:conv-1:abc",
                    "status": "pending",
                    "question": "Need more detail?",
                    "schema": {
                        "title": "Need more detail?",
                        "questions": [{"id": "brand_name", "type": "input"}],
                    },
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ask-user:conv-1:abc",
                "answer": '{"brand_name":{"type":"input","value":"Acme","label":"Acme"}}',
                "answers": {"brand_name": {"type": "input", "value": "Acme", "label": "Acme"}},
                "display_label": "Acme",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ask-user",
    )

    result = asyncio.run(_apply_user_input(step, _Gateway()))  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["phase"] == "planning"
    assert result.runtime_patch["run_state"] == "planning"
    assert result.runtime_patch["activity"] == "planning_outline"
    contract = result.runtime_patch["runtime_contract"]
    assert contract["active_skill_context"] == {"skill_id": "xlsx"}
    submission = contract["ask_user_answer_map"]["ask-user:conv-1:abc"]
    assert submission["title"] == "Need more detail?"
    assert submission["question_ids"] == ["brand_name"]
    assert submission["answers"]["brand_name"]["value"] == "Acme"
    _, body = _interaction_submission_message(result)
    assert body["schema"]["questions"][0]["id"] == "brand_name"
    assert body["answers"]["brand_name"]["value"] == "Acme"
    assert result.next_steps[0].step_type == STEP_PLAN_LIFECYCLE
    assert result.next_steps[0].input["kind"] == "resume_interaction"
    assert result.next_steps[0].idempotency_key == (
        "run:run-1:step:plan_lifecycle:after-interaction:ask-user:conv-1:abc"
    )


@pytest.mark.asyncio
async def test_apply_ask_user_canvas_submission_resumes_execution_even_if_phase_is_planning(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-canvas",
            "runtime_profile": "canvas",
            "artifact_mode": "web",
            "phase": "planning",
            "runtime_state": {
                "user_interaction": {
                    "kind": "ask_user",
                    "request_id": "ask-user:conv-canvas:abc",
                    "resume_turn": 3,
                    "status": "pending",
                    "question": "Continue?",
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-canvas",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ask-user:conv-canvas:abc",
                "answer": "continue",
                "display_label": "Continue",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ask-user",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["phase"] == "executing"
    assert result.runtime_patch["run_state"] == "executing"
    assert result.runtime_patch["activity"] == "executing"
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["turn"] == 3
    assert result.next_steps[0].idempotency_key == (
        "run:run-1:step:prepare_context_session:after-interaction:ask-user:conv-canvas:abc"
    )


@pytest.mark.asyncio
async def test_apply_ask_user_during_plan_revision_resumes_revising_context_session(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "spreadsheet",
            "skill_id": "xlsx",
            "phase": "revising_plan",
            "plan_state": {"title": "Workbook"},
            "runtime_state": {
                "user_interaction": {
                    "kind": "ask_user",
                    "request_id": "ask-user:conv-1:abc",
                    "status": "pending",
                    "question": "Revise which sheet?",
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ask-user:conv-1:abc",
                "answer": "sheet 2",
                "display_label": "Sheet 2",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ask-user",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["phase"] == "revising_plan"
    assert result.runtime_patch["run_state"] == "revising_plan"
    assert result.runtime_patch["activity"] == "planning_outline"
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION


@pytest.mark.asyncio
async def test_persist_tool_result_enqueues_next_tool_before_next_model_turn():
    tool_calls = [
        {"id": "call-1", "name": "first", "arguments": "{}"},
        {"id": "call-2", "name": "second", "arguments": "{}"},
    ]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [_tool_outcome(index=0, tool_name="first", call_id="call-1")],
            "outcome_index": 0,
        }
    )
    gateway = _Gateway()

    result = await _persist_tool_result(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_EXECUTE_TOOL
    assert result.next_steps[0].input["segment_start_index"] == 1
    assert "tool_index" not in result.next_steps[0].input
    assert "tool_call" not in result.next_steps[0].input
    assert result.messages[0].metadata["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_persist_tool_result_enqueues_next_segment_outcome_before_next_segment():
    tool_calls = [
        {"id": "call-1", "name": "read_file", "arguments": "{}"},
        {"id": "call-2", "name": "grep_files", "arguments": "{}"},
        {"id": "call-3", "name": "write_file", "arguments": "{}"},
    ]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 2,
            "outcomes": [
                _tool_outcome(index=0, tool_name="read_file", call_id="call-1", output="read ok"),
                _tool_outcome(index=1, tool_name="grep_files", call_id="call-2", output="grep ok"),
            ],
            "outcome_index": 0,
        }
    )
    gateway = _Gateway()

    result = await _persist_tool_result(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PERSIST_TOOL_RESULT
    assert result.next_steps[0].input["outcome_index"] == 1
    assert result.next_steps[0].input["segment_start_index"] == 0
    assert result.messages[0].metadata["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_persist_tool_result_enqueues_next_segment_after_segment_outcomes_complete():
    tool_calls = [
        {"id": "call-1", "name": "read_file", "arguments": "{}"},
        {"id": "call-2", "name": "write_file", "arguments": "{}"},
    ]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 3,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [_tool_outcome(index=0, tool_name="read_file", call_id="call-1")],
            "outcome_index": 0,
        }
    )
    gateway = _Gateway()

    result = await _persist_tool_result(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_EXECUTE_TOOL
    assert result.next_steps[0].input["segment_start_index"] == 1
    assert "tool_call" not in result.next_steps[0].input
    assert "tool_index" not in result.next_steps[0].input


@pytest.mark.asyncio
async def test_persist_tool_result_enqueues_render_context_after_last_tool():
    tool_calls = [{"id": "call-1", "name": "first", "arguments": "{}"}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 3,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [_tool_outcome(index=0, tool_name="first", call_id="call-1")],
            "outcome_index": 0,
        }
    )
    gateway = _Gateway()

    result = await _persist_tool_result(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 4
    assert result.messages[0].metadata["model_visible"] is True


@pytest.mark.asyncio
async def test_persist_tool_result_clean_publish_uses_unique_finalize_key():
    # A clean (shipped) publish must enqueue a finalize step keyed per publish call
    # (turn + call_id) so a later publish in the same run cannot be deduped away.
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 5,
            "tool_calls": [{"id": "call-pub", "name": "publish_output", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="publish_output",
                    call_id="call-pub",
                    metadata={"critique_publish_status": "shipped"},
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_FINALIZE
    assert result.next_steps[0].input["reason"] == "artifact_published"
    assert result.next_steps[0].idempotency_key == "run:run-1:step:finalize:after-publish-output:5:call-pub"


@pytest.mark.asyncio
async def test_persist_tool_result_failopen_publish_continues_instead_of_finalizing():
    # A degraded/fail-open publish (review crashed, published as fallback) must NOT
    # be treated as a clean terminal ship — hand control back to the model instead of
    # summarizing/ending the run on an unvalidated artifact.
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 5,
            "tool_calls": [{"id": "call-pub", "name": "publish_output", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="publish_output",
                    call_id="call-pub",
                    metadata={"critique_publish_status": "degraded"},
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 6
    assert result.activity_summary.get("publish_fail_open_continue") is True


def test_persist_read_file_result_keeps_full_window_model_visible():
    read_output = "[read_file window: lines 1-80 of 80]\n" + "\n".join(
        f"schema line {index}: field_{index}" for index in range(80)
    )
    outcome = _tool_outcome(index=0, tool_name="read_file", call_id="call-1", output=read_output)
    outcome["result_payload"]["review"] = {
        "summary": "read_file returned 80 lines",
        "output_excerpt": "short preview",
    }
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 3,
            "tool_calls": [{"id": "call-1", "name": "read_file", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [outcome],
            "outcome_index": 0,
        }
    )

    result = asyncio.run(_persist_tool_result(step, _Gateway()))  # type: ignore[arg-type]

    model_payload = json.loads(result.messages[0].content)
    assert model_payload["status"] == "completed"
    # Full raw output now reaches the model verbatim (no excerpt-only view).
    assert model_payload["output"] == read_output
    assert "output_excerpt" not in model_payload


def test_persist_grep_result_sends_full_output_to_model():
    grep_output = json.dumps(
        {"mode": "content", "numFiles": 2, "content": "src/a.py:1:def f()\nsrc/b.py:9:def g()"},
        ensure_ascii=False,
    )
    outcome = _tool_outcome(index=0, tool_name="grep_files", call_id="call-1", output=grep_output)
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 3,
            "tool_calls": [{"id": "call-1", "name": "grep_files", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [outcome],
            "outcome_index": 0,
        }
    )

    result = asyncio.run(_persist_tool_result(step, _Gateway()))  # type: ignore[arg-type]

    model_payload = json.loads(result.messages[0].content)
    # Raw grep output (incl. matched lines) now reaches the model verbatim.
    assert model_payload["output"] == grep_output
    assert "def f()" in model_payload["output"]
    assert "output_truncated" not in model_payload


def test_persist_media_tool_result_hides_processing_payload_from_model():
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="generate_image",
                    call_id="call-1",
                    output=json.dumps(
                        {
                            "task_id": "101",
                            "artifact_ref": "artifact_ref:abc123",
                            "status": "processing",
                            "result_url": None,
                        },
                        ensure_ascii=False,
                    ),
                    metadata={
                        "task_id": "101",
                        "artifact_ref": "artifact_ref:abc123",
                        "media_type": "image",
                        "status": "processing",
                        "result_url": None,
                    },
                )
            ],
            "outcome_index": 0,
        }
    )

    result = asyncio.run(_persist_tool_result(step, _Gateway()))  # type: ignore[arg-type]

    model_message = result.messages[0]
    model_payload = json.loads(model_message.content)
    assert model_message.metadata["model_visible"] is False
    assert model_payload["status"] == "completed"
    assert model_payload["artifact_ref"] == "artifact_ref:abc123"
    assert "processing" not in json.dumps(model_payload, ensure_ascii=False)

    media_event = next(event for event in result.events if event.event_type == "presentation.block.complete")
    assert media_event.payload["status"] == "processing"
    assert media_event.payload["payload"]["status"] == "processing"


def test_persist_media_tool_validation_failure_does_not_render_media_card():
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="generate_image",
                    call_id="call-1",
                    output=(
                        "Invalid parameters: 1 validation error for GenerateImageParams "
                        "prompt Field required"
                    ),
                    is_error=True,
                    metadata={"failure_kind": "invalid_parameters"},
                )
            ],
            "outcome_index": 0,
        }
    )

    result = asyncio.run(_persist_tool_result(step, _Gateway()))  # type: ignore[arg-type]

    assert [event.event_type for event in result.events] == ["tool_result"]
    model_message = result.messages[0]
    assert model_message.metadata["model_visible"] is True
    model_payload = json.loads(model_message.content)
    assert model_payload["status"] == "failed"
    assert "Invalid parameters" in model_payload["output"]


def test_persist_duplicate_generation_reuse_does_not_render_media_card():
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="generate_image",
                    call_id="call-1",
                    output=json.dumps(
                        {
                            "task_id": "101",
                            "artifact_ref": "artifact_ref:abc123",
                            "status": "processing",
                            "duplicate_generation_blocked": True,
                            "emit_media_card": False,
                        },
                        ensure_ascii=False,
                    ),
                    metadata={
                        "task_id": "101",
                        "artifact_ref": "artifact_ref:abc123",
                        "media_type": "image",
                        "status": "processing",
                        "duplicate_generation_blocked": True,
                        "emit_media_card": False,
                    },
                )
            ],
            "outcome_index": 0,
        }
    )

    result = asyncio.run(_persist_tool_result(step, _Gateway()))  # type: ignore[arg-type]

    assert [event.event_type for event in result.events] == ["tool_result"]
    model_message = result.messages[0]
    assert model_message.metadata["model_visible"] is False
    assert model_message.metadata["suppress_model_context"] is True
    model_payload = json.loads(model_message.content)
    assert model_payload["status"] == "completed"
    assert model_payload["artifact_ref"] == "artifact_ref:abc123"
    assert result.next_steps[0].step_type == STEP_FINALIZE
    assert result.next_steps[0].input["reason"] == "duplicate_media_generation_reuse"


@pytest.mark.asyncio
async def test_persist_failed_web_search_card_keeps_original_search_args():
    outcome = _tool_outcome(
        index=0,
        tool_name="web_search",
        call_id="call-image",
        output="Tool error: ConnectError: tls handshake eof",
        is_error=True,
        metadata={"query": None, "search_type": "", "results": []},
    )
    outcome["raw_args"] = {
        "query": "Friedrich Nietzsche photo portrait 尼采 照片",
        "num_results": 5,
        "search_type": "image",
    }
    outcome["result_payload"]["args"] = dict(outcome["raw_args"])
    step = _step(
        input_payload={
            "payload": {"content": "再搜索下尼采的照片"},
            "turn": 2,
            "tool_calls": [
                {
                    "id": "call-image",
                    "name": "web_search",
                    "arguments": dict(outcome["raw_args"]),
                }
            ],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [outcome],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    web_search_event = next(event for event in result.events if event.event_type == "presentation.block.complete")
    assert web_search_event.payload["block"]["ui_kind"] == "web_search_card"
    assert web_search_event.payload["status"] == "failed"
    assert web_search_event.payload["payload"]["status"] == "failed"
    assert web_search_event.payload["payload"]["search_type"] == "image"
    assert web_search_event.payload["payload"]["query"] == "Friedrich Nietzsche photo portrait 尼采 照片"
    assert web_search_event.payload["payload"]["results"] == []


@pytest.mark.asyncio
async def test_plan_lifecycle_start_enqueues_context_session(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "phase": "planning_ready",
            "plan_state": {
                "outline_state": {
                    "outline_id": "outline-1",
                    "version": 1,
                    "artifact_type": "spreadsheet",
                    "title": "Workbook",
                    "items": [{"id": "sheet-1", "title": "Sheet", "summary": "Build sheet"}],
                },
                "execution_state": {
                    "status": "planning_ready",
                    "steps": [{"id": "step-1", "title": "Build sheet", "status": "pending"}],
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-plan",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="plan_lifecycle",
        status="running",
        input={
            "kind": RUN_KIND_START_PLAN,
            "payload": {
                "content": "start",
                "user_message_event": {
                    "id": "plan-execution-approved",
                    "role": "user",
                    "content": "执行计划",
                    "created_at": "2026-06-04T00:00:00+00:00",
                },
            },
            "turn": 2,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:update-plan",
    )

    result = await _plan_lifecycle(step, _Gateway())  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["turn"] == 2
    user_events = [event for event in result.events if event.event_type == "user_message"]
    assert len(user_events) == 1
    assert user_events[0].payload["content"] == "执行计划"
    assert user_events[0].idempotency_key == "run:run-1:user-message"


@pytest.mark.asyncio
async def test_plan_lifecycle_revision_enqueues_revising_context_session(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "phase": "planning_ready",
            "plan_state": {
                "outline_state": {
                    "outline_id": "outline-1",
                    "version": 1,
                    "artifact_type": "spreadsheet",
                    "title": "Workbook",
                    "items": [{"id": "sheet-1", "title": "Sheet", "summary": "Build sheet"}],
                },
                "execution_state": {
                    "status": "planning_ready",
                    "steps": [{"id": "step-1", "title": "Build sheet", "status": "pending"}],
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-plan",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="request_plan_approval",
        status="running",
        input={
            "kind": RUN_KIND_REVISE_PLAN,
            "payload": {"instruction": "make it shorter"},
            "turn": 2,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:update-plan-revise",
    )

    result = await _plan_lifecycle(step, _Gateway())  # type: ignore[arg-type]

    assert result.runtime_patch["phase"] == "revising_plan"
    assert result.runtime_patch["run_state"] == "revising_plan"
    assert result.runtime_patch["activity"] == "planning_outline"
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION


def test_plan_lifecycle_after_ask_user_planning_resume_uses_interaction_context_key(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "slides",
            "skill_id": "html-ppt",
            "phase": "planning",
            "turn_route": {
                "source": "interaction_submitted",
                "activity": "planning_outline",
                "route_kind": "artifact_creation",
                "requires_plan_gate": True,
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-plan-after-ask-user",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="request_plan_approval",
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "call_ask_template",
                "answer": '{"starting_point":"tech-sharing"}',
                "display_label": "tech-sharing",
            },
            "turn": 1,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:request_plan_approval:after-interaction:call_ask_template",
    )

    result = asyncio.run(_plan_lifecycle(step, _Gateway()))  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["turn"] == 1
    assert result.next_steps[0].idempotency_key == (
        "run:run-1:step:prepare_context_session:after-interaction:call_ask_template"
    )


def test_plan_lifecycle_after_ask_user_planning_resume_without_kind_uses_interaction_context_key(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "artifact_mode": "slides",
            "skill_id": "html-ppt",
            "phase": "planning",
            "turn_route": {
                "source": "interaction_submitted",
                "activity": "planning_outline",
                "route_kind": "artifact_creation",
                "requires_plan_gate": True,
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-plan-after-ask-user",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="request_plan_approval",
        status="running",
        input={
            "payload": {
                "request_id": "call_ask_template",
                "answer": '{"starting_template":{"value":"tech_sharing"}}',
                "display_label": "tech-sharing",
            },
            "turn": 1,
        },
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:request_plan_approval:after-interaction:call_ask_template",
    )

    result = asyncio.run(_plan_lifecycle(step, _Gateway()))  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["turn"] == 1
    assert result.next_steps[0].idempotency_key == (
        "run:run-1:step:prepare_context_session:after-plan"
    )


@pytest.mark.asyncio
async def test_persist_plan_lifecycle_waits_for_user_when_plan_gate_opens(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {"id": "conv-1", "phase": "planning", "turn_route": {"requires_plan_gate": True}}

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    tool_calls = [{"id": "call-1", "name": "request_plan_approval", "arguments": "{}"}]
    plan_state = {
        "title": "Plan",
        "summary": "Summary",
        "steps": [{"id": "step-1", "title": "Step", "status": "in_progress"}],
        "outline_state": {
            "outline_id": "outline-1",
            "version": 1,
            "artifact_type": "spreadsheet",
            "title": "Sheet",
            "items": [{"id": "item-1", "title": "Sheet", "summary": "Build sheet"}],
        },
        "execution_state": {
            "steps": [{"id": "step-1", "title": "Step", "status": "in_progress"}],
        },
    }
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="request_plan_approval",
                    call_id="call-1",
                    metadata={"plan_state": plan_state},
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_WAITING_INPUT
    assert result.next_steps == []
    assert result.runtime_patch["runtime_status"] == "waiting_input"
    assert result.runtime_patch["phase"] == "planning_ready"
    assert result.activity_summary["awaiting_user"] is True


@pytest.mark.asyncio
async def test_persist_ask_user_waits_for_user_and_emits_interaction():
    tool_calls = [{"id": "call-ask", "name": "ask_user", "arguments": "{}"}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="ask_user",
                    call_id="call-ask",
                    output="Approve?",
                    metadata={
                        "type": "ask_user",
                        "question": "Approve?",
                        "schema": {
                            "title": "Approve?",
                            "submit_label": "Start",
                            "fields": [
                                {
                                    "id": "approval",
                                    "label": "Approval",
                                    "type": "radio",
                                    "required": True,
                                    "options": [{"label": "Start", "value": "start"}],
                                }
                            ],
                        },
                    },
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_WAITING_INPUT
    assert result.next_steps == []
    assert result.runtime_patch["runtime_status"] == "waiting_input"
    assert result.runtime_patch["user_interaction"]["request_id"] == "call-ask"
    assert result.runtime_patch["user_interaction"]["resume_turn"] == 1
    assert [event.event_type for event in result.events] == [
        "tool_result",
        "presentation.block.upsert",
        "turn_completed",
    ]
    interaction_event = result.events[1]
    assert interaction_event.payload["block"]["ui_kind"] == "interaction_form"
    assert interaction_event.payload["payload"]["status"] == "pending"
    assert result.events[-1].payload["status"] == "waiting_input"
    assert result.events[-1].payload["runtime_snapshot"]["user_interaction"]["request_id"] == "call-ask"


@pytest.mark.asyncio
async def test_persist_ecommerce_tool_interaction_waits_for_user():
    step = _step(
        input_payload={
            "payload": {"content": "make product image"},
            "turn": 0,
            "tool_calls": [{"id": "call-ecom", "name": "prepare_ecommerce_generation", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="prepare_ecommerce_generation",
                    call_id="call-ecom",
                    output='{"kind":"ecommerce_generation_options"}',
                    metadata={
                        "type": "interaction",
                        "interaction": {
                            "kind": "ecommerce_generation_options",
                            "question": "商品图生成配置",
                            "defaults": {
                                "generation_count": 4,
                                "generation_count_min": 1,
                                "generation_count_max": 6,
                            },
                        },
                    },
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_WAITING_INPUT
    interaction = result.runtime_patch["user_interaction"]
    assert interaction["kind"] == "ecommerce_generation_options"
    assert interaction["request_id"] == "call-ecom"
    assert interaction["defaults"]["generation_count"] == 4
    assert result.events[1].payload["payload"]["kind"] == "ecommerce_generation_options"


@pytest.mark.asyncio
async def test_apply_ecommerce_generation_options_cancel_does_not_create_generation_context(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-product",
            "runtime_profile": "canvas",
            "artifact_mode": "image",
            "skill_id": "menswear-ecommerce-hero",
            "phase": "executing",
            "runtime_state": {
                "runtime_contract": {"active_skill_context": {"skill_id": "menswear-ecommerce-hero"}},
                "user_interaction": {
                    "kind": "ecommerce_generation_options",
                    "request_id": "ecom-options:req",
                    "resume_turn": 3,
                    "status": "pending",
                    "question": "商品图生成配置",
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ecom-options:req",
                "answer": "cancel",
                "display_label": "取消",
                "answers": {
                    "action": "cancel",
                },
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ecom-analysis",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    workflow = result.runtime_patch["runtime_contract"]["ecommerce_product_workflow"]
    assert workflow["last_action"] == "cancel"
    _, body = _interaction_submission_message(result)
    assert body["kind"] == "ecommerce_generation_options"
    assert body["action"] == "cancel"


@pytest.mark.asyncio
async def test_apply_ecommerce_generation_options_confirm_adds_model_visible_context(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-product",
            "runtime_profile": "canvas",
            "artifact_mode": "image",
            "skill_id": "menswear-ecommerce-hero",
            "phase": "executing",
            "runtime_state": {
                "runtime_contract": {"active_skill_context": {"skill_id": "menswear-ecommerce-hero"}},
                "user_interaction": {
                    "kind": "ecommerce_generation_options",
                    "request_id": "ecom-options:req",
                    "resume_turn": 5,
                    "status": "pending",
                    "question": "商品图生成配置",
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_CONTEXT_TEMPLATE",
        "{图片分类提示词}\n{图片风格提示词}\n{平台规则提示词}\n{人物参考图提示词}\n{人物参考图}\n{背景参考图提示词}\n{背景参考图}\n{其他商品主图参考图提示词}\n{其他商品参考图}\n{负面约束提示词}\n生成商品图数量：{生成商品图数量}\n{用户需求}",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_PLATFORM_RULE_PROMPT",
        "平台规则",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_MODEL_REFERENCE_PROMPT",
        "人物规则",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_BACKGROUND_REFERENCE_PROMPT",
        "背景规则",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_OTHER_MAIN_IMAGE_REFERENCE_PROMPT",
        "其他主图规则",
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_NEGATIVE_PROMPT",
        "负面规则",
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ecom-options:req",
                "answer": "confirm",
                "display_label": "提交",
                "answers": {
                    "action": "confirm",
                    "category_id": 11,
                    "category_name": "夹克",
                    "category_prompt": "夹克分类提示词",
                    "style_id": 22,
                    "style_name": "都市通勤",
                    "style_prompt": "都市通勤风格提示词",
                    "enable_background_reference": True,
                    "background_reference_image_urls": ["artifact_ref:bg"],
                    "enable_model_reference": True,
                    "model_reference_image_urls": ["artifact_ref:model"],
                    "enable_other_main_image_reference": False,
                    "other_main_image_reference_image_urls": ["artifact_ref:ignored"],
                    "generation_count": 5,
                },
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ecom",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["turn"] == 5
    assert result.next_steps[0].idempotency_key.endswith(
        ":after-interaction:ecom-options:req"
    )
    contract = result.runtime_patch["runtime_contract"]
    workflow = contract["ecommerce_product_workflow"]
    assert workflow["last_action"] == "confirm"
    assert len(result.messages) == 2
    submission_message = result.messages[0]
    assert (submission_message.metadata or {})["agent_context_kind"] == "interaction_submission"
    body = json.loads(submission_message.content or "{}")
    assert body["kind"] == "ecommerce_generation_options"
    assert body["action"] == "confirm"
    assert body["category_name"] == "夹克"
    assert body["style_name"] == "都市通勤"
    context_message = result.messages[1]
    assert context_message.role == "user"
    assert (context_message.metadata or {})["agent_context_kind"] == "ecommerce_generation_context"
    assert (context_message.metadata or {})["model_visible"] is True
    assert (context_message.metadata or {})["ui_visible"] is False
    assert "夹克分类提示词" in (context_message.content or "")
    assert "都市通勤风格提示词" in (context_message.content or "")
    assert "背景规则" in (context_message.content or "")
    assert "artifact_ref:bg" in (context_message.content or "")
    assert "人物规则" in (context_message.content or "")
    assert "artifact_ref:model" in (context_message.content or "")
    assert "其他主图规则" not in (context_message.content or "")
    assert "artifact_ref:ignored" not in (context_message.content or "")
    assert "生成商品图数量：5" in (context_message.content or "")


@pytest.mark.asyncio
async def test_apply_ecommerce_options_confirm_uses_reference_gallery_taxonomy_prompts(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-product",
            "phase": "executing",
            "runtime_state": {
                "user_interaction": {
                    "kind": "ecommerce_generation_options",
                    "request_id": "ecom-options:req",
                    "status": "pending",
                    "resume_turn": 4,
                },
            },
        }

    async def _resolve_taxonomy_prompts(answers: dict):
        return {
            **answers,
            "category_name": "服务端夹克",
            "category_prompt": "服务端分类提示词",
            "style_name": "服务端通勤",
            "style_prompt": "服务端风格提示词",
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.resolve_ecommerce_taxonomy_prompts",
        _resolve_taxonomy_prompts,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.settings.ECOMMERCE_PRODUCT_IMAGE_CONTEXT_TEMPLATE",
        "{图片分类提示词}\n{图片风格提示词}\n生成商品图数量：{生成商品图数量}",
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-apply",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_APPLY_USER_INPUT,
        status="running",
        input={
            "kind": "resume_interaction",
            "payload": {
                "request_id": "ecom-options:req",
                "answer": "confirm",
                "display_label": "提交",
                "answers": {
                    "action": "confirm",
                    "category_id": 11,
                    "category_name": "前端夹克",
                    "category_prompt": "前端分类提示词",
                    "style_id": 22,
                    "style_name": "前端通勤",
                    "style_prompt": "前端风格提示词",
                    "generation_count": 4,
                },
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:apply_user_input:ecom",
    )

    result = await _apply_user_input(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert len(result.messages) == 2
    submission_body = json.loads(result.messages[0].content or "{}")
    assert submission_body["category_prompt"] == "服务端分类提示词"
    assert submission_body["style_prompt"] == "服务端风格提示词"
    context_content = result.messages[1].content or ""
    assert "服务端分类提示词" in context_content
    assert "服务端风格提示词" in context_content
    assert "前端分类提示词" not in context_content
    assert "前端风格提示词" not in context_content


@pytest.mark.asyncio
async def test_persist_plan_gate_blocked_tool_waits_without_next_step(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {"id": "conv-1", "phase": "planning_ready"}

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 2,
            "tool_calls": [{"id": "call-write", "name": "write_file", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="write_file",
                    call_id="call-write",
                    output="Plan approval is required",
                    is_error=True,
                    metadata={"plan_gate_blocked": True},
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_WAITING_INPUT
    assert result.next_steps == []
    assert result.runtime_patch["phase"] == "planning_ready"
    assert result.activity_summary["plan_gate_blocked"] is True


@pytest.mark.asyncio
async def test_prepare_skill_routes_planning_spreadsheet_to_discovery_schema(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {"id": "conv-1", "phase": "planning", "skill_id": "xlsx", "artifact_mode": "spreadsheet"}

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_skill", lambda _skill_id: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_artifact_family", lambda **_kwargs: "spreadsheet")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.prepare_active_skill_runtime_context",
        lambda **_kwargs: {
            "runtime_root": "skill",
            "active_skill_context": {"source_digest": "digest"},
            "staged_skill": {"id": "xlsx"},
        },
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-prepare",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_PREPARE_SKILL,
        status="running",
        input={
            "kind": "message",
            "payload": {
                "content": "生成一个表格",
                "user_message_event": {
                    "id": "user-msg-1",
                    "role": "user",
                    "content": "生成一个表格",
                    "attachments": [{"type": "image", "url": "https://example.test/a.png"}],
                    "created_at": "2026-06-04T00:00:00+00:00",
                },
                "message_metadata": {"skill_id": "xlsx"},
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:prepare_skill:0",
    )

    result = await _prepare_skill(step, _Gateway())  # type: ignore[arg-type]

    assert result.error is None
    assert result.next_steps[0].step_type == STEP_DISCOVERY_SCHEMA
    assert result.next_steps[0].input["artifact_family"] == "spreadsheet"
    assert result.messages == []
    assert len(result.events) == 1
    assert result.events[0].event_type == "user_message"
    assert result.events[0].idempotency_key == "run:run-1:user-message"
    assert result.events[0].payload["content"] == "生成一个表格"
    assert result.events[0].payload["metadata"] == {"skill_id": "xlsx"}
    assert result.events[0].payload["attachments"] == [{"type": "image", "url": "https://example.test/a.png"}]


@pytest.mark.asyncio
async def test_prepare_skill_routes_canvas_image_phase_to_context_session(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-canvas",
            "runtime_profile": "canvas",
            "project_id": 64,
            "phase": "executing",
            "skill_id": "design_workflow",
            "artifact_mode": "image",
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_skill", lambda _skill_id: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_artifact_family", lambda **_kwargs: "image")
    step = WorkflowStepRecord(
        id=1,
        step_id="step-prepare",
        run_id="run-1",
        conversation_id="conv-canvas",
        user_id=7,
        step_type=STEP_PREPARE_SKILL,
        status="running",
        input={"kind": "message", "payload": {"canvas": {"project_id": 64, "references": []}}},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:prepare_skill:0",
    )

    result = await _prepare_skill(step, _Gateway())  # type: ignore[arg-type]

    assert result.error is None
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert result.next_steps[0].input["payload"]["canvas"]["project_id"] == 64


@pytest.mark.asyncio
async def test_prepare_skill_routes_executing_phase_to_context_session(monkeypatch):
    async def _conversation(_user_id: int, _conversation_id: str):
        return {"id": "conv-1", "phase": "executing", "skill_id": "xlsx"}

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_skill", lambda _skill_id: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_artifact_family", lambda **_kwargs: "spreadsheet")
    step = WorkflowStepRecord(
        id=1,
        step_id="step-prepare",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_PREPARE_SKILL,
        status="running",
        input={"kind": "message", "payload": {}},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:prepare_skill:0",
    )

    result = await _prepare_skill(step, _Gateway())  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION


@pytest.mark.asyncio
async def test_prepare_skill_backfills_default_skill_for_artifact_execution(monkeypatch):
    updates: list[dict] = []

    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "phase": "executing",
            "skill_id": None,
            "resolved_skill_id": None,
            "skill_selection_mode": "auto",
            "turn_route": {
                "route_kind": "artifact_creation",
                "activity": "planning_outline",
                "requires_skill_selection": True,
            },
        }

    async def _update(_user_id: int, _conversation_id: str, **kwargs):
        updates.append(kwargs)
        return {"id": _conversation_id, **kwargs}

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.update_conversation_async", _update)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.default_skill_id_for_artifact_mode", lambda _mode: "web")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_skill", lambda skill_id: object() if skill_id == "web" else None)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_artifact_family", lambda **_kwargs: "web")
    step = WorkflowStepRecord(
        id=1,
        step_id="step-prepare",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_PREPARE_SKILL,
        status="running",
        input={"kind": "message", "payload": {}},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:prepare_skill:0",
    )

    result = await _prepare_skill(step, _Gateway())  # type: ignore[arg-type]

    assert result.error is None
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert updates == [
        {
            "skill_id": "web",
            "resolved_skill_id": "web",
            "skill_selection_mode": "auto",
            "skill_resolution_source": "deterministic_default",
            "last_skill_decision_reason": "Default skill required for plan-first artifact mode.",
            "last_skill_decision_confidence": 1.0,
        }
    ]


@pytest.mark.asyncio
async def test_prepare_skill_prefers_requested_canvas_skill_over_default_web(monkeypatch):
    updates: list[dict] = []

    async def _conversation(_user_id: int, _conversation_id: str):
        return {
            "id": "conv-1",
            "runtime_profile": "canvas",
            "artifact_mode": "web",
            "phase": "executing",
            "skill_id": None,
            "resolved_skill_id": None,
            "skill_selection_mode": "auto",
            "turn_route": {
                "route_kind": "workflow_continuation",
                "activity": "executing",
                "requires_skill_selection": False,
            },
        }

    async def _update(_user_id: int, _conversation_id: str, **kwargs):
        updates.append(kwargs)
        return {"id": _conversation_id, **kwargs}

    product_skill = SimpleNamespace(artifact_mode="image")

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", _conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.update_conversation_async", _update)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.default_skill_id_for_artifact_mode", lambda _mode: "web")
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.get_skill",
        lambda skill_id: product_skill if skill_id == "menswear-ecommerce-hero" else object() if skill_id == "web" else None,
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_artifact_family", lambda **_kwargs: "image")
    step = WorkflowStepRecord(
        id=1,
        step_id="step-prepare",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_PREPARE_SKILL,
        status="running",
        input={
            "kind": "message",
            "payload": {
                "skill_selection": {
                    "requested_skill_id": "menswear-ecommerce-hero",
                    "mode": "manual",
                }
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:prepare_skill:0",
    )

    result = await _prepare_skill(step, _Gateway())  # type: ignore[arg-type]

    assert result.error is None
    assert result.next_steps[0].step_type == STEP_PREPARE_CONTEXT_SESSION
    assert updates == [
        {
            "skill_id": "menswear-ecommerce-hero",
            "resolved_skill_id": "menswear-ecommerce-hero",
            "skill_selection_mode": "manual",
            "skill_resolution_source": "user_selected",
            "artifact_mode": "image",
        }
    ]


@pytest.mark.asyncio
async def test_render_context_restores_session_and_latest_checkpoint(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-render",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_RENDER_CONTEXT,
        status="running",
        input={"payload": {}, "turn": 4},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:render_context:4",
    )
    session = {"fingerprint": "fp", "system_prompt": "system", "tool_schemas": [], "model": "GPT-5.4"}
    seen: dict = {}
    provider_calls: list[dict] = []

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _Projector:
        def render(self, **kwargs):
            seen.update(kwargs)
            return {
                "turn_context": {"system": "system", "messages": [], "tools": [], "model": "GPT-5.4", "language": "zh"},
                "checkpoint": {
                    "version": 1,
                    "message_seq_end": 12,
                    "event_seq_end": 20,
                    "dynamic_context_digest": "digest",
                    "history_source": "full_history",
                },
                "diagnostics": {"message_count": 0, "tool_schema_count": 0, "static_context_hash": "hash"},
            }

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_runtime_snapshot(_run_id):
        return {"context_session": session}

    async def fake_latest_checkpoint(**_kwargs):
        return {"message_seq_end": 10, "event_seq_end": 19}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "model_preferences": {"multimodal_provider": "builtin"},
        }

    def fake_create_harness_model_provider(**kwargs):
        provider_calls.append(kwargs)
        return object()

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_latest_step_checkpoint_async", fake_latest_checkpoint)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.ContextProjector", lambda: _Projector())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", fake_create_harness_model_provider)

    gateway = _Gateway()
    result = await _render_context(step, gateway)  # type: ignore[arg-type]

    assert seen["context_session"] == session
    assert provider_calls == [{"multimodal_provider": "builtin"}]
    assert seen["previous_checkpoint"]["message_seq_end"] == 10
    assert seen["include_runtime_time"] is False
    assert gateway.checkpoints[0]["patch"]["message_seq_end"] == 12
    assert result.next_steps[0].step_type == "model_turn"
    assert result.events[0].event_type == "render_context_completed"


@pytest.mark.asyncio
async def test_render_context_keeps_current_user_message_out_of_direct_persist_path(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-render-user",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_RENDER_CONTEXT,
        status="running",
        input={
            "payload": {
                "content": "分析下这张图片",
                "user_message_event": {
                    "id": "user-msg-1",
                    "created_at": "2026-06-04T00:00:00+00:00",
                    "attachments": [{"type": "image", "url": "references/inputs/upload_001/source.jpg"}],
                },
            },
            "turn": 0,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:render_context:0",
    )
    session = {
        "fingerprint": "fp",
        "system_prompt": "stable system",
        "context_snapshot_blocks": [{"id": "state.plan", "content": "Plan state payload:\n{}"}],
        "turn_append_blocks": [],
        "tool_schemas": [],
        "model": "GPT-5.4",
        "language": "zh",
    }

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_runtime_snapshot(_run_id):
        return {"context_session": session}

    async def fake_latest_checkpoint(**_kwargs):
        return {}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "protocol_version": 2,
            "model_preferences": {"multimodal_provider": "builtin"},
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_latest_step_checkpoint_async", fake_latest_checkpoint)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.context_session.compact_if_needed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.assembler.load_messages",
        lambda *_args: [{"_seq": 1, "role": "assistant", "content": "ready"}],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.assembler.load_latest_boundary_v2",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.assembler.latest_conversation_event_sequence",
        lambda *_args: 5,
    )

    result = await _render_context(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert all(message.metadata.get("ui_visible") is False for message in result.messages)
    assert all(message.metadata.get("model_visible") is True for message in result.messages)
    assert [message.metadata["message_kind"] for message in result.messages] == [
        "agent_context",
        "agent_context",
        "agent_context",
    ]
    user_intent_messages = [
        message for message in result.messages if message.metadata.get("agent_context_kind") == "user_intent"
    ]
    assert len(user_intent_messages) == 1
    assert user_intent_messages[0].role == "user"
    assert user_intent_messages[0].content == "分析下这张图片"
    assert user_intent_messages[0].idempotency_key == "user-msg-1:agent-context:user-intent"
    turn_context_messages = result.next_steps[0].input["turn_context"]["messages"]
    current_user_message = turn_context_messages[-1]
    assert current_user_message["role"] == "user"
    assert current_user_message["content"].startswith("分析下这张图片")
    assert "references/inputs/upload_001/source.jpg" in current_user_message["content"]
    assert "analyze_image.image_url" in current_user_message["content"]
    assert current_user_message["metadata"]["idempotency_key"] == "user-msg-1"


@pytest.mark.asyncio
async def test_render_context_fails_on_context_session_fingerprint_mismatch(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-render",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_RENDER_CONTEXT,
        status="running",
        input={"payload": {}, "turn": 0},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:render_context:0",
    )

    async def fake_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "stale"}}

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (False, {}))

    result = await _render_context(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_FAILED
    assert result.error is not None
    assert result.error.error_type == "ContextSessionFingerprintMismatch"


@pytest.mark.asyncio
async def test_persist_tool_result_allows_control_tool_validation_failure_before_breaker(monkeypatch):
    async def _previous_failures(**_kwargs):
        return 1

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.count_consecutive_tool_validation_failures_async",
        _previous_failures,
    )
    tool_calls = [{"id": "call-1", "name": "request_plan_approval", "arguments": "{}"}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="request_plan_approval",
                    call_id="call-1",
                    output="Invalid parameters: bad payload",
                    is_error=True,
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT


@pytest.mark.asyncio
async def test_persist_tool_result_breaks_control_tool_validation_loop(monkeypatch):
    async def _previous_failures(**_kwargs):
        return 2

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.count_consecutive_tool_validation_failures_async",
        _previous_failures,
    )
    tool_calls = [{"id": "call-1", "name": "request_plan_approval", "arguments": "{}"}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="request_plan_approval",
                    call_id="call-1",
                    output="Invalid parameters: bad payload",
                    is_error=True,
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_FAILED
    assert result.next_steps == []
    assert result.runtime_patch["failure"]["error_type"] == "tool_validation_loop"
    assert result.events[-1].event_type == "turn_completed"
    assert result.events[-1].payload["status"] == "failed"
    assert result.events[-1].payload["error"]["summary"] == "request_plan_approval failed validation 3 consecutive times"


@pytest.mark.asyncio
async def test_execute_tool_recovers_completed_checkpoint_without_rerunning_tool(monkeypatch):
    recovered_outcome = {
        "tool_name": "generate_image",
        "call_id": "call-1",
        "status": "completed",
        "is_error": False,
        "result_payload": {"tool": "generate_image", "tool_call_id": "call-1", "output": "ok"},
        "prepared_runtime": {},
        "billing_breakdown": [],
        "timings": {},
    }
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
        },
        attempts=2,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:turn:0:tool-segment:0:execute",
        checkpoint={
            "tool_segment": {
                "completed": True,
                "segment_start_index": 0,
                "next_tool_index": 1,
                "outcomes": [recovered_outcome],
            }
        },
    )

    def _fail_runner():
        raise AssertionError("activity runner must not run when the tool already completed")

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.get_workflow_activity_runner",
        _fail_runner,
    )
    gateway = _Gateway()

    result = await _execute_tool(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PERSIST_TOOL_RESULT
    assert result.next_steps[0].input["outcomes"][0]["call_id"] == "call-1"
    assert result.next_steps[0].input["next_tool_index"] == 1
    assert gateway.checkpoints == []  # no checkpoint rewrite on recovery


@pytest.mark.asyncio
async def test_execute_tool_records_child_billing_with_function_label(monkeypatch):
    recovered_outcome = {
        "tool_name": "generate_image",
        "call_id": "call-1",
        "status": "completed",
        "is_error": False,
        "result_payload": {"tool": "generate_image", "tool_call_id": "call-1", "output": "ok"},
        "billing_breakdown": [
            {
                "category": "image_generation",
                "amount": 12,
                "detail": {"model_name": "seedream", "elapsed_ms": 1000},
            }
        ],
        "timings": {},
    }
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:turn:0:tool-segment:0:execute",
        checkpoint={
            "tool_segment": {
                "completed": True,
                "segment_start_index": 0,
                "next_tool_index": 1,
                "outcomes": [recovered_outcome],
            }
        },
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.get_conversation_async",
        lambda *_args, **_kwargs: {"id": "conv-1", "runtime_profile": "canvas", "skill_id": "design_workflow"},
    )

    gateway = _Gateway()
    await _execute_tool(step, gateway)  # type: ignore[arg-type]

    assert gateway.billings[0].task_type == "image_generation"
    assert gateway.billings[0].billing_label == "billing.labels.image_generate"


@pytest.mark.asyncio
async def test_execute_tool_skips_subagent_llm_billing_breakdown_replay(monkeypatch):
    recovered_outcome = {
        "tool_name": "publish_output",
        "call_id": "call-1",
        "status": "completed",
        "is_error": False,
        "result_payload": {"tool": "publish_output", "tool_call_id": "call-1", "output": "ok"},
        "billing_breakdown": [
            {
                "category": "multimodal",
                "amount": 3,
                "detail": {
                    "kind": "subagent_llm",
                    "model_name": "gpt-5.4",
                    "input_tokens": 100,
                    "output_tokens": 20,
                },
            },
            {
                "category": "image_generation",
                "amount": 12,
                "detail": {"model_name": "seedream", "elapsed_ms": 1000},
            },
        ],
        "timings": {},
    }
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "publish_output", "arguments": "{}"}],
            "segment_start_index": 0,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:turn:0:tool-segment:0:execute",
        checkpoint={
            "tool_segment": {
                "completed": True,
                "segment_start_index": 0,
                "next_tool_index": 1,
                "outcomes": [recovered_outcome],
            }
        },
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.get_conversation_async",
        lambda *_args, **_kwargs: {"id": "conv-1", "runtime_profile": "canvas", "skill_id": "design_workflow"},
    )

    gateway = _Gateway()
    await _execute_tool(step, gateway)  # type: ignore[arg-type]

    assert len(gateway.billings) == 1
    assert gateway.billings[0].task_type == "image_generation"


@pytest.mark.asyncio
async def test_execute_tool_skips_analyze_image_billing_breakdown_replay(monkeypatch):
    recovered_outcome = {
        "tool_name": "analyze_image",
        "call_id": "call-1",
        "status": "completed",
        "is_error": False,
        "result_payload": {"tool": "analyze_image", "tool_call_id": "call-1", "output": "ok"},
        "billing_breakdown": [
            {
                "category": "image_analysis",
                "amount": 8,
                "detail": {
                    "kind": "analyze_image",
                    "model_name": "gpt-5.4",
                    "provider_code": "ollama",
                    "input_tokens": 2902,
                    "output_tokens": 843,
                    "elapsed_ms": 19270,
                },
            }
        ],
        "timings": {},
    }
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "analyze_image", "arguments": "{}"}],
            "segment_start_index": 0,
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:turn:0:tool-segment:0:execute",
        checkpoint={
            "tool_segment": {
                "completed": True,
                "segment_start_index": 0,
                "next_tool_index": 1,
                "outcomes": [recovered_outcome],
            }
        },
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.get_conversation_async",
        lambda *_args, **_kwargs: {"id": "conv-1", "runtime_profile": "home"},
    )

    gateway = _Gateway()
    await _execute_tool(step, gateway)  # type: ignore[arg-type]

    assert gateway.billings == []


@pytest.mark.asyncio
async def test_execute_tool_uses_context_session_without_runtime_preparation(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-1", "name": "tool_a", "arguments": "{}"}],
            "segment_start_index": 0,
        },
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-1:execute",
    )

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _Registry:
        def classify_tool_call(self, _raw_call, absolute_index):
            return type(
                "Classification",
                (),
                {"is_concurrency_safe": False, "call_id": "call-1", "tool_name": "tool_a", "raw_args": {}, "parsed_args": None},
            )()

        async def execute(self, *_args):
            return type("ToolResult", (), {"output": "ok", "is_error": False, "metadata": {}})()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "language": "zh"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "language": "zh", "runtime_contract": {}}}


    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.critique_runtime_payload",
        lambda *, harness_run_id: None,
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})

    result = await _execute_tool(step, _Gateway())  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_PERSIST_TOOL_RESULT
    assert result.next_steps[0].input["outcomes"][0]["result_payload"]["output"] == "ok"


@pytest.mark.asyncio
async def test_execute_tool_media_card_uses_tool_message_scope(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-image", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
        },
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-image:execute",
    )

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _Registry:
        async def execute(self, *_args):
            return type(
                "ToolResult",
                (),
                {
                    "output": "ok",
                    "is_error": False,
                    "metadata": {"artifact_ref": "artifact_ref:abc", "status": "processing"},
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "language": "zh", "runtime_profile": "canvas"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "language": "zh", "runtime_contract": {}}}

    gateway = _Gateway()
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.critique_runtime_payload",
        lambda *, harness_run_id: None,
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})

    result = await _execute_tool(step, gateway)  # type: ignore[arg-type]

    outcome = result.next_steps[0].input["outcomes"][0]
    assert outcome["presentation_scope"]["message_key"] == "run:run-1:message:tool:0:call-image"
    assert outcome["presentation_order"] == 1


@pytest.mark.asyncio
async def test_persist_tool_result_media_card_uses_outcome_scope():
    step = _step(
        input_payload={
            "payload": {},
            "turn": 0,
            "tool_calls": [{"id": "call-image", "name": "generate_image", "arguments": "{}"}],
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="generate_image",
                    call_id="call-image",
                    metadata={"artifact_ref": "artifact_ref:abc", "status": "processing"},
                )
                | {
                    "presentation_scope": {
                        "message_key": "run:run-1:message:tool:0:call-image",
                        "parent_block_key": None,
                    },
                    "presentation_order": 1,
                }
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    media_event = next(event for event in result.events if event.event_type == "presentation.block.complete")
    assert media_event.payload["message_key"] == "run:run-1:message:tool:0:call-image"
    assert media_event.payload["message_key"] != "conv-1:run-1:assistant"
    assert media_event.payload["order"] == 1


def test_execute_tool_resolves_generation_artifact_dependencies_before_tool_run(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "analyze_image",
                    "arguments": {
                        "image_url": "artifact_ref:abc123",
                        "question": "describe it",
                    },
                }
            ],
            "segment_start_index": 0,
        },
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-1:execute",
    )
    executed_args = []
    reviewed_args = []

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _Registry:
        def classify_tool_call(self, _raw_call, absolute_index):
            return type(
                "Classification",
                (),
                {"is_concurrency_safe": False, "call_id": "call-1", "tool_name": "analyze_image", "raw_args": {}, "parsed_args": None},
            )()

        async def execute(self, _tool_name, args, _ctx):
            executed_args.append(dict(args))
            return type("ToolResult", (), {"output": "ok", "is_error": False, "metadata": {}})()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "language": "zh"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "language": "zh", "runtime_contract": {}}}

    async def fake_resolve_dependencies(_ctx, args, **_kwargs):
        assert args["image_url"] == "artifact_ref:abc123"
        return {**args, "image_url": "references/generated/generated_image_abc/original.png"}, None

    def fake_review(_tool_name, args, _result):
        reviewed_args.append(dict(args))
        return {"summary": "ok"}

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", fake_review)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve_dependencies,
    )

    async def run_case():
        return await _execute_tool(step, _Gateway())  # type: ignore[arg-type]

    result = asyncio.run(run_case())

    assert executed_args == [{"image_url": "references/generated/generated_image_abc/original.png", "question": "describe it"}]
    assert reviewed_args == executed_args
    outcome = result.next_steps[0].input["outcomes"][0]
    assert outcome["raw_args"] == executed_args[0]
    assert outcome["result_payload"]["args"] == executed_args[0]


def test_recent_media_generation_window_ignores_future_calls_in_same_assistant_message():
    messages = [
        {
            "_seq": 1,
            "role": "assistant",
            "tool_calls": [
                {"id": "call-read", "name": "list_files", "arguments": {}},
                {"id": "call-image", "name": "generate_image", "arguments": {}},
            ],
        }
    ]

    assert not _recent_tool_invocations_include_media_generation(
        messages,
        limit=5,
        exclude_call_id="call-read",
    )


@pytest.mark.asyncio
async def test_execute_tool_waits_for_recent_pending_media_before_sensitive_read(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.settings.HARNESS_MEDIA_BARRIER_RECENT_TOOL_WINDOW", 5)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-read:execute",
    )
    executed_args = []
    waited = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            executed_args.append(dict(args))
            return type("ToolResult", (), {"output": "ok", "is_error": False, "metadata": {}})()

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "language": "zh"}

    async def fake_wait(_ctx, **_kwargs):
        waited.append(True)
        return None

    async def fake_resolve(_ctx, args, **_kwargs):
        return args, None

    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.load_messages",
        lambda *_args: [
            {"_seq": 1, "role": "tool", "tool_name": "generate_image", "tool_call_id": "call-image"},
            {"_seq": 2, "role": "assistant", "tool_calls": [{"id": "call-read", "name": "list_files", "arguments": {}}]},
        ],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.wait_for_pending_conversation_media_artifacts",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve,
    )

    outcome = await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={"id": "call-read", "name": "list_files", "arguments": {}},
        absolute_tool_index=0,
        context_session={},
    )

    assert waited == [True]
    assert executed_args == [{}]
    assert outcome["result_payload"]["output"] == "ok"


@pytest.mark.asyncio
async def test_execute_tool_does_not_wait_for_media_generation_outside_recent_window(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.settings.HARNESS_MEDIA_BARRIER_RECENT_TOOL_WINDOW", 5)
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-read:execute",
    )
    waited = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            return type("ToolResult", (), {"output": json.dumps(args), "is_error": False, "metadata": {}})()

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "language": "zh"}

    async def fake_wait(_ctx, **_kwargs):
        waited.append(True)
        return None

    async def fake_resolve(_ctx, args, **_kwargs):
        return args, None

    recent_non_media = [
        {"_seq": index, "role": "tool", "tool_name": "read_file", "tool_call_id": f"call-read-{index}"}
        for index in range(2, 8)
    ]
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.load_messages",
        lambda *_args: [
            {"_seq": 1, "role": "tool", "tool_name": "generate_image", "tool_call_id": "call-image"},
            *recent_non_media,
            {"_seq": 8, "role": "assistant", "tool_calls": [{"id": "call-read", "name": "list_files", "arguments": {}}]},
        ],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.wait_for_pending_conversation_media_artifacts",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve,
    )

    await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={"id": "call-read", "name": "list_files", "arguments": {}},
        absolute_tool_index=0,
        context_session={},
    )

    assert waited == []


@pytest.mark.asyncio
async def test_execute_tool_prefers_explicit_artifact_dependency_over_recent_media_barrier(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-analyze:execute",
    )
    waited = []
    resolved_args = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            resolved_args.append(dict(args))
            return type("ToolResult", (), {"output": "ok", "is_error": False, "metadata": {}})()

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "language": "zh"}

    async def fake_wait(_ctx, **_kwargs):
        waited.append(True)
        return None

    async def fake_resolve(_ctx, args, **_kwargs):
        return {**args, "image_url": "references/generated/image.png"}, None

    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.load_messages",
        lambda *_args: [{"_seq": 1, "role": "tool", "tool_name": "generate_image", "tool_call_id": "call-image"}],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.wait_for_pending_conversation_media_artifacts",
        fake_wait,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve,
    )

    await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={
            "id": "call-analyze",
            "name": "analyze_image",
            "arguments": {"image_url": "artifact_ref:abc123", "question": "describe it"},
        },
        absolute_tool_index=0,
        context_session={},
    )

    assert waited == []
    assert resolved_args == [{"image_url": "references/generated/image.png", "question": "describe it"}]


@pytest.mark.asyncio
async def test_product_hero_generate_image_runs_generic_tool_without_review_card(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-image:execute",
    )
    executed = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            executed.append(args)
            return type(
                "ToolResult",
                (),
                {
                    "output": "ok",
                    "is_error": False,
                    "metadata": {"task_id": "task-1"},
                },
            )()

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-product", "language": "zh", "skill_id": "menswear-ecommerce-hero"}

    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "blocked"})

    outcome = await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={
            "id": "call-image",
            "name": "generate_image",
            "arguments": {
                "prompt": "生成港风天台商品图",
                "reference_image_urls": ["/api/v1/uploads/master.png"],
            },
        },
        absolute_tool_index=0,
        context_session={},
    )

    assert executed == [
        {
            "prompt": "生成港风天台商品图",
            "reference_image_urls": ["/api/v1/uploads/master.png"],
        }
    ]
    assert outcome["is_error"] is False
    assert outcome["result_payload"]["metadata"] == {"task_id": "task-1"}


@pytest.mark.asyncio
async def test_product_hero_generate_image_allows_any_generic_prompt_and_references(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-image:execute",
    )
    executed = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            executed.append(dict(args))
            return type("ToolResult", (), {"output": "ok", "is_error": False, "metadata": {}})()

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-product",
            "language": "zh",
            "skill_id": "menswear-ecommerce-hero",
        }

    async def fake_resolve(_ctx, args, **_kwargs):
        return args, None

    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve,
    )

    args = {
        "prompt": "生成港风天台商品图，保持商品不变。",
        "reference_image_urls": ["artifact_ref:left", "artifact_ref:master"],
    }
    outcome = await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={"id": "call-image", "name": "generate_image", "arguments": args},
        absolute_tool_index=0,
        context_session={},
    )

    assert outcome["is_error"] is False
    assert executed == [args]


@pytest.mark.asyncio
async def test_product_hero_generate_image_does_not_apply_ecommerce_policy_gate(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-image:execute",
    )
    executed = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            executed.append(dict(args))
            return type("ToolResult", (), {"output": "ok", "is_error": False, "metadata": {}})()

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-product",
            "language": "zh",
            "skill_id": "menswear-ecommerce-hero",
        }

    async def fake_resolve(_ctx, args, **_kwargs):
        return args, None

    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "blocked"})
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve,
    )

    outcome = await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={
            "id": "call-image",
            "name": "generate_image",
            "arguments": {
                "prompt": "生成正面白底商品图。",
                "reference_image_urls": ["artifact_ref:master"],
            },
        },
        absolute_tool_index=0,
        context_session={},
    )

    assert executed == [
        {
            "prompt": "生成正面白底商品图。",
            "reference_image_urls": ["artifact_ref:master"],
        }
    ]
    assert outcome["is_error"] is False


@pytest.mark.asyncio
async def test_product_hero_existing_image_edit_uses_generic_generate_image(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-product",
        user_id=7,
        step_type=STEP_EXECUTE_TOOL,
        status="running",
        input={},
        attempts=1,
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token=None,
        claim_expires_at=None,
        idempotency_key="run:run-1:tool:call-image:execute",
    )
    executed = []

    class _Registry:
        async def execute(self, _tool_name, args, _ctx):
            executed.append(dict(args))
            return type(
                "ToolResult",
                (),
                {
                    "output": "ok",
                    "is_error": False,
                    "metadata": {"task_id": "task-edit"},
                },
            )()

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-product", "language": "zh", "skill_id": "menswear-ecommerce-hero"}

    async def fake_resolve(_ctx, args, **_kwargs):
        return args, None

    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.create_harness_registry", lambda **_kwargs: _Registry())
    monkeypatch.setattr("app.services.agent_harness.workflow.tool_execution.review_tool_result", lambda *_args: {"summary": "ok"})
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.tool_execution.generation_store.resolve_artifact_dependencies",
        fake_resolve,
    )

    args = {
        "prompt": "把当前图背景调白，商品保持不变。",
        "reference_image_urls": ["artifact_ref:last-image"],
    }
    outcome = await execute_tool_invocation(
        step=step,
        gateway=_Gateway(),
        activity_gateway=_Gateway(),
        scheduler_loop=asyncio.get_running_loop(),
        payload={},
        turn=0,
        tool_call={"id": "call-image", "name": "generate_image", "arguments": args},
        absolute_tool_index=0,
        context_session={},
    )

    assert outcome["is_error"] is False
    assert executed == [args]
    assert outcome["result_payload"]["metadata"] == {"task_id": "task-edit"}


@pytest.mark.asyncio
async def test_model_turn_recovers_completed_checkpoint_without_calling_provider(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", False)
    message_id = "run:run-1:message:assistant:0:attempt:1"
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={"payload": {}, "turn": 0},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
        checkpoint={"model_turn": {"completed": True}, "stream": {"message_id": message_id}},
    )
    gateway = _Gateway()
    gateway.messages[message_id] = {"id": message_id, "role": "assistant", "content": "done", "tool_calls": []}

    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_FINALIZE
    assert result.next_steps[0].input["turn"] == 0
    assert result.next_steps[0].idempotency_key == "run:run-1:step:finalize:0:model_turn_completed"
    assert result.events[0].event_type == "presentation.block.complete"
    assert result.activity_summary["recovered_from_checkpoint"] is True


def test_finalize_step_idempotency_key_separates_repeated_model_turns():
    first_key = _finalize_step_idempotency_key("run-1", turn=0, reason="model_turn_completed")
    recovery_key = _finalize_step_idempotency_key("run-1", turn=2, reason="model_turn_completed")

    assert first_key == "run:run-1:step:finalize:0:model_turn_completed"
    assert recovery_key == "run:run-1:step:finalize:2:model_turn_completed"
    assert first_key != recovery_key


@pytest.mark.asyncio
async def test_model_turn_records_multimodal_billing_without_agent_runtime_usage_log(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "hello"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()
    billing_calls: list[dict] = []
    provider_calls: list[dict] = []

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": "done",
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                    "elapsed_ms": 11700,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_record_model_usage_billing(**kwargs):
        billing_calls.append(kwargs)
        return True

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "parent_usage_log_id": 123,
            "model_preferences": {"multimodal_provider": "builtin"},
        }

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [],
                "runtime_contract": {},
            }
        }

    def fail_runtime_preparation(**_kwargs):
        raise AssertionError("model_turn must consume render_context without runtime preparation")

    def fake_create_harness_model_provider(**kwargs):
        provider_calls.append(kwargs)
        return object()

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", fake_create_harness_model_provider)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.record_model_usage_billing",
        fake_record_model_usage_billing,
        raising=False,
    )

    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_FINALIZE
    assert provider_calls == [{"multimodal_provider": "builtin"}]
    assert gateway.activities[0]["activity_type"] == "model_turn"
    assert gateway.billings == []
    assert len(billing_calls) == 1
    assert billing_calls[0]["user_id"] == 7
    assert billing_calls[0]["model_name"] == "GPT-5.4"
    assert billing_calls[0]["usage"] == {"input_tokens": 12, "output_tokens": 3}
    assert billing_calls[0]["elapsed_ms"] == 11700
    assert billing_calls[0]["kind"] == "agent_llm"
    assert billing_calls[0]["category"] == "multimodal"
    assert billing_calls[0]["billing_key"] == "run:run-1:step:step-1:billing:model"


@pytest.mark.asyncio
async def test_model_turn_empty_response_fails_without_enqueueing_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-empty",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "build"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": "",
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                    "elapsed_ms": 900,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "runtime_profile": "home", "artifact_mode": "slides"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [],
                "runtime_contract": {},
            }
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.record_model_usage_billing", fake_record_model_usage_billing, raising=False)

    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_FAILED
    assert result.error is not None
    assert result.error.error_type == "EmptyModelResponse"
    assert result.next_steps == []
    assert result.runtime_patch["runtime_status"] == "failed"
    assert [event.event_type for event in result.events] == ["turn_completed"]
    assert result.events[0].payload["status"] == "failed"
    assert result.events[0].payload["error"]["error_type"] == "EmptyModelResponse"
    assert gateway.activities[0]["status"] == "failed"
    assert gateway.activities[0]["diagnostics"]["empty_model_response"] is True


@pytest.mark.asyncio
async def test_model_turn_planning_plain_text_without_tool_requeues_lifecycle_recovery(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-planning-question",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {"phase": "planning"},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "做一个落地页"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return SimpleNamespace(
                assistant_text="这里是普通规划说明，但没有调用生命周期工具。",
                tool_calls=[],
                finish_reason="stop",
                usage={"input_tokens": 12, "output_tokens": 6},
                elapsed_ms=900,
            )

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "phase": "planning", "runtime_profile": "home", "artifact_mode": "web"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "model": "GPT-5.4", "language": "zh", "tool_schemas": []}}

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.record_model_usage_billing", fake_record_model_usage_billing, raising=False)
    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.error is None
    assert result.runtime_patch["runtime_status"] == "running"
    assert result.runtime_patch["run_state"] == "planning"
    assert result.runtime_patch["activity"] == "planning_lifecycle_required"
    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 1
    assert result.next_steps[0].input["payload"]["_planning_lifecycle_recovery_attempts"] == 1
    assert "update_planning_draft" in result.next_steps[0].input["transient_messages"][0]["content"]


@pytest.mark.asyncio
async def test_model_turn_planning_plain_text_after_recovery_fails_without_finalizing(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-planning-question",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {"phase": "planning", "_planning_lifecycle_recovery_attempts": 1},
            "turn": 1,
            "turn_context": {
                "messages": [{"role": "user", "content": "系统提醒：请调用 lifecycle tool"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:1",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return SimpleNamespace(
                assistant_text="仍然只是普通规划说明。",
                tool_calls=[],
                finish_reason="stop",
                usage={"input_tokens": 12, "output_tokens": 6},
                elapsed_ms=900,
            )

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "phase": "planning", "runtime_profile": "home", "artifact_mode": "web"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "model": "GPT-5.4", "language": "zh", "tool_schemas": []}}

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.record_model_usage_billing", fake_record_model_usage_billing, raising=False)
    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_FAILED
    assert result.next_steps == []
    assert result.error is not None
    assert result.error.error_type == "PlanningLifecycleToolRequired"
    assert result.runtime_patch["runtime_status"] == "failed"
    assert result.events[-1].event_type == "turn_completed"
    assert result.events[-1].payload["status"] == "failed"
    assert result.events[-1].payload["error"]["error_type"] == "PlanningLifecycleToolRequired"


@pytest.mark.asyncio
async def test_model_turn_execution_unfinished_plan_without_tools_requeues_progress(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-execution-no-progress",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {"phase": "executing"},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "开始执行"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return SimpleNamespace(
                assistant_text="我先同步一下当前执行状态。",
                tool_calls=[],
                finish_reason="stop",
                usage={"input_tokens": 12, "output_tokens": 6},
                elapsed_ms=900,
            )

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        steps = [
            {"id": "step-1", "title": "Build page", "status": "in_progress"},
            {"id": "step-2", "title": "Publish", "status": "pending"},
        ]
        return {
            "id": "conv-1",
            "phase": "executing",
            "language": "zh",
            "runtime_profile": "home",
            "artifact_mode": "web",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {"outline_id": "outline-1", "title": "Landing page"},
                "execution_state": {"status": "in_progress", "steps": steps},
            },
            "outline_runtime": {
                "current_outline": {"outline_id": "outline-1", "title": "Landing page"},
                "execution_state": {"status": "in_progress", "steps": steps},
            },
        }

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "model": "GPT-5.4", "language": "zh", "tool_schemas": []}}

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.record_model_usage_billing", fake_record_model_usage_billing, raising=False)
    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.error is None
    assert result.runtime_patch["run_state"] == "rendering_context"
    assert result.runtime_patch["activity"] == "execution_progress_required"
    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 1
    assert result.next_steps[0].input["payload"]["_execution_no_progress_recovery_attempts"] == 1
    assert "不要等待用户再次批准" in result.next_steps[0].input["transient_messages"][0]["content"]
    assert all(next_step.step_type != STEP_FINALIZE for next_step in result.next_steps)
    assert result.activity_summary["execution_no_progress_recovery"] is True


@pytest.mark.asyncio
async def test_model_turn_invalid_artifact_block_continues_to_repair_turn(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "build"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "en",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": '<artifact type="text/html">summary only</artifact>',
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                    "elapsed_ms": 100,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "model": "GPT-5.4", "language": "en", "tool_schemas": []}}

    async def fake_capture_artifact_block(*_args, **_kwargs):
        return ArtifactCaptureResult(
            entry=None,
            title=None,
            manifest=None,
            replacement_text="Artifact capture failed; repair required.",
            error_text="<artifact-error>artifact body must be a complete standalone html document</artifact-error>",
        )

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.record_model_usage_billing", fake_record_model_usage_billing, raising=False)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_protocol_for_context", lambda _ctx: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.capture_artifact_block", fake_capture_artifact_block)

    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 1
    assert result.next_steps[0].input["payload"]["_artifact_repair_attempts"] == 1
    assert result.next_steps[0].input["transient_messages"][0]["content"].startswith("<artifact-error>")
    assert result.activity_summary["artifact_capture_error"] is True


@pytest.mark.asyncio
async def test_model_turn_artifact_repair_loop_stops_at_attempt_cap(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {"_artifact_repair_attempts": 3},
            "turn": 5,
            "turn_context": {
                "messages": [{"role": "user", "content": "build"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "en",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:5",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, **_kwargs):
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": '<artifact type="text/html">summary only</artifact>',
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                    "elapsed_ms": 100,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "runtime_profile": "home", "artifact_mode": "web"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {"context_session": {"fingerprint": "fp", "model": "GPT-5.4", "language": "en", "tool_schemas": []}}

    async def fake_capture_artifact_block(*_args, **_kwargs):
        return ArtifactCaptureResult(
            entry=None,
            title=None,
            manifest=None,
            replacement_text="Artifact capture failed; repair required.",
            error_text="<artifact-error>artifact body must be a complete standalone html document</artifact-error>",
        )

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_harness_multimodal_model", lambda _conversation: "GPT-5.4")
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.record_model_usage_billing", fake_record_model_usage_billing, raising=False)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.resolve_protocol_for_context", lambda _ctx: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.capture_artifact_block", fake_capture_artifact_block)
    result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    # At the cap the run must NOT spawn yet another repair render-context; it
    # finalizes instead so the turn cannot wedge in an infinite capture loop.
    assert result.next_steps[0].step_type == STEP_FINALIZE
    assert all(s.step_type != STEP_RENDER_CONTEXT for s in result.next_steps)


@pytest.mark.asyncio
async def test_finalize_emits_final_answer_and_refreshes_parent_usage():
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:0",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "final text"}

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert gateway.refreshed_statuses == ["success"]
    assert [event.event_type for event in result.events] == [
        "presentation.block.complete",
        "assistant_message_finalized",
        "turn_completed",
    ]
    assert result.events[0].payload["block"]["ui_kind"] == "text"
    assert result.events[0].payload["payload"]["message_kind"] == "final_answer"
    assert result.events[-1].payload["status"] == "completed"
    assert result.events[-1].payload["runtime_snapshot"]["runtime_status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_enqueues_system_publish_when_manifest_registered_but_unpublished(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"content": "hello"}, "turn": 5},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:0",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "final text"}
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.read_artifact_manifest",
        lambda _user_id, _conversation_id: {"entry": "deck/index.html", "kind": "deck"},
    )

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert gateway.refreshed_statuses == []
    assert result.runtime_patch["run_state"] == "waiting_tool"
    assert result.next_steps[0].step_type == STEP_EXECUTE_TOOL
    assert result.next_steps[0].idempotency_key == "run:run-1:system-publish-output:execute"
    assert result.next_steps[0].input["tool_calls"][0]["name"] == "publish_output"
    assert result.next_steps[0].input["tool_calls"][0]["id"] == "system_publish:run-1"
    assert result.next_steps[0].input["segment_start_index"] == 0
    assert "tool_call" not in result.next_steps[0].input
    assert "tool_index" not in result.next_steps[0].input


@pytest.mark.asyncio
async def test_finalize_prompts_model_to_register_artifact_when_manifest_missing(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    entry_path = (
        tmp_path
        / "users"
        / "7"
        / "conversations"
        / "conv-1"
        / "project"
        / "open-design-landing-prepared"
        / "index.html"
    )
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(
        "<!doctype html><html><body><main><h1>Landing page</h1></main></body></html>",
        encoding="utf-8",
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"artifact_mode": "web", "language": "zh"}, "turn": 5},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:0",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "final text"}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "title": "生成一个设计公司的落地页",
            "artifact_mode": "web",
            "language": "zh",
            "plan_state": {
                "user_plan": {
                    "artifact_type": "html",
                    "file_path": "project/open-design-landing-prepared/index.html",
                    "items": [
                        {
                            "title": "最终交付",
                            "artifact_ref": "project/open-design-landing-prepared/index.html",
                        }
                    ],
                }
            },
        }

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [{"name": "register_artifact"}, {"name": "publish_output"}],
                "runtime_contract": {},
            }
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.read_artifact_manifest", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert gateway.refreshed_statuses == []
    assert result.runtime_patch["activity"] == "pre_final_artifact_manifest_gate"
    assert result.next_steps[0].step_type == STEP_MODEL_TURN
    assert result.next_steps[0].idempotency_key == "run:run-1:pre-final-artifact-manifest:6"
    turn_context = result.next_steps[0].input["turn_context"]
    assert turn_context["tools"] == [{"name": "register_artifact"}, {"name": "publish_output"}]
    assert turn_context["model"] == "GPT-5.4"
    assert "register_artifact" in turn_context["messages"][0]["content"]
    assert 'entry="open-design-landing-prepared/index.html"' in turn_context["messages"][0]["content"]
    assert 'kind="html"' in turn_context["messages"][0]["content"]
    assert "publish_output" in turn_context["messages"][0]["content"]


@pytest.mark.asyncio
async def test_finalize_skips_manifest_gate_for_empty_prepared_entry(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    entry_path = (
        tmp_path
        / "users"
        / "7"
        / "conversations"
        / "conv-1"
        / "project"
        / "open-design-landing-prepared"
        / "index.html"
    )
    entry_path.parent.mkdir(parents=True, exist_ok=True)
    entry_path.write_text(
        "<!doctype html><html><head><meta charset=\"utf-8\"></head><body></body></html>",
        encoding="utf-8",
    )
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"artifact_mode": "web", "language": "zh"}, "turn": 5},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:5:model_turn_completed",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "缺少品牌资料，先确认方向。"}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "artifact_mode": "web",
            "language": "zh",
            "plan_state": {
                "user_plan": {
                    "artifact_type": "html",
                    "file_path": "project/open-design-landing-prepared/index.html",
                }
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.read_artifact_manifest", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps == []
    assert result.runtime_patch["runtime_status"] == "completed"
    assert result.runtime_patch["run_state"] == "completed"
    assert gateway.refreshed_statuses == ["success"]
    assert [event.event_type for event in result.events] == [
        "presentation.block.complete",
        "assistant_message_finalized",
        "turn_completed",
    ]
    assert result.events[-1].payload["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_unfinished_execution_plan_requeues_progress_without_completing(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"phase": "executing", "language": "zh"}, "turn": 3, "reason": "model_turn_completed"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:3:model_turn_completed",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "我先同步一下当前执行状态。"}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "phase": "executing",
            "language": "zh",
            "artifact_mode": "web",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {"outline_id": "outline-1", "title": "Landing page"},
                "execution_state": {
                    "status": "in_progress",
                    "steps": [
                        {"id": "step-1", "status": "completed"},
                        {"id": "step-2", "status": "pending"},
                    ],
                },
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.read_artifact_manifest", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "rendering_context"
    assert result.runtime_patch["activity"] == "execution_progress_required"
    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 4
    assert result.next_steps[0].input["payload"]["_execution_no_progress_recovery_attempts"] == 1
    assert "不要等待用户再次批准" in result.next_steps[0].input["transient_messages"][0]["content"]
    assert gateway.refreshed_statuses == []
    assert result.events == []


@pytest.mark.asyncio
async def test_finalize_final_summary_completed_skips_no_progress_gate(monkeypatch):
    # The post-summary finalize is the legitimate terminal turn (text-only by
    # design); it must NOT be failed by the execution no-progress gate even when the
    # plan was never synced to completed.
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"phase": "executing", "language": "zh"}, "turn": 7, "reason": "final_summary_completed"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:7:final_summary_completed",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "已发布完成，总结如下。"}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "phase": "executing",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {"outline_id": "outline-1", "title": "Landing"},
                "execution_state": {"status": "in_progress", "steps": [{"id": "s1", "status": "in_progress"}]},
            },
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.read_artifact_manifest", lambda *_args: None)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "completed"
    assert result.next_steps == []


@pytest.mark.asyncio
async def test_finalize_published_artifact_skips_no_progress_gate_and_syncs_plan(monkeypatch):
    # A published deliverable means a tool-less finalize is success, not a stall —
    # even with reason=model_turn_completed and an in-progress plan. The run should
    # complete AND the lingering plan should be synced to completed.
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"phase": "executing", "language": "zh"}, "turn": 9, "reason": "model_turn_completed"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:9:model_turn_completed",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "已发布并完成总结。"}

    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "phase": "executing",
            "plan_state": {
                "status": "in_progress",
                "outline_state": {"outline_id": "outline-1", "title": "Landing", "version": 1},
                "execution_state": {
                    "status": "in_progress",
                    "steps": [{"id": "s1", "status": "completed"}, {"id": "s2", "status": "in_progress"}],
                },
            },
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.read_artifact_manifest",
        lambda *_args: {"entry": "index.html", "publication": {"status": "published"}},
    )
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "completed"
    # Plan synced to completed (Fix 3) layered under the terminal run-state fields.
    assert result.runtime_patch["plan_state"]["status"] == "completed"
    assert all(s["status"] == "completed" for s in result.runtime_patch["plan_state"]["execution_state"]["steps"])
    assert any(e.event_type == "execution_projection_updated" for e in result.events)


@pytest.mark.asyncio
async def test_finalize_does_not_enqueue_publish_when_manifest_already_published(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:0",
    )
    gateway = _Gateway()
    gateway.messages["assistant-1"] = {"id": "assistant-1", "role": "assistant", "content": "final text"}
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.read_artifact_manifest",
        lambda _user_id, _conversation_id: {
            "entry": "deck/index.html",
            "kind": "deck",
            "publication": {"status": "published"},
        },
    )

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert gateway.refreshed_statuses == ["success"]
    assert result.next_steps == []
    assert result.runtime_patch["run_state"] == "completed"


@pytest.mark.asyncio
async def test_finalize_enqueues_final_summary_when_published_latest_assistant_is_tool_only(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"language": "zh"}, "turn": 4, "reason": "artifact_published"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:after-publish-output",
    )
    gateway = _Gateway()
    gateway.messages["assistant-tool"] = {
        "id": "assistant-tool",
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call-publish", "name": "publish_output", "arguments": {}}],
        "metadata": {"finish_reason": "tool_calls"},
    }
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.read_artifact_manifest",
        lambda _user_id, _conversation_id: {
            "entry": "open-design-landing-prepared/index.html",
            "title": "灵犀设计落地页",
            "kind": "html",
            "publication": {
                "status": "published",
                "payload": {
                    "file_id": "f_8b40f57dbc",
                    "current_version_id": "v0001",
                    "current_version_path": "published/f_8b40f57dbc/v0001/source.zip",
                    "open_design_lint": {"p0_count": 0, "p1_count": 2, "p2_count": 0},
                },
            },
        }
    )
    async def fake_get_conversation(*_args, **_kwargs):
        return {
            "id": "conv-1",
            "title": "生成一个设计公司的落地页",
            "runtime_state": {
                "critique": {
                    "status": "shipped",
                    "round": 1,
                    "composite": 8.6,
                    "must_fix_count": 0,
                    "scores": {"critic": 8.6},
                    "dimensions": [{"role": "critic", "name": "visual-quality", "score": 8.6, "note": "视觉层级清晰"}],
                }
            },
            "user_plan": {
                "items": [
                    {"title": "Hero 区", "summary": "说明品牌定位和核心行动按钮", "artifact_ref": "project/index.html#hero"},
                    {"title": "服务介绍", "summary": "展示服务内容与目标客户"},
                ]
            },
        }

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [{"name": "publish_output"}],
                "runtime_contract": {},
            }
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "summarizing"
    assert result.next_steps[0].step_type == STEP_MODEL_TURN
    assert result.next_steps[0].input["turn"] == 5
    turn_context = result.next_steps[0].input["turn_context"]
    assert turn_context["tools"] == []
    assert turn_context["model"] == "GPT-5.4"
    assert "系统收尾" in turn_context["messages"][0]["content"]
    assert "200-400 字中文总结" in turn_context["messages"][0]["content"]
    assert "生成内容的大致结构" in turn_context["messages"][0]["content"]
    assert "灵犀设计落地页" in turn_context["messages"][0]["content"]
    assert "published/f_8b40f57dbc/v0001/source.zip" in turn_context["messages"][0]["content"]
    assert "Hero 区" in turn_context["messages"][0]["content"]
    assert "Design Jury" in turn_context["messages"][0]["content"]
    assert "不能用它代替 Design Jury 的 must-fix 状态" in turn_context["messages"][0]["content"]
    assert '"p1_count": 2' in turn_context["messages"][0]["content"]
    assert not any(event.event_type == "run_completed" for event in result.events)


@pytest.mark.asyncio
async def test_finalize_final_summary_uses_runtime_critique_when_conversation_snapshot_is_stale(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-with-critique",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"language": "zh"}, "turn": 4, "reason": "artifact_published"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-with-critique:step:finalize:after-publish-output",
    )
    gateway = _Gateway()
    gateway.messages["assistant-tool"] = {
        "id": "assistant-tool",
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call-publish", "name": "publish_output", "arguments": {}}],
        "metadata": {"finish_reason": "tool_calls"},
    }
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.read_artifact_manifest",
        lambda _user_id, _conversation_id: {
            "entry": "open-design-landing-prepared/index.html",
            "title": "灵犀设计落地页",
            "kind": "html",
            "publication": {
                "status": "published",
                "payload": {"current_version_path": "published/f_8b40f57dbc/v0001/source.zip"},
            },
        },
    )

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "title": "生成一个设计公司的落地页", "runtime_state": {}}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [{"name": "publish_output"}],
                "runtime_contract": {},
            }
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.critique_runtime_payload",
        lambda *, harness_run_id: {
            "status": "below_threshold",
            "round": 2,
            "selected_round": 2,
            "selected_score": 7.92,
            "composite": 7.92,
            "must_fix_count": 0,
            "warnings": [{"code": "p1_gradient_density", "message": "渐变使用偏多"}],
        },
    )

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    turn_context = result.next_steps[0].input["turn_context"]
    content = turn_context["messages"][0]["content"]
    assert '"critique"' in content
    assert '"status": "below_threshold"' in content
    assert '"selected_round": 2' in content
    assert '"selected_score": 7.92' in content
    assert "当前未提供 Design Jury" not in content


@pytest.mark.asyncio
async def test_finalize_enqueues_final_summary_after_publish_even_when_latest_assistant_has_text(monkeypatch):
    step = WorkflowStepRecord(
        id=1,
        step_id="step-final",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {"language": "zh"}, "turn": 4, "reason": "artifact_published"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:after-publish-output",
    )
    gateway = _Gateway()
    gateway.messages["assistant-critique"] = {
        "id": "assistant-critique",
        "role": "assistant",
        "content": "Design Jury 已完成，准备发布。",
        "tool_calls": [],
    }
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.read_artifact_manifest",
        lambda _user_id, _conversation_id: {
            "entry": "html-ppt-prepared/index.html",
            "title": "设计行业趋势 PPT",
            "kind": "deck",
            "renderer": "deck-html",
            "publication": {
                "status": "published",
                "payload": {"current_version_path": "published/f_8b40f57dbc/v0001/source.zip"},
            },
        }
    )

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "title": "生成设计行业趋势 PPT"}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [{"name": "publish_output"}],
                "runtime_contract": {},
            }
        }

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.critique_runtime_payload",
        lambda *, harness_run_id: None,
    )

    result = await _finalize(step, gateway)  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "summarizing"
    assert result.next_steps[0].step_type == STEP_MODEL_TURN
    assert result.next_steps[0].input["final_summary"] is True


@pytest.mark.asyncio
async def test_persist_publish_output_success_enqueues_finalize():
    tool_calls = [{"id": "call-publish", "name": "publish_output", "arguments": {}}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 4,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="publish_output",
                    call_id="call-publish",
                    output="{}",
                    metadata={"entry": "deck/index.html"},
                )
            ],
            "outcome_index": 0,
        }
    )
    gateway = _Gateway()

    result = await _persist_tool_result(step, gateway)  # type: ignore[arg-type]

    assert result.next_steps[0].step_type == STEP_FINALIZE
    assert result.next_steps[0].input["reason"] == "artifact_published"
    assert result.runtime_patch["run_state"] == "finalizing"


@pytest.mark.asyncio
async def test_persist_system_publish_critique_rejection_enqueues_repair_turn():
    tool_calls = [{"id": "system_publish:run-1", "name": "publish_output", "arguments": {}}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 0,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="publish_output",
                    call_id="system_publish:run-1",
                    output="Design Jury did not authorize publication.",
                    is_error=True,
                    metadata={
                        "reason_code": "critique_not_authorized",
                        "repair_instruction": "Fix contrast and spacing, then publish again.",
                    },
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "rendering_context"
    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 1
    assert result.next_steps[0].input["transient_messages"] == [
        {"role": "user", "content": "Fix contrast and spacing, then publish again."}
    ]
    assert result.activity_summary["publish_critique_repair_enqueued"] is True


@pytest.mark.asyncio
async def test_persist_model_publish_critique_failure_terminalizes_instead_of_looping():
    tool_calls = [{"id": "call-publish", "name": "publish_output", "arguments": {}}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 6,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="publish_output",
                    call_id="call-publish",
                    output="Design Jury selected round is missing.",
                    is_error=True,
                    metadata={"reason_code": "critique_selected_round_missing"},
                )
            ],
            "outcome_index": 0,
        }
    )

    result = await _persist_tool_result(step, _Gateway())  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_FAILED
    assert result.next_steps == []
    assert result.runtime_patch["failure"]["error_type"] == "critique_selected_round_missing"
    assert result.events[-1].event_type == "turn_completed"
    assert result.events[-1].payload["status"] == "failed"


def test_persist_system_publish_lint_failure_continues_to_repair_turn():
    tool_calls = [{"id": "system_publish:run-1", "name": "publish_output", "arguments": {}}]
    step = _step(
        input_payload={
            "payload": {"content": "hello"},
            "turn": 2,
            "tool_calls": tool_calls,
            "segment_start_index": 0,
            "next_tool_index": 1,
            "outcomes": [
                _tool_outcome(
                    index=0,
                    tool_name="publish_output",
                    call_id="system_publish:run-1",
                    output="<artifact-lint>fix P0</artifact-lint>",
                    is_error=True,
                    metadata={
                        "reason_code": "open_design_artifact_lint_failed",
                        "failure_kind": "artifact_lint_failed",
                    },
                )
            ],
            "outcome_index": 0,
        }
    )

    result = asyncio.run(_persist_tool_result(step, _Gateway()))  # type: ignore[arg-type]

    assert result.status == STEP_STATUS_SUCCEEDED
    assert result.runtime_patch["run_state"] == "rendering_context"
    assert result.next_steps[0].step_type == STEP_RENDER_CONTEXT
    assert result.next_steps[0].input["turn"] == 3
    assert result.activity_summary["system_publish_lint_repair"] is True


@pytest.mark.asyncio
async def test_model_turn_coalesces_stream_delta_events(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "hello"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, *, on_chunk, **_kwargs):
            for delta in ["a", "b", "c", "d", "e"]:
                await on_chunk({"content": delta})
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": "abcde",
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 1, "output_tokens": 5},
                    "elapsed_ms": 10,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "parent_usage_log_id": 123}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [],
                "runtime_contract": {},
            }
        }

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.record_model_usage_billing",
        fake_record_model_usage_billing,
        raising=False,
    )

    await _model_turn(step, gateway)  # type: ignore[arg-type]

    delta_events = [event for event in gateway.events if event.event_type == "presentation.block.delta"]
    assert len(delta_events) == 1
    assert delta_events[0].payload["payload"]["delta"] == "abcde"


def _visible_assistant_text_blocks(events) -> list[tuple[str, str, str]]:
    """Collect (block_id, ui_kind, text) for every user-visible assistant text block completion."""
    blocks: list[tuple[str, str, str]] = []
    for event in events:
        if event.event_type != "presentation.block.complete":
            continue
        block = event.payload.get("block") if isinstance(event.payload.get("block"), dict) else {}
        ui_kind = str(block.get("ui_kind") or event.payload.get("ui_kind") or "")
        if ui_kind not in {"text", "assistant_text", "assistant_final_answer"}:
            continue
        block_id = str(event.payload.get("block_key") or block.get("block_key") or block.get("id") or "")
        text = str((event.payload.get("payload") or {}).get("text") or "")
        blocks.append((block_id, ui_kind, text))
    return blocks


@pytest.mark.asyncio
async def test_model_turn_then_finalize_does_not_duplicate_assistant_text(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    answer = "已完成，文件已生成。"
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "做个文件"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, *, on_chunk, **_kwargs):
            await on_chunk({"content": answer})
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": answer,
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 1, "output_tokens": 5},
                    "elapsed_ms": 10,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 0.5):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "parent_usage_log_id": 123}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [],
                "runtime_contract": {},
            }
        }

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.record_model_usage_billing",
        fake_record_model_usage_billing,
        raising=False,
    )

    model_result = await _model_turn(step, gateway)  # type: ignore[arg-type]

    finalize_step = WorkflowStepRecord(
        id=2,
        step_id="step-finalize",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_FINALIZE,
        status="running",
        input={"payload": {}, "reason": "model_turn_completed"},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-2",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:finalize:0",
    )
    finalize_result = await _finalize(finalize_step, gateway)  # type: ignore[arg-type]

    visible_blocks = (
        _visible_assistant_text_blocks(model_result.events)
        + _visible_assistant_text_blocks(finalize_result.events)
    )

    # The assistant's answer must be carried by a single block id so the client renders
    # it once: model_turn streams it as `assistant_text`, and finalize seals the same
    # block into `assistant_final_answer` (reusing the block id) instead of emitting a
    # second block.
    answer_block_ids = {block_id for block_id, _ui_kind, text in visible_blocks if text == answer}
    assert len(answer_block_ids) == 1, visible_blocks

    final_answer_events = [
        event
        for event in finalize_result.events
        if event.event_type == "presentation.block.complete"
        and (event.payload.get("payload") or {}).get("message_kind") == "final_answer"
    ]
    assert len(final_answer_events) == 1


@pytest.mark.asyncio
async def test_model_turn_resets_stream_block_on_retry(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    step = WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type="model_turn",
        status="running",
        input={
            "payload": {},
            "turn": 0,
            "turn_context": {
                "messages": [{"role": "user", "content": "hello"}],
                "system": "system",
                "tools": [],
                "model": "GPT-5.4",
                "language": "zh",
            },
        },
        attempts=2,  # retry attempt
        max_attempts=2,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:model_turn:0",
    )
    gateway = _Gateway()

    class _Runner:
        def submit(self, coroutine):
            return coroutine

    class _TurnRunner:
        def __init__(self, _provider) -> None:
            pass

        async def run(self, *, on_chunk, **_kwargs):
            await on_chunk({"content": "retry answer"})
            return type(
                "TurnResult",
                (),
                {
                    "assistant_text": "retry answer",
                    "tool_calls": [],
                    "finish_reason": "stop",
                    "usage": {"input_tokens": 1, "output_tokens": 2},
                    "elapsed_ms": 10,
                },
            )()

    async def fake_await_activity(_step, future, *, poll_seconds: float = 2.0):
        return await future

    async def fake_get_conversation(*_args, **_kwargs):
        return {"id": "conv-1", "parent_usage_log_id": 123}

    async def fake_get_run_runtime_snapshot(_run_id):
        return {
            "context_session": {
                "fingerprint": "fp",
                "model": "GPT-5.4",
                "language": "zh",
                "tool_schemas": [],
                "runtime_contract": {},
            }
        }

    async def fake_record_model_usage_billing(**_kwargs):
        return True

    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_workflow_activity_runner", lambda: _Runner())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers._await_activity", fake_await_activity)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_conversation_async", fake_get_conversation)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.get_run_runtime_snapshot_async", fake_get_run_runtime_snapshot)
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.validate_context_session_integrity", lambda _session: (True, {}))
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_model_provider", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.create_harness_registry", lambda **_kwargs: object())
    monkeypatch.setattr("app.services.agent_harness.workflow.handlers.TurnRunner", _TurnRunner)
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.handlers.record_model_usage_billing",
        fake_record_model_usage_billing,
        raising=False,
    )

    await _model_turn(step, gateway)  # type: ignore[arg-type]

    event_types = [event.event_type for event in gateway.events]
    patch_events = [event for event in gateway.events if event.event_type == "presentation.block.patch"]
    # A retry resets the streaming block text once, before any delta is streamed.
    assert len(patch_events) == 1
    assert patch_events[0].payload["payload"]["payload"]["text"] == ""
    assert event_types.index("presentation.block.patch") < event_types.index("presentation.block.delta")
