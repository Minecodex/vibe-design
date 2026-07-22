from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.services.agent_harness.agent_run.control import enqueue_service
from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError


@dataclass
class _Request:
    id: int
    run_id: str
    status: str = "queued"
    parent_usage_log_id: int | None = None
    created: bool = True


def _stub_turn_started_dependencies(monkeypatch, calls: list[tuple[str, object]] | None = None):
    async def _get_conversation_async(_user_id, _conversation_id):
        return {"runtime_profile": "home"}

    async def _append_event_async(*_args, **kwargs):
        if calls is not None:
            calls.append(("append", kwargs))
        return {"sequence": 1, "type": kwargs["event_type"]}

    monkeypatch.setattr(enqueue_service, "get_conversation_async", _get_conversation_async)
    monkeypatch.setattr(enqueue_service, "append_event_async", _append_event_async)


@pytest.mark.asyncio
async def test_enqueue_message_run_persists_request_and_only_wakes_worker(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def _create_run_async(**kwargs):
        calls.append(("create", kwargs))
        return _Request(id=42, run_id=kwargs["run_id"])

    async def _update_conversation_async(_user_id, _conversation_id, updates):
        calls.append(("update", updates))

    monkeypatch.setattr(enqueue_service, "create_run_async", _create_run_async)
    monkeypatch.setattr(enqueue_service, "update_conversation_async", _update_conversation_async)
    _stub_turn_started_dependencies(monkeypatch, calls)

    async def _wake():
        calls.append(("wake", None))

    monkeypatch.setattr(enqueue_service, "wake_agent_run_worker", _wake)

    request = await enqueue_service.enqueue_message_run(
        user_id=7,
        conversation_id="conv-1",
        payload={"payload_version": 1, "content": "hello"},
        idempotency_key="message:conv-1:hello",
    )

    assert request.id == 42
    assert [name for name, _ in calls] == ["create", "append", "update", "wake"]
    assert calls[0][1]["kind"] == "message"
    assert calls[0][1]["first_step"].step_type == "prepare_skill"
    assert calls[1][1]["event_type"] == "turn_started"
    assert calls[1][1]["idempotency_key"] == f"run:{request.run_id}:turn-started"
    assert calls[1][1]["payload"]["turn_id"] == request.run_id
    assert calls[2][1]["run_state"] == "queued"


@pytest.mark.asyncio
async def test_enqueue_message_run_allows_one_retry_for_planning_outline(monkeypatch):
    calls: list[dict[str, object]] = []

    async def _create_run_async(**kwargs):
        calls.append(kwargs)
        return _Request(id=42, run_id=kwargs["run_id"])

    async def _update_conversation_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(enqueue_service, "create_run_async", _create_run_async)
    monkeypatch.setattr(enqueue_service, "update_conversation_async", _update_conversation_async)
    _stub_turn_started_dependencies(monkeypatch)

    async def _wake():
        return None

    monkeypatch.setattr(enqueue_service, "wake_agent_run_worker", _wake)

    await enqueue_service.enqueue_message_run(
        user_id=7,
        conversation_id="conv-1",
        payload={
            "payload_version": 1,
            "content": "make a spreadsheet",
            "activity": "planning_outline",
        },
        idempotency_key="message:conv-1:planning",
    )

    assert calls[0]["first_step"].max_attempts == 2


@pytest.mark.asyncio
async def test_enqueue_message_run_keeps_single_attempt_for_execution(monkeypatch):
    calls: list[dict[str, object]] = []

    async def _create_run_async(**kwargs):
        calls.append(kwargs)
        return _Request(id=42, run_id=kwargs["run_id"])

    async def _update_conversation_async(*_args, **_kwargs):
        return None

    monkeypatch.setattr(enqueue_service, "create_run_async", _create_run_async)
    monkeypatch.setattr(enqueue_service, "update_conversation_async", _update_conversation_async)
    _stub_turn_started_dependencies(monkeypatch)

    async def _wake():
        return None

    monkeypatch.setattr(enqueue_service, "wake_agent_run_worker", _wake)

    await enqueue_service.enqueue_message_run(
        user_id=7,
        conversation_id="conv-1",
        payload={
            "payload_version": 1,
            "content": "continue",
            "activity": "executing",
        },
        idempotency_key="message:conv-1:executing",
    )

    assert calls[0]["first_step"].max_attempts == 1


@pytest.mark.asyncio
async def test_enqueue_message_run_creates_canvas_parent_usage_log(monkeypatch):
    calls: list[tuple[str, object]] = []

    async def _create_run_async(**kwargs):
        calls.append(("create", kwargs))
        return _Request(id=42, run_id=kwargs["run_id"], parent_usage_log_id=None, created=True)

    async def _create_run_parent_usage_log(**kwargs):
        calls.append(("billing", kwargs))
        return 987

    async def _set_run_parent_usage_log_id_async(run_id: str, parent_usage_log_id: int):
        calls.append(("set_parent", {"run_id": run_id, "parent_usage_log_id": parent_usage_log_id}))

    async def _update_conversation_async(*_args, **_kwargs):
        calls.append(("update", _kwargs))

    async def _wake():
        calls.append(("wake", None))

    monkeypatch.setattr(enqueue_service, "create_run_async", _create_run_async)
    monkeypatch.setattr(enqueue_service, "set_run_parent_usage_log_id_async", _set_run_parent_usage_log_id_async)
    monkeypatch.setattr(enqueue_service, "update_conversation_async", _update_conversation_async)
    monkeypatch.setattr(enqueue_service, "wake_agent_run_worker", _wake)
    _stub_turn_started_dependencies(monkeypatch, calls)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.execution_support.billing_controller.create_run_parent_usage_log",
        _create_run_parent_usage_log,
    )

    request = await enqueue_service.enqueue_message_run(
        user_id=7,
        conversation_id="conv-canvas",
        payload={"payload_version": 1, "content": "draw"},
        idempotency_key="message:conv-canvas:draw",
        parent_usage_log_id=None,
        parent_billing_conversation={
            "id": "conv-canvas",
            "runtime_profile": "canvas",
            "skill_id": "design_workflow",
            "artifact_mode": "web",
        },
    )

    assert request.parent_usage_log_id == 987
    assert [name for name, _ in calls] == ["create", "append", "billing", "set_parent", "update", "wake"]
    assert calls[1][1]["event_type"] == "turn_started"
    assert calls[2][1]["run_id"] == request.run_id
    assert calls[3][1] == {"run_id": request.run_id, "parent_usage_log_id": 987}


