from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.capabilities.skills import get_skill
from app.services.agent_harness.capabilities.skill_protocols import ProtocolRuntimeContext, resolve_skill_protocol
from app.services.agent_harness.capabilities.skill_protocols.tool_guard import ProtocolToolGuard
from app.services.agent_harness.capabilities.skill_protocols.registry import (
    prepare_skill_runtime,
    resolve_protocol_for_context,
)
from app.services.agent_harness.capabilities.skill_protocols.base import PreparedWorkspace, RuntimePrepareRequest
from app.services.agent_harness.capabilities.skill_protocols.open_design import infer_mode, normalize_surface, parse_open_design_facts
from app.services.agent_harness.capabilities.skill_protocols.open_design.materializer import (
    materialize_open_design_prepared_workspace,
)
from app.services.agent_harness.capabilities.skill_protocols.validation_profiles import validate_protocol_html_path
from app.services.agent_harness.capabilities.tools.edit_file import EditFileInput, EditFileTool
from app.services.agent_harness.capabilities.tools.list_files import ListFilesInput, ListFilesTool
from app.services.agent_harness.capabilities.tools.publish_output import PublishOutputInput, PublishOutputTool
from app.services.agent_harness.capabilities.tools.register_artifact import RegisterArtifactInput, RegisterArtifactTool
from app.services.agent_harness.capabilities.tools.read_file import ReadFileInput, ReadFileTool
from app.services.agent_harness.capabilities.tools.write_file import WriteFileInput, WriteFileTool
from app.services.agent_harness.capabilities.tools.exec_command import ExecCommandInput, ExecCommandTool
from app.services.agent_harness.runtime.system_write_lease import register_system_write_lease, system_write_lease
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation


def _prepared_full_deck_context(tmp_path: Path, *, conversation_id: str = "conv-protocol-guard") -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id=conversation_id,
        run_id="run-protocol-guard",
        workspace_root=tmp_path,
        skill_id="html-ppt",
        artifact_mode="slides",
    )
    ctx.ensure_dirs()
    prepared_dir = ctx.work_dir / "deck-prepared"
    (prepared_dir / "assets").mkdir(parents=True)
    (prepared_dir / "assets" / "runtime.js").write_text("console.log('runtime')", encoding="utf-8")
    (prepared_dir / "index.html").write_text(
        "<html><body><main class='deck'><section class='slide'>Ready</section>"
        "<script src='assets/runtime.js'></script></main></body></html>",
        encoding="utf-8",
    )
    ctx.prepared_workspace = PreparedWorkspace(
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
        artifact_work_root="deck-prepared",
        entry_file="index.html",
        selected_template="presenter-mode-reveal",
        source_root="templates/full-decks/presenter-mode-reveal",
    )
    ctx.artifact_work_root = "deck-prepared"
    ctx.prepared_entry_file = "deck-prepared/index.html"
    ctx.workspace_runtime_session = {"active_entry": "deck-prepared/index.html"}
    return ctx


def _skill(tmp_path: Path, *, mode: str = "other", body: str = "", description: str = ""):
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    return SimpleNamespace(
        id="synthetic-skill",
        mode=mode,
        surface=None,
        description=description,
        system_prompt=body,
        skill_dir=skill_dir,
    )


def test_open_design_parser_matches_seed_and_preflight_protocol(tmp_path: Path) -> None:
    skill = _skill(
        tmp_path,
        mode="deck",
        body="Read assets/template.html, references/layouts.md, and references/checklist.md first.",
    )
    (skill.skill_dir / "assets").mkdir()
    (skill.skill_dir / "references").mkdir()

    facts = parse_open_design_facts(skill)
    protocol = resolve_skill_protocol(skill, ProtocolRuntimeContext(artifact_mode="slides"))

    assert facts.has_seed_template is True
    assert facts.preflight_paths == ["assets/template.html", "references/layouts.md", "references/checklist.md"]
    assert facts.checklist_path == "references/checklist.md"
    assert protocol.family == "open_design_seed_template"
    assert protocol.execution_contract.requires_seed_template is False
    assert protocol.execution_contract.requires_deck_framework is False
    assert protocol.validation_profile.hard_block is False


