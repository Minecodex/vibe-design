from app.services.agent_harness.runtime.eventing.turn_protocol import (
    TURN_COMPLETED,
    build_turn_completed_payload,
    build_turn_error,
    is_turn_completed_event,
)


def test_turn_completed_failed_payload_contains_error_and_snapshot():
    error = build_turn_error("WorkflowFailed", "render failed")

    payload = build_turn_completed_payload(
        conversation_id="conv-1",
        run_id="run-1",
        status="failed",
        runtime_snapshot={"runtime_status": "failed"},
        error=error,
        completed_at="2026-06-02T10:00:00+00:00",
        duration_ms=1234,
    )

    assert payload["conversation_id"] == "conv-1"
    assert payload["run_id"] == "run-1"
    assert payload["turn_id"] == "run-1"
    assert payload["status"] == "failed"
    assert payload["runtime_snapshot"] == {"runtime_status": "failed"}
    assert payload["error"] == {
        "error_type": "WorkflowFailed",
        "summary": "render failed",
        "user_visible": True,
        "failure_signature": None,
    }
    assert payload["duration_ms"] == 1234


def test_turn_completed_waiting_input_has_null_error():
    payload = build_turn_completed_payload(
        conversation_id="conv-1",
        run_id="run-1",
        status="waiting_input",
        runtime_snapshot={"runtime_status": "waiting_input"},
    )

    assert payload["status"] == "waiting_input"
    assert payload["error"] is None
    assert payload["runtime_snapshot"] == {"runtime_status": "waiting_input"}


def test_is_turn_completed_event_requires_event_type():
    assert is_turn_completed_event({"type": TURN_COMPLETED})
    assert is_turn_completed_event({"event_type": TURN_COMPLETED})
    assert not is_turn_completed_event({"type": "run_completed"})
    assert not is_turn_completed_event({"payload": {"status": "completed"}})


def test_error_summary_is_clamped():
    error = build_turn_error("WorkflowFailed", "x" * 600)

    assert len(error["summary"]) == 500
