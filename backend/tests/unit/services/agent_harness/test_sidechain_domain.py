from __future__ import annotations

import pytest

from app.services.agent_harness.runtime.sidechain.domain import (
    SIDECHAIN_TERMINAL_STATUSES,
    SidechainIdentity,
    SidechainStatus,
    assert_valid_transition,
    is_retryable_terminal_status,
)


def test_sidechain_identity_requires_parent_and_task_linkage() -> None:
    identity = SidechainIdentity(
        task_id="sub-123",
        parent_conversation_id="conv-1",
        parent_run_id="run-1",
        parent_tool_call_id="functions.Agent:1",
        parent_usage_log_id=42,
        child_run_id="sub-123",
    )

    assert identity.to_event_identity() == {
        "task_id": "sub-123",
        "parent_conversation_id": "conv-1",
        "parent_run_id": "run-1",
        "parent_tool_call_id": "functions.Agent:1",
        "parent_usage_log_id": 42,
        "child_run_id": "sub-123",
    }


def test_sidechain_status_taxonomy_includes_required_lifecycle_states() -> None:
    assert {status.value for status in SidechainStatus} >= {
        "created",
        "started",
        "progress",
        "completed",
        "failed",
        "cancelled",
    }


def test_sidechain_terminal_statuses_are_immutable_and_retryable_rules_are_stable() -> None:
    assert SIDECHAIN_TERMINAL_STATUSES == {
        SidechainStatus.COMPLETED,
        SidechainStatus.FAILED,
        SidechainStatus.CANCELLED,
    }
    assert is_retryable_terminal_status(SidechainStatus.FAILED) is True
    assert is_retryable_terminal_status(SidechainStatus.CANCELLED) is True
    assert is_retryable_terminal_status(SidechainStatus.COMPLETED) is False


def test_sidechain_transition_rejects_stale_progress_after_terminal_state() -> None:
    with pytest.raises(ValueError):
        assert_valid_transition(SidechainStatus.FAILED, SidechainStatus.PROGRESS)

    assert_valid_transition(SidechainStatus.CREATED, SidechainStatus.STARTED)
    assert_valid_transition(SidechainStatus.STARTED, SidechainStatus.COMPLETED)
    assert_valid_transition(SidechainStatus.FAILED, SidechainStatus.FAILED)