def test_open_design_protocol_uses_generic_deck_only_without_seed(tmp_path: Path) -> None:
    deck_skill = _skill(tmp_path, mode="deck", body="Create a pitch deck.")

    protocol = resolve_skill_protocol(deck_skill, ProtocolRuntimeContext(artifact_mode="slides"))

    assert protocol.family == "open_design_generic_deck"
    assert protocol.execution_contract.requires_deck_framework is False
    assert protocol.validation_profile.required_selectors == []
    assert protocol.validation_profile.hard_block is False


def test_open_design_prepared_materializer_creates_entry_directory_without_placeholder_file(tmp_path: Path) -> None:
    skill_root = tmp_path / "skill-root"
    skill_root.mkdir()
    work_dir = tmp_path / "work"
    prepared = materialize_open_design_prepared_workspace(
        skill_root=skill_root,
        work_dir=work_dir,
        candidate_name="deck-prepared",
        family="open_design_generic_deck",
        strategy="template_driven_deck",
        skill_id="html-ppt",
    )
    entry = work_dir / prepared.entry_path
    skill = _skill(tmp_path, mode="deck", body="Create a pitch deck.")
    protocol = resolve_skill_protocol(
        skill,
        ProtocolRuntimeContext(
            artifact_mode="slides",
            workspace_runtime_session={"active_entry": prepared.entry_path},
        ),
    )

    assert prepared.entry_file == "index.html"
    assert prepared.entry_path == "deck-prepared/index.html"
    assert prepared.source_root == "skill"
    assert prepared.copied_files == []
    assert (work_dir / prepared.artifact_work_root).is_dir()
    assert entry.parent.is_dir()
    assert not entry.exists()
    assert protocol.write_policy is not None
    assert prepared.entry_path in protocol.write_policy.protected_entry_paths


def test_open_design_prepared_materializer_can_copy_template_as_editing_draft(tmp_path: Path) -> None:
    skill_root = tmp_path / "skill-root"
    (skill_root / "assets").mkdir(parents=True)
    (skill_root / "assets" / "template.html").write_text(
        '<html><head><link href="template_files/site.css"></head><body><main id="app"></main></body></html>',
        encoding="utf-8",
    )

    prepared = materialize_open_design_prepared_workspace(
        skill_root=skill_root,
        work_dir=tmp_path / "work",
        candidate_name="seed-prepared",
        family="open_design_seed_template",
        strategy="open_design_seed_template",
        skill_id="seed",
        entry_file="index.html",
    )

    entry = tmp_path / "work" / prepared.entry_path
    assert entry.is_file()
    assert entry.read_text(encoding="utf-8") == (skill_root / "assets" / "template.html").read_text(encoding="utf-8")
    assert not (tmp_path / "work" / prepared.artifact_work_root / "references").exists()


def test_open_design_protocol_routes_media_away_from_html_validation(tmp_path: Path) -> None:
    media_skill = _skill(tmp_path, mode="image", body="Generate an image poster.")

    protocol = resolve_skill_protocol(media_skill, ProtocolRuntimeContext(artifact_mode="image"))

    assert protocol.family == "open_design_media"
    assert protocol.execution_contract.requires_media_contract is True
    assert protocol.publish_profile.skip_html_validation is True


def test_seed_template_checklist_is_validated_as_skill_specific_protocol(tmp_path: Path) -> None:
    skill = _skill(
        tmp_path,
        mode="prototype",
        body="Read assets/template.html and references/checklist.md first.",
    )
    (skill.skill_dir / "assets").mkdir()
    (skill.skill_dir / "assets" / "template.html").write_text("<html></html>", encoding="utf-8")
    entry = tmp_path / "entry.html"
    entry.write_text("<html><body>ok</body></html>", encoding="utf-8")

    protocol = resolve_skill_protocol(skill, ProtocolRuntimeContext(artifact_mode="web"))
    validation = validate_protocol_html_path(entry, protocol)

    assert protocol.family == "open_design_seed_template"
    assert validation["valid"] is True


def test_html_ppt_full_deck_protocol_is_detected_without_skill_id_special_case() -> None:
    skill = get_skill("html-ppt")
    assert skill is not None

    protocol = resolve_skill_protocol(skill, ProtocolRuntimeContext(artifact_mode="slides"))

    assert protocol.family == "harness_full_deck_runtime"
    assert protocol.execution_contract.kind == "harness_full_deck_runtime"


