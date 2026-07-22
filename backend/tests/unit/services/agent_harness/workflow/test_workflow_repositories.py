from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import HarnessAgentActivity, HarnessAgentRun, HarnessAgentStep, HarnessConversation
from app.services.agent_harness.workflow.contracts import StepSpec
from app.services.agent_harness.workflow import repositories
from app.services.agent_harness.workflow.status import (
    RUN_STATUS_CANCELLED,
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_QUEUED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_WAITING_INPUT,
    NATIVE_STEP_TYPES,
    STEP_APPLY_USER_INPUT,
    STEP_RENDER_CONTEXT,
    STEP_PREPARE_SKILL,
    STEP_PLAN_LIFECYCLE,
    STEP_STATUS_CLAIMED,
    STEP_STATUS_CANCELLED,
    STEP_STATUS_QUEUED,
    STEP_STATUS_RUNNING,
    STEP_STATUS_SUCCEEDED,
)


def _utc_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _insert_conversation(
    conversation_id: str = "wf-conv",
    user_id: int = 7,
    *,
    parent_usage_log_id: int | None = None,
) -> None:
    with harness_sync_session_scope() as session:
        session.add(
            HarnessConversation(
                conversation_id=conversation_id,
                user_id=user_id,
                workspace_dir=f"/tmp/{conversation_id}",
                title="workflow",
                parent_usage_log_id=parent_usage_log_id,
            )
        )


def test_create_run_creates_first_step_and_marks_conversation_active():
    _insert_conversation("wf-create")

    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-create",
        kind="message",
        input={"content": "hello"},
        idempotency_key="wf-create:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT, input={"kind": "message", "payload": {"content": "hello"}}),
    )

    assert run.created is True
    assert run.status == RUN_STATUS_QUEUED
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, "wf-create")
        steps = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).all()
        assert conversation is not None
        assert conversation.active_run_id == run.run_id
        assert "current_step_type" not in dict(conversation.runtime_snapshot_json or {})
        assert len(steps) == 1
        assert steps[0].step_type == STEP_RENDER_CONTEXT
        assert steps[0].status == STEP_STATUS_QUEUED


def test_create_run_inherits_conversation_parent_usage_log_id_when_missing():
    _insert_conversation("wf-parent-usage", parent_usage_log_id=321)

    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-parent-usage",
        kind="message",
        input={"content": "hello"},
        idempotency_key="wf-parent-usage:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT, input={"kind": "message"}),
    )

    assert run.parent_usage_log_id == 321
    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        assert stored_run.parent_usage_log_id == 321


def test_enqueue_message_run_creates_prepare_skill_first_step():
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_message_run
    import asyncio

    _insert_conversation("wf-enqueue")

    run = asyncio.run(
        enqueue_message_run(
            user_id=7,
            conversation_id="wf-enqueue",
            payload={"content": "hello"},
            idempotency_key="wf-enqueue:message",
            wake_worker=False,
        )
    )

    with harness_sync_session_scope() as session:
        step = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).one()
        assert step.step_type == STEP_PREPARE_SKILL


def test_enqueue_plan_runs_create_plan_lifecycle_first_step():
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_revise_plan_run, enqueue_start_plan_run
    import asyncio

    _insert_conversation("wf-start-plan")
    _insert_conversation("wf-revise-plan")

    start_run = asyncio.run(
        enqueue_start_plan_run(
            user_id=7,
            conversation_id="wf-start-plan",
            payload={"language": "zh"},
            idempotency_key="wf-start-plan:start",
            wake_worker=False,
        )
    )
    revise_run = asyncio.run(
        enqueue_revise_plan_run(
            user_id=7,
            conversation_id="wf-revise-plan",
            payload={"instruction": "revise"},
            idempotency_key="wf-revise-plan:revise",
            wake_worker=False,
        )
    )

    with harness_sync_session_scope() as session:
        start_step = session.query(HarnessAgentStep).filter_by(run_id=start_run.run_id).one()
        revise_step = session.query(HarnessAgentStep).filter_by(run_id=revise_run.run_id).one()
        assert start_step.step_type == STEP_PLAN_LIFECYCLE
        assert revise_step.step_type == STEP_PLAN_LIFECYCLE


