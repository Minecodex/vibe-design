from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation


def test_projection_perf_log_redacts_sensitive_payload(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.context_projection_observability.HARNESS_CONTEXT_PROJECTION_PERF_LOG_ENABLED",
        True,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.context_projection_observability.HARNESS_CONTEXT_PROJECTION_PERF_LOG_DIR",
        str(tmp_path),
    )

    from app.services.agent_harness.runtime.context_projection_observability import (
        emit_projection_perf_event,
    )

    emit_projection_perf_event(
        "projection.test",
        conversation_id="conv-1",
        status="ok",
        elapsed_ms=12.3,
        dirty_responsibilities=["recall_sidecar_refresh"],
        prompt="full prompt must not be logged",
        tool_output="secret tool output",
        Authorization="Bearer real-token",
        cookie="session=secret",
        nested={"api_key": "real-key", "count": 2},
    )

    log_path = tmp_path / "harness_context_projection_perf.jsonl"
    payload = json.loads(log_path.read_text(encoding="utf-8").strip())
    text = json.dumps(payload, ensure_ascii=False)

    assert payload["event"] == "projection.test"
    assert payload["conversation_id"] == "conv-1"
    assert payload["dirty_responsibilities"] == ["recall_sidecar_refresh"]
    assert "full prompt" not in text
    assert "secret tool output" not in text
    assert "real-token" not in text
    assert "real-key" not in text


def test_context_projection_health_reports_idle_lagging_processing_and_failing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path / "harness"))

    from app.services.agent_harness.runtime.context_projection import (
        claim_next_projection,
        fail_projection,
        mark_projection_dirty,
    )
    from app.services.agent_harness.runtime.context_projection_observability import (
        get_context_projection_worker_health,
    )

    assert get_context_projection_worker_health()["status"] == "idle"

    lagging = create_conversation(7, title="Lagging projection")
    mark_projection_dirty(
        7,
        lagging["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=3,
        reason="message_appended",
    )
    assert get_context_projection_worker_health()["status"] == "lagging"

    claim = claim_next_projection(worker_id="health-worker", lease_seconds=60)
    assert claim is not None
    assert get_context_projection_worker_health()["status"] == "processing"

    fail_projection(
        lagging["id"],
        worker_id="health-worker",
        lease_token=claim["lease_token"],
        error=RuntimeError("bounded failure"),
    )
    failing = get_context_projection_worker_health(repeated_failure_threshold=2)
    assert failing["status"] == "failing"
    assert failing["dirty_conversations"] == 1
    assert failing["failed_conversations"] == 1

    mark_projection_dirty(
        7,
        lagging["id"],
        responsibilities=["recall_sidecar_refresh"],
        latest_event_sequence=4,
        reason="retry",
        next_project_at=datetime.now(),
    )
    claim = claim_next_projection(worker_id="health-worker", lease_seconds=60)
    assert claim is not None
    fail_projection(
        lagging["id"],
        worker_id="health-worker",
        lease_token=claim["lease_token"],
        error=RuntimeError("second bounded failure"),
    )
    assert get_context_projection_worker_health(repeated_failure_threshold=2)["status"] == "repeated_failure"
