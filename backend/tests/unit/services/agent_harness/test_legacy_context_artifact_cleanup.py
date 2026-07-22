from __future__ import annotations

from pathlib import Path

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.conversation_events import load_conversation_events
from app.services.agent_harness.runtime.context_recall import store as context_recall_store
from app.services.agent_harness.runtime.context_recall import load_memory_index
from app.services.agent_harness.runtime.context_recall.store import (
    append_collapse_commit,
    record_llm_compact_failure,
)
from app.services.agent_harness.runtime.state.store_core import ensure_harness_meta
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation


def test_context_recall_no_longer_exports_legacy_sidecar_path_contracts() -> None:
    legacy_names = {
        "append_context_snapshot",
        "load_context_snapshots",
        "context_recall_dir",
        "context_snapshots_path",
        "memory_index_path",
        "compact_failures_path",
        "collapse_commits_path",
    }

    for name in legacy_names:
        assert not hasattr(context_recall_store, name)


def test_harness_context_no_longer_exposes_legacy_file_state_helpers(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-cleanup",
        run_id="run-cleanup",
        workspace_root=tmp_path,
    )

    for name in {
        "manifest_path",
        "read_files_path",
        "session_memory_path",
        "load_manifest",
        "update_manifest",
        "load_session_memory",
        "append_session_memory",
        "update_session_memory_from_tool",
        "append_log",
    }:
        assert not hasattr(ctx, name)


def test_context_recall_persists_non_snapshot_facts_without_legacy_json_sidecars(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="No legacy context sidecars")
    conversation_id = str(conversation["id"])
    meta_dir = ensure_harness_meta(7, conversation_id)

    append_collapse_commit(
        7,
        conversation_id,
        source_item_count=10,
        replacement_item_count=2,
        estimated_tokens_before=1000,
        estimated_tokens_after=200,
        levels_applied=["context_collapse"],
        searchable_sources=["conversation"],
        preserved_recent_groups=1,
        meta_dir=meta_dir,
    )
    record_llm_compact_failure(7, conversation_id, meta_dir=meta_dir)

    assert load_memory_index(7, conversation_id, meta_dir=meta_dir)["entries"] == []
    assert {
        event["type"]
        for event in load_conversation_events(7, conversation_id)
    } >= {"collapse_commit", "llm_compact_failure"}

    forbidden = {
        meta_dir / "context_snapshots.jsonl",
        meta_dir / "memory_index.json",
        meta_dir / "compact_failures.json",
        meta_dir / "collapse_commits.jsonl",
        meta_dir / "manifest.json",
        meta_dir / "read_files.json",
        meta_dir.parent / "logs" / "execution.log",
    }
    assert all(not path.exists() for path in forbidden)
