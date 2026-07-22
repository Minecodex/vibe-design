from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from app.services.agent_harness.workflow import repositories as workflow_repository
from app.services.agent_harness.workflow.contracts import StepSpec
from app.services.agent_harness.workflow.records import run_from_orm
from app.services.agent_harness.workflow.status import (
    RUN_KIND_MESSAGE,
    RUN_KIND_RESUME_INTERACTION,
    STEP_APPLY_USER_INPUT,
    STEP_PREPARE_SKILL,
    STEP_STATUS_CANCELLED,
    STEP_STATUS_FAILED,
    STEP_STATUS_SUCCEEDED,
    STEP_STATUS_WAITING_INPUT,
)


def _create_workflow_run(
    *,
    user_id: int,
    conversation_id: str,
    kind: str,
    payload: dict,
    idempotency_key: str,
    run_id: str,
    priority: int = 0,
    max_attempts: int = 1,
    reject_active_conflicts: bool = False,
):
    step_type = STEP_APPLY_USER_INPUT if kind == RUN_KIND_RESUME_INTERACTION else STEP_PREPARE_SKILL
    return workflow_repository.create_run(
        user_id=user_id,
        conversation_id=conversation_id,
        kind=kind,
        input=payload,
        idempotency_key=idempotency_key,
        run_id=run_id,
        first_step=StepSpec(
            step_type=step_type,
            input={"kind": kind, "payload": payload},
            priority=priority,
            max_attempts=max_attempts,
            idempotency_key=f"run:{run_id}:step:{step_type}:0",
        ),
        reject_active_conflicts=reject_active_conflicts,
    )


def _complete_workflow_step_by_pk(request_id: int, *, claim_token: str, status: str):
    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentStep

    if status == "completed":
        step_status = STEP_STATUS_SUCCEEDED
    elif status == "waiting_input":
        step_status = STEP_STATUS_WAITING_INPUT
    elif status == "cancelled":
        step_status = STEP_STATUS_CANCELLED
    else:
        step_status = STEP_STATUS_FAILED
    with harness_sync_session_scope() as session:
        step = session.get(HarnessAgentStep, int(request_id))
        step_id = str(step.step_id) if step is not None else str(request_id)
    return workflow_repository.complete_step(
        step_id,
        claim_token=claim_token,
        status=step_status,
        terminal_run=True,
    )


def _get_workflow_run_by_pk(request_id: int):
    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentRun

    with harness_sync_session_scope() as session:
        row = session.get(HarnessAgentRun, int(request_id))
        return run_from_orm(row) if row is not None else None


def test_v2_conversation_creates_session_state_projection_and_index(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    conversation = create_conversation(7, title="V2")
    conversation_dir = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    assert (conversation_dir / "project").is_dir()
    assert (conversation_dir / "references" / "inputs").is_dir()
    assert (conversation_dir / "references" / "sources").is_dir()
    assert (conversation_dir / "references" / "generated").is_dir()
    assert (conversation_dir / "skill").is_dir()
    assert (conversation_dir / "published").is_dir()
    assert (conversation_dir / ".agent").is_dir()
    assert (conversation_dir / ".meta").is_dir()
    assert not (conversation_dir / "logs").exists()
    assert not (conversation_dir / "work").exists()
    assert not (conversation_dir / "assets").exists()
    assert not (conversation_dir / "preview_cache").exists()
    assert not (conversation_dir / ".meta" / "session.jsonl").exists()
    assert not (tmp_path / "users" / "7" / "conversations" / ".index.json").exists()


def test_v2_create_conversation_starts_planning_but_idle_for_plan_first_modes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    for mode in ("web", "document", "spreadsheet", "slides"):
        conversation = create_conversation(7, title=f"Neutral {mode}", artifact_mode=mode)

        assert conversation["artifact_mode"] == mode
        assert conversation["phase"] == "planning"
        assert conversation["runtime_status"] == "idle"
        assert conversation["run_state"] == "idle"
        assert conversation["activity"] is None
        assert conversation["turn_route"] is None


def test_v2_turn_route_and_activity_persist_in_runtime_state(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import (
        create_conversation,
        get_conversation,
        update_conversation,
    )

    conversation = create_conversation(7, title="Route persist")
    route = {
        "route_kind": "informational_turn",
        "source": "classifier",
        "confidence": 0.9,
        "requires_plan_gate": False,
        "requires_skill_selection": False,
        "requires_design_system_selection": False,
        "activity": "answering",
    }

    update_conversation(7, conversation["id"], turn_route=route, activity="answering")
    stored = get_conversation(7, conversation["id"])

    assert stored is not None
    assert stored["turn_route"] == route
    assert stored["activity"] == "answering"
    assert stored["runtime_state"]["turn_route"] == route
    assert stored["runtime_state"]["activity"] == "answering"


def test_v2_terminal_runtime_status_clears_nested_running_fields(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import (
        create_conversation,
        get_conversation,
    )
    from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state

    conversation = create_conversation(7, title="Terminal nested state")
    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "runtime_state": {
                "runtime_status": "running",
                "run_state": "executing",
                "run_status": "running",
                "current_action": "running:generate_image",
            },
        },
    )

    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "completed",
            "run_state": "completed",
        },
    )
    stored = get_conversation(7, conversation["id"])

    assert stored is not None
    assert stored["runtime_status"] == "completed"
    assert stored["runtime_state"]["runtime_status"] == "completed"
    assert stored["runtime_state"]["run_state"] == "completed"
    assert stored["runtime_state"]["run_status"] == "completed"
    assert stored["runtime_state"]["current_action"] is None


