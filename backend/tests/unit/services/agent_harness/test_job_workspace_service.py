from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent_harness.workspace.conversation.conversation_meta_store import get_conversation
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.workspace.generated_content.job_workspace_service import JobWorkspaceService


def _conversation_root(tmp_path: Path, conversation_id: str) -> Path:
    return tmp_path / "users" / "7" / "conversations" / conversation_id


def test_job_workspace_service_publish_creates_version_without_active_job(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Job workspace publish")
    root = _conversation_root(tmp_path, conversation["id"])
    service = JobWorkspaceService(user_id=7, conversation_id=conversation["id"], run_id="run_1")

    work_file = root / "project" / "report.md"
    work_file.write_text("# Report\n", encoding="utf-8")

    published = service.publish_output(
        source_path="project/report.md",
        entry_path="project/report.md",
        note="Initial version",
    )

    assert published["path"].startswith("published/")
    assert published["current_version_id"] == "v0001"
    stored = get_conversation(7, conversation["id"]) or {}
    assert "active_job" not in stored


def test_job_workspace_service_publish_same_entry_creates_new_version(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Job workspace republish")
    root = _conversation_root(tmp_path, conversation["id"])
    service = JobWorkspaceService(user_id=7, conversation_id=conversation["id"], run_id="run_1")

    work_file = root / "project" / "report.md"
    work_file.write_text("# Report\n", encoding="utf-8")
    first = service.publish_output(source_path="project/report.md", entry_path="project/report.md", note="Initial version")

    work_file.write_text("# Report\n\nUpdated\n", encoding="utf-8")
    second = service.publish_output(source_path="project/report.md", entry_path="project/report.md", note="Second version")

    assert first["file_id"] == second["file_id"]
    assert first["current_version_id"] == "v0001"
    assert second["current_version_id"] == "v0002"


@pytest.mark.parametrize("kind, display_name", [("image", "cover.png"), ("video", "demo.mp4")])
def test_job_workspace_service_rejects_media_publish_jobs(monkeypatch, tmp_path: Path, kind: str, display_name: str):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Job workspace media")
    service = JobWorkspaceService(user_id=7, conversation_id=conversation["id"], run_id="run_1")
    root = _conversation_root(tmp_path, conversation["id"])
    (root / "project" / display_name).write_bytes(b"binary")

    with pytest.raises(ValueError, match="not supported for version publishing"):
        service.publish_output(source_path=f"project/{display_name}", entry_path=f"project/{display_name}")