def test_enqueue_start_plan_terminalizes_waiting_plan_gate_run():
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_start_plan_run
    import asyncio

    _insert_conversation("wf-start-from-waiting")
    waiting_run = repositories.create_run(
        user_id=7,
        conversation_id="wf-start-from-waiting",
        kind="message",
        input={},
        idempotency_key="wf-start-from-waiting:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=waiting_run.run_id).one()
        stored_run.status = RUN_STATUS_WAITING_INPUT
        stored_step = session.query(HarnessAgentStep).filter_by(run_id=waiting_run.run_id).one()
        stored_step.status = STEP_STATUS_QUEUED

    start_run = asyncio.run(
        enqueue_start_plan_run(
            user_id=7,
            conversation_id="wf-start-from-waiting",
            payload={"language": "zh"},
            idempotency_key="wf-start-from-waiting:start",
            wake_worker=False,
        )
    )

    assert start_run.run_id != waiting_run.run_id
    with harness_sync_session_scope() as session:
        old_run = session.query(HarnessAgentRun).filter_by(run_id=waiting_run.run_id).one()
        old_step = session.query(HarnessAgentStep).filter_by(run_id=waiting_run.run_id).one()
        new_step = session.query(HarnessAgentStep).filter_by(run_id=start_run.run_id).one()
        assert old_run.status == RUN_STATUS_COMPLETED
        assert old_step.status == STEP_STATUS_CANCELLED
        assert new_step.step_type == STEP_PLAN_LIFECYCLE


def test_enqueue_start_plan_preserves_planning_outline_snapshot():
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_start_plan_run
    import asyncio

    conversation_id = "wf-start-preserves-outline"
    _insert_conversation(conversation_id)
    waiting_run = repositories.create_run(
        user_id=7,
        conversation_id=conversation_id,
        kind="message",
        input={},
        idempotency_key=f"{conversation_id}:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    plan_state = {
        "status": "planning_ready",
        "outline_state": {
            "outline_id": "outline-1",
            "version": 1,
            "title": "Birth data workbook",
            "items": [{"id": "sheet-1", "title": "Data sheet"}],
        },
        "execution_state": {"status": "planning_ready", "outline_id": "outline-1"},
    }
    outline_runtime = {"current_outline": plan_state["outline_state"]}
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        assert conversation is not None
        conversation.phase = "planning_ready"
        conversation.runtime_status = RUN_STATUS_WAITING_INPUT
        conversation.run_state = RUN_STATUS_WAITING_INPUT
        conversation.turn_status = RUN_STATUS_WAITING_INPUT
        conversation.active_run_id = waiting_run.run_id
        conversation.runtime_snapshot_json = {
            "phase": "planning_ready",
            "runtime_status": RUN_STATUS_WAITING_INPUT,
            "run_state": RUN_STATUS_WAITING_INPUT,
            "turn_status": RUN_STATUS_WAITING_INPUT,
            "run_id": waiting_run.run_id,
            "plan_state": plan_state,
            "outline_runtime": outline_runtime,
        }
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=waiting_run.run_id).one()
        stored_run.status = RUN_STATUS_WAITING_INPUT

    start_run = asyncio.run(
        enqueue_start_plan_run(
            user_id=7,
            conversation_id=conversation_id,
            payload={"language": "zh"},
            idempotency_key=f"{conversation_id}:start",
            wake_worker=False,
        )
    )

    assert start_run.run_id != waiting_run.run_id
    with harness_sync_session_scope() as session:
        conversation = session.get(HarnessConversation, conversation_id)
        assert conversation is not None
        snapshot = dict(conversation.runtime_snapshot_json or {})
        assert snapshot["run_id"] == start_run.run_id
        assert snapshot["plan_state"]["outline_state"]["outline_id"] == "outline-1"
        assert snapshot["outline_runtime"]["current_outline"]["outline_id"] == "outline-1"


