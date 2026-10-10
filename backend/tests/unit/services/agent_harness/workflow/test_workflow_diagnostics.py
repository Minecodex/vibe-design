from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.services.agent_harness.workflow import diagnostics


def test_workflow_diagnostics_default_off(monkeypatch, caplog):
    monkeypatch.setattr(settings, "HARNESS_WORKFLOW_DIAGNOSTICS_ENABLED", False)
    monkeypatch.setattr(settings, "HARNESS_ACTIVITY_DIAGNOSTICS_ENABLED", False)
    monkeypatch.setattr(settings, "HARNESS_PERF_SEGMENT_WARNING_SECONDS", 0.001)
    monkeypatch.setattr(settings, "HARNESS_WORKFLOW_STEP_WARNING_SECONDS", 0.001)
    monkeypatch.setattr(settings, "HARNESS_ACTIVITY_WARNING_SECONDS", 0.001)

    with caplog.at_level(logging.INFO, logger=diagnostics.logger.name):
        with diagnostics.workflow_step_timer(step_type="model_turn", step_id="step-1", run_id="run-1", attempt=1):
            pass
        diagnostics.log_activity_slow(
            activity_type="model_turn",
            activity_id="activity-1",
            step_id="step-1",
            elapsed_ms=1000,
        )

    assert caplog.records == []


def test_workflow_diagnostics_enabled_redacted_shape(monkeypatch, caplog):
    monkeypatch.setattr(settings, "HARNESS_WORKFLOW_DIAGNOSTICS_ENABLED", True)
    monkeypatch.setattr(settings, "HARNESS_ACTIVITY_DIAGNOSTICS_ENABLED", True)
    monkeypatch.setattr(settings, "HARNESS_PERF_SEGMENT_WARNING_SECONDS", 0.0)
    monkeypatch.setattr(settings, "HARNESS_WORKFLOW_STEP_WARNING_SECONDS", 0.0)
    monkeypatch.setattr(settings, "HARNESS_ACTIVITY_WARNING_SECONDS", 0.0)

    with caplog.at_level(logging.INFO, logger=diagnostics.logger.name):
        with diagnostics.workflow_step_timer(step_type="model_turn", step_id="step-1", run_id="run-1", attempt=2):
            time.sleep(0.11)
        diagnostics.log_activity_slow(
            activity_type="model_turn",
            activity_id="activity-1",
            step_id="step-1",
            elapsed_ms=1000,
        )
        diagnostics.log_event_fanout_slow(event_type="message_block_delta", sequence=3, publish_elapsed_ms=1000)
        diagnostics.log_step_terminalized(run_id="run-1", step_id="step-1", status="succeeded")
        diagnostics.log_step_terminalized(run_id="run-1", step_id="step-2", status="failed")
        diagnostics.log_workflow_phase_timing(
            phase="execute_tool.tool_execute",
            step_type="execute_tool",
            step_id="step-3",
            run_id="run-1",
            elapsed_ms=1234,
            metadata={"tool_name": "request_plan_approval"},
        )

    messages = [record.getMessage() for record in caplog.records]
    assert any("Workflow step slow" in message for message in messages), (
        f"logger disabled={diagnostics.logger.disabled} propagate={diagnostics.logger.propagate} "
        f"level={diagnostics.logger.level} registered={logging.getLogger(diagnostics.logger.name) is diagnostics.logger} "
        f"messages={messages}"
    )
    assert any("Activity slow" in message for message in messages)
    assert any("Event fanout slow" in message for message in messages)
    assert any("Workflow phase timing" in message for message in messages)
    succeeded = next(record for record in caplog.records if "status=succeeded" in record.getMessage())
    failed = next(record for record in caplog.records if "status=failed" in record.getMessage())
    assert succeeded.levelno == logging.INFO
    assert failed.levelno == logging.WARNING
    assert all("prompt" not in message.lower() for message in messages)