def test_open_design_adapter_prepares_full_deck_runtime_as_prepared_artifact(tmp_path: Path) -> None:
    skill = get_skill("html-ppt")
    assert skill is not None
    assert skill.skill_dir is not None

    result = prepare_skill_runtime(
        skill,
        RuntimePrepareRequest(
            skill=skill,
            conversation={"id": "conv-full-deck"},
            latest_user_request="做一份 product-launch 风格的 deck",
            work_dir=tmp_path,
            active_skill_dir=Path(skill.skill_dir),
            artifact_mode="slides",
        ),
    )

    assert result is not None
    assert result.family == "harness_full_deck_runtime"
    assert result.active_entry == "html-ppt-prepared/index.html"
    assert result.prepared_workspace is not None
    assert result.prepared_workspace["source_root"] == "skill"
    assert result.prepared_workspace["entry_file"] == "index.html"
    assert result.prepared_workspace["entry_path"] == "html-ppt-prepared/index.html"
    assert result.prepared_workspace["copied_files"] == []
    assert (tmp_path / "html-ppt-prepared").is_dir()
    assert not (tmp_path / "html-ppt-prepared" / "index.html").exists()
    assert not (tmp_path / "html-ppt-prepared" / "assets" / "runtime.js").exists()


def test_full_deck_runtime_validation_does_not_hard_require_deck_shell(tmp_path: Path) -> None:
    skill = _skill(tmp_path, mode="deck", body="Create slides.")
    work_dir = tmp_path / "work"
    artifact_work_dir = work_dir / "deck-prepared"
    (artifact_work_dir / "assets").mkdir(parents=True)
    (artifact_work_dir / "assets" / "runtime.js").write_text("console.log('runtime')", encoding="utf-8")
    entry = artifact_work_dir / "index.html"
    entry.write_text("<html><body><section class='slide'>No deck wrapper</section></body></html>", encoding="utf-8")
    session = PreparedWorkspace(
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
        artifact_work_root="deck-prepared",
        entry_file="index.html",
        selected_template="presenter-mode-reveal",
        source_root="templates/full-decks/presenter-mode-reveal",
    )
    protocol = resolve_skill_protocol(
        skill,
        ProtocolRuntimeContext(artifact_mode="slides", prepared_workspace=session, work_dir=work_dir),
    )

    validation = validate_protocol_html_path(entry, protocol)

    assert protocol.family == "harness_full_deck_runtime"
    assert validation["valid"] is True
    assert validation["errors"] == []


def test_prepared_full_deck_protocol_exports_runtime_execution_contract(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)
    skill = get_skill("html-ppt")
    assert skill is not None

    protocol = resolve_skill_protocol(
        skill,
        ProtocolRuntimeContext(
            artifact_mode="slides",
            prepared_workspace=ctx.prepared_workspace,
            workspace_runtime_session=ctx.workspace_runtime_session,
            work_dir=ctx.work_dir,
        ),
    )

    contract = protocol.runtime_execution_contract
    assert contract is not None
    assert contract.active_entry == "deck-prepared/index.html"
    assert contract.artifact_work_root == "deck-prepared"
    assert "deck-prepared" in contract.writable_roots
    assert "references" in contract.readonly_roots


def test_resolve_protocol_for_context_uses_ctx_work_dir_for_prepared_runtime(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)
    skill = get_skill("html-ppt")
    assert skill is not None
    assert skill.skill_dir is not None
    ctx.skill_runtime_dir = Path(skill.skill_dir)

    protocol = resolve_protocol_for_context(ctx)

    assert protocol.family == "harness_full_deck_runtime"


@pytest.mark.asyncio
async def test_write_file_allows_plain_html_in_prepared_runtime_entry(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-protocol-write",
        run_id="run-protocol-write",
        workspace_root=tmp_path,
        skill_id="html-ppt",
        artifact_mode="slides",
    )
    ctx.ensure_dirs()
    prepared_dir = ctx.work_dir / "deck-prepared"
    (prepared_dir / "assets").mkdir(parents=True)
    (prepared_dir / "assets" / "runtime.js").write_text("console.log('runtime')", encoding="utf-8")
    ctx.prepared_workspace = PreparedWorkspace(
        family="harness_full_deck_runtime",
        strategy="template_driven_deck",
        skill_id="html-ppt",
        artifact_work_root="deck-prepared",
        entry_file="index.html",
        selected_template="presenter-mode-reveal",
        source_root="templates/full-decks/presenter-mode-reveal",
    )
    ctx.artifact_work_root = "deck-prepared"

    result = await WriteFileTool().execute(
        WriteFileInput(
            base="work",
            file_path="deck-prepared/index.html",
            content="<html><body><section class='slide'>Static buttons only</section></body></html>",
        ),
        ctx,
    )

    assert result.is_error is False
    assert (prepared_dir / "index.html").read_text(encoding="utf-8") == "<html><body><section class='slide'>Static buttons only</section></body></html>"