def test_resume_interaction_reuses_waiting_workflow_run():
    from app.services.agent_harness.agent_run.control.enqueue_service import enqueue_resume_interaction_run
    import asyncio

    _insert_conversation("wf-resume")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-resume",
        kind="message",
        input={},
        idempotency_key="wf-resume:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        stored_run.status = RUN_STATUS_WAITING_INPUT

    resumed = asyncio.run(
        enqueue_resume_interaction_run(
            user_id=7,
            conversation_id="wf-resume",
            payload={"answer": "ok"},
            idempotency_key="wf-resume:resume",
            wake_worker=False,
        )
    )

    assert resumed.run_id == run.run_id
    with harness_sync_session_scope() as session:
        steps = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).all()
        assert {step.step_type for step in steps} == {STEP_RENDER_CONTEXT, STEP_APPLY_USER_INPUT}
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        assert stored_run.status == "running"


def test_all_native_step_types_have_handlers():
    from app.services.agent_harness.workflow.handlers import HANDLERS

    assert NATIVE_STEP_TYPES.issubset(set(HANDLERS))


def test_workflow_runtime_path_does_not_import_run_level_executor():
    root = Path(__file__).resolve().parents[5] / "app" / "services" / "agent_harness"
    scanned = [
        *(root / "workflow").glob("*.py"),
    ]

    forbidden = (
        "HarnessEngine",
        "dispatch_agent_run",
        "AgentRunExecutor",
        "execution_context",
        "heartbeat_loop",
        "cancellation_watch_loop",
    )
    for path in scanned:
        text = path.read_text(encoding="utf-8")
        assert not any(token in text for token in forbidden), path

    execution_dir = root / "agent_run" / "execution"
    assert not list(execution_dir.glob("*.py")) if execution_dir.exists() else True


def test_application_runtime_no_longer_instantiates_legacy_harness_engine():
    app_root = Path(__file__).resolve().parents[5] / "app"
    offenders: list[Path] = []
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "HarnessEngine(" in text or "import HarnessEngine" in text:
            offenders.append(path)
    assert offenders == []


def _validation_outcome(tool_name: str, *, call_id: str, output: str = "Invalid parameters: bad payload") -> dict:
    return {
        "tool_index": 0,
        "tool_name": tool_name,
        "call_id": call_id,
        "status": "failed",
        "is_error": True,
        "result_payload": {
            "tool": tool_name,
            "tool_call_id": call_id,
            "output": output,
            "metadata": {},
            "review": {"summary": output, "output_excerpt": output},
        },
    }


def _insert_persist_step(
    *,
    run_id: str,
    conversation_id: str,
    step_id: str,
    outcomes: list[dict],
    outcome_index: int,
) -> int:
    with harness_sync_session_scope() as session:
        step = HarnessAgentStep(
            step_id=step_id,
            run_id=run_id,
            conversation_id=conversation_id,
            user_id=7,
            step_type="persist_tool_result",
            status=STEP_STATUS_SUCCEEDED,
            input_json={
                "payload": {},
                "turn": 0,
                "tool_calls": [],
                "segment_start_index": 0,
                "next_tool_index": len(outcomes),
                "outcomes": outcomes,
                "outcome_index": outcome_index,
            },
            attempts=1,
            max_attempts=1,
            priority=0,
            idempotency_key=step_id,
        )
        session.add(step)
        session.flush()
        return int(step.id)


def test_count_consecutive_tool_validation_failures_reads_current_segment_outcome():
    conversation_id = "wf-validation-current-outcome"
    _insert_conversation(conversation_id)
    run = repositories.create_run(
        user_id=7,
        conversation_id=conversation_id,
        kind="message",
        input={},
        idempotency_key=f"{conversation_id}:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    previous_id = _insert_persist_step(
        run_id=run.run_id,
        conversation_id=conversation_id,
        step_id="wf-validation-current-outcome:previous",
        outcomes=[
            _validation_outcome("read_file", call_id="call-read"),
            _validation_outcome("request_plan_approval", call_id="call-plan"),
        ],
        outcome_index=1,
    )

    assert (
        repositories.count_consecutive_tool_validation_failures(
            run_id=run.run_id,
            before_step_pk=previous_id + 1,
            tool_name="request_plan_approval",
        )
        == 1
    )
    assert (
        repositories.count_consecutive_tool_validation_failures(
            run_id=run.run_id,
            before_step_pk=previous_id + 1,
            tool_name="read_file",
        )
        == 0
    )