def test_v2_list_conversations_reads_only_user_index(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, list_conversations

    first = create_conversation(7, title="First")
    create_conversation(7, title="Second")

    items, total = list_conversations(7, page=1, page_size=20)

    assert total == 2
    assert {item["id"] for item in items} >= {first["id"]}


def test_v2_detail_snapshot_uses_projection_tail_without_workspace_scan(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.runtime.eventing.live_event_publisher import publish_user_event
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.conversation.conversation_snapshot import build_conversation_detail_snapshot

    conversation = create_conversation(7, title="Detail")
    publish_user_event(
        7,
        conversation["id"],
        run_id="run-detail",
        event_type="user_message",
        data={"content": "hello"},
        idempotency_key="detail:user-message",
    )

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.workspace_preview_service.list_workspace_files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("workspace scan should not run")),
    )

    snapshot = build_conversation_detail_snapshot(7, conversation["id"])

    assert snapshot is not None
    assert snapshot["messages"][0]["content"] == "hello"
    assert snapshot["messages_page"]["limit"] == 80
    assert snapshot["workspace_files"] == []


def test_internal_transcript_message_delta_updates_record(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import (
        append_message,
        append_message_content_delta,
        create_conversation,
        load_messages,
    )

    conversation = create_conversation(7, title="Delta")
    message = append_message(
        7,
        conversation["id"],
        {
            "role": "assistant",
            "content": "",
            "streaming": True,
            "metadata": {"message_kind": "agent_context", "model_visible": True, "ui_visible": False},
        },
    )

    updated = append_message_content_delta(7, conversation["id"], message_id=message["id"], delta="hello")

    assert updated["content"] == "hello"
    assert load_messages(7, conversation["id"])[0]["content"] == "hello"


def test_internal_transcript_message_id_is_bounded_and_still_updateable(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import (
        append_message,
        append_message_content_delta,
        create_conversation,
        load_messages,
    )
    from app.services.agent_harness.workspace.session_v2.service import normalize_message_id

    conversation = create_conversation(7, title="Long message id")
    long_message_id = "run:" + "r" * 80 + ":message:assistant:0:attempt:1"

    message = append_message(
        7,
        conversation["id"],
        {
            "id": long_message_id,
            "role": "assistant",
            "content": "",
            "streaming": True,
            "metadata": {"message_kind": "agent_context", "model_visible": True, "ui_visible": False},
        },
    )
    updated = append_message_content_delta(
        7,
        conversation["id"],
        message_id=long_message_id,
        delta="hello",
    )

    assert message["id"] == normalize_message_id(long_message_id)
    assert len(message["id"]) <= 40
    assert updated is not None
    assert updated["id"] == message["id"]
    assert updated["content"] == "hello"
    assert load_messages(7, conversation["id"])[0]["id"] == message["id"]


def test_internal_tool_message_promotes_tool_identity_from_metadata(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import (
        append_message,
        create_conversation,
        load_messages,
    )

    conversation = create_conversation(7, title="Tool metadata")

    stored = append_message(
        7,
        conversation["id"],
        {
            "role": "tool",
            "content": "workspace exists",
            "metadata": {
                "tool_call_id": "call-1",
                "tool_name": "workspace_map",
                "model_visible": True,
                "ui_visible": False,
            },
        },
    )

    assert stored["tool_call_id"] == "call-1"
    assert stored["tool_name"] == "workspace_map"
    assert load_messages(7, conversation["id"])[0]["tool_call_id"] == "call-1"
    assert load_messages(7, conversation["id"])[0]["tool_name"] == "workspace_map"


def test_v2_runtime_owner_state_is_derived_from_agent_run_queue(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.session_v2.state_store import read_state

    conversation = create_conversation(7, title="Runtime")

    _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:runtime",
        run_id="run-runtime",
    )
    claimed = workflow_repository.claim_next_step(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None

    conversation_dir = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    state = read_state(7, conversation["id"])
    assert state["run_owner"] == "worker-a"
    assert state["run_owner_token"] == claimed.claim_token
    assert state["run_lease_expires_at"] is not None
    assert state["cancel_requested"] is False
    assert not (conversation_dir / ".meta" / "active_run.json").exists()
    assert not (conversation_dir / ".meta" / "cancel.flag").exists()
    assert not (conversation_dir / ".meta" / "state.json").exists()
    assert not (conversation_dir / ".meta" / "session_state.json").exists()

    assert workflow_repository.request_cancel(conversation["id"], reason="test") is True
    state = read_state(7, conversation["id"])
    assert state["cancel_requested"] is True


def test_v2_workspace_projection_updates_when_files_and_assets_are_registered(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.conversation.conversation_service import list_workspace_files
    from app.services.agent_harness.workspace.generated_content.asset_store import register_asset_bytes
    from app.services.agent_harness.workspace.generated_content.file_version_store import append_file_version

    conversation = create_conversation(7, title="Workspace")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = root / "project" / "report.txt"
    source.write_text("hello", encoding="utf-8")

    append_file_version(7, conversation["id"], source_path=source, name="report.txt")
    register_asset_bytes(
        7,
        conversation["id"],
        content=b"image",
        kind="input",
        original_name="input.png",
        mime_type="image/png",
    )

    workspace_files = list_workspace_files(7, conversation["id"])
    by_name = {item["name"]: item for item in workspace_files}
    assert {"report.txt", "input.png"}.issubset(by_name)
    assert by_name["report.txt"]["path"].startswith("published/")
    assert by_name["report.txt"]["source"] == "versioned_file"
    assert by_name["input.png"]["path"].startswith("references/inputs/")
    assert by_name["input.png"]["source"] == "input_asset"

    from app.services.agent_harness.runtime.conversation_events import query_conversation_events

    events = query_conversation_events(7, conversation["id"])
    workspace_events = [event for event in events if event["event_type"] == "workspace_file_upserted"]
    assert len(workspace_events) == 2
    event_payloads = [event["payload"] for event in workspace_events]
    event_names = {payload["name"] for payload in event_payloads}
    assert {"report.txt", "input.png"}.issubset(event_names)
    assert any(payload["source"] == "versioned_file" for payload in event_payloads)
    assert any(payload["source"] == "input_asset" for payload in event_payloads)


def test_v2_update_conversation_refreshes_updated_at_and_list_order(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import (
        create_conversation,
        get_conversation,
        list_conversations,
        update_conversation,
    )

    first = create_conversation(7, title="First")
    second = create_conversation(7, title="Second")
    before = get_conversation(7, first["id"])
    assert before is not None

    update_conversation(7, first["id"], last_error_summary="bumped")

    after = get_conversation(7, first["id"])
    assert after is not None
    assert after["updated_at"] != before["updated_at"]

    items, _ = list_conversations(7, page=1, page_size=20)
    assert items[0]["id"] == first["id"]


def test_v2_active_run_state_prefers_active_run_id(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentRun, HarnessAgentStep, HarnessConversation
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, get_conversation

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    conversation = create_conversation(7, title="Active run wins")

    with harness_sync_session_scope() as session:
        stored = session.get(HarnessConversation, conversation["id"])
        assert stored is not None
        stored.active_run_id = "run-current"
        for run_id in ("run-stale", "run-current"):
            session.add(
                HarnessAgentRun(
                    run_id=run_id,
                    user_id=7,
                    conversation_id=conversation["id"],
                    kind="message",
                    status="running",
                    input_json={},
                    idempotency_key=f"message:{run_id}",
                    cancel_requested=False,
                    created_at=now,
                    updated_at=now,
                )
            )
        session.add(
            HarnessAgentStep(
                step_id="step-stale",
                run_id="run-stale",
                conversation_id=conversation["id"],
                user_id=7,
                step_type="model_turn",
                status="running",
                input_json={},
                attempts=3,
                max_attempts=3,
                priority=0,
                idempotency_key="step:stale",
                claim_owner="worker-stale",
                claim_token="token-stale",
                claimed_at=now + timedelta(seconds=10),
                last_renewed_at=now + timedelta(seconds=10),
                claim_expires_at=now + timedelta(seconds=70),
                updated_at=now + timedelta(seconds=10),
            )
        )
        session.add(
            HarnessAgentStep(
                step_id="step-current",
                run_id="run-current",
                conversation_id=conversation["id"],
                user_id=7,
                step_type="model_turn",
                status="running",
                input_json={},
                attempts=1,
                max_attempts=3,
                priority=0,
                idempotency_key="step:current",
                claim_owner="worker-current",
                claim_token="token-current",
                claimed_at=now,
                last_renewed_at=now,
                claim_expires_at=now + timedelta(seconds=60),
                updated_at=now,
            )
        )

    stored = get_conversation(7, conversation["id"])

    assert stored is not None
    assert stored["active_run_id"] == "run-current"
    assert stored["run_owner"] == "worker-current"
    assert stored["run_owner_token"] == "token-current"
    assert stored["run_checkpoint"] == 1


def test_v2_list_conversations_skips_active_run_state_lookup(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, list_conversations
    from app.services.agent_harness.workspace.session_v2 import db_store

    create_conversation(7, title="List without lease lookup")

    def fail_active_state_lookup(*_args, **_kwargs):
        raise AssertionError("list view should not query active run state")

    monkeypatch.setattr(db_store, "_active_run_state", fail_active_state_lookup)

    items, total = list_conversations(7, page=1, page_size=20)

    assert total == 1
    assert items[0]["title"] == "List without lease lookup"
    assert items[0]["run_owner"] is None


def test_v2_read_runtime_state_payload_uses_serialized_active_state_once(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.session_v2 import db_store

    conversation = create_conversation(7, title="Runtime state")
    calls = []

    def fake_active_state(conversation_id: str, *, active_run_id: str | None = None):
        calls.append((conversation_id, active_run_id))
        return {
            "cancel_requested": True,
            "heartbeat_at": "2026-06-04T00:00:00+00:00",
            "run_owner": "worker-one",
            "run_owner_token": "token-one",
            "run_claimed_at": None,
            "run_last_renewed_at": "2026-06-04T00:00:00+00:00",
            "run_lease_expires_at": None,
            "run_checkpoint": 2,
        }

    monkeypatch.setattr(db_store, "_active_run_state", fake_active_state)

    payload = db_store.read_runtime_state_payload(7, conversation["id"])

    assert payload is not None
    assert len(calls) == 1
    assert payload["cancel_requested"] is True
    assert payload["run_owner"] == "worker-one"
    assert payload["run_checkpoint"] == 2


def test_v2_delete_soft_marks_conversation_and_hides_from_active_reads(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessConversation
    from app.services.agent_harness.workspace.conversation.conversation_service import (
        create_conversation,
        delete_conversation,
        get_conversation,
        list_conversations,
    )

    conversation = create_conversation(7, title="Delete me")

    assert delete_conversation(7, conversation["id"]) is True
    assert get_conversation(7, conversation["id"]) is None

    items, total = list_conversations(7, page=1, page_size=20)
    assert total == 0
    assert items == []

    with harness_sync_session_scope() as session:
        stored = session.get(HarnessConversation, conversation["id"])
        assert stored is not None
        assert stored.status == "deleted"


def test_v2_workspace_listing_uses_db_index_only(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.workspace_preview_service import list_workspace_files

    monkeypatch.setattr(
        "app.services.agent_harness.workspace.session_v2.db_store.list_workspace_file_payloads",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.generated_content.asset_store.list_assets",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("filesystem fallback should not run")),
    )
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.generated_content.file_version_store.list_versioned_files",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("filesystem fallback should not run")),
    )

    assert list_workspace_files(7, "conv-no-db-index") == []


def test_v2_conversation_create_rolls_back_db_when_workspace_init_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.workspace.conversation.conversation_meta_store.generate_conversation_id",
        lambda: "conv-rollback",
    )

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, get_conversation

    real_mkdir = Path.mkdir

    def _guarded_mkdir(self: Path, *args, **kwargs):
        if self.name == "published" and self.parent.name == "conv-rollback":
            raise OSError("disk full")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", _guarded_mkdir)

    with pytest.raises(OSError):
        create_conversation(7, title="Rollback")

    conversation_dir = tmp_path / "users" / "7" / "conversations" / "conv-rollback"
    assert get_conversation(7, "conv-rollback") is None
    assert not (conversation_dir / "published").exists()


def test_append_trace_is_best_effort_when_trace_log_write_fails(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.runtime.eventing.persistence import append_trace

    conversation = create_conversation(7, title="Trace best effort")

    def _failing_open(*_args, **_kwargs):
        raise OSError("read only")

    monkeypatch.setattr(Path, "open", _failing_open)

    append_trace(
        7,
        conversation["id"],
        trace_type="turn_completed",
        summary="should not raise",
        payload={"stage": "test"},
    )


def test_v2_non_running_runtime_status_clears_owner_fields(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, get_conversation
    from app.services.agent_harness.workspace.session_v2.service import patch_runtime_state
    from app.services.agent_harness.workspace.session_v2.state_store import read_state

    now = datetime.now(timezone.utc)
    conversation = create_conversation(7, title="owner-cleared-on-waiting-input")

    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "running",
            "run_state": "executing",
            "turn_status": "running",
            "heartbeat_at": now.timestamp(),
            "run_owner": "worker-a",
            "run_owner_token": "owner-a",
            "run_claimed_at": now.isoformat(),
            "run_last_renewed_at": now.isoformat(),
            "run_lease_expires_at": (now + timedelta(seconds=60)).isoformat(),
            "run_checkpoint": 3,
        },
        touch_updated_at=False,
    )

    patch_runtime_state(
        7,
        conversation["id"],
        {
            "runtime_status": "waiting_input",
            "run_state": "waiting_input",
            "turn_status": "waiting_input",
            "heartbeat_at": now.timestamp(),
            "run_owner": "worker-a",
            "run_owner_token": "owner-a",
            "run_claimed_at": now.isoformat(),
            "run_last_renewed_at": now.isoformat(),
            "run_lease_expires_at": (now + timedelta(seconds=60)).isoformat(),
            "run_checkpoint": 4,
        },
        touch_updated_at=False,
    )

    stored = get_conversation(7, conversation["id"])
    state = read_state(7, conversation["id"])

    assert stored is not None
    assert stored["runtime_status"] == "waiting_input"
    assert stored["heartbeat_at"] is None
    assert stored["run_owner"] is None
    assert stored["run_owner_token"] is None
    assert stored["run_claimed_at"] is None
    assert stored["run_last_renewed_at"] is None
    assert stored["run_lease_expires_at"] is None
    assert stored["run_checkpoint"] is None
    assert state["heartbeat_at"] is None
    assert state["run_owner"] is None
    assert state["run_owner_token"] is None
    assert state["run_lease_expires_at"] is None
    assert state["run_checkpoint"] is None


def test_v2_agent_run_claim_blocks_same_conversation_until_lease_expires(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.session_v2.state_store import read_state

    conversation = create_conversation(7, title="future-lease-blocks-claim")
    _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:first",
        run_id="run-first",
        priority=99,
    )
    _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:second",
        run_id="run-second",
        priority=98,
    )

    claimed = workflow_repository.claim_next_step(worker_id="worker-remote", lease_seconds=60)
    blocked = workflow_repository.claim_next_step(worker_id="worker-local", lease_seconds=60)
    assert claimed is not None
    assert claimed.conversation_id == conversation["id"]
    assert blocked is None
    stored = read_state(7, conversation["id"])
    assert stored is not None
    assert stored["run_owner"] == "worker-remote"
    assert stored["run_owner_token"] == claimed.claim_token


def test_v2_agent_run_claim_picks_queued_request_without_runtime_owner(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    conversation = create_conversation(7, title="missing-owner-takeover")
    _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:takeover",
        run_id="run-takeover",
    )

    claimed = workflow_repository.claim_next_step(worker_id="worker-takeover", lease_seconds=60)

    assert claimed is not None
    assert claimed.claim_owner == "worker-takeover"
    assert claimed.claim_token is not None
    assert claimed.claim_expires_at is not None


def test_v2_agent_run_request_reuses_active_but_not_terminal_idempotency_key(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation

    conversation = create_conversation(7, title="repeat-idempotency")
    first = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "continue"},
        idempotency_key="message:repeat",
        run_id="run-repeat-1",
    )
    same_active = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "continue"},
        idempotency_key="message:repeat",
        run_id="run-repeat-duplicate",
    )
    assert same_active.id == first.id
    assert first.created is True
    assert same_active.created is False

    claimed = workflow_repository.claim_next_step(worker_id="worker-repeat", lease_seconds=60)
    assert claimed is not None
    terminalized = _complete_workflow_step_by_pk(claimed.id, claim_token=claimed.claim_token or "", status="completed")
    assert terminalized is not None

    second = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "continue"},
        idempotency_key="message:repeat",
        run_id="run-repeat-2",
    )
    same_second_active = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "continue"},
        idempotency_key="message:repeat",
        run_id="run-repeat-2-duplicate",
    )

    assert second.id != first.id
    assert second.run_id == "run-repeat-2"
    assert second.created is True
    assert same_second_active.id == second.id
    assert same_second_active.created is False


def test_v2_agent_run_cancel_prefers_queued_request_over_waiting_input(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workspace.session_v2.state_store import read_state

    conversation = create_conversation(7, title="cancel-queued-before-waiting")
    waiting = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "needs input"},
        idempotency_key="message:waiting",
        run_id="run-waiting",
    )
    claimed = workflow_repository.claim_next_step(worker_id="worker-waiting", lease_seconds=60)
    assert claimed is not None
    assert claimed.run_id == waiting.run_id
    assert _complete_workflow_step_by_pk(claimed.id, claim_token=claimed.claim_token or "", status="waiting_input") is not None

    queued = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="resume_interaction",
        payload={"payload_version": 1, "answer": "continue"},
        idempotency_key="resume:queued",
        run_id="run-queued",
    )
    state_before_cancel = read_state(7, conversation["id"])
    assert state_before_cancel["run_owner"] is None
    assert state_before_cancel["run_checkpoint"] == 0

    assert workflow_repository.request_cancel(conversation["id"], reason="test") is True

    waiting_after = _get_workflow_run_by_pk(waiting.id)
    queued_after = _get_workflow_run_by_pk(queued.id)
    assert waiting_after is not None
    assert queued_after is not None
    assert waiting_after.status == "cancelled"
    assert queued_after.status == "cancelled"