@pytest.mark.asyncio
async def test_write_file_rejects_parallel_candidate_for_prepared_runtime(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)

    result = await WriteFileTool().execute(
        WriteFileInput(
            base="project:design-trends-2025",
            file_path="index.html",
            content="<html><body><main class='deck'><section class='slide'>Parallel</section></main></body></html>",
        ),
        ctx,
    )

    assert result.is_error is True
    assert result.metadata["failure_kind"] == "artifact_work_root_mismatch"
    assert result.metadata["artifact_work_root"] == "project/deck-prepared"
    assert "project/deck-prepared" in result.output
    assert not (ctx.work_dir / "design-trends-2025").exists()


@pytest.mark.asyncio
async def test_write_file_legacy_relative_path_stays_inside_prepared_runtime(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)

    result = await WriteFileTool().execute(
        WriteFileInput(
            base="work",
            file_path="nested/index.html",
            content="<html><body>nested</body></html>",
        ),
        ctx,
    )

    assert result.is_error is False
    assert (ctx.work_dir / "deck-prepared" / "nested" / "index.html").is_file()
    assert not (ctx.work_dir / "nested").exists()


@pytest.mark.asyncio
async def test_file_tools_support_skill_base_and_reject_skill_writes(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)
    skill_root = ctx.skill_dir
    (skill_root / "assets").mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("# Skill\n", encoding="utf-8")
    (skill_root / "assets" / "template.html").write_text("<html>template</html>", encoding="utf-8")
    ctx.active_skill_dir = skill_root

    read_result = await ReadFileTool().execute(ReadFileInput(base="skill", path="SKILL.md"), ctx)
    list_result = await ListFilesTool().execute(ListFilesInput(base="skill", path="assets"), ctx)
    write_result = await WriteFileTool().execute(
        WriteFileInput(base="skill", path="x.txt", content="nope"),
        ctx,
    )

    assert read_result.is_error is False
    assert read_result.metadata["conversation_path"] == "skill/SKILL.md"
    assert "# Skill" in read_result.output
    assert list_result.is_error is False
    assert any(entry["path"] == "skill/assets/template.html" for entry in list_result.metadata["entries"])
    assert write_result.is_error is True
    assert write_result.metadata["failure_kind"] in {"read_only_base", "readonly_root", "path_outside_workspace", "path_not_writable"}


@pytest.mark.asyncio
async def test_exec_command_skill_base_can_copy_template_to_work(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)
    skill_root = ctx.skill_dir
    (skill_root / "assets").mkdir(parents=True)
    (skill_root / "assets" / "template.html").write_text("<html>template</html>", encoding="utf-8")
    ctx.active_skill_dir = skill_root

    command = (
        f'"{sys.executable}" -c "import os, shutil; '
        "shutil.copyfile('assets/template.html', os.path.join(os.environ['HARNESS_ARTIFACT_WORK_DIR'], 'index.html'))\""
    )
    result = await ExecCommandTool().execute(ExecCommandInput(base="skill", command=command), ctx)

    assert result.is_error is False
    assert (ctx.work_dir / "deck-prepared" / "index.html").read_text(encoding="utf-8") == "<html>template</html>"


@pytest.mark.asyncio
async def test_exec_command_explicit_project_base_runs_from_project_root(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)

    command = f'"{sys.executable}" -c "import os; print(os.getcwd())"'
    result = await ExecCommandTool().execute(ExecCommandInput(base="project", command=command), ctx)

    assert result.is_error is False
    assert str(ctx.project_dir.resolve()) in result.metadata["stdout"]


