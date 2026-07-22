from __future__ import annotations

import asyncio
import logging
import os
import socket
import time
from dataclasses import replace

from app.core.config import settings
from app.services.agent_harness.agent_coordination.run_wakeup_bus import wait_agent_run_wakeup, wake_agent_run_worker
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    TURN_COMPLETED,
    build_turn_completed_payload,
    build_turn_error,
)

from .diagnostics import log_lease_safety, log_step_retry, log_step_schedule_timing, log_step_terminalized, workflow_step_timer
from .gateway import AgentRuntimeGateway
from .handlers import get_step_handler
from .repositories import (
    claim_next_step_async,
    complete_step_async,
    is_cancel_requested,
    mark_step_running_async,
    recover_stuck_running_runs_async,
    release_step_for_retry_async,
    renew_step_claim_async,
)
from .status import STEP_STATUS_CANCELLED, STEP_STATUS_FAILED, STEP_STATUS_SUCCEEDED, STEP_STATUS_WAITING_INPUT
from .contracts import EventSpec, StepError, StepResult

logger = logging.getLogger(__name__)

WORKFLOW_STEP_WORKER_POLL_SECONDS = 2.0
WORKFLOW_STEP_LEASE_SECONDS = 300


def _datetime_elapsed_ms(started_at, finished_at) -> float | None:
    if started_at is None or finished_at is None:
        return None
    try:
        return max((finished_at - started_at).total_seconds() * 1000.0, 0.0)
    except (TypeError, ValueError):
        return None


def _with_user_visible_failure(result: StepResult) -> StepResult:
    if result.status != STEP_STATUS_FAILED or result.error is None:
        return result
    failure = _failure_payload(result.error)
    runtime_patch = dict(result.runtime_patch or {})
    runtime_patch.setdefault("last_error_summary", failure["summary"])
    existing_failure = runtime_patch.get("failure")
    if not isinstance(existing_failure, dict):
        runtime_patch["failure"] = failure
    else:
        merged_failure = dict(existing_failure)
        merged_failure.setdefault("error_type", failure["error_type"])
        merged_failure.setdefault("summary", failure["summary"])
        runtime_patch["failure"] = merged_failure
    events = [_event_with_failure_payload(event, result.error) for event in result.events]
    return replace(result, runtime_patch=runtime_patch, events=events)


def _event_with_failure_payload(event: EventSpec, error: StepError) -> EventSpec:
    if event.event_type != TURN_COMPLETED:
        return event
    failure = _failure_payload(error)
    payload = dict(event.payload or {})
    if payload.get("error") is None:
        payload["error"] = {
            "error_type": failure["error_type"],
            "summary": failure["summary"],
            "user_visible": True,
            "failure_signature": None,
        }
    return replace(event, payload=payload)


def _failure_payload(error: StepError) -> dict[str, str]:
    summary = str(error.summary or error.error_type or "Workflow step failed")
    return {"error_type": str(error.error_type or "WorkflowStepFailed"), "summary": summary}