@pytest.mark.asyncio
async def test_enqueue_message_run_turn_started_idempotency_key_is_stable(monkeypatch):
    appended_by_key: dict[str, object] = {}

    async def _create_run_async(**_kwargs):
        return _Request(id=42, run_id="stable-run")

    async def _update_conversation_async(*_args, **_kwargs):
        return None

    async def _get_conversation_async(_user_id, _conversation_id):
        return {"runtime_profile": "canvas"}

    async def _append_event_async(*_args, **kwargs):
        appended_by_key.setdefault(kwargs["idempotency_key"], kwargs)
        return {"sequence": len(appended_by_key), "type": kwargs["event_type"]}

    async def _wake():
        return None

    monkeypatch.setattr(enqueue_service, "create_run_async", _create_run_async)
    monkeypatch.setattr(enqueue_service, "update_conversation_async", _update_conversation_async)
    monkeypatch.setattr(enqueue_service, "get_conversation_async", _get_conversation_async)
    monkeypatch.setattr(enqueue_service, "append_event_async", _append_event_async)
    monkeypatch.setattr(enqueue_service, "wake_agent_run_worker", _wake)

    await enqueue_service.enqueue_message_run(
        user_id=7,
        conversation_id="conv-1",
        payload={"payload_version": 1, "content": "hello"},
        idempotency_key="message:conv-1:hello",
    )
    await enqueue_service.enqueue_message_run(
        user_id=7,
        conversation_id="conv-1",
        payload={"payload_version": 1, "content": "hello"},
        idempotency_key="message:conv-1:hello",
    )

    assert list(appended_by_key) == ["run:stable-run:turn-started"]
    event = appended_by_key["run:stable-run:turn-started"]
    assert event["payload"]["runtime_profile"] == "canvas"


@pytest.mark.asyncio
async def test_enqueue_rejects_same_conversation_active_run(monkeypatch):
    async def _create_run_async(**_kwargs):
        raise AgentRunAlreadyActiveError("active")

    monkeypatch.setattr(enqueue_service, "create_run_async", _create_run_async)

    with pytest.raises(AgentRunAlreadyActiveError):
        await enqueue_service.enqueue_message_run(
            user_id=7,
            conversation_id="conv-1",
            payload={"payload_version": 1},
            idempotency_key="message:conv-1",
        )
