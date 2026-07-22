from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import HarnessAgentRun, HarnessAgentStep, HarnessConversation
from app.services.agent_harness.workflow import repositories as workflow_repository
from app.services.agent_harness.workflow.contracts import StepSpec
from app.services.agent_harness.workflow.status import (
    RUN_KIND_MESSAGE,
    RUN_STATUS_WAITING_INPUT,
    STEP_APPLY_USER_INPUT,
    STEP_RENDER_CONTEXT,
    STEP_PREPARE_SKILL,
    STEP_STATUS_CLAIMED,
    STEP_STATUS_FAILED,
    STEP_STATUS_QUEUED,
    STEP_STATUS_RUNNING,
    STEP_STATUS_WAITING_INPUT,
)


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _insert_conversation(conversation_id: str, user_id: int = 7) -> None:
    with harness_sync_session_scope() as session:
        session.add(
            HarnessConversation(
                conversation_id=conversation_id,
                user_id=user_id,
                workspace_dir=f"/tmp/{conversation_id}",
                title="t",
            )
        )


def _create_workflow_run(
    *,
    conversation_id: str,
    run_id: str,
    idempotency_key: str,
    priority: int = 0,
):
    return workflow_repository.create_run(
        user_id=7,
        conversation_id=conversation_id,
        kind=RUN_KIND_MESSAGE,
        input={"payload_version": 2},
        idempotency_key=idempotency_key,
        run_id=run_id,
        first_step=StepSpec(
            step_type=STEP_PREPARE_SKILL,
            input={"kind": RUN_KIND_MESSAGE, "payload": {"payload_version": 2}},
            priority=priority,
            max_attempts=3,
            idempotency_key=f"run:{run_id}:step:{STEP_PREPARE_SKILL}:0",
        ),
        reject_active_conflicts=False,
    )


def _step_for_run(run_id: str) -> HarnessAgentStep:
    with harness_sync_session_scope() as session:
        return session.query(HarnessAgentStep).filter_by(run_id=run_id).one()


def test_claim_skips_when_same_conversation_has_active_step():
    _insert_conversation("conv-a")
    _create_workflow_run(conversation_id="conv-a", run_id="run-live", idempotency_key="conv-a:live", priority=10)
    _create_workflow_run(conversation_id="conv-a", run_id="run-queued", idempotency_key="conv-a:queued", priority=9)

    first = workflow_repository.claim_next_step(worker_id="worker-A", lease_seconds=30)
    second = workflow_repository.claim_next_step(worker_id="worker-B", lease_seconds=30)

    assert first is not None
    assert first.run_id == "run-live"
    assert second is None
    with harness_sync_session_scope() as session:
        live = session.query(HarnessAgentStep).filter_by(run_id="run-live").one()
        queued = session.query(HarnessAgentStep).filter_by(run_id="run-queued").one()
        assert live.status == STEP_STATUS_CLAIMED
        assert queued.status == STEP_STATUS_QUEUED


def test_claim_picks_up_step_when_no_other_active_in_conversation():
    _insert_conversation("conv-b")
    _create_workflow_run(conversation_id="conv-b", run_id="run-fresh", idempotency_key="conv-b:fresh")

    claimed = workflow_repository.claim_next_step(worker_id="worker-1", lease_seconds=30)

    assert claimed is not None
    assert claimed.run_id == "run-fresh"
    assert claimed.status == STEP_STATUS_CLAIMED
    assert claimed.claim_owner == "worker-1"
    assert claimed.attempts == 1


def test_claim_reclaims_step_whose_lease_expired():
    _insert_conversation("conv-c")
    _create_workflow_run(conversation_id="conv-c", run_id="run-stale", idempotency_key="conv-c:stale")
    first = workflow_repository.claim_next_step(worker_id="dead-worker", lease_seconds=30)
    assert first is not None
    with harness_sync_session_scope() as session:
        step = session.query(HarnessAgentStep).filter_by(run_id="run-stale").one()
        step.status = STEP_STATUS_RUNNING
        step.claim_expires_at = _utc_naive() - timedelta(seconds=120)

    claimed = workflow_repository.claim_next_step(worker_id="worker-rescuer", lease_seconds=30)

    assert claimed is not None
    assert claimed.run_id == "run-stale"
    assert claimed.claim_owner == "worker-rescuer"
    assert claimed.attempts == 2


