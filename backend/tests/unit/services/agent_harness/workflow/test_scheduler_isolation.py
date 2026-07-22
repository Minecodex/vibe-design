from __future__ import annotations

import asyncio
from concurrent.futures import Future
from datetime import datetime, timedelta

import pytest

from app.services.agent_harness.workflow.contracts import EventSpec, MessageSpec, StepError, StepResult, StepSpec
from app.services.agent_harness.workflow.records import WorkflowStepRecord
from app.services.agent_harness.workflow import handlers, scheduler
from app.services.agent_harness.workflow.status import STEP_RENDER_CONTEXT, STEP_STATUS_CANCELLED, STEP_STATUS_FAILED, STEP_STATUS_SUCCEEDED


@pytest.mark.asyncio
async def test_step_lease_renew_loop_stays_responsive_during_awaited_work(monkeypatch):
    renews: list[str] = []
    first_renew = asyncio.Event()

    async def fake_renew_step_claim_async(step_id: str, *, claim_token: str, lease_seconds: int) -> bool:
        assert claim_token == "token-1"
        assert lease_seconds == 1
        renews.append(step_id)
        first_renew.set()
        return True

    monkeypatch.setattr(scheduler, "renew_step_claim_async", fake_renew_step_claim_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    loop.lease_seconds = 1
    stop_event = asyncio.Event()
    renew_task = asyncio.create_task(
        loop._renew_loop(
            "step-1",
            claim_token="token-1",
            stop_event=stop_event,
            lease_state={"lost": False},
            step_task=asyncio.current_task(),
        )
    )
    try:
        await asyncio.wait_for(first_renew.wait(), timeout=2.5)
        await asyncio.sleep(0.05)
    finally:
        stop_event.set()
        renew_task.cancel()
        await asyncio.gather(renew_task, return_exceptions=True)

    assert renews


@pytest.mark.asyncio
async def test_step_lease_loss_cancels_handler_to_prevent_split_brain(monkeypatch):
    async def fake_renew_step_claim_async(step_id: str, *, claim_token: str, lease_seconds: int) -> bool:
        # The lease was stolen / the step was terminalized out from under us.
        return False

    monkeypatch.setattr(scheduler, "renew_step_claim_async", fake_renew_step_claim_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    loop.lease_seconds = 1
    stop_event = asyncio.Event()
    lease_state = {"lost": False}

    async def victim() -> str:
        # Stand-in for a long-running step handler.
        await asyncio.sleep(60)
        return "handler completed despite lease loss"

    victim_task = asyncio.create_task(victim())
    renew_task = asyncio.create_task(
        loop._renew_loop(
            "step-1",
            claim_token="token-1",
            stop_event=stop_event,
            lease_state=lease_state,
            step_task=victim_task,
        )
    )

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(victim_task, timeout=2.5)

    stop_event.set()
    await asyncio.gather(renew_task, return_exceptions=True)

    assert lease_state["lost"] is True
    assert victim_task.cancelled()


def _step() -> WorkflowStepRecord:
    created_at = datetime(2026, 5, 28, 13, 0, 0)
    return WorkflowStepRecord(
        id=1,
        step_id="step-1",
        run_id="run-1",
        conversation_id="conv-1",
        user_id=7,
        step_type=STEP_RENDER_CONTEXT,
        status="claimed",
        input={},
        attempts=1,
        max_attempts=1,
        priority=0,
        claim_owner="worker-a",
        claim_token="token-1",
        claim_expires_at=None,
        idempotency_key="run:run-1:step:render_context:0",
        created_at=created_at,
        started_at=created_at + timedelta(seconds=1),
    )


def test_scheduler_poll_fallback_stays_short():
    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")

    assert loop.poll_seconds <= 2.0


@pytest.mark.asyncio
async def test_scheduler_observes_cancel_after_activity_before_side_effects(monkeypatch):
    running = _step()
    cancel_checks = iter([False, True])
    appended_events: list[str] = []
    appended_messages: list[str] = []
    enqueued_steps: list[str] = []
    completed: list[dict] = []
    refreshed_usage_statuses: list[str] = []

    async def fake_mark_step_running_async(step_id: str, *, claim_token: str):
        assert step_id == "step-1"
        assert claim_token == "token-1"
        return running

    def fake_is_cancel_requested(run_id: str) -> bool:
        assert run_id == "run-1"
        return next(cancel_checks)

    async def fake_handler(_step, _gateway):
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            messages=[MessageSpec(role="assistant", content="late")],
            next_steps=[StepSpec(step_type=STEP_RENDER_CONTEXT)],
        )

    async def fake_append_event(self, spec):
        appended_events.append(spec.event_type)
        return {"sequence": len(appended_events)}

    async def fake_append_message(self, spec):
        appended_messages.append(str(spec.content or ""))
        return {"id": spec.idempotency_key or "message"}

    async def fake_enqueue_step(self, spec):
        enqueued_steps.append(spec.step_type)

    async def fake_complete_step_async(step_id: str, **kwargs):
        completed.append({"step_id": step_id, **kwargs})
        return running

    async def fake_refresh_parent_usage_log(self, *, status: str = "success") -> None:
        refreshed_usage_statuses.append(status)

    monkeypatch.setattr(scheduler, "mark_step_running_async", fake_mark_step_running_async)
    monkeypatch.setattr(scheduler, "is_cancel_requested", fake_is_cancel_requested)
    monkeypatch.setattr(scheduler, "get_step_handler", lambda _step_type: fake_handler)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_event", fake_append_event)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_message", fake_append_message)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "enqueue_step", fake_enqueue_step)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "refresh_parent_usage_log", fake_refresh_parent_usage_log)
    monkeypatch.setattr(scheduler, "complete_step_async", fake_complete_step_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    await loop._execute_step(running)

    assert appended_events == ["turn_completed"]
    assert appended_messages == []
    assert enqueued_steps == []
    assert completed[-1]["status"] == STEP_STATUS_CANCELLED
    assert refreshed_usage_statuses == ["cancelled"]


@pytest.mark.asyncio
async def test_scheduler_wakes_worker_after_enqueuing_follow_up_steps(monkeypatch):
    running = _step()
    enqueued_steps: list[str] = []
    wake_calls: list[None] = []
    schedule_timings: list[dict] = []

    async def fake_mark_step_running_async(step_id: str, *, claim_token: str):
        assert step_id == "step-1"
        assert claim_token == "token-1"
        return running

    async def fake_handler(_step, _gateway):
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            next_steps=[StepSpec(step_type=STEP_RENDER_CONTEXT)],
        )

    async def fake_enqueue_step(self, spec):
        enqueued_steps.append(spec.step_type)

    async def fake_complete_step_async(step_id: str, **_kwargs):
        assert enqueued_steps == [STEP_RENDER_CONTEXT]
        assert wake_calls == []
        return running

    async def fake_wake_agent_run_worker():
        wake_calls.append(None)

    def fake_log_step_schedule_timing(**kwargs):
        schedule_timings.append(kwargs)

    monkeypatch.setattr(scheduler, "mark_step_running_async", fake_mark_step_running_async)
    monkeypatch.setattr(scheduler, "is_cancel_requested", lambda _run_id: False)
    monkeypatch.setattr(scheduler, "get_step_handler", lambda _step_type: fake_handler)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "enqueue_step", fake_enqueue_step)
    monkeypatch.setattr(scheduler, "complete_step_async", fake_complete_step_async)
    monkeypatch.setattr(scheduler, "wake_agent_run_worker", fake_wake_agent_run_worker, raising=False)
    monkeypatch.setattr(scheduler, "log_step_schedule_timing", fake_log_step_schedule_timing)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    await loop._execute_step(running, wake_source="redis")

    assert enqueued_steps == [STEP_RENDER_CONTEXT]
    assert wake_calls == [None]
    assert schedule_timings == [
        {
            "step_type": STEP_RENDER_CONTEXT,
            "step_id": "step-1",
            "run_id": "run-1",
            "queue_ms": 1000.0,
            "run_ms": schedule_timings[0]["run_ms"],
            "wake_source": "redis",
            "next_step_count": 1,
            "status": STEP_STATUS_SUCCEEDED,
        }
    ]
    assert schedule_timings[0]["run_ms"] >= 0


