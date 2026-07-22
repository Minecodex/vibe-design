from pathlib import Path

from app.services.agent_harness.runtime.state.conversation_state import ConversationStateSnapshot
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    get_conversation,
    update_conversation,
)
from app.services.agent_harness.runtime.state.runtime_state import RuntimeState


def test_conversation_persists_run_metadata(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Run metadata")

    update_conversation(
        7,
        conversation["id"],
        run_id="run-42",
        runtime_status="running",
    )

    stored = get_conversation(7, conversation["id"])

    assert stored["run_id"] == "run-42"
    assert stored["runtime_status"] == "running"


def test_conversation_persists_parent_usage_log_id(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Parent usage log")

    update_conversation(
        7,
        conversation["id"],
        parent_usage_log_id=123,
    )

    stored = get_conversation(7, conversation["id"])

    assert stored["parent_usage_log_id"] == 123


def test_conversation_state_audit_payload_includes_execution_contract_fields():
    runtime_state = RuntimeState.from_conversation(
        phase="executing",
        skill_id="pptx",
        plan_policy="force_create",
    )
    snapshot = ConversationStateSnapshot.build(
        runtime_state=runtime_state,
        history_summary={"goal": ["Ship it"]},
        plan_state={"current_step": "Implement"},
        recovery_summary=None,
        manifest_summary="manifest",
        session_memory="memory",
    )

    payload = snapshot.to_audit_payload()

    assert payload["runtime_state"]["phase"] == "executing"
    assert payload["runtime_state"]["execution_policy"] == "committed"
    assert payload["runtime_state"]["is_committed_execution"] is True


def test_conversation_state_audit_payload_reports_default_contract_during_planning():
    runtime_state = RuntimeState.from_conversation(
        phase="planning",
        skill_id="pptx",
        plan_policy="force_create",
    )
    snapshot = ConversationStateSnapshot.build(
        runtime_state=runtime_state,
        history_summary=None,
        plan_state=None,
        recovery_summary=None,
        manifest_summary="manifest",
        session_memory="memory",
    )

    payload = snapshot.to_audit_payload()

    assert payload["runtime_state"]["phase"] == "planning"
    assert payload["runtime_state"]["execution_policy"] == "default"
    assert payload["runtime_state"]["is_committed_execution"] is False


def test_conversation_state_audit_payload_reports_coherent_default_execution_without_skill():
    runtime_state = RuntimeState.from_conversation(
        phase="executing",
        skill_id=None,
        plan_policy="model_decides",
    )
    snapshot = ConversationStateSnapshot.build(
        runtime_state=runtime_state,
        history_summary=None,
        plan_state=None,
        recovery_summary=None,
        manifest_summary="manifest",
        session_memory="memory",
    )

    payload = snapshot.to_audit_payload()

    assert payload["runtime_state"]["execution_policy"] == "default"
    assert payload["runtime_state"]["is_committed_execution"] is False