def test_claim_two_steps_in_different_conversations_both_picked_up():
    _insert_conversation("conv-d1")
    _insert_conversation("conv-d2")
    _create_workflow_run(conversation_id="conv-d1", run_id="run-d1", idempotency_key="conv-d1:k")
    _create_workflow_run(conversation_id="conv-d2", run_id="run-d2", idempotency_key="conv-d2:k")

    first = workflow_repository.claim_next_step(worker_id="w-1", lease_seconds=30)
    second = workflow_repository.claim_next_step(worker_id="w-2", lease_seconds=30)

    assert first is not None
    assert second is not None
    assert {first.run_id, second.run_id} == {"run-d1", "run-d2"}


def test_active_step_with_live_lease_is_not_claimable():
    _insert_conversation("conv-live")
    _create_workflow_run(conversation_id="conv-live", run_id="run-live", idempotency_key="conv-live:k")
    first = workflow_repository.claim_next_step(worker_id="other-worker", lease_seconds=30)
    assert first is not None

    claimed = workflow_repository.claim_next_step(worker_id="me", lease_seconds=30)

    assert claimed is None


def test_terminalize_blocked_clears_claim_fields():
    _insert_conversation("conv-blocked-terminal")
    _create_workflow_run(
        conversation_id="conv-blocked-terminal",
        run_id="run-blocked-terminal",
        idempotency_key="conv-blocked-terminal:k",
    )

    claimed = workflow_repository.claim_next_step(worker_id="worker-blocked", lease_seconds=30)
    assert claimed is not None

    terminalized = workflow_repository.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token or "",
        status=STEP_STATUS_FAILED,
        terminal_run=True,
    )

    assert terminalized is not None
    assert terminalized.status == STEP_STATUS_FAILED
    assert terminalized.claim_owner is None
    assert terminalized.claim_token is None
    assert terminalized.claim_expires_at is None
    assert terminalized.finished_at is not None


def test_terminalize_waiting_input_releases_worker_claim():
    _insert_conversation("conv-waiting-terminal")
    _create_workflow_run(
        conversation_id="conv-waiting-terminal",
        run_id="run-waiting-terminal",
        idempotency_key="conv-waiting-terminal:k",
    )

    claimed = workflow_repository.claim_next_step(worker_id="worker-waiting", lease_seconds=30)
    assert claimed is not None

    terminalized = workflow_repository.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token or "",
        status=STEP_STATUS_WAITING_INPUT,
        terminal_run=True,
    )

    assert terminalized is not None
    assert terminalized.status == STEP_STATUS_WAITING_INPUT
    assert terminalized.claim_owner is None
    assert terminalized.claim_token is None
    assert terminalized.claim_expires_at is None


def test_claim_skips_regular_queued_step_for_waiting_input_run():
    _insert_conversation("conv-waiting-skip")
    _create_workflow_run(
        conversation_id="conv-waiting-skip",
        run_id="run-waiting-skip",
        idempotency_key="conv-waiting-skip:k",
    )
    with harness_sync_session_scope() as session:
        run = session.query(HarnessAgentRun).filter_by(run_id="run-waiting-skip").one()
        step = session.query(HarnessAgentStep).filter_by(run_id="run-waiting-skip").one()
        run.status = RUN_STATUS_WAITING_INPUT
        step.step_type = STEP_RENDER_CONTEXT
        step.status = STEP_STATUS_QUEUED

    claimed = workflow_repository.claim_next_step(worker_id="worker-waiting-skip", lease_seconds=30)

    assert claimed is None
    with harness_sync_session_scope() as session:
        step = session.query(HarnessAgentStep).filter_by(run_id="run-waiting-skip").one()
        assert step.status == STEP_STATUS_QUEUED


def test_claim_allows_apply_user_input_for_waiting_input_run():
    _insert_conversation("conv-waiting-apply")
    _create_workflow_run(
        conversation_id="conv-waiting-apply",
        run_id="run-waiting-apply",
        idempotency_key="conv-waiting-apply:k",
    )
    with harness_sync_session_scope() as session:
        run = session.query(HarnessAgentRun).filter_by(run_id="run-waiting-apply").one()
        step = session.query(HarnessAgentStep).filter_by(run_id="run-waiting-apply").one()
        run.status = RUN_STATUS_WAITING_INPUT
        step.step_type = STEP_APPLY_USER_INPUT
        step.status = STEP_STATUS_QUEUED

    claimed = workflow_repository.claim_next_step(worker_id="worker-waiting-apply", lease_seconds=30)

    assert claimed is not None
    assert claimed.step_type == STEP_APPLY_USER_INPUT

