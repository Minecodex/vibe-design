from pathlib import Path

from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.workspace.conversation.conversation_service import list_workspace_files
from app.services.agent_harness.workspace.generated_content.file_version_store import (
    append_file_version,
    set_current_version,
    workspace_file_event_payload,
)


def test_append_file_version_stores_only_under_published(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Versioned file")
    conversation_root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = conversation_root / "work" / "generated" / "run-1" / "report.pptx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"pptx")

    published = append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="report.pptx",
        run_id="run-1",
    )

    assert published["path"].startswith("published/")
    assert published["current_version_path"].endswith("/v0001/source.pptx")
    assert (conversation_root / published["current_version_path"]).exists()
    assert not (conversation_root / "files").exists()
    manifest_path = conversation_root / "published" / published["file_id"] / "manifest.json"
    assert manifest_path.exists()


def test_list_workspace_files_returns_versioned_and_asset_outputs(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Workspace list")
    conversation_root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = conversation_root / "work" / "generated" / "run-1" / "report.xlsx"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"xlsx")

    append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="report.xlsx",
        run_id="run-1",
    )

    files = list_workspace_files(7, conversation["id"])

    assert [item["name"] for item in files] == ["report.xlsx"]
    assert files[0]["path"].startswith("published/")
    assert files[0]["type"] == "sheet"


def test_workspace_file_event_payload_uses_selected_current_version(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Version switch")
    conversation_root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    source = conversation_root / "work" / "generated" / "run-1" / "report.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("v1", encoding="utf-8")

    first = append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="report.md",
        run_id="run-1",
    )
    source.write_text("v2", encoding="utf-8")
    append_file_version(
        7,
        conversation["id"],
        source_path=source,
        name="report.md",
        file_id=first["file_id"],
        run_id="run-2",
    )

    switched = set_current_version(7, conversation["id"], first["file_id"], "v0001")
    payload = workspace_file_event_payload(switched)

    assert payload["current_version"]["version_id"] == "v0001"
    assert payload["version"]["version_id"] == "v0001"
