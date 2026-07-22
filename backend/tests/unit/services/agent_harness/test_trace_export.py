from __future__ import annotations

import json
from pathlib import Path

import pytest


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_export_trace_log_writes_default_conversation_trace(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.event_log import append_event
    from app.services.agent_harness.runtime.eventing.trace_export import export_trace_log
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    conversation = create_conversation(7, title="Trace export")
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="execution_started",
        data={"message": "begin", "status": "running"},
    )

    output = export_trace_log(7, conversation["id"], profile="diagnostic")

    assert output == tmp_path / "users" / "7" / "conversations" / conversation["id"] / "trace.log"
    rows = _read_jsonl(output)
    assert rows[0]["type"] == "trace_header"
    assert rows[0]["conversation_id"] == conversation["id"]
    assert rows[0]["profile"] == "diagnostic"
    assert rows[1]["type"] == "event"
    assert rows[1]["event_type"] == "execution_started"
    assert rows[1]["payload"]["message"] == "begin"


def test_export_trace_log_filters_run_and_redacts_tokens(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.event_log import append_event
    from app.services.agent_harness.runtime.eventing.trace_export import export_trace_log
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    conversation = create_conversation(7, title="Trace redact")
    append_event(
        7,
        conversation["id"],
        run_id="run-1",
        event_type="prompt_bundle_assembled",
        data={
            "prompt": "Authorization: Bearer sk-secret-1234567890",
            "url": "https://example.test/download?token=abc123",
        },
    )
    append_event(
        7,
        conversation["id"],
        run_id="run-2",
        event_type="turn_completed",
        data={"message": "done"},
    )

    output = export_trace_log(
        7,
        conversation["id"],
        profile="full",
        run_id="run-1",
        output_path="exports/run-1.trace.log",
    )

    rows = _read_jsonl(output)
    assert output == tmp_path / "users" / "7" / "conversations" / conversation["id"] / "exports" / "run-1.trace.log"
    assert len(rows) == 2
    assert rows[1]["run_id"] == "run-1"
    assert rows[1]["payload"]["prompt"] == "Authorization: Bearer [REDACTED]"
    assert rows[1]["payload"]["url"].endswith("token=[REDACTED]")


def test_runtime_export_harness_trace_cli_writes_under_conversation_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from runtime.export_harness_trace import main

    conversation = create_conversation(7, title="Trace cli")

    exit_code = main(
        [
            "--user-id",
            "7",
            "--conversation-id",
            conversation["id"],
            "--output-file",
            "cli-trace.log",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "users" / "7" / "conversations" / conversation["id"] / "cli-trace.log").exists()


def test_export_trace_log_rejects_output_outside_conversation_dir(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.trace_export import export_trace_log
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    conversation = create_conversation(7, title="Trace path guard")

    with pytest.raises(ValueError):
        export_trace_log(7, conversation["id"], output_path="../trace.log")


def test_export_trace_log_uses_canvas_project_workspace(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.trace_export import export_trace_log
    from app.services.agent_harness.workspace.conversation.conversation_meta_store import create_conversation

    conversation = create_conversation(
        7,
        title="Canvas trace",
        runtime_profile="canvas",
        project_id=42,
    )

    output = export_trace_log(7, conversation["id"])

    assert output == tmp_path / "project" / "42" / "users" / "7" / "conversations" / conversation["id"] / "trace.log"


def test_export_trace_log_summarizes_context_session_without_prompt(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.trace_export import export_trace_log
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.session_v2.service import update_conversation

    conversation = create_conversation(7, title="Context trace")
    update_conversation(
        7,
        conversation["id"],
        {
            "runtime_snapshot_json": {
                "context_session": {
                    "version": 1,
                    "fingerprint": "fp",
                    "runtime_preparation_fingerprint": "fp",
                    "static_context_hash": "hash",
                    "language": "zh",
                    "model": "GPT-5.4",
                    "skill_id": "xlsx",
                    "artifact_mode": "document",
                    "system_prompt": "do not export this prompt",
                    "tool_schemas": [{"type": "function", "function": {"name": "write_file"}}],
                    "runtime_contract": {"secret-ish prompt body": "also do not export"},
                    "workspace_runtime_session": {},
                    "prepared_workspace": {},
                },
                "render_context": {
                    "turn": 2,
                    "message_seq_end": 10,
                    "event_seq_end": 15,
                    "dynamic_context_digest": "digest",
                },
            }
        },
    )

    output = export_trace_log(7, conversation["id"], profile="full")
    rows = _read_jsonl(output)
    header = rows[0]

    assert header["agent_context"]["context_session"]["fingerprint"] == "fp"
    assert header["agent_context"]["context_session"]["tool_schema_count"] == 1
    assert header["agent_context"]["render_context"]["message_seq_end"] == 10
    serialized = json.dumps(header, ensure_ascii=False)
    assert "do not export this prompt" not in serialized
    assert "write_file" not in serialized
