from __future__ import annotations

import asyncio
import json

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.capabilities.skill_protocols.base import PreparedWorkspace
from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.capabilities.tools._internal.command_runner import build_env


def test_workspace_map_omits_active_job(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Workspace map")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()
    registry = create_harness_registry()

    result = asyncio.run(registry.execute("workspace_map", {}, ctx))

    assert result.is_error is False
    assert "active_job" not in (result.metadata or {})


def test_workspace_map_explains_conversation_dir_path_forms(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Workspace map forms")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()
    registry = create_harness_registry()

    result = asyncio.run(registry.execute("workspace_map", {}, ctx))
    payload = result.metadata or {}

    assert payload["root"] == "CONVERSATION_DIR"
    assert payload["visible_roots"]["project"]["path"] == "CONVERSATION_DIR/project"
    assert payload["visible_roots"]["references"]["path"] == "CONVERSATION_DIR/references"
    assert payload["path_forms"]["workspace_relative"] == "project/report.py"
    assert payload["path_forms"]["work_directory_relative"] == "report.py"
    assert payload["path_forms"]["command_cwd_relative"] == "python report.py"
    assert payload["visible_roots"]["skill"]["path"] == "CONVERSATION_DIR/skill"
    assert "read_active_skill_overview" not in payload["examples"]
    assert "read_active_skill_reference" not in payload["examples"]
    assert "list_active_skill_folder_if_needed" not in payload["examples"]
    assert "SKILL.md" not in json.dumps(payload, ensure_ascii=False)
    assert payload["examples"]["list_other_prepared_directory"] == {
        "tool": "list_files",
        "base": "project:other-prepared",
        "path": ".",
        "recursive": False,
    }
    assert "$HARNESS_REFERENCE_INPUTS_DIR/" in payload["examples"]["script_reads_upload"]
    assert "active_job" not in payload
    assert ".skill_runtime" not in json.dumps(payload, ensure_ascii=False)


def test_workspace_map_includes_protocol_execution_contract(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Workspace map protocol")
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-1",
        workspace_root=tmp_path,
        skill_id="html-ppt",
        artifact_mode="slides",
    )
    ctx.ensure_dirs()
    ctx.prepared_workspace = PreparedWorkspace(
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
        artifact_work_root="deck-prepared",
        entry_file="index.html",
        selected_template="presenter-mode-reveal",
        source_root="templates/full-decks/presenter-mode-reveal",
    )
    ctx.prepared_entry_file = "deck-prepared/index.html"
    ctx.artifact_work_root = "deck-prepared"
    ctx.workspace_runtime_session = {"active_entry": "deck-prepared/index.html"}
    (ctx.work_dir / "deck-prepared" / "assets").mkdir(parents=True)
    (ctx.work_dir / "deck-prepared" / "assets" / "runtime.js").write_text("console.log('runtime')", encoding="utf-8")
    registry = create_harness_registry()

    result = asyncio.run(registry.execute("workspace_map", {}, ctx))
    payload = result.metadata or {}

    assert payload["protocol_runtime"]["active_entry"] == "deck-prepared/index.html"
    assert payload["protocol_runtime"]["artifact_work_root"] == "deck-prepared"
    assert payload["default_command_cwd"] == "project/deck-prepared"
    assert payload["artifact_work_root"] == "project/deck-prepared"
    assert "references" in payload["protocol_runtime"]["readonly_roots"]


def test_build_env_omits_active_job_variables(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    conversation = create_conversation(7, title="Command env")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()

    env = build_env(ctx)

    assert env["HARNESS_CONVERSATION_DIR"]
    assert env["HARNESS_PROJECT_DIR"]
    assert env["HARNESS_ARTIFACT_WORK_DIR"] == env["HARNESS_PROJECT_DIR"]
    assert env["HARNESS_ARTIFACT_WORK_ROOT"] == ""
    assert env["HARNESS_REFERENCES_DIR"]
    assert env["HARNESS_REFERENCE_INPUTS_DIR"]
    assert env["HARNESS_PUBLISHED_DIR"]
    assert all(not key.startswith("HARNESS_ACTIVE_") for key in env)
    assert "PLAYWRIGHT_BROWSERS_PATH" not in env


def test_build_env_preserves_playwright_browser_path(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/custom-playwright")
    conversation = create_conversation(7, title="Command env")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()

    env = build_env(ctx)

    assert env["PLAYWRIGHT_BROWSERS_PATH"] == "/custom-playwright"


def test_build_env_points_skill_dir_to_staged_runtime_copy(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Command env staged skill")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()
    runtime_dir = ctx.skill_dir
    runtime_dir.mkdir(parents=True, exist_ok=True)
    ctx.active_skill_dir = runtime_dir
    ctx.skill_runtime_dir = runtime_dir

    env = build_env(ctx)

    assert env["HARNESS_SKILL_ROOT"] == str(runtime_dir.resolve())


def test_build_env_exposes_active_artifact_work_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Command env work dir")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()
    ctx.workspace_runtime_session = {
        "artifact_work_root": "dashboard-prepared",
        "agent_cwd": "project/dashboard-prepared",
    }

    env = build_env(ctx)

    assert env["HARNESS_ARTIFACT_WORK_ROOT"] == "dashboard-prepared"
    assert env["HARNESS_ARTIFACT_WORK_DIR"] == str((ctx.project_dir / "dashboard-prepared").resolve())


def test_build_env_routes_node_tool_caches_into_active_artifact_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Command env node cache")
    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    ctx.ensure_dirs()
    ctx.workspace_runtime_session = {
        "artifact_work_root": "html-ppt-prepared",
        "agent_cwd": "project/html-ppt-prepared",
    }

    env = build_env(ctx)

    expected_cache_root = ctx.project_dir / "html-ppt-prepared" / ".cache"
    assert env["HOME"] == str(expected_cache_root.resolve())
    assert env["XDG_CACHE_HOME"] == str(expected_cache_root.resolve())
    assert env["NPM_CONFIG_CACHE"] == str((expected_cache_root / "npm").resolve())
    assert env["npm_config_cache"] == str((expected_cache_root / "npm").resolve())
