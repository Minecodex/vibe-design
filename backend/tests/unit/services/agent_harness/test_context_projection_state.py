from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db.harness_session import harness_sync_session_scope
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.workflow import repositories as workflow_repository
from app.services.agent_harness.workflow.contracts import StepSpec
from app.services.agent_harness.workflow.status import RUN_KIND_MESSAGE, STEP_PREPARE_SKILL


def test_context_projection_dirty_marks_merge_and_claim_without_touching_run_owner(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection tracer")

    workflow_repository.create_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind=RUN_KIND_MESSAGE,
        input={"payload_version": 1},
        idempotency_key="message:projection",
        run_id="run-projection",
        first_step=StepSpec(
            step_type=STEP_PREPARE_SKILL,
            input={"kind": RUN_KIND_MESSAGE, "payload": {"payload_version": 1}},
            priority=99,
            idempotency_key=f"run:run-projection:step:{STEP_PREPARE_SKILL}:0",
        ),
        reject_active_conflicts=False,
    )
    run_owner = workflow_repository.claim_next_step(worker_id="run-worker", lease_seconds=60)
    assert run_owner is not None

    from app.services.agent_harness.runtime.context_projection import (
        claim_next_projection,
        complete_projection,
        get_projection_state,
        mark_projection_dirty,
    )

    first = mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=3,
        reason="message_appended",
    )
    second = mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=5,
        reason="tool_result_recorded",
    )
    claimed = claim_next_projection(worker_id="projection-worker-a", lease_seconds=60)
    blocked = claim_next_projection(worker_id="projection-worker-b", lease_seconds=60)

    assert first["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert second["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert second["latest_observed_sequence"] == 5
    assert claimed is not None
    assert claimed["conversation_id"] == conversation["id"]
    assert claimed["target_sequence"] == 5
    assert blocked is None

    completed = complete_projection(
        conversation["id"],
        worker_id="projection-worker-a",
        lease_token=claimed["lease_token"],
        processed_sequence=5,
        completed_responsibilities=claimed["dirty_responsibilities"],
        result={"recall_path": "recall.sqlite"},
    )
    state = get_projection_state(7, conversation["id"])

    assert completed["dirty_responsibilities"] == []
    assert state["latest_processed_sequence"] == 5
    assert state["lease_owner"] is None
    assert state["last_result"]["recall_path"] == "recall.sqlite"

    from app.services.agent_harness.workspace.session_v2.state_store import read_state

    run_state = read_state(7, conversation["id"])
    assert run_state["run_owner"] == "run-worker"
    assert run_state["run_owner_token"] == run_owner.claim_token


def test_context_projection_stale_lease_can_be_reclaimed(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection stale lease")

    from app.services.agent_harness.runtime.context_projection import claim_next_projection, mark_projection_dirty
    from app.models.harness_session import ContextProjectionState

    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=9,
        reason="turn_completed",
    )
    first = claim_next_projection(worker_id="projection-worker-a", lease_seconds=60)
    assert first is not None

    with harness_sync_session_scope() as session:
        state = session.get(ContextProjectionState, conversation["id"])
        state.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        session.flush()

    second = claim_next_projection(worker_id="projection-worker-b", lease_seconds=60)

    assert second is not None
    assert second["conversation_id"] == conversation["id"]
    assert second["lease_owner"] == "projection-worker-b"
    assert second["lease_token"] != first["lease_token"]
    assert second["dirty_responsibilities"] == ["recall_sidecar_refresh"]


def test_projection_completion_preserves_dirty_state_for_newer_events(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Projection new event while running")

    from app.services.agent_harness.runtime.context_projection import (
        claim_next_projection,
        complete_projection,
        mark_projection_dirty,
    )

    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=5,
        reason="message_appended",
    )
    claimed = claim_next_projection(worker_id="projection-worker-a", lease_seconds=60)
    assert claimed is not None

    mark_projection_dirty(
        7,
        conversation["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=8,
        reason="assistant_message_finalized",
    )
    completed = complete_projection(
        conversation["id"],
        worker_id="projection-worker-a",
        lease_token=claimed["lease_token"],
        processed_sequence=5,
        completed_responsibilities=["recall_sidecar_refresh"],
    )

    assert completed["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert completed["latest_observed_sequence"] == 8
    assert completed["latest_processed_sequence"] == 0