@pytest.mark.asyncio
async def test_publish_output_rejects_manifest_outside_artifact_work_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(1, title="Manifest outside work root")
    ctx = _prepared_full_deck_context(tmp_path, conversation_id=conversation["id"])
    class _Sink:
        def emit(self, *args, **kwargs):
            return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.register_artifact.sink_from_context",
        lambda _ctx: _Sink(),
    )
    parallel_dir = ctx.work_dir / "design-trends-2025"
    (parallel_dir / "assets").mkdir(parents=True)
    (parallel_dir / "assets" / "runtime.js").write_text("console.log('parallel')", encoding="utf-8")
    (parallel_dir / "index.html").write_text(
        "<html><body><main class='deck'><section class='slide'>Parallel</section>"
        "<script src='assets/runtime.js'></script></main></body></html>",
        encoding="utf-8",
    )

    registered = await RegisterArtifactTool().execute(
        RegisterArtifactInput(entry="design-trends-2025/index.html", kind="html"),
        ctx,
    )
    assert registered.is_error is False

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is True
    assert result.metadata["protocol_failure"]["failure_kind"] == "artifact_work_root_mismatch"


@pytest.mark.asyncio
async def test_exec_command_reports_readonly_asset_write_for_prepared_runtime(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)

    command = (
        f'"{sys.executable}" -c "import os,pathlib; '
        "pathlib.Path(os.environ['HARNESS_REFERENCES_DIR'], 'generated.txt').write_text('x', encoding='utf-8')\""
    )
    result = await ExecCommandTool().execute(ExecCommandInput(command=command), ctx)

    assert result.is_error is True
    assert result.metadata["protocol_failure"]["failure_kind"] == "readonly_root_write"
    assert "references" in result.output


@pytest.mark.asyncio
async def test_exec_command_start_reports_readonly_asset_write_for_prepared_runtime(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)

    command = (
        f'"{sys.executable}" -c "import os,pathlib; '
        "pathlib.Path(os.environ['HARNESS_REFERENCES_DIR'], 'started.txt').write_text('x', encoding='utf-8')\""
    )
    result = await ExecCommandTool().execute(ExecCommandInput(command=command, action="start", timeout=1), ctx)

    assert result.is_error is True
    assert result.metadata["protocol_failure"]["failure_kind"] == "readonly_root_write"


