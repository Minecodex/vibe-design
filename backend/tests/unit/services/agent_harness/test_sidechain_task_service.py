from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.sidechain.domain import SidechainIdentity, SidechainStatus
from app.services.agent_harness.runtime.sidechain.service import SidechainTaskService


def _identity() -> SidechainIdentity:
    return SidechainIdentity(
        task_id="sub-task-1",
        parent_conversation_id="conv-1",
        parent_run_id="run-parent",
        parent_tool_call_id="functions.Agent:1",
        child_run_id="sub-task-1",
    )


def test_sidechain_task_service_records_normal_completion() -> None:
    events: list[dict] = []
    service = SidechainTaskService(event_appender=events.append)

    service.create(identity=_identity(), label="Worker", objective="build.asset", context_mode="fork")
    service.transition("sub-task-1", SidechainStatus.STARTED)
    service.transition("sub-task-1", SidechainStatus.COMPLETED, summary="Done", result_ref=".agent/results/sub-task-1.json")

    task = service.get("sub-task-1")
    assert task.status == SidechainStatus.COMPLETED
    assert task.summary == "Done"
    assert task.result_ref == ".agent/results/sub-task-1.json"
    assert [event["status"] for event in events] == ["created", "started", "completed"]


def test_sidechain_task_service_keeps_terminal_state_immutable_and_idempotent() -> None:
    events: list[dict] = []
    service = SidechainTaskService(event_appender=events.append)

    service.create(identity=_identity(), label="Worker", objective="build.asset", context_mode="fork")
    failed = service.transition("sub-task-1", SidechainStatus.FAILED, summary="Failed")
    repeated = service.transition("sub-task-1", SidechainStatus.FAILED, summary="Older failure")

    assert repeated is failed
    assert service.get("sub-task-1").summary == "Failed"
    assert [event["status"] for event in events] == ["created", "failed"]

    stale = service.transition("sub-task-1", SidechainStatus.PROGRESS, summary="stale progress")
    conflicting_terminal = service.transition("sub-task-1", SidechainStatus.COMPLETED, summary="late completion")

    assert stale is failed
    assert conflicting_terminal is failed
    assert service.get("sub-task-1").summary == "Failed"
    assert [event["status"] for event in events] == ["created", "failed"]


def test_sidechain_task_service_preserves_cancelled_partial_metadata() -> None:
    service = SidechainTaskService()
    service.create(identity=_identity(), label="Worker", objective="build.asset", context_mode="fork")

    service.transition(
        "sub-task-1",
        SidechainStatus.CANCELLED,
        summary="Cancelled by user",
        transcript_ref=".agent/transcripts/sub-task-1.jsonl",
        usage_summary={"multimodal_calls": 1},
    )

    task = service.get("sub-task-1")
    assert task.status == SidechainStatus.CANCELLED
    assert task.transcript_ref == ".agent/transcripts/sub-task-1.jsonl"
    assert task.usage_summary == {"multimodal_calls": 1}


def test_sidechain_task_service_reports_missing_task() -> None:
    service = SidechainTaskService()

    with pytest.raises(KeyError):
        service.transition("missing", SidechainStatus.STARTED)
