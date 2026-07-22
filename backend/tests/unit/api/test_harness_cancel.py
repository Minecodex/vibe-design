from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import harness as harness_endpoint
from app.schemas.harness import PlanRevisionRequest, RespondToHarnessAgentRequest
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state
from app.services.agent_harness.workspace.session_v2.state_store import read_state
from app.services.agent_harness.workflow import repositories as workflow_repository
from app.services.agent_harness.workflow.contracts import StepSpec
from app.services.agent_harness.workflow.status import (
    RUN_KIND_MESSAGE,
    RUN_KIND_RESUME_INTERACTION,
    STEP_APPLY_USER_INPUT,
    STEP_PREPARE_SKILL,
    STEP_STATUS_WAITING_INPUT,
)


def _create_workflow_run(
    *,
    user_id: int,
    conversation_id: str,
    kind: str,
    payload: dict,
    idempotency_key: str,
    run_id: str,
    priority: int = 0,
):
    step_type = STEP_APPLY_USER_INPUT if kind == RUN_KIND_RESUME_INTERACTION else STEP_PREPARE_SKILL
    return workflow_repository.create_run(
        user_id=user_id,
        conversation_id=conversation_id,
        kind=kind,
        input=payload,
        idempotency_key=idempotency_key,
        run_id=run_id,
        first_step=StepSpec(
            step_type=step_type,
            input={"kind": kind, "payload": payload},
            priority=priority,
            idempotency_key=f"run:{run_id}:step:{step_type}:0",
        ),
        reject_active_conflicts=False,
    )


@pytest.mark.asyncio
async def test_cancel_conversation_returns_cancelled_snapshot_for_healthy_foreign_owner(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    now = datetime.now(timezone.utc)
    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentRun

    conversation = create_conversation(7, title="api-foreign-owner-cancel")
    request = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind=RUN_KIND_MESSAGE,
        payload={"payload_version": 1},
        idempotency_key="cancel-running",
        run_id="cancel-running",
    )
    claimed = workflow_repository.claim_next_step(worker_id="worker-remote", lease_seconds=60)
    assert claimed is not None
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
            "heartbeat_at": now.timestamp(),
            "run_owner": "worker-remote",
            "run_owner_token": "owner-remote",
            "run_claimed_at": now.isoformat(),
            "run_last_renewed_at": now.isoformat(),
            "run_lease_expires_at": (now + timedelta(seconds=60)).isoformat(),
        },
        touch_updated_at=False,
    )

    snapshot = await harness_endpoint.cancel_conversation(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
    )

    assert snapshot["runtime_status"] == "cancelled"
    assert snapshot["run_state"] == "cancelling"
    assert snapshot["runtime_state"]["runtime_status"] == "cancelled"
    assert snapshot["runtime_state"]["cancel_requested"] is True
    with harness_sync_session_scope() as session:
        row = session.get(HarnessAgentRun, request.id)
        assert row is not None
        assert row.status == "running"
        assert row.cancel_requested is True


@pytest.mark.asyncio
async def test_cancel_conversation_terminalizes_waiting_input_without_active_request(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="api-waiting-input-cancel")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )

    snapshot = await harness_endpoint.cancel_conversation(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
    )

    assert snapshot["runtime_status"] == "cancelled"
    assert snapshot["run_state"] == "cancelled"
    assert read_state(7, conversation["id"]).get("user_interaction") is None