def test_count_consecutive_tool_validation_failures_still_breaks_by_tool_name():
    conversation_id = "wf-validation-break-tool"
    _insert_conversation(conversation_id)
    run = repositories.create_run(
        user_id=7,
        conversation_id=conversation_id,
        kind="message",
        input={},
        idempotency_key=f"{conversation_id}:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    _insert_persist_step(
        run_id=run.run_id,
        conversation_id=conversation_id,
        step_id="wf-validation-break-tool:first",
        outcomes=[_validation_outcome("ask_user", call_id="call-ask")],
        outcome_index=0,
    )
    latest_id = _insert_persist_step(
        run_id=run.run_id,
        conversation_id=conversation_id,
        step_id="wf-validation-break-tool:second",
        outcomes=[_validation_outcome("request_plan_approval", call_id="call-plan")],
        outcome_index=0,
    )

    assert (
        repositories.count_consecutive_tool_validation_failures(
            run_id=run.run_id,
            before_step_pk=latest_id + 1,
            tool_name="request_plan_approval",
        )
        == 1
    )


def test_claim_renew_and_complete_step_requires_claim_token():
    _insert_conversation("wf-claim")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-claim",
        kind="message",
        input={},
        idempotency_key="wf-claim:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )

    claimed = repositories.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.run_id == run.run_id
    assert claimed.status == STEP_STATUS_CLAIMED
    assert claimed.claim_token

    running = repositories.mark_step_running(claimed.step_id, claim_token=claimed.claim_token)
    assert running is not None
    assert running.status == STEP_STATUS_RUNNING

    assert repositories.renew_step_claim(claimed.step_id, claim_token="bad", lease_seconds=60) is False
    assert repositories.renew_step_claim(claimed.step_id, claim_token=claimed.claim_token, lease_seconds=60) is True

    assert (
        repositories.complete_step(
            claimed.step_id,
            claim_token="bad",
            status=STEP_STATUS_SUCCEEDED,
            terminal_run=True,
        )
        is None
    )
    completed = repositories.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token,
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={"runtime_status": "completed"},
        terminal_run=True,
    )
    assert completed is not None
    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        conversation = session.get(HarnessConversation, "wf-claim")
        assert stored_run.status == "completed"
        assert conversation is not None
        assert conversation.active_run_id is None
        assert "current_step_type" not in dict(conversation.runtime_snapshot_json or {})


def test_recover_stuck_running_run_without_remaining_steps():
    _insert_conversation("wf-stuck")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-stuck",
        kind="message",
        input={},
        idempotency_key="wf-stuck:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )

    claimed = repositories.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.claim_token
    assert repositories.mark_step_running(claimed.step_id, claim_token=claimed.claim_token) is not None
    completed = repositories.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token,
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={"runtime_status": RUN_STATUS_RUNNING, "run_state": "rendering_context"},
        terminal_run=False,
    )
    assert completed is not None

    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        stored_run.status = RUN_STATUS_RUNNING
        stored_run.updated_at = _utc_naive() - timedelta(seconds=300)
        conversation = session.get(HarnessConversation, "wf-stuck")
        assert conversation is not None
        conversation.active_run_id = run.run_id
        conversation.runtime_status = RUN_STATUS_RUNNING

    assert repositories.recover_stuck_running_runs(grace_seconds=1) == 1

    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        conversation = session.get(HarnessConversation, "wf-stuck")
        assert stored_run.status == RUN_STATUS_FAILED
        assert stored_run.last_error_type == "stuck_running_run"
        assert conversation is not None
        assert conversation.active_run_id is None
        assert conversation.runtime_status == RUN_STATUS_FAILED
        assert (conversation.runtime_snapshot_json or {}).get("failure", {}).get("error_type") == "stuck_running_run"


