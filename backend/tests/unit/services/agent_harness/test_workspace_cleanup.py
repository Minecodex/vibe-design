from __future__ import annotations

import asyncio
from pathlib import Path

from app.services.agent_harness.runtime.execution_support.cleanup import cleanup_workspaces
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation


def test_cleanup_workspaces_keeps_db_backed_workspace_without_legacy_meta_files(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Cleanup keep")
    conv_dir = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    assert conv_dir.exists()
    assert not (conv_dir / ".meta" / "session.jsonl").exists()
    assert not (conv_dir / ".meta" / "state.json").exists()
    assert not (conv_dir / ".meta" / "projection.json").exists()

    stats = asyncio.run(cleanup_workspaces(dry_run=True))

    assert stats.orphan_dirs_removed == 0
    assert conv_dir.exists()


def test_cleanup_workspaces_removes_orphan_without_db_record(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    orphan_dir = tmp_path / "users" / "7" / "conversations" / "orphan-conv"
    for subdir in ("work", "assets", "published", ".meta"):
        (orphan_dir / subdir).mkdir(parents=True, exist_ok=True)
    (orphan_dir / "trace.log").touch()

    stats = asyncio.run(cleanup_workspaces(dry_run=False))

    assert stats.orphan_dirs_removed == 1
    assert not orphan_dir.exists()