@pytest.mark.asyncio
async def test_scheduler_appends_messages_before_runtime_snapshot(monkeypatch):
    running = _step()
    side_effect_order: list[str] = []

    async def fake_mark_step_running_async(step_id: str, *, claim_token: str):
        assert step_id == "step-1"
        assert claim_token == "token-1"
        return running

    async def fake_handler(_step, _gateway):
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={"agent_prompt_context_v2": {"version": 2}},
            messages=[
                MessageSpec(role="system", content="context", idempotency_key="ctx"),
                MessageSpec(role="user", content="hello", idempotency_key="user"),
            ],
        )

    async def fake_append_message(self, spec):
        side_effect_order.append(f"message:{spec.role}")
        return {"id": spec.idempotency_key or spec.role}

    async def fake_update_runtime_snapshot(self, patch):
        assert side_effect_order == ["message:system", "message:user"]
        side_effect_order.append(f"snapshot:{'agent_prompt_context_v2' in patch}")

    async def fake_complete_step_async(step_id: str, **_kwargs):
        return running

    monkeypatch.setattr(scheduler, "mark_step_running_async", fake_mark_step_running_async)
    monkeypatch.setattr(scheduler, "is_cancel_requested", lambda _run_id: False)
    monkeypatch.setattr(scheduler, "get_step_handler", lambda _step_type: fake_handler)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_message", fake_append_message)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "update_runtime_snapshot", fake_update_runtime_snapshot)
    monkeypatch.setattr(scheduler, "complete_step_async", fake_complete_step_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    await loop._execute_step(running)

    assert side_effect_order == ["message:system", "message:user", "snapshot:True"]


@pytest.mark.asyncio
async def test_scheduler_does_not_update_runtime_snapshot_when_message_append_fails(monkeypatch):
    running = _step()
    snapshots: list[dict] = []
    completed: list[dict] = []

    async def fake_mark_step_running_async(step_id: str, *, claim_token: str):
        assert step_id == "step-1"
        assert claim_token == "token-1"
        return running

    async def fake_handler(_step, _gateway):
        return StepResult(
            status=STEP_STATUS_SUCCEEDED,
            runtime_patch={"agent_prompt_context_v2": {"version": 2}},
            messages=[MessageSpec(role="system", content="context", idempotency_key="ctx")],
        )

    async def fake_append_message(self, _spec):
        raise RuntimeError("append failed")

    async def fake_update_runtime_snapshot(self, patch):
        snapshots.append(patch)

    async def fake_append_event(self, _spec):
        return {"sequence": 1}

    async def fake_complete_step_async(step_id: str, **kwargs):
        completed.append({"step_id": step_id, **kwargs})
        return running

    monkeypatch.setattr(scheduler, "mark_step_running_async", fake_mark_step_running_async)
    monkeypatch.setattr(scheduler, "is_cancel_requested", lambda _run_id: False)
    monkeypatch.setattr(scheduler, "get_step_handler", lambda _step_type: fake_handler)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_message", fake_append_message)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_event", fake_append_event)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "update_runtime_snapshot", fake_update_runtime_snapshot)
    monkeypatch.setattr(scheduler, "complete_step_async", fake_complete_step_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    await loop._execute_step(running)

    assert snapshots == [
        {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "last_error_summary": "append failed",
            "failure": {"error_type": "RuntimeError", "summary": "append failed"},
        }
    ]
    assert completed[-1]["status"] == STEP_STATUS_FAILED


@pytest.mark.asyncio
async def test_scheduler_persists_failed_step_error_for_user_visibility(monkeypatch):
    running = _step()
    appended_events: list[EventSpec] = []
    completed: list[dict] = []
    refreshed_usage_statuses: list[str] = []
    snapshots: list[dict] = []

    async def fake_mark_step_running_async(step_id: str, *, claim_token: str):
        assert step_id == "step-1"
        assert claim_token == "token-1"
        return running

    async def fake_handler(_step, _gateway):
        return StepResult(
            status=STEP_STATUS_FAILED,
            runtime_patch={"runtime_status": "failed", "run_state": "failed", "turn_status": "failed"},
            events=[
                EventSpec(
                    event_type="turn_completed",
                    payload={
                        "conversation_id": "conv-1",
                        "run_id": "run-1",
                        "turn_id": "run-1",
                        "status": "failed",
                        "runtime_snapshot": {
                            "runtime_status": "failed",
                            "run_state": "failed",
                            "turn_status": "failed",
                        },
                        "error": None,
                    },
                    idempotency_key="run:run-1:turn-completed",
                )
            ],
            error=StepError("ToolExecutionFailed", "exec_command failed after retries"),
        )

    async def fake_append_event(self, spec):
        appended_events.append(spec)
        return {"sequence": len(appended_events)}

    async def fake_update_runtime_snapshot(self, patch):
        snapshots.append(patch)

    async def fake_complete_step_async(step_id: str, **kwargs):
        completed.append({"step_id": step_id, **kwargs})
        return running

    async def fake_refresh_parent_usage_log(self, *, status: str = "success") -> None:
        refreshed_usage_statuses.append(status)

    monkeypatch.setattr(scheduler, "mark_step_running_async", fake_mark_step_running_async)
    monkeypatch.setattr(scheduler, "is_cancel_requested", lambda _run_id: False)
    monkeypatch.setattr(scheduler, "get_step_handler", lambda _step_type: fake_handler)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_event", fake_append_event)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "update_runtime_snapshot", fake_update_runtime_snapshot)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "refresh_parent_usage_log", fake_refresh_parent_usage_log)
    monkeypatch.setattr(scheduler, "complete_step_async", fake_complete_step_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    await loop._execute_step(running)

    assert snapshots[-1]["last_error_summary"] == "exec_command failed after retries"
    assert snapshots[-1]["failure"] == {
        "error_type": "ToolExecutionFailed",
        "summary": "exec_command failed after retries",
    }
    assert appended_events[-1].payload["error"] == {
        "error_type": "ToolExecutionFailed",
        "summary": "exec_command failed after retries",
        "user_visible": True,
        "failure_signature": None,
    }
    assert completed[-1]["runtime_patch"]["last_error_summary"] == "exec_command failed after retries"
    assert refreshed_usage_statuses == ["failed"]


@pytest.mark.asyncio
async def test_scheduler_syncs_runtime_snapshot_when_handler_exception_terminalizes_run(monkeypatch):
    running = _step()
    appended_events: list[EventSpec] = []
    completed: list[dict] = []
    snapshots: list[dict] = []
    refreshed_usage_statuses: list[str] = []

    async def fake_mark_step_running_async(step_id: str, *, claim_token: str):
        assert step_id == "step-1"
        assert claim_token == "token-1"
        return running

    async def fake_handler(_step, _gateway):
        raise RuntimeError("upstream_first_byte_timeout")

    async def fake_append_event(self, spec):
        appended_events.append(spec)
        return {"sequence": len(appended_events)}

    async def fake_update_runtime_snapshot(self, patch):
        snapshots.append(patch)

    async def fake_complete_step_async(step_id: str, **kwargs):
        completed.append({"step_id": step_id, **kwargs})
        return running

    async def fake_refresh_parent_usage_log(self, *, status: str = "success") -> None:
        refreshed_usage_statuses.append(status)

    monkeypatch.setattr(scheduler, "mark_step_running_async", fake_mark_step_running_async)
    monkeypatch.setattr(scheduler, "is_cancel_requested", lambda _run_id: False)
    monkeypatch.setattr(scheduler, "get_step_handler", lambda _step_type: fake_handler)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "append_event", fake_append_event)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "update_runtime_snapshot", fake_update_runtime_snapshot)
    monkeypatch.setattr(scheduler.AgentRuntimeGateway, "refresh_parent_usage_log", fake_refresh_parent_usage_log)
    monkeypatch.setattr(scheduler, "complete_step_async", fake_complete_step_async)

    loop = scheduler.WorkflowStepScheduler(worker_id="worker-a")
    await loop._execute_step(running)

    assert appended_events[-1].event_type == "turn_completed"
    assert appended_events[-1].payload["status"] == "failed"
    assert appended_events[-1].payload["error"] == {
        "error_type": "RuntimeError",
        "summary": "upstream_first_byte_timeout",
        "user_visible": True,
        "failure_signature": None,
    }
    assert snapshots == [
        {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "last_error_summary": "upstream_first_byte_timeout",
            "failure": {
                "error_type": "RuntimeError",
                "summary": "upstream_first_byte_timeout",
            },
        }
    ]
    assert completed[-1]["runtime_patch"] == snapshots[-1]
    assert refreshed_usage_statuses == ["failed"]


@pytest.mark.asyncio
async def test_activity_await_observes_cancel_while_activity_is_running(monkeypatch):
    running = _step()
    pending: Future[dict] = Future()

    monkeypatch.setattr(handlers, "is_cancel_requested", lambda run_id: run_id == "run-1")

    with pytest.raises(asyncio.CancelledError):
        await handlers._await_activity(running, pending, poll_seconds=0.01)

    assert pending.cancelled()


@pytest.mark.asyncio
async def test_activity_await_cancels_future_when_step_task_is_cancelled(monkeypatch):
    running = _step()
    pending: Future[dict] = Future()

    monkeypatch.setattr(handlers, "is_cancel_requested", lambda _run_id: False)

    task = asyncio.create_task(handlers._await_activity(running, pending, poll_seconds=0.01))
    await asyncio.sleep(0.02)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert pending.cancelled()