def test_recover_stuck_running_run_with_published_artifact_completes(monkeypatch):
    # A stuck run whose artifact is already published should be recovered as
    # COMPLETED, not FAILED — the deliverable exists (e.g. the post-publish finalize
    # step was lost to a duplicate idempotency key).
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.artifacts.manifest.read_artifact_manifest",
        lambda _user_id, _conversation_id: {"entry": "index.html", "publication": {"status": "published"}},
    )
    _insert_conversation("wf-stuck-published")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-stuck-published",
        kind="message",
        input={},
        idempotency_key="wf-stuck-published:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    claimed = repositories.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    assert repositories.mark_step_running(claimed.step_id, claim_token=claimed.claim_token) is not None
    assert repositories.complete_step(
        claimed.step_id,
        claim_token=claimed.claim_token,
        status=STEP_STATUS_SUCCEEDED,
        runtime_patch={"runtime_status": RUN_STATUS_RUNNING, "run_state": "finalizing"},
        terminal_run=False,
    ) is not None

    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        stored_run.status = RUN_STATUS_RUNNING
        stored_run.updated_at = _utc_naive() - timedelta(seconds=300)
        conversation = session.get(HarnessConversation, "wf-stuck-published")
        assert conversation is not None
        conversation.active_run_id = run.run_id
        conversation.runtime_status = RUN_STATUS_RUNNING

    assert repositories.recover_stuck_running_runs(grace_seconds=1) == 1

    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        conversation = session.get(HarnessConversation, "wf-stuck-published")
        assert stored_run.status == RUN_STATUS_COMPLETED
        assert stored_run.last_error_type is None
        assert conversation is not None
        assert conversation.runtime_status == RUN_STATUS_COMPLETED
        assert conversation.active_run_id is None


def test_update_step_checkpoint_requires_claim_token():
    _insert_conversation("wf-checkpoint")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-checkpoint",
        kind="message",
        input={},
        idempotency_key="wf-checkpoint:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )

    claimed = repositories.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    assert claimed.run_id == run.run_id
    assert claimed.claim_token

    assert (
        repositories.update_step_checkpoint(
            claimed.step_id,
            claim_token="bad",
            patch={"stream": {"delta_index": 1}},
        )
        is None
    )
    updated = repositories.update_step_checkpoint(
        claimed.step_id,
        claim_token=claimed.claim_token,
        patch={"stream": {"delta_index": 1}},
    )
    merged = repositories.update_step_checkpoint(
        claimed.step_id,
        claim_token=claimed.claim_token,
        patch={"stream": {"block_id": "block-1"}},
    )

    assert updated is not None
    assert updated.checkpoint == {"stream": {"delta_index": 1}}
    assert merged is not None
    assert merged.checkpoint == {"stream": {"delta_index": 1, "block_id": "block-1"}}
    with harness_sync_session_scope() as session:
        step = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).one()
        assert step.checkpoint_json == {"stream": {"delta_index": 1, "block_id": "block-1"}}


def test_expired_claimed_step_can_be_reclaimed():
    _insert_conversation("wf-reclaim")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-reclaim",
        kind="message",
        input={},
        idempotency_key="wf-reclaim:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    expired = _utc_naive() - timedelta(seconds=30)
    with harness_sync_session_scope() as session:
        step = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).one()
        step.status = STEP_STATUS_RUNNING
        step.claim_owner = "dead-worker"
        step.claim_token = "old-token"
        step.claim_expires_at = expired

    reclaimed = repositories.claim_next_step(worker_id="worker-b", lease_seconds=60)
    assert reclaimed is not None
    assert reclaimed.run_id == run.run_id
    assert reclaimed.claim_owner == "worker-b"
    assert reclaimed.claim_token != "old-token"


