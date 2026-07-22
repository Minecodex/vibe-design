from pathlib import Path

from app.services.agent_harness.workspace.conversation.conversation_store_support import (
    guess_workspace_file_type,
    is_within_path,
    read_json,
    write_json,
)
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta


def test_conversation_store_support_handles_json_paths_and_file_types(tmp_path: Path):
    payload = {"id": "conv-1", "phase": "planning"}
    json_path = tmp_path / "conversation.json"

    write_json(json_path, payload)

    assert read_json(json_path) == payload
    assert guess_workspace_file_type(Path("deck.pptx")) == "pptx"
    assert guess_workspace_file_type(Path("sheet.xlsx")) == "xlsx"
    assert guess_workspace_file_type(Path("notes.md")) == "text"
    assert guess_workspace_file_type(Path("image.png")) == "image"
    assert guess_workspace_file_type(Path("movie.mp4")) == "video"
    assert guess_workspace_file_type(Path("unknown.bin")) == "file"
    assert is_within_path(tmp_path / "nested" / "file.txt", tmp_path) is True
    assert is_within_path(tmp_path.parent / "elsewhere.txt", tmp_path) is False


def test_ensure_harness_meta_initializes_only_internal_meta(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    ensure_harness_meta(7, "conv-1")
    conversation_dir = tmp_path / "users" / "7" / "conversations" / "conv-1"

    assert (conversation_dir / ".meta").exists()
    assert not (conversation_dir / "work").exists()
    assert not (conversation_dir / "assets").exists()
    assert not (conversation_dir / "preview_cache").exists()
    assert not (conversation_dir / "published").exists()
    assert not (conversation_dir / "logs").exists()
    assert not (conversation_dir / ".meta" / "model_session.json").exists()
    assert (conversation_dir / ".meta" / "tool_blobs").exists()
    assert not (conversation_dir / ".meta" / "session_state.json").exists()
    assert not (conversation_dir / ".meta" / "plan_state.json").exists()
    assert not (conversation_dir / ".meta" / "runtime_state.json").exists()
    assert not (conversation_dir / ".work").exists()
