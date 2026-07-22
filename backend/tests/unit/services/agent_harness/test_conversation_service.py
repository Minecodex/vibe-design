from pathlib import Path

from app.schemas.harness import HarnessConversationListRead, WorkspaceFileRead
from app.services.agent_harness.workspace.conversation import conversation_message_store, conversation_meta_store, workspace_preview_service
from app.services.agent_harness.workspace.conversation.conversation_service import (
    _write_json,
    build_auto_selection_announcement_message,
    build_internal_skill_activation_message,
    create_conversation,
    get_conversation,
    list_conversations,
    list_workspace_files,
    load_messages,
    update_conversation,
)
from app.services.agent_harness.workspace.generated_content.file_version_store import append_file_version


def test_conversation_service_uses_direct_aliases_for_basic_stores():
    assert create_conversation is conversation_meta_store.create_conversation
    assert get_conversation is conversation_meta_store.get_conversation
    assert update_conversation is conversation_meta_store.update_conversation
    assert _write_json is conversation_meta_store.write_json
    assert load_messages is conversation_message_store.load_messages
    assert list_workspace_files is workspace_preview_service.list_workspace_files


def test_create_conversation_defaults_to_planning_phase_for_plan_first_artifact_modes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    for artifact_mode in ("web", "document", "spreadsheet", "slides"):
        conversation = create_conversation(7, title=f"{artifact_mode} mode", artifact_mode=artifact_mode)
        assert conversation["phase"] == "planning"