def test_v2_agent_run_create_rejects_different_active_request_in_same_transaction(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.workflow.errors import AgentRunAlreadyActiveError

    conversation = create_conversation(7, title="atomic-active-guard")
    first = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "first"},
        idempotency_key="message:first",
        run_id="run-first",
        reject_active_conflicts=True,
    )
    same_active = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1, "content": "first"},
        idempotency_key="message:first",
        run_id="run-first-retry",
        reject_active_conflicts=True,
    )
    assert same_active.id == first.id

    with pytest.raises(AgentRunAlreadyActiveError):
        _create_workflow_run(
            user_id=7,
            conversation_id=conversation["id"],
            kind="message",
            payload={"payload_version": 1, "content": "second"},
            idempotency_key="message:second",
            run_id="run-second",
            reject_active_conflicts=True,
        )


def test_v2_agent_run_claim_takes_over_expired_claim(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentStep

    now = datetime.now(timezone.utc)
    conversation = create_conversation(7, title="expired-lease-takeover")
    request = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:expired",
        run_id="run-expired",
        max_attempts=2,
    )
    first = workflow_repository.claim_next_step(worker_id="worker-stale", lease_seconds=60)
    assert first is not None
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentStep).filter_by(run_id=request.run_id).one()
        row.claim_expires_at = now.replace(tzinfo=None) - timedelta(seconds=30)
        row.updated_at = now.replace(tzinfo=None) - timedelta(seconds=30)

    claimed = workflow_repository.claim_next_step(worker_id="worker-takeover", lease_seconds=60)

    assert claimed is not None
    assert claimed.claim_owner == "worker-takeover"
    assert claimed.claim_token != first.claim_token
    assert claimed.attempts == 2