class WorkflowStepScheduler:
    def __init__(self, *, worker_id: str | None = None) -> None:
        self.worker_id = worker_id or f"agent-workflow:{socket.gethostname()}:{os.getpid()}"
        self.max_active_steps = max(int(getattr(settings, "HARNESS_WORKFLOW_MAX_ACTIVE_STEPS", 8) or 8), 1)
        self.lease_seconds = WORKFLOW_STEP_LEASE_SECONDS
        self.poll_seconds = WORKFLOW_STEP_WORKER_POLL_SECONDS
        self._shutdown = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()

    async def run(self) -> None:
        wake_source = "startup"
        while not self._shutdown.is_set():
            self._tasks = {task for task in self._tasks if not task.done()}
            claimed_any = False
            while len(self._tasks) < self.max_active_steps:
                step = await claim_next_step_async(worker_id=self.worker_id, lease_seconds=self.lease_seconds)
                if step is None:
                    break
                claimed_any = True
                task = asyncio.create_task(
                    self._execute_step(step, wake_source=wake_source),
                    name=f"agent-step-{step.step_id}",
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
                wake_source = "immediate"
            if claimed_any:
                await asyncio.sleep(0)
                continue
            recovered = await recover_stuck_running_runs_async(grace_seconds=self.lease_seconds)
            if recovered:
                wake_source = "stuck-recovery"
                await asyncio.sleep(0)
                continue
            woken = await wait_agent_run_wakeup(timeout_seconds=self.poll_seconds)
            wake_source = "redis" if woken else "poll"

    async def shutdown(self) -> None:
        self._shutdown.set()
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def _execute_step(self, claimed_step, *, wake_source: str = "direct") -> None:
        if not claimed_step.claim_token:
            return
        running = await mark_step_running_async(claimed_step.step_id, claim_token=claimed_step.claim_token)
        if running is None:
            return
        step_started = time.perf_counter()
        stop_event = asyncio.Event()
        lease_state = {"lost": False}
        step_task = asyncio.current_task()
        renew_task = asyncio.create_task(
            self._renew_loop(
                running.step_id,
                claim_token=claimed_step.claim_token,
                stop_event=stop_event,
                lease_state=lease_state,
                step_task=step_task,
            ),
            name=f"agent-step-lease-{running.step_id}",
        )
        gateway = AgentRuntimeGateway(
            user_id=running.user_id,
            conversation_id=running.conversation_id,
            run_id=running.run_id,
            step_id=running.step_id,
        )
        try:
            if await asyncio.to_thread(is_cancel_requested, running.run_id):
                await self._terminalize_cancelled(running, gateway, claim_token=claimed_step.claim_token)
                return
            handler = get_step_handler(running.step_type)
            with workflow_step_timer(
                step_type=running.step_type,
                step_id=running.step_id,
                run_id=running.run_id,
                attempt=running.attempts,
            ):
                result = await handler(running, gateway)
            if result is None:
                raise RuntimeError(f"workflow step handler returned None: {running.step_type}")
            if await asyncio.to_thread(is_cancel_requested, running.run_id):
                await self._terminalize_cancelled(running, gateway, claim_token=claimed_step.claim_token)
                return
            result = _with_user_visible_failure(result)
            for message in result.messages:
                await gateway.append_message(message)
            for event in result.events:
                await gateway.append_event(event)
            await gateway.update_runtime_snapshot(result.runtime_patch)
            for spec in result.next_steps:
                await gateway.enqueue_step(spec)
            terminal_run = not result.next_steps and result.status in {STEP_STATUS_SUCCEEDED, STEP_STATUS_FAILED, STEP_STATUS_CANCELLED, STEP_STATUS_WAITING_INPUT}
            completed = await complete_step_async(
                running.step_id,
                claim_token=claimed_step.claim_token,
                status=result.status,
                output=result.activity_summary,
                runtime_patch=result.runtime_patch,
                error_type=result.error.error_type if result.error else None,
                error_summary=result.error.summary if result.error else None,
                terminal_run=terminal_run,
            )
            if terminal_run and completed is not None and result.status in {STEP_STATUS_FAILED, STEP_STATUS_CANCELLED}:
                await self._refresh_parent_usage_terminal(gateway, status=result.status)
            if result.next_steps and completed is not None:
                await wake_agent_run_worker()
            log_step_schedule_timing(
                step_type=running.step_type,
                step_id=running.step_id,
                run_id=running.run_id,
                queue_ms=_datetime_elapsed_ms(running.created_at, running.started_at),
                run_ms=(time.perf_counter() - step_started) * 1000.0,
                wake_source=wake_source,
                next_step_count=len(result.next_steps),
                status=result.status,
            )
            log_step_terminalized(run_id=running.run_id, step_id=running.step_id, status=result.status)
        except asyncio.CancelledError:
            if lease_state["lost"]:
                logger.warning(
                    "Workflow step lease lost; abandoning execution so the claiming worker can proceed: "
                    "step_id=%s run_id=%s",
                    running.step_id,
                    running.run_id,
                )
                return
            if await asyncio.to_thread(is_cancel_requested, running.run_id):
                await self._terminalize_cancelled(running, gateway, claim_token=claimed_step.claim_token)
                return
            raise
        except Exception as exc:
            logger.exception("Workflow step failed: step_id=%s run_id=%s", running.step_id, running.run_id)
            log_step_retry(step_id=running.step_id, attempt=running.attempts, error_type=exc.__class__.__name__)
            if running.attempts < running.max_attempts:
                await release_step_for_retry_async(
                    running.step_id,
                    claim_token=claimed_step.claim_token,
                    error_type=exc.__class__.__name__,
                    error_summary=str(exc)[:500],
                    retry_delay_seconds=min(float(2 ** max(running.attempts - 1, 0)), 30.0),
                )
                return
            await self._terminalize_failed(
                running,
                gateway,
                claim_token=claimed_step.claim_token,
                error_type=exc.__class__.__name__,
                error_summary=str(exc)[:500],
            )
        finally:
            stop_event.set()
            renew_task.cancel()
            await asyncio.gather(renew_task, return_exceptions=True)

    async def _terminalize_cancelled(self, running, gateway: AgentRuntimeGateway, *, claim_token: str) -> None:
        patch = {"runtime_status": "cancelled", "run_state": "cancelled", "turn_status": "cancelled"}
        await gateway.append_event(
            EventSpec(
                event_type=TURN_COMPLETED,
                payload=build_turn_completed_payload(
                    conversation_id=running.conversation_id,
                    run_id=running.run_id,
                    status="cancelled",
                    runtime_snapshot=patch,
                ),
                idempotency_key=f"run:{running.run_id}:turn-completed",
            )
        )
        await gateway.update_runtime_snapshot(patch)
        await complete_step_async(
            running.step_id,
            claim_token=claim_token,
            status=STEP_STATUS_CANCELLED,
            runtime_patch=patch,
            error_type="Cancelled",
            error_summary="cancelled",
            terminal_run=True,
        )
        await self._refresh_parent_usage_terminal(gateway, status=STEP_STATUS_CANCELLED)
        log_step_terminalized(run_id=running.run_id, step_id=running.step_id, status=STEP_STATUS_CANCELLED)

    async def _terminalize_failed(
        self,
        running,
        gateway: AgentRuntimeGateway,
        *,
        claim_token: str,
        error_type: str,
        error_summary: str,
    ) -> None:
        patch = {
            "runtime_status": "failed",
            "run_state": "failed",
            "turn_status": "failed",
            "last_error_summary": error_summary,
            "failure": {"error_type": error_type, "summary": error_summary},
        }
        await gateway.append_event(
            EventSpec(
                event_type=TURN_COMPLETED,
                payload=build_turn_completed_payload(
                    conversation_id=running.conversation_id,
                    run_id=running.run_id,
                    status="failed",
                    runtime_snapshot=patch,
                    error=build_turn_error(error_type, error_summary),
                ),
                idempotency_key=f"run:{running.run_id}:turn-completed",
            )
        )
        await gateway.update_runtime_snapshot(patch)
        await complete_step_async(
            running.step_id,
            claim_token=claim_token,
            status=STEP_STATUS_FAILED,
            runtime_patch=patch,
            error_type=error_type,
            error_summary=error_summary,
            terminal_run=True,
        )
        await self._refresh_parent_usage_terminal(gateway, status=STEP_STATUS_FAILED)
        log_step_terminalized(run_id=running.run_id, step_id=running.step_id, status=STEP_STATUS_FAILED)

    async def _refresh_parent_usage_terminal(self, gateway: AgentRuntimeGateway, *, status: str) -> None:
        usage_status = "cancelled" if status == STEP_STATUS_CANCELLED else "failed"
        try:
            await gateway.refresh_parent_usage_log(status=usage_status)
        except Exception:
            logger.warning(
                "Failed to refresh terminal parent usage log: run_id=%s status=%s",
                gateway.run_id,
                usage_status,
                exc_info=True,
            )

    async def _renew_loop(
        self,
        step_id: str,
        *,
        claim_token: str,
        stop_event: asyncio.Event,
        lease_state: dict[str, bool],
        step_task: asyncio.Task,
    ) -> None:
        interval = max(min(float(self.lease_seconds) / 3.0, 30.0), 1.0)
        while not stop_event.is_set():
            started = time.perf_counter()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                pass
            renew_started = time.perf_counter()
            ok = await renew_step_claim_async(step_id, claim_token=claim_token, lease_seconds=self.lease_seconds)
            renew_elapsed_ms = (time.perf_counter() - renew_started) * 1000.0
            heartbeat_late_ms = max((time.perf_counter() - started - interval) * 1000.0, 0.0)
            lease_remaining_ms = max((float(self.lease_seconds) - interval) * 1000.0, 0.0)
            log_lease_safety(
                step_id=step_id,
                lease_remaining_ms=lease_remaining_ms,
                heartbeat_late_ms=heartbeat_late_ms,
                renew_elapsed_ms=renew_elapsed_ms,
            )
            if not ok:
                # The step is no longer ours: either the lease expired and another
                # worker re-claimed it, or it was terminalized out from under us.
                # If the step task is already finishing (stop requested), this is a
                # benign completion race — do nothing. Otherwise cancel the handler
                # so two workers can't execute the same step concurrently.
                if stop_event.is_set():
                    return
                logger.warning("Workflow step lease renewal failed; cancelling handler: step_id=%s", step_id)
                lease_state["lost"] = True
                step_task.cancel()
                return