@pytest.mark.asyncio
async def test_exec_command_reports_readonly_reference_write_without_prepared_runtime(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-command-guard",
        run_id="run-v2-command-guard",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()

    command = (
        f'"{sys.executable}" -c "import os,pathlib; '
        "pathlib.Path(os.environ['HARNESS_REFERENCES_DIR'], 'generated.txt').write_text('x', encoding='utf-8')\""
    )
    result = await ExecCommandTool().execute(ExecCommandInput(command=command), ctx)

    assert result.is_error is True
    assert result.metadata["protocol_failure"]["failure_kind"] == "readonly_root_write"


@pytest.mark.asyncio
async def test_exec_command_reports_system_root_write_without_prepared_runtime(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-hidden-command-guard",
        run_id="run-v2-hidden-command-guard",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()

    command = (
        f'"{sys.executable}" -c "import os,pathlib; '
        "pathlib.Path(os.environ['HARNESS_CONVERSATION_DIR'], '.meta', 'secret.txt').write_text('x', encoding='utf-8')\""
    )
    result = await ExecCommandTool().execute(ExecCommandInput(command=command), ctx)

    assert result.is_error is True
    assert result.metadata["protocol_failure"]["failure_kind"] == "system_root_write"


def test_protocol_guard_ignores_leased_recall_sidecar_writes(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-system-write-lease",
        run_id="run-v2-system-write-lease",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    guard = ProtocolToolGuard(ctx)
    before = guard.snapshot_effects()

    with system_write_lease(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        owner="recall_sidecar",
        paths=[".meta/recall.sqlite"],
        workspace_root=ctx.workspace_root,
    ):
        (ctx.meta_dir / "recall.sqlite").write_text("system", encoding="utf-8")

    assert guard.check_command_effects(before) is None
    journal_entries = sorted((tmp_path / ".system" / "effect_journal" / "1" / ctx.conversation_id).glob("*.json"))
    assert journal_entries
    journal = json.loads(journal_entries[-1].read_text(encoding="utf-8"))
    assert journal["result"] == "allowed"
    assert journal["changed_paths"][0]["attribution"] == "system_write_lease"


def test_protocol_guard_treats_sqlite_journal_as_part_of_leased_database(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-system-write-lease-journal",
        run_id="run-v2-system-write-lease-journal",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    guard = ProtocolToolGuard(ctx)
    before = guard.snapshot_effects()

    with system_write_lease(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        owner="recall_sidecar",
        paths=[".meta/recall.sqlite"],
        workspace_root=ctx.workspace_root,
    ):
        (ctx.meta_dir / "recall.sqlite-journal").write_text("system", encoding="utf-8")

    assert guard.check_command_effects(before) is None


def test_register_system_write_lease_cleans_expired_leases(tmp_path: Path) -> None:
    lease_root = tmp_path / ".system" / "effect_leases"
    lease_root.mkdir(parents=True)
    stale_path = lease_root / "stale.json"
    active_path = lease_root / "active.json"
    base_payload = {
        "user_id": 1,
        "conversation_id": "conv-v2-lease-cleanup",
        "owner": "recall_sidecar",
        "paths": [".meta/recall.sqlite"],
        "started_at_ns": 0,
        "finished_at_ns": None,
        "run_id": None,
        "tool_call_id": None,
    }
    stale_path.write_text(
        json.dumps({**base_payload, "lease_id": "stale", "expires_at_ns": 0}),
        encoding="utf-8",
    )
    active_path.write_text(
        json.dumps({**base_payload, "lease_id": "active", "expires_at_ns": 9_999_999_999_999_999_999}),
        encoding="utf-8",
    )

    lease = register_system_write_lease(
        user_id=1,
        conversation_id="conv-v2-lease-cleanup",
        owner="recall_sidecar",
        paths=[".meta/recall.sqlite"],
        workspace_root=tmp_path,
    )

    assert not stale_path.exists()
    assert active_path.exists()
    assert (lease_root / f"{lease.lease_id}.json").exists()


def test_protocol_guard_does_not_apply_system_write_lease_from_other_run(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-system-write-lease-run-scope",
        run_id="run-current",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    guard = ProtocolToolGuard(ctx)
    before = guard.snapshot_effects()

    with system_write_lease(
        user_id=ctx.user_id,
        conversation_id=ctx.conversation_id,
        owner="recall_sidecar",
        paths=[".meta/recall.sqlite"],
        run_id="run-other",
        workspace_root=ctx.workspace_root,
    ):
        (ctx.meta_dir / "recall.sqlite").write_text("system", encoding="utf-8")

    failure = guard.check_command_effects(before)
    assert failure is not None
    assert failure.failure_kind == "system_root_write"
    journal_entries = sorted((tmp_path / ".system" / "effect_journal" / "1" / ctx.conversation_id).glob("*.json"))
    assert journal_entries
    journal = json.loads(journal_entries[-1].read_text(encoding="utf-8"))
    assert journal["result"] == "blocked"
    assert journal["changed_paths"][0]["failure_kind"] == "system_root_write"


@pytest.mark.asyncio
async def test_protocol_guard_applies_tool_scoped_system_write_lease_only_to_matching_tool(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-system-write-lease-tool-scope",
        run_id="run-current",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    ctx.bind_tool_stream_scope(tool_name="exec_command", tool_call_id="tool-a")
    try:
        guard = ProtocolToolGuard(ctx)
        before = guard.snapshot_effects()

        with system_write_lease(
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            owner="recall_sidecar",
            paths=[".meta/recall.sqlite"],
            run_id=ctx.run_id,
            tool_call_id="tool-b",
            workspace_root=ctx.workspace_root,
        ):
            (ctx.meta_dir / "recall.sqlite").write_text("wrong-tool", encoding="utf-8")

        failure = guard.check_command_effects(before)
        assert failure is not None
        assert failure.failure_kind == "system_root_write"

        before = guard.snapshot_effects()
        with system_write_lease(
            user_id=ctx.user_id,
            conversation_id=ctx.conversation_id,
            owner="recall_sidecar",
            paths=[".meta/recall_cursor.json"],
            run_id=ctx.run_id,
            tool_call_id="tool-a",
            workspace_root=ctx.workspace_root,
        ):
            (ctx.meta_dir / "recall_cursor.json").write_text("{}", encoding="utf-8")

        assert guard.check_command_effects(before) is None
    finally:
        ctx.clear_tool_stream_scope()


def test_protocol_guard_still_blocks_unleased_meta_writes(tmp_path: Path) -> None:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-v2-unleased-hidden-write",
        run_id="run-v2-unleased-hidden-write",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    guard = ProtocolToolGuard(ctx)
    before = guard.snapshot_effects()

    (ctx.meta_dir / "recall.sqlite").write_text("user", encoding="utf-8")

    failure = guard.check_command_effects(before)
    assert failure is not None
    assert failure.failure_kind == "system_root_write"


@pytest.mark.asyncio
async def test_edit_file_protocol_failure_is_atomic_for_prepared_runtime(tmp_path: Path) -> None:
    ctx = _prepared_full_deck_context(tmp_path)
    target = ctx.work_dir / "design-trends-2025" / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("<html><body>parallel</body></html>", encoding="utf-8")

    result = await EditFileTool().execute(
        EditFileInput(
            base="project:design-trends-2025",
            file_path="index.html",
            edits=[{"old_text": "parallel", "new_text": "changed"}],
        ),
        ctx,
    )

    assert result.is_error is True
    assert result.metadata["failure_kind"] == "artifact_work_root_mismatch"
    assert target.read_text(encoding="utf-8") == "<html><body>parallel</body></html>"


def test_publish_output_schema_rejects_removed_mode_parameter() -> None:
    with pytest.raises(ValidationError):
        PublishOutputInput(file_path="index.html", mode="html_bundle")


def test_open_design_infer_mode_and_surface_follow_daemon_rules() -> None:
    assert infer_mode(description="Shortform motion video", body="") == "video"
    assert infer_mode(description="", body="Build a slide deck") == "deck"
    assert normalize_surface(None, "image") == "image"
    assert normalize_surface(None, "prototype") == "web"


def test_real_office_and_web_skills_expose_open_design_facts() -> None:
    docx = get_skill("docx")
    pptx = get_skill("pptx")
    web = get_skill("web")

    assert docx is not None
    assert pptx is not None
    assert web is not None

    docx_facts = parse_open_design_facts(docx)
    pptx_facts = parse_open_design_facts(pptx)
    web_facts = parse_open_design_facts(web)
    docx_protocol = resolve_skill_protocol(docx, ProtocolRuntimeContext(artifact_mode="document"))
    pptx_protocol = resolve_skill_protocol(pptx, ProtocolRuntimeContext(artifact_mode="slides"))
    web_protocol = resolve_skill_protocol(web, ProtocolRuntimeContext(artifact_mode="web"))

    assert docx_facts.mode == "document"
    assert docx_facts.surface == "web"
    assert docx_protocol.provider == "builtin"
    assert docx_protocol.family == "builtin_default"
    assert docx_protocol.mode == "document"
    assert pptx_facts.mode == "document"
    assert pptx_facts.surface == "web"
    assert pptx_protocol.provider == "builtin"
    assert pptx_protocol.family == "builtin_default"
    assert pptx_protocol.mode == "document"
    assert web_facts.mode == "prototype"
    assert web_facts.surface == "web"
    assert web_protocol.family == "open_design_free_web"


def test_adapted_template_and_missing_mode_skills_resolve_protocol_families(tmp_path: Path) -> None:
    social_media_matrix = get_skill("social-media-matrix-tracker-template")
    html_ppt_taste = get_skill("html-ppt-taste-brutalist")
    web_prototype_taste = get_skill("web-prototype-taste-brutalist")

    assert social_media_matrix is not None
    assert html_ppt_taste is not None
    assert web_prototype_taste is not None

    social_media_protocol = resolve_skill_protocol(
        social_media_matrix,
        ProtocolRuntimeContext(artifact_mode="web"),
    )
    html_ppt_taste_protocol = resolve_skill_protocol(
        html_ppt_taste,
        ProtocolRuntimeContext(artifact_mode="slides"),
    )
    web_prototype_taste_protocol = resolve_skill_protocol(
        web_prototype_taste,
        ProtocolRuntimeContext(artifact_mode="web"),
    )

    assert social_media_matrix.mode == "template"
    assert social_media_protocol.family == "open_design_seed_template"
    assert html_ppt_taste.mode == "deck"
    assert html_ppt_taste_protocol.family == "open_design_generic_deck"
    assert web_prototype_taste.mode == "prototype"
    assert web_prototype_taste_protocol.family == "open_design_free_web"

    prepared = prepare_skill_runtime(
        social_media_matrix,
        RuntimePrepareRequest(
            skill=social_media_matrix,
            conversation={"id": "conv-social-matrix"},
            latest_user_request="做一个社媒矩阵追踪模板",
            work_dir=tmp_path,
            active_skill_dir=Path(social_media_matrix.skill_dir),
            artifact_mode="web",
        ),
    )

    assert prepared is not None
    assert prepared.family == "open_design_seed_template"
    assert prepared.active_entry == "social-media-matrix-tracker-template-prepared/index.html"