def test_v2_agent_run_claim_fails_expired_request_after_max_attempts(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentStep
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, get_conversation

    now = datetime.now(timezone.utc)
    conversation = create_conversation(7, title="expired-max-attempts")
    request = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:max-attempts",
        run_id="run-max-attempts",
        max_attempts=1,
    )
    first = workflow_repository.claim_next_step(worker_id="worker-stale", lease_seconds=60)
    assert first is not None
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentStep).filter_by(run_id=request.run_id).one()
        row.claim_expires_at = now.replace(tzinfo=None) - timedelta(seconds=30)
        row.updated_at = now.replace(tzinfo=None) - timedelta(seconds=30)

    claimed = workflow_repository.claim_next_step(worker_id="worker-next", lease_seconds=60)

    assert claimed is None
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentStep).filter_by(run_id=request.run_id).one()
        assert row.status == "failed"
        assert row.last_error_type == "MaxAttemptsExceeded"
    stored = get_conversation(7, conversation["id"])
    assert stored["runtime_status"] == "failed"
    assert stored["run_state"] == "failed"


def test_v2_agent_run_exhaustion_explains_incomplete_model_call(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.db.harness_session import harness_sync_session_scope
    from app.models.harness_session import HarnessAgentStep
    from app.services.agent_harness.runtime.conversation_events import load_conversation_events
    from app.services.agent_harness.workspace.conversation.conversation_service import (
        create_conversation,
        get_conversation,
        update_conversation,
    )

    now = datetime.now(timezone.utc)
    conversation = create_conversation(7, title="incomplete-model-call")
    request = _create_workflow_run(
        user_id=7,
        conversation_id=conversation["id"],
        kind="message",
        payload={"payload_version": 1},
        idempotency_key="message:model-incomplete",
        run_id="run-model-incomplete",
        max_attempts=1,
    )
    first = workflow_repository.claim_next_step(worker_id="worker-stale", lease_seconds=60)
    assert first is not None
    update_conversation(
        7,
        conversation["id"],
        runtime_status="running",
        run_state="waiting_model",
        turn_status="running",
        activity="planning_outline",
        last_activity_source="llm_call_started",
        last_activity_at=now.isoformat(),
    )
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentStep).filter_by(run_id=request.run_id).one()
        row.claim_expires_at = now.replace(tzinfo=None) - timedelta(seconds=30)
        row.updated_at = now.replace(tzinfo=None) - timedelta(seconds=30)

    claimed = workflow_repository.claim_next_step(worker_id="worker-next", lease_seconds=60)

    assert claimed is None
    expected_summary = (
        "Agent run exceeded max attempts after model call started; "
        "the model call did not complete."
    )
    with harness_sync_session_scope() as session:
        row = session.query(HarnessAgentStep).filter_by(run_id=request.run_id).one()
        assert row.status == "failed"
        assert row.last_error_type == "MaxAttemptsExceeded"
        assert row.last_error_summary == expected_summary
    stored = get_conversation(7, conversation["id"])
    assert stored["runtime_status"] == "failed"
    assert stored["run_state"] == "failed"
    assert stored["last_activity_source"] == "llm_call_started"
    assert stored["last_error_summary"] == expected_summary
    failed_events = [
        event
        for event in load_conversation_events(7, conversation["id"])
        if event.get("type") == "turn_completed"
    ]
    assert len(failed_events) == 1
    assert failed_events[0]["run_id"] == "run-model-incomplete"
    assert failed_events[0]["payload"]["error"]["summary"] == expected_summary
    assert failed_events[0]["payload"]["runtime_snapshot"]["failure"]["failure_source"] == "queue_exhausted"