def test_create_canvas_conversation_skips_plan_first_phase_even_for_web_artifact_mode(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(
        7,
        title="Canvas web mode",
        runtime_profile="canvas",
        project_id=9,
        artifact_mode="web",
    )

    assert conversation["phase"] == "executing"


def test_auto_selection_announcement_includes_replay_metadata():
    message = build_auto_selection_announcement_message(
        previous_skill_id=None,
        next_skill_id="html-ppt",
        language="zh",
    )

    assert message == {
        "role": "assistant",
        "content": "已自动选择技能：Html Ppt。",
        "metadata": {
            "source": "auto_selection_announcement",
            "selected_skill_id": "html-ppt",
            "previous_skill_id": None,
        },
    }


def test_internal_skill_activation_message_includes_loaded_skill_metadata():
    message = build_internal_skill_activation_message(
        selected_skill_id="html-ppt",
        internal_skill_ids=["critique", "tweaks"],
        language="zh",
    )

    assert message == {
        "role": "assistant",
        "content": "已加载内部技能：Critique、Tweaks。",
        "metadata": {
            "message_kind": "internal_audit_note",
            "source": "internal_hidden_skill_activation",
            "selected_skill_id": "html-ppt",
            "internal_skill_ids": ["critique", "tweaks"],
        },
    }


def test_create_conversation_keeps_direct_execution_for_non_plan_first_modes(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    for artifact_mode in ("image", "video"):
        conversation = create_conversation(7, title=f"{artifact_mode} mode", artifact_mode=artifact_mode)
        assert conversation["phase"] == "executing"


def test_create_conversation_defaults_to_planning_phase_for_skill(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Skill mode", skill_id="pptx")

    assert conversation["phase"] == "planning"


def test_list_conversations_allows_planning_ready_phase(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Pending plan", skill_id="pptx")
    update_conversation(
        7,
        conversation["id"],
        phase="planning_ready",
        runtime_status="waiting_input",
        run_state="waiting_input",
    )

    items, total = list_conversations(7)

    assert total == 1
    assert items[0]["phase"] == "planning_ready"
    HarnessConversationListRead(
        items=items,
        total=total,
        page=1,
        page_size=20,
        has_more=False,
    )


def test_list_workspace_files_returns_workspace_file_schema(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Files")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    image_path = root / "work" / "sample.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"fake-image")
    append_file_version(
        7,
        conversation["id"],
        source_path=image_path,
        name="sample.png",
        file_type="image",
        run_id="run-1",
    )

    result = list_workspace_files(7, conversation["id"])

    assert len(result) == 1
    assert result[0]["name"] == "sample.png"
    assert result[0]["path"].startswith("published/")
    assert result[0]["type"] == "image"
    assert result[0]["size"] == len(b"fake-image")
    assert result[0]["source"] == "versioned_file"
    assert result[0]["current_version_id"] == "v0001"


def test_workspace_file_schema_preserves_web_bundle_metadata(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Web bundle")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    bundle_path = root / "work" / "site.zip"
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_bytes(b"zip")
    append_file_version(
        7,
        conversation["id"],
        source_path=bundle_path,
        name="index.zip",
        file_type="web",
        run_id="run-1",
        artifact_metadata={
            "artifact_kind": "web_bundle",
            "bundle_format": "zip",
            "entry": "index.html",
        },
    )

    result = list_workspace_files(7, conversation["id"])
    serialized = WorkspaceFileRead(**result[0]).dict()

    assert serialized["artifact_kind"] == "web_bundle"
    assert serialized["artifact_metadata"]["bundle_format"] == "zip"
    assert serialized["artifact_metadata"]["entry"] == "index.html"
    assert serialized["versions"][0]["artifact_metadata"]["entry"] == "index.html"


def test_list_workspace_files_normalizes_nested_paths_for_generated_media(
    monkeypatch, tmp_path: Path
):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Generated media")
    root = tmp_path / "users" / "7" / "conversations" / conversation["id"]
    video_path = root / "work" / "generated" / "sample.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"fake-video")
    append_file_version(
        7,
        conversation["id"],
        source_path=video_path,
        name="sample.mp4",
        file_type="video",
        run_id="run-1",
    )

    result = list_workspace_files(7, conversation["id"])

    assert len(result) == 1
    assert result[0]["name"] == "sample.mp4"
    assert result[0]["path"].startswith("published/")
    assert result[0]["type"] == "video"
    assert result[0]["size"] == len(b"fake-video")
    assert result[0]["source"] == "versioned_file"


def test_list_workspace_files_includes_uploaded_input_assets(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    root = tmp_path / "users" / "7" / "conversations" / "conv-1"
    input_dir = root / "references" / "inputs" / "upload_001"
    input_dir.mkdir(parents=True)
    image_path = input_dir / "source.png"
    image_path.write_bytes(b"fake-image")
    (root / ".meta").mkdir(parents=True)
    (root / ".meta" / "assets_manifest.json").write_text(
        (
            '{"assets":[{'
            '"asset_id":"upload_001",'
            '"kind":"input",'
            '"original_name":"客厅.png",'
            '"path":"references/inputs/upload_001/source.png",'
            '"mime_type":"image/png",'
            '"size":10,'
            '"created_at":"2026-04-30T00:00:00+00:00"'
            "}]} "
        ),
        encoding="utf-8",
    )

    result = list_workspace_files(7, "conv-1")

    assert result == [
        {
            "file_id": "upload_001",
            "name": "客厅.png",
            "path": "references/inputs/upload_001/source.png",
            "type": "image",
            "size": len(b"fake-image"),
            "created_at": "2026-04-30T00:00:00+00:00",
            "updated_at": None,
            "current_version_id": "",
            "versions": [],
            "source": "input_asset",
        }
    ]


def test_conversation_persists_and_reloads_recovery_summary(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))

    conversation = create_conversation(7, title="Recovery summary")
    recovery_summary = {
        "last_successful_phase": "executing",
        "last_successful_step": "tool:file_read",
        "last_failure_signature": "syntax_error:bash:file=code/build_doc.js",
        "recovery_attempts_used": 1,
        "suggested_next_action": "switch_strategy",
    }

    update_conversation(7, conversation["id"], recovery_summary=recovery_summary)
    stored = get_conversation(7, conversation["id"])

    assert stored["recovery_summary"] == recovery_summary


def test_write_json_uses_atomic_replace(monkeypatch, tmp_path: Path):
    target = tmp_path / "runtime_state.json"
    replaced: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def tracking_replace(self: Path, target_path: Path) -> Path:
        replaced.append((self, Path(target_path)))
        return original_replace(self, target_path)

    monkeypatch.setattr(Path, "replace", tracking_replace)

    _write_json(target, {"runtime_status": "running"})

    assert replaced
    tmp_path_used, target_path = replaced[0]
    assert tmp_path_used.parent == target.parent
    assert tmp_path_used.name.startswith(f".{target.name}.")
    assert target_path == target
    assert target.read_text(encoding="utf-8").strip().startswith("{")
