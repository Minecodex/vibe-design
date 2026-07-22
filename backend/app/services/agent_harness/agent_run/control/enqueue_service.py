from __future__ import annotations

import uuid
from typing import Any

from app.services.agent_harness.agent_coordination.run_wakeup_bus import wake_agent_run_worker
from app.services.agent_harness.runtime.eventing.event_log import append_event_async
from app.services.agent_harness.runtime.eventing.turn_protocol import (
    TURN_STARTED,
    build_turn_started_payload,
)
from app.services.agent_harness.workflow.status import (
    RUN_KIND_MESSAGE,
    RUN_KIND_RESUME_INTERACTION,
    RUN_KIND_REVISE_PLAN,
    RUN_KIND_START_PLAN,
)
from app.services.agent_harness.workflow.contracts import StepSpec
from app.services.agent_harness.workflow.repositories import (
    complete_waiting_input_runs_for_conversation_async,
    create_run_async,
    enqueue_step_async,
    get_active_run_for_conversation_async,
    set_run_parent_usage_log_id_async,
)
from app.services.agent_harness.workflow.status import RUN_STATUS_QUEUED, RUN_STATUS_WAITING_INPUT, STEP_PREPARE_SKILL
from app.services.agent_harness.workflow.status import STEP_APPLY_USER_INPUT
from app.services.agent_harness.workflow.status import STEP_PLAN_LIFECYCLE
from app.services.agent_harness.workspace.session_v2.service import get_conversation_async, update_conversation_async


def _default_max_attempts(*, kind: str, payload: dict[str, Any]) -> int:
    activity = str((payload or {}).get("activity") or "").strip().lower()
    if kind == RUN_KIND_MESSAGE and activity == "planning_outline":
        return 2
    return 1


async def _append_turn_started_event(
    *,
    user_id: int,
    conversation_id: str,
    run_id: str,
) -> None:
    conversation = await get_conversation_async(user_id, conversation_id) or {}
    runtime_profile = str(conversation.get("runtime_profile") or "home")
    await append_event_async(
        user_id,
        conversation_id,
        run_id=run_id,
        event_type=TURN_STARTED,
        payload=build_turn_started_payload(
            conversation_id=conversation_id,
            run_id=run_id,
            runtime_profile=runtime_profile,
        ),
        lane="user",
        idempotency_key=f"run:{run_id}:turn-started",
    )


async def enqueue_agent_run(
    *,
    user_id: int,
    conversation_id: str,
    kind: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    priority: int = 0,
    parent_usage_log_id: int | None = None,
    parent_billing_conversation: dict[str, Any] | None = None,
    wake_worker: bool = True,
    max_attempts: int | None = None,
):
    run_id = uuid.uuid4().hex
    if kind == RUN_KIND_RESUME_INTERACTION:
        first_step_type = STEP_APPLY_USER_INPUT
    elif kind in {RUN_KIND_START_PLAN, RUN_KIND_REVISE_PLAN}:
        first_step_type = STEP_PLAN_LIFECYCLE
    else:
        first_step_type = STEP_PREPARE_SKILL
    if kind == RUN_KIND_RESUME_INTERACTION:
        active = await get_active_run_for_conversation_async(conversation_id)
        if active is not None and active.status == RUN_STATUS_WAITING_INPUT:
            await enqueue_step_async(
                run_id=active.run_id,
                user_id=user_id,
                conversation_id=conversation_id,
                spec=StepSpec(
                    step_type=STEP_APPLY_USER_INPUT,
                    input={"kind": kind, "payload": payload},
                    priority=priority,
                    max_attempts=(
                        int(max_attempts)
                        if max_attempts is not None
                        else _default_max_attempts(kind=kind, payload=payload)
                    ),
                    idempotency_key=f"run:{active.run_id}:step:{STEP_APPLY_USER_INPUT}:{idempotency_key or uuid.uuid4().hex}",
                ),
            )
            await update_conversation_async(
                user_id,
                conversation_id,
                {
                    "run_id": active.run_id,
                    "active_run_id": active.run_id,
                    "runtime_status": "running",
                    "run_state": "queued",
                    "turn_status": "queued",
                    "status": "active",
                    "finished_at": None,
                },
            )
            if wake_worker:
                await wake_agent_run_worker()
            return active
    if kind in {RUN_KIND_START_PLAN, RUN_KIND_REVISE_PLAN}:
        active = await get_active_run_for_conversation_async(conversation_id)
        if active is not None and active.status == RUN_STATUS_WAITING_INPUT:
            await complete_waiting_input_runs_for_conversation_async(conversation_id)
    request = await create_run_async(
        user_id=user_id,
        conversation_id=conversation_id,
        kind=kind,
        input=payload,
        idempotency_key=idempotency_key or f"{kind}:{run_id}",
        run_id=run_id,
        first_step=StepSpec(
            step_type=first_step_type,
            input={"kind": kind, "payload": payload},
            priority=priority,
            max_attempts=(
                int(max_attempts)
                if max_attempts is not None
                else _default_max_attempts(kind=kind, payload=payload)
            ),
            idempotency_key=f"run:{run_id}:step:{first_step_type}:0",
        ),
        parent_usage_log_id=parent_usage_log_id,
        reject_active_conflicts=True,
    )
    if request.status == RUN_STATUS_QUEUED:
        await _append_turn_started_event(
            user_id=user_id,
            conversation_id=conversation_id,
            run_id=request.run_id,
        )
        if getattr(request, "created", False) and parent_usage_log_id is None and parent_billing_conversation is not None:
            from dataclasses import replace

            from app.services.agent_harness.runtime.execution_support.billing_controller import (
                create_run_parent_usage_log,
            )

            created_parent_id = await create_run_parent_usage_log(
                user_id=user_id,
                conversation_id=conversation_id,
                run_id=request.run_id,
                conversation=parent_billing_conversation,
            )
            await set_run_parent_usage_log_id_async(request.run_id, created_parent_id)
            request = replace(request, parent_usage_log_id=created_parent_id)
        await update_conversation_async(
            user_id,
            conversation_id,
            {
                "run_id": request.run_id,
                "active_run_id": request.run_id,
                "runtime_status": "running",
                "run_state": "queued",
                "turn_status": "queued",
                "status": "active",
                "finished_at": None,
            },
        )
        if wake_worker:
            await wake_agent_run_worker()
    return request


async def enqueue_message_run(**kwargs):
    return await enqueue_agent_run(kind=RUN_KIND_MESSAGE, **kwargs)


async def enqueue_resume_interaction_run(**kwargs):
    return await enqueue_agent_run(kind=RUN_KIND_RESUME_INTERACTION, priority=10, **kwargs)


async def enqueue_start_plan_run(**kwargs):
    return await enqueue_agent_run(kind=RUN_KIND_START_PLAN, **kwargs)


async def enqueue_revise_plan_run(**kwargs):
    return await enqueue_agent_run(kind=RUN_KIND_REVISE_PLAN, **kwargs)
