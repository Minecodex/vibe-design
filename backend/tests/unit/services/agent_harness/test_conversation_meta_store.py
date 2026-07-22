from __future__ import annotations

import json
from pathlib import Path


def test_conversation_meta_store_keeps_state_projection_and_index_lightweight(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation_dir
    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation, update_conversation

    conversation = create_conversation(7, title="Lightweight Meta")
    update_conversation(
        7,
        conversation["id"],
        runtime_status="running",
        run_state="waiting_tool",
        last_error_summary="tool failed",
        last_activity_at="2026-05-02T00:00:00+00:00",
        recovery_summary={"step": "retry"},
        plan_state={"steps": [{"id": "step-1", "title": "step-1"}]},
    )

    conversation_dir = get_conversation_dir(7, conversation["id"])
    assert (conversation_dir / "project").is_dir()
    assert (conversation_dir / "references").is_dir()
    assert (conversation_dir / "published").is_dir()
    assert (conversation_dir / "skill").is_dir()
    assert (conversation_dir / ".meta").is_dir()
    assert not (conversation_dir / ".meta" / "state.json").exists()
    assert not (conversation_dir / ".meta" / "projection.json").exists()
    assert not (tmp_path / "users" / "7" / "conversations" / ".index.json").exists()


def test_harness_meta_initializes_single_session_state_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
    from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta

    conversation = create_conversation(7, title="Session state")

    meta_dir = ensure_harness_meta(7, conversation["id"])

    assert not (meta_dir / "session_state.json").exists()
    assert not (meta_dir / "plan_state.json").exists()
    assert not (meta_dir / "runtime_state.json").exists()
    assert not (meta_dir / "model_session.json").exists()
    assert not (meta_dir / "tool_results").exists()
    assert (meta_dir / "tool_blobs").is_dir()
    assert not (meta_dir / "compaction_events.jsonl").exists()


def test_harness_meta_supports_canvas_profile_workspace_and_profile_listing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    from app.services.agent_harness.workspace.conversation.conversation_meta_store import (
        create_conversation,
        get_conversation_dir,
        list_conversations,
    )

    home_conversation = create_conversation(
        7,
        title="Home session",
        runtime_profile="home",
    )
    canvas_conversation = create_conversation(
        7,
        title="Canvas session",
        runtime_profile="canvas",
        project_id=42,
    )

    home_dir = get_conversation_dir(7, home_conversation["id"])
    canvas_dir = get_conversation_dir(7, canvas_conversation["id"])

    assert home_dir == tmp_path / "users" / "7" / "conversations" / str(home_conversation["id"])
    assert canvas_dir == tmp_path / "project" / "42" / "users" / "7" / "conversations" / str(canvas_conversation["id"])

    home_items, home_total = list_conversations(7, runtime_profile="home", page=1, page_size=20)
    canvas_items, canvas_total = list_conversations(7, runtime_profile="canvas", project_id=42, page=1, page_size=20)

    assert home_total == 1
    assert [item["id"] for item in home_items] == [home_conversation["id"]]
    assert home_items[0]["runtime_profile"] == "home"
    assert home_items[0]["project_id"] is None

    assert canvas_total == 1
    assert [item["id"] for item in canvas_items] == [canvas_conversation["id"]]
    assert canvas_items[0]["runtime_profile"] == "canvas"
    assert canvas_items[0]["project_id"] == 42