@pytest.mark.asyncio
async def test_cancel_conversation_clears_waiting_interaction_when_resume_is_queued(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentRun

    conversation = create_conversation(7, title="api-waiting-plus-queued-cancel")
    waiting = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind=RUN_KIND_MESSAGE,
        payload={"payload_version": 1, "content": "needs input"},
        idempotency_key="cancel-waiting",
        run_id="cancel-waiting",
    )
    claimed = workflow_repository.claim_next_step(worker_id="worker-waiting", lease_seconds=60)
    assert claimed is not None
    assert workflow_repository.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token or "",
        status=STEP_STATUS_WAITING_INPUT,
        terminal_run=True,
    ) is not None
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )
    queued = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind=RUN_KIND_RESUME_INTERACTION,
        payload={"payload_version": 1, "answer": "continue"},
        idempotency_key="cancel-queued-resume",
        run_id="cancel-queued-resume",
    )

    snapshot = await harness_endpoint.cancel_conversation(
        conversation_id=conversation["id"],
        user=SimpleNamespace(id=7),
    )

    assert snapshot["runtime_status"] == "cancelled"
    assert snapshot["run_state"] == "cancelled"
    assert read_state(7, conversation["id"]).get("user_interaction") is None
    with harness_sync_session_scope() as session:
        waiting_row = session.get(HarnessAgentRun, waiting.id)
        queued_row = session.get(HarnessAgentRun, queued.id)
        assert waiting_row.status == "cancelled"
        assert queued_row.status == "cancelled"


@pytest.mark.asyncio
async def test_respond_to_agent_rejects_when_cancellation_already_requested(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="api-cancel-requested-respond")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "cancel_requested": True,
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.respond_to_agent(
            conversation_id=conversation["id"],
            data=RespondToHarnessAgentRequest(
                request_id="req-1",
                answer="approve",
            ),
            request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
            user=SimpleNamespace(id=7),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Conversation cancellation already requested"


@pytest.mark.asyncio
async def test_respond_to_agent_does_not_append_submission_event_when_enqueue_conflicts(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events

    conversation = create_conversation(7, title="api-resume-enqueue-conflict")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )
    updates: list[dict] = []

    async def _enqueue_conflict(**_kwargs):
        raise AgentRunAlreadyActiveError("active")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_resume_interaction_run",
        _enqueue_conflict,
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_build_live_streaming_response",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **kwargs: updates.append(kwargs) or conversation,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.respond_to_agent(
            conversation_id=conversation["id"],
            data=RespondToHarnessAgentRequest(
                request_id="req-1",
                answer="approve",
            ),
            request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
            user=SimpleNamespace(id=7),
        )

    assert exc_info.value.status_code == 409
    assert updates == []
    assert [
        event
        for event in load_conversation_events(7, conversation["id"])
        if event.get("type") == "interaction_submitted"
    ] == []


@pytest.mark.asyncio
async def test_respond_to_agent_allows_waiting_workflow_run(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="api-resume-waiting-workflow")
    waiting = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind=RUN_KIND_MESSAGE,
        payload={"payload_version": 1, "content": "needs input"},
        idempotency_key="resume-waiting-workflow",
        run_id="resume-waiting-workflow",
    )
    claimed = workflow_repository.claim_next_step(worker_id="worker-waiting", lease_seconds=60)
    assert claimed is not None
    assert workflow_repository.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token or "",
        status=STEP_STATUS_WAITING_INPUT,
        terminal_run=True,
    ) is not None
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )
    captured: list[dict] = []

    async def _enqueue_capture(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(id=waiting.id, run_id=waiting.run_id, status="waiting_input")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_resume_interaction_run",
        _enqueue_capture,
    )
    response = object()
    monkeypatch.setattr(
        harness_endpoint,
        "_build_live_streaming_response",
        lambda *_args, **_kwargs: response,
    )

    result = await harness_endpoint.respond_to_agent(
        conversation_id=conversation["id"],
        data=RespondToHarnessAgentRequest(
            request_id="req-1",
            answer="approve",
        ),
        request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
        user=SimpleNamespace(id=7),
    )

    assert result is response
    assert captured
    assert captured[0]["conversation_id"] == conversation["id"]