def test_cancel_flag_terminalizes_queued_run():
    _insert_conversation("wf-cancel")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-cancel",
        kind="message",
        input={},
        idempotency_key="wf-cancel:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )

    assert repositories.request_cancel("wf-cancel", reason="user") is True
    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        step = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).one()
        conversation = session.get(HarnessConversation, "wf-cancel")
        assert stored_run.status == RUN_STATUS_CANCELLED
        assert stored_run.cancel_requested is True
        assert step.status == RUN_STATUS_CANCELLED
        assert conversation is not None
        assert conversation.active_run_id is None
        assert conversation.runtime_status == RUN_STATUS_CANCELLED


def test_cancel_flag_keeps_running_run_active_but_conversation_cancelled():
    _insert_conversation("wf-cancel-running")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-cancel-running",
        kind="message",
        input={},
        idempotency_key="wf-cancel-running:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT),
    )
    claimed = repositories.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None and claimed.run_id == run.run_id
    repositories.mark_step_running(claimed.step_id, claim_token=claimed.claim_token or "")

    assert repositories.request_cancel("wf-cancel-running", reason="user") is True
    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        step = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).one()
        conversation = session.get(HarnessConversation, "wf-cancel-running")
        assert stored_run.status == RUN_STATUS_RUNNING
        assert stored_run.cancel_requested is True
        assert step.status == STEP_STATUS_RUNNING
        assert conversation is not None
        assert conversation.runtime_status == RUN_STATUS_CANCELLED
        assert conversation.run_state == "cancelling"
        assert conversation.runtime_snapshot_json["runtime_status"] == RUN_STATUS_CANCELLED


def test_release_step_for_retry_requeues_without_terminalizing_run():
    _insert_conversation("wf-retry")
    run = repositories.create_run(
        user_id=7,
        conversation_id="wf-retry",
        kind="message",
        input={},
        idempotency_key="wf-retry:message",
        first_step=StepSpec(step_type=STEP_RENDER_CONTEXT, max_attempts=3),
    )
    claimed = repositories.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None and claimed.claim_token
    repositories.mark_step_running(claimed.step_id, claim_token=claimed.claim_token)

    assert repositories.release_step_for_retry(
        claimed.step_id,
        claim_token=claimed.claim_token,
        error_type="TransientFailure",
        error_summary="temporary",
        retry_delay_seconds=0,
    )

    with harness_sync_session_scope() as session:
        stored_run = session.query(HarnessAgentRun).filter_by(run_id=run.run_id).one()
        step = session.query(HarnessAgentStep).filter_by(run_id=run.run_id).one()
        assert stored_run.status == RUN_STATUS_QUEUED
        assert step.status == STEP_STATUS_QUEUED
        assert step.claim_token is None
        assert step.attempts == 1


def test_record_activity_bounds_long_activity_id_and_keeps_idempotency():
    long_activity_id = (
        "run:"
        + "r" * 80
        + ":step:"
        + "s" * 80
        + ":activity:model_turn:1:recovered"
    )

    repositories.record_activity(
        activity_id=long_activity_id,
        run_id="run-long-activity",
        step_id="step-long-activity",
        conversation_id="wf-long-activity",
        activity_type="model_turn",
        status="running",
        attempt=1,
        diagnostics={"attempt": 1},
    )
    repositories.record_activity(
        activity_id=long_activity_id,
        run_id="run-long-activity",
        step_id="step-long-activity",
        conversation_id="wf-long-activity",
        activity_type="model_turn",
        status="succeeded",
        attempt=1,
        diagnostics={"attempt": 1, "done": True},
    )

    with harness_sync_session_scope() as session:
        rows = session.query(HarnessAgentActivity).filter_by(run_id="run-long-activity").all()
        assert len(rows) == 1
        assert len(rows[0].activity_id) <= 120
        assert rows[0].activity_id.endswith(repositories._activity_id(long_activity_id)[-25:])
        assert rows[0].status == "succeeded"
        assert rows[0].diagnostics_json == {"attempt": 1, "done": True}
