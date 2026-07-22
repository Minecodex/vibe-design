from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints import harness as harness_endpoint
from app.services.agent_harness.workspace.conversation.turns.plan_turn import (
    build_plan_execution_approval_user_event,
)


@pytest.mark.asyncio
async def test_start_plan_rejects_non_waiting_phase(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: {
            "id": "conv-not-ready",
            "phase": "executing",
            "plan_state": {"outline_state": {"outline_id": "outline-1"}},
        },
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.repositories.get_active_run_for_conversation",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.start_plan_execution(
            conversation_id="conv-not-ready",
            request=SimpleNamespace(headers={}),
            user=SimpleNamespace(id=7),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Plan is not waiting for execution approval"


@pytest.mark.asyncio
async def test_start_plan_rejects_missing_outline(monkeypatch):
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: {
            "id": "conv-no-outline",
            "phase": "planning_ready",
            "plan_state": {},
        },
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.repositories.get_active_run_for_conversation",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(HTTPException) as exc_info:
        await harness_endpoint.start_plan_execution(
            conversation_id="conv-no-outline",
            request=SimpleNamespace(headers={}),
            user=SimpleNamespace(id=7),
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Current outline is required before starting execution"


@pytest.mark.asyncio
async def test_start_plan_allows_waiting_input_gate_run(monkeypatch):
    calls: list[dict] = []
    approval_events: list[dict] = []
    conversation = {
        "id": "conv-ready",
        "phase": "planning_ready",
        "outline_runtime": {
            "current_outline": {
                "outline_id": "outline-1",
                "plan_instance_id": "plan-1",
                "version": 1,
            },
            "execution_state": {"status": "planning_ready"},
        },
        "plan_state": {"outline_state": {"outline_id": "outline-1"}},
        "web_search_enabled": False,
    }
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.get_conversation",
        lambda *_args, **_kwargs: conversation,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.update_conversation",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workflow.repositories.get_active_run_for_conversation",
        lambda *_args, **_kwargs: SimpleNamespace(status="waiting_input"),
    )

    async def _enqueue_start_plan_run(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(id=42, run_id="run-start")

    monkeypatch.setattr(
        "app.services.agent_harness.agent_run.control.enqueue_service.enqueue_start_plan_run",
        _enqueue_start_plan_run,
    )

    async def _build_plan_execution_approval_user_event(**kwargs):
        approval_events.append(kwargs)
        return {
            "id": "plan-execution-approved",
            "role": "user",
            "content": "执行计划",
            "created_at": "2026-06-04T00:00:00+00:00",
            "metadata": {"kind": "plan_execution_approved"},
        }

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.turns.plan_turn.build_plan_execution_approval_user_event",
        _build_plan_execution_approval_user_event,
    )
    monkeypatch.setattr(
        harness_endpoint,
        "_build_live_streaming_response",
        lambda *_args, **_kwargs: {"ok": True, "run_id": _kwargs.get("run_id")},
    )

    response = await harness_endpoint.start_plan_execution(
        conversation_id="conv-ready",
        request=SimpleNamespace(headers={}),
        user=SimpleNamespace(id=7),
    )

    assert response == {"ok": True, "run_id": "run-start"}
    assert approval_events[0]["conversation_id"] == "conv-ready"
    assert approval_events[0]["language"] == "zh"
    assert calls[0]["payload"]["turn_route"]["activity"] == "executing"
    assert calls[0]["payload"]["user_message_event"]["id"] == "plan-execution-approved"
    assert calls[0]["payload"]["user_message_event"]["content"] == "执行计划"
    assert calls[0]["payload"]["user_message_event"]["metadata"]["kind"] == "plan_execution_approved"


@pytest.mark.asyncio
async def test_build_plan_execution_approval_user_event_is_stable():
    conversation = {
        "outline_runtime": {
            "current_outline": {
                "outline_id": "outline-1",
                "plan_instance_id": "plan-1",
                "version": 2,
            },
        },
    }

    first = await build_plan_execution_approval_user_event(
        conversation_id="conv-ready",
        conversation=conversation,
        language="zh-CN",
    )
    second = await build_plan_execution_approval_user_event(
        conversation_id="conv-ready",
        conversation=conversation,
        language="zh-CN",
    )

    assert first == second
    assert first["role"] == "user"
    assert first["content"] == "执行计划"
    assert first["metadata"]["kind"] == "plan_execution_approved"
    assert first["metadata"]["plan_instance_id"] == "plan-1"
    assert first["metadata"]["outline_version"] == 2