@pytest.mark.asyncio
async def test_respond_to_agent_reads_top_level_pending_interaction(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="api-resume-top-level-pending")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-top-level",
                "kind": "ecommerce_generation_options",
                "question": "商品图生成配置",
            },
            "runtime_state": {
                "runtime_status": "waiting_input",
                "run_state": "waiting_input",
                "turn_status": "waiting_input",
            },
        },
        touch_updated_at=False,
    )
    captured: list[dict] = []

    async def _enqueue_capture(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(id=1, run_id="run-top-level")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_resume_interaction_run",
        _enqueue_capture,
    )
    response = object()
    monkeypatch.setattr(
        harness_endpoint,
        "_build_live_streaming_response",
        lambda *_args, **_kwargs: response,
    )

    result = await harness_endpoint.respond_to_agent(
        conversation_id=conversation["id"],
        data=RespondToHarnessAgentRequest(
            request_id="req-top-level",
            answer="confirm",
            answers={"action": "confirm", "analysis": "confirmed"},
            display_label="确认分析",
        ),
        request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
        user=SimpleNamespace(id=7),
    )

    assert result is response
    assert captured
    assert captured[0]["payload"]["request_id"] == "req-top-level"


@pytest.mark.asyncio
async def test_respond_to_agent_idempotency_key_includes_structured_answers(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    captured_keys: list[str] = []
    conversation = create_conversation(7, title="api-resume-idempotency")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )

    async def _enqueue_capture(**kwargs):
        captured_keys.append(kwargs["idempotency_key"])
        return SimpleNamespace(id=len(captured_keys), run_id=f"run-{len(captured_keys)}")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_resume_interaction_run",
        _enqueue_capture,
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_build_live_streaming_response",
        lambda *_args, **_kwargs: object(),
    )

    await harness_endpoint.respond_to_agent(
        conversation_id=conversation["id"],
        data=RespondToHarnessAgentRequest(
            request_id="req-1",
            answer="approve",
            answers={"choice": "a"},
            display_label="Option A",
            approved=True,
        ),
        request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
        user=SimpleNamespace(id=7),
    )
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-1",
                "question": "Need approval",
            },
        },
        touch_updated_at=False,
    )
    await harness_endpoint.respond_to_agent(
        conversation_id=conversation["id"],
        data=RespondToHarnessAgentRequest(
            request_id="req-1",
            answer="approve",
            answers={"choice": "b"},
            display_label="Option B",
            approved=True,
        ),
        request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
        user=SimpleNamespace(id=7),
    )

    assert len(captured_keys) == 2
    assert captured_keys[0] != captured_keys[1]


@pytest.mark.asyncio
async def test_respond_to_agent_rejects_legacy_ask_user_fields(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="api-resume-legacy-ask-user")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "user_interaction": {
                "request_id": "req-legacy",
                "kind": "ask_user",
                "question": "Need details",
                "schema": {
                    "title": "Legacy prompt",
                    "fields": [
                        {
                            "id": "tone",
                            "label": "Tone",
                            "type": "textarea",
                            "required": True,
                        }
                    ],
                },
            },
        },
        touch_updated_at=False,
    )

    with pytest.raises(HTTPException) as exc:
        await harness_endpoint.respond_to_agent(
            conversation_id=conversation["id"],
            data=RespondToHarnessAgentRequest(
                request_id="req-legacy",
                answer="Warm",
            ),
            request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
            user=SimpleNamespace(id=7),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Unsupported legacy ask_user interaction"


@pytest.mark.asyncio
async def test_revise_plan_idempotency_key_is_bounded_for_long_instruction(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    captured_keys: list[str] = []
    conversation = create_conversation(7, title="api-plan-revise-idempotency")
    patch_runtime_state(
        7,
        conversation["id"],
        {"phase": "planning_ready"},
        touch_updated_at=False,
    )

    async def _enqueue_capture(**kwargs):
        captured_keys.append(kwargs["idempotency_key"])
        return SimpleNamespace(id=1, run_id="run-revise")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_revise_plan_run",
        _enqueue_capture,
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_build_live_streaming_response",
        lambda *_args, **_kwargs: object(),
    )

    await harness_endpoint.revise_plan(
        conversation_id=conversation["id"],
        data=PlanRevisionRequest(instruction="请调整计划。" * 200),
        request=SimpleNamespace(headers={"accept-language": "zh-CN"}),
        user=SimpleNamespace(id=7),
    )

    assert len(captured_keys) == 1
    assert len(captured_keys[0]) <= 255
