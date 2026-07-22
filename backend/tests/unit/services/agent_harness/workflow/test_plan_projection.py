from __future__ import annotations

import pytest

from app.services.agent_harness.authoring.planning.outline_plan import (
    build_outline_projection,
    compile_execution_plan,
    create_outline_state,
    outline_to_user_plan,
)
from app.services.agent_harness.workflow.plan_projection import (
    apply_execution_progress_projection,
    apply_plan_approval_projection,
    apply_planning_draft_projection,
    start_plan_execution_projection,
)


def _plan_state(status: str = "planning_ready") -> dict:
    outline = create_outline_state(
        artifact_type="ppt",
        title="Deck",
        summary="Build deck",
        items=[{"id": "slide-1", "title": "Intro", "summary": "Opening"}],
        status="draft",
    )
    execution = {
        **compile_execution_plan(outline),
        "status": status,
    }
    return {
        "title": "Deck",
        "summary": "Build deck",
        "status": status,
        "steps": execution["steps"],
        "outline_state": outline,
        "execution_state": execution,
        "projection_state": build_outline_projection(outline, execution),
        "user_plan": outline_to_user_plan(outline),
    }


def test_apply_planning_draft_projection_does_not_create_ready_outline():
    runtime_patch, events = apply_planning_draft_projection(
        run_id="run-1",
        step_id="step-1",
        conversation={"phase": "planning"},
        planning_draft={
            "summary": "Need more detail",
            "confirmed_inputs": {"artifact": "deck"},
            "open_questions": ["Brand?"],
        },
    )

    assert runtime_patch["phase"] == "planning"
    assert runtime_patch["runtime_status"] == "running"
    assert runtime_patch["planning_draft"]["open_questions"] == ["Brand?"]
    assert "plan_state" not in runtime_patch
    assert "outline_runtime" not in runtime_patch
    event_types = [event.event_type for event in events]
    # The domain event still leads; a live planning-draft presentation op now
    # follows it so the draft card renders without a reload (B1).
    assert event_types[0] == "planning_draft_updated"
    assert "presentation.block.upsert" in event_types
    draft_op = next(e for e in events if e.event_type == "presentation.block.upsert")
    assert draft_op.payload["block"]["ui_kind"] == "planning_draft_card"


def test_apply_plan_approval_projection_creates_only_approval_requested_outline():
    runtime_patch, events = apply_plan_approval_projection(
        run_id="run-1",
        step_id="step-1",
        conversation={"phase": "planning"},
        plan_state=_plan_state(),
    )

    assert runtime_patch["phase"] == "planning_ready"
    assert runtime_patch["runtime_status"] == "waiting_input"
    assert runtime_patch["plan_state"]["status"] == "planning_ready"
    assert runtime_patch["plan_state"]["execution_state"]["status"] == "planning_ready"
    assert runtime_patch["outline_runtime"]["current_outline"]
    assert "status" not in runtime_patch["outline_runtime"]["current_outline"]["items"][0]
    assert "progress_message" not in runtime_patch["outline_runtime"]["current_outline"]["items"][0]
    assert [event.event_type for event in events] == ["current_outline_updated"]
    assert events[0].payload["change_source"] == "approval_requested"


def test_apply_plan_approval_projection_emits_revision_applied_when_revising():
    _, events = apply_plan_approval_projection(
        run_id="run-1",
        step_id="step-1",
        conversation={"phase": "revising_plan"},
        plan_state=_plan_state(),
    )

    assert [event.event_type for event in events] == [
        "current_outline_updated",
        "plan_revision_applied",
    ]
    assert events[0].payload["change_source"] == "approval_requested"


def test_apply_execution_progress_projection_replaces_existing_card_source():
    plan_state = _plan_state(status="in_progress")
    plan_state["execution_state"] = {
        **plan_state["execution_state"],
        "status": "in_progress",
        "steps": [
            {**plan_state["execution_state"]["steps"][0], "status": "in_progress"}
        ],
    }

    runtime_patch, events = apply_execution_progress_projection(
        run_id="run-1",
        step_id="step-1",
        plan_state=plan_state,
    )

    assert runtime_patch["phase"] == "executing"
    assert runtime_patch["runtime_status"] == "running"
    assert events[0].event_type == "execution_projection_updated"
    assert events[0].payload["change_source"] == "execution_progress"


def test_start_plan_execution_projection_locks_outline_and_emits_execution_started():
    plan_state = _plan_state(status="planning_ready")
    runtime_patch, events = start_plan_execution_projection(
        run_id="run-1",
        step_id="step-1",
        conversation={"plan_state": plan_state},
        payload={
            "user_message_event": {
                "id": "plan-execution-approved:conv:plan-1:v1",
                "created_at": "2026-06-04T00:00:00.000Z",
            },
        },
    )

    assert runtime_patch["runtime_status"] == "running"
    assert runtime_patch["plan_state"]["status"] == "in_progress"
    assert runtime_patch["plan_state"]["outline_state"]["snapshot_status"] == "active"
    assert runtime_patch["plan_state"]["user_plan"]["readonly"] is True
    assert runtime_patch["run_output_anchor"] == {
        "anchor_message_id": "plan-execution-approved:conv:plan-1:v1",
        "anchor_source": "plan_execution_approved",
        "anchor_created_at": "2026-06-04T00:00:00.000Z",
    }
    assert [event.event_type for event in events] == ["execution_started"]
    assert events[0].payload["anchor_message_id"] == "plan-execution-approved:conv:plan-1:v1"


def test_start_plan_execution_projection_rejects_draft_only_or_unapproved_plan():
    plan_state = _plan_state(status="pending")
    plan_state["execution_state"] = {
        **plan_state["execution_state"],
        "status": "pending",
    }

    with pytest.raises(ValueError, match="planning_ready"):
        start_plan_execution_projection(
            run_id="run-1",
            step_id="step-1",
            conversation={"plan_state": plan_state},
        )
