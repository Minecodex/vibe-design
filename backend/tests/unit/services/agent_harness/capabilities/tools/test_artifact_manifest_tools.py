from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from pydantic import ValidationError
from openpyxl import Workbook

from app.db.harness_session import harness_sync_session_scope
from app.models.harness_session import HarnessAgentRun, HarnessConversation
from app.services.agent_harness.capabilities.tools.publish_output import PublishOutputInput, PublishOutputTool
from app.services.agent_harness.capabilities.tools.register_artifact import RegisterArtifactInput, RegisterArtifactTool
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.artifacts.kind_registry import validate_kind_contract
from app.services.agent_harness.runtime.artifacts.manifest import read_artifact_manifest
from app.services.agent_harness.runtime.critique.repository import create_run, finalize_run, insert_round
from app.services.agent_harness.workflow.gateway import AgentRuntimeGateway
from app.services.agent_harness.workspace.conversation.conversation_service import create_conversation
from app.services.agent_harness.workspace.session_v2 import db_store


def _ctx(tmp_path: Path, conversation_id: str) -> HarnessContext:
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation_id,
        run_id="run-artifact-manifest",
        workspace_root=tmp_path,
        skill_id="xlsx",
        artifact_mode="xlsx",
    )
    ctx.ensure_dirs()
    return ctx


def _html_ctx(tmp_path: Path, conversation_id: str) -> HarnessContext:
    ctx = HarnessContext(
        user_id=7,
        conversation_id=conversation_id,
        run_id="run-open-design-html",
        workspace_root=tmp_path,
        runtime_profile="home",
        skill_id="open-design-landing",
        artifact_mode="web",
    )
    ctx.ensure_dirs()
    return ctx


def _write_workbook(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Data"
    sheet["A1"] = "Year"
    sheet["B1"] = "Births"
    sheet.append([2024, 100])
    workbook.save(path)


def _write_html(path: Path, html: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _agent_run(ctx: HarnessContext) -> None:
    with harness_sync_session_scope() as session:
        session.merge(
            HarnessConversation(
                conversation_id=ctx.conversation_id,
                user_id=ctx.user_id,
                title="Publish critique",
                runtime_profile=ctx.runtime_profile,
                skill_id=ctx.skill_id,
                artifact_mode=ctx.artifact_mode,
                status="active",
                runtime_status="running",
            )
        )
        session.add(
            HarnessAgentRun(
                run_id=ctx.run_id,
                user_id=ctx.user_id,
                conversation_id=ctx.conversation_id,
                kind="message",
                status="running",
                input_json={},
                runtime_snapshot_json={},
                idempotency_key=ctx.run_id,
            )
        )


def _open_design_protocol() -> SimpleNamespace:
    return SimpleNamespace(
        provider="open_design",
        family="open_design_free_web",
        mode="prototype",
        surface="web",
        runtime_execution_contract=None,
        publish_profile=SimpleNamespace(skip_html_validation=False),
    )


def _active_design_system_context() -> dict:
    return {
        "kind": "active_design_system_context",
        "design_system_id": "test",
        "tokens_css": """
        :root {
          --bg: #FFFFFF;
          --surface: #F8FAFC;
          --fg: #0F172A;
          --muted: #64748B;
          --border: #CBD5E1;
          --accent: #FECE14;
          --font-display: Georgia, serif;
          --font-body: Arial, sans-serif;
          --text-base: 16px;
          --radius-md: 8px;
          --focus-ring: 0 0 0 3px rgba(254, 206, 20, 0.35);
          --container-max: 1120px;
        }
        """,
    }


async def _persist_active_design_system_context(user_id: int, conversation_id: str) -> None:
    gateway = AgentRuntimeGateway(
        user_id=user_id,
        conversation_id=conversation_id,
        run_id="run-open-design-html",
        step_id="step-design-system",
    )
    await gateway.update_runtime_snapshot(
        {
            "runtime_state": {
                "runtime_contract": {
                    "design_system_id": "test",
                    "active_design_system_context": _active_design_system_context(),
                }
            }
        }
    )


@pytest.mark.asyncio
async def test_register_artifact_writes_manifest_and_runtime_session(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Register spreadsheet")
    ctx = _ctx(tmp_path, conversation["id"])
    _write_workbook(ctx.project_dir / "xlsx-prepared" / "births.xlsx")
    (ctx.project_dir / "xlsx-prepared" / "build.py").write_text("print('build')", encoding="utf-8")

    result = await RegisterArtifactTool().execute(
        RegisterArtifactInput(
            entry="xlsx-prepared/births.xlsx",
            kind="spreadsheet",
            title="Births",
            supporting_files=["xlsx-prepared/build.py"],
        ),
        ctx,
    )

    assert result.is_error is False
    payload = db_store.read_runtime_state_payload(7, conversation["id"])
    runtime_state = payload["runtime_state"]
    manifest = runtime_state["artifact_manifest"]
    assert manifest["entry"] == "xlsx-prepared/births.xlsx"
    assert manifest["kind"] == "spreadsheet"
    assert manifest["renderer"] == "file"
    assert manifest["exports"] == ["xlsx"]
    assert manifest["supporting_files"] == ["xlsx-prepared/build.py"]
    assert manifest["validation"]["status"] == "passed"
    assert runtime_state["workspace_runtime_session"]["active_entry"] == "xlsx-prepared/births.xlsx"
    assert "publish_targets" not in runtime_state["workspace_runtime_session"]


@pytest.mark.asyncio
async def test_register_artifact_rejects_script_as_spreadsheet(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Reject script entry")
    ctx = _ctx(tmp_path, conversation["id"])
    script = ctx.project_dir / "xlsx-prepared" / "build.py"
    script.parent.mkdir(parents=True)
    script.write_text("print('not a workbook')", encoding="utf-8")

    result = await RegisterArtifactTool().execute(
        RegisterArtifactInput(
            entry="xlsx-prepared/build.py",
            kind="spreadsheet",
            title="Build script",
        ),
        ctx,
    )

    assert result.is_error is True
    assert ".py files may only be registered as code artifacts" in result.output
    payload = db_store.read_runtime_state_payload(7, conversation["id"])
    runtime_state = payload["runtime_state"] or {}
    assert "artifact_manifest" not in runtime_state


@pytest.mark.asyncio
async def test_publish_output_requires_registered_manifest(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Publish without manifest")
    ctx = _ctx(tmp_path, conversation["id"])

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is True
    assert result.metadata["reason_code"] == "artifact_manifest_missing"
    assert result.metadata["required_tool"] == "register_artifact"


@pytest.mark.asyncio
async def test_publish_output_keeps_manifest_after_runtime_snapshot_patch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Publish after runtime patch")
    ctx = _ctx(tmp_path, conversation["id"])
    _write_workbook(ctx.project_dir / "births.xlsx")

    register_result = await RegisterArtifactTool().execute(
        RegisterArtifactInput(
            entry="births.xlsx",
            kind="spreadsheet",
            title="Births",
        ),
        ctx,
    )
    assert register_result.is_error is False

    gateway = AgentRuntimeGateway(
        user_id=7,
        conversation_id=conversation["id"],
        run_id="run-artifact-manifest",
        step_id="step-render-context",
    )
    await gateway.update_runtime_snapshot(
        {"runtime_status": "running", "run_state": "rendering_context", "turn_status": "running"}
    )

    publish_result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert publish_result.is_error is False
    assert publish_result.metadata["artifact_manifest"]["entry"] == "births.xlsx"
    assert publish_result.metadata["published_file"]["path"].startswith("project/")


@pytest.mark.asyncio
async def test_publish_output_blocks_home_open_design_html_with_p0_lint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.resolve_protocol_for_context",
        lambda _ctx: _open_design_protocol(),
    )
    conversation = create_conversation(
        7,
        title="Publish lint p0",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = _html_ctx(tmp_path, conversation["id"])
    _write_html(
        ctx.project_dir / "landing" / "index.html",
        "<!doctype html><html><head><style>"
        ".hero { background: linear-gradient(90deg, #3b82f6, #06b6d4); }"
        "</style></head><body><h1>Feature One</h1></body></html>",
    )
    registered = await RegisterArtifactTool().execute(
        RegisterArtifactInput(entry="landing/index.html", kind="html", title="Landing"),
        ctx,
    )
    assert registered.is_error is False

    async def fail_if_quality_review_runs(**_kwargs):
        pytest.fail("P0 open-design lint should block before quality review")

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.ensure_quality_review_authorized",
        fail_if_quality_review_runs,
    )

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is True
    assert result.metadata["reason_code"] == "open_design_artifact_lint_failed"
    assert result.metadata["failure_kind"] == "artifact_lint_failed"
    assert result.metadata["p0_count"] >= 1
    assert "trust-gradient" in {item["id"] for item in result.metadata["lint_findings"]}
    assert result.output.startswith("<artifact-lint>")


@pytest.mark.asyncio
async def test_publish_output_blocks_modified_active_design_system_tokens(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.resolve_protocol_for_context",
        lambda _ctx: _open_design_protocol(),
    )
    conversation = create_conversation(
        7,
        title="Publish design system drift",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = _html_ctx(tmp_path, conversation["id"])
    await _persist_active_design_system_context(ctx.user_id, ctx.conversation_id)
    _write_html(
        ctx.project_dir / "landing" / "index.html",
        "<!doctype html><html><head><style>"
        ":root { --bg:#FFFFFF; --surface:#F8FAFC; --fg:#0F172A; --muted:#64748B; --border:#CBD5E1; "
        "--accent:#2563EB; --font-display:Georgia, serif; --font-body:Arial, sans-serif; --text-base:16px; "
        "--radius-md:8px; --focus-ring:0 0 0 3px rgba(254, 206, 20, 0.35); --container-max:1120px; }"
        ".cta { background: var(--accent); }"
        "</style></head><body><a class='cta'>Start</a></body></html>",
    )
    registered = await RegisterArtifactTool().execute(
        RegisterArtifactInput(entry="landing/index.html", kind="html", title="Landing"),
        ctx,
    )
    assert registered.is_error is False

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is True
    assert result.metadata["reason_code"] == "design_system_contract_failed"
    assert result.metadata["design_system_compliance"]["blocks_publish"] is True
    assert "design-system-core-token-modified" in {item["id"] for item in result.metadata["lint_findings"]}


@pytest.mark.asyncio
async def test_publish_output_blocks_raw_hex_outside_active_design_system_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.resolve_protocol_for_context",
        lambda _ctx: _open_design_protocol(),
    )
    conversation = create_conversation(
        7,
        title="Publish raw hex drift",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = _html_ctx(tmp_path, conversation["id"])
    await _persist_active_design_system_context(ctx.user_id, ctx.conversation_id)
    _write_html(
        ctx.project_dir / "landing" / "index.html",
        "<!doctype html><html><head><style>"
        ":root { --bg:#FFFFFF; --surface:#F8FAFC; --fg:#0F172A; --muted:#64748B; --border:#CBD5E1; "
        "--accent:#FECE14; --font-display:Georgia, serif; --font-body:Arial, sans-serif; --text-base:16px; "
        "--radius-md:8px; --focus-ring:0 0 0 3px rgba(254, 206, 20, 0.35); --container-max:1120px; }"
        ".cta { background: #FECE14; }"
        "</style></head><body><a class='cta'>Start</a></body></html>",
    )
    registered = await RegisterArtifactTool().execute(
        RegisterArtifactInput(entry="landing/index.html", kind="html", title="Landing"),
        ctx,
    )
    assert registered.is_error is False

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is True
    assert result.metadata["reason_code"] == "design_system_contract_failed"
    assert "design-system-raw-hex" in {item["id"] for item in result.metadata["lint_findings"]}


@pytest.mark.asyncio
async def test_publish_output_allows_home_open_design_html_with_p1_lint(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.resolve_protocol_for_context",
        lambda _ctx: _open_design_protocol(),
    )
    conversation = create_conversation(
        7,
        title="Publish lint p1",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = _html_ctx(tmp_path, conversation["id"])
    _write_html(
        ctx.project_dir / "landing" / "index.html",
        "<!doctype html><html><head><style>"
        ".eyebrow { text-transform: uppercase; font-size: 24px; letter-spacing: 1px; }"
        "</style></head><body><p class='eyebrow'>Launch notes</p></body></html>",
    )
    registered = await RegisterArtifactTool().execute(
        RegisterArtifactInput(entry="landing/index.html", kind="html", title="Landing"),
        ctx,
    )
    assert registered.is_error is False

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is False
    assert result.metadata["open_design_lint"]["p0_count"] == 0
    assert any(item["id"] == "all-caps-no-tracking" for item in result.metadata["open_design_lint"]["findings"])
    manifest = read_artifact_manifest(ctx.user_id, ctx.conversation_id)
    assert manifest is not None
    assert manifest["publication"]["payload"]["open_design_lint"]["p1_count"] >= 1


@pytest.mark.asyncio
async def test_publish_output_restores_selected_critique_snapshot_before_bundle(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_ENABLED", True)
    monkeypatch.setattr("app.core.config.settings.HARNESS_CRITIQUE_MAX_ROUNDS", 3)
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.resolve_protocol_for_context",
        lambda _ctx: _open_design_protocol(),
    )
    async def _authorized(**_kwargs):
        return None

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.publish_output.ensure_quality_review_authorized",
        _authorized,
    )
    conversation = create_conversation(
        7,
        title="Publish selected critique snapshot",
        runtime_profile="home",
        artifact_mode="web",
        skill_id="open-design-landing",
        resolved_skill_id="open-design-landing",
    )
    ctx = _html_ctx(tmp_path, conversation["id"])
    ctx.artifact_work_root = "landing"
    _agent_run(ctx)
    _write_html(
        ctx.project_dir / "landing" / "index.html",
        "<!doctype html><html><body><main><h1>Round 3</h1></main></body></html>",
    )
    snapshot = ctx.conversation_dir / "critique" / "critique-1" / "round-2"
    _write_html(
        snapshot / "artifact-work-root" / "index.html",
        "<!doctype html><html><body><main><h1>Round 2</h1></main></body></html>",
    )
    (snapshot / "artifact_manifest.json").write_text(
        '{"entry":"landing/index.html","kind":"html","renderer":"html","exports":["html"],"supporting_files":[]}',
        encoding="utf-8",
    )
    (snapshot / "round.json").write_text(
        '{"artifact_work_root":"landing","active_entry":"landing/index.html"}',
        encoding="utf-8",
    )
    registered = await RegisterArtifactTool().execute(
        RegisterArtifactInput(entry="landing/index.html", kind="html", title="Landing"),
        ctx,
    )
    assert registered.is_error is False
    with harness_sync_session_scope() as session:
        create_run(
            session,
            critique_run_id="critique-1",
            harness_run_id=ctx.run_id,
            conversation_id=ctx.conversation_id,
            user_id=ctx.user_id,
            artifact_mode="web",
            artifact_work_root="landing",
        )
        insert_round(
            session,
            critique_run_id="critique-1",
            round_number=2,
            active_entry="landing/index.html",
            snapshot_relpath="critique/critique-1/round-2",
            composite=8.0,
            must_fix_count=8,
            findings=[],
        )
        assert finalize_run(
            session,
            critique_run_id="critique-1",
            status="below_threshold",
            best_round=2,
            score=8.0,
            selected_snapshot_relpath="critique/critique-1/round-2",
        )

    result = await PublishOutputTool().execute(PublishOutputInput(), ctx)

    assert result.is_error is False
    assert (ctx.project_dir / "landing" / "index.html").read_text(encoding="utf-8").find("Round 2") >= 0
    published_relpath = result.metadata.get("file_path") or result.metadata.get("path") or result.metadata.get("current_version_path")
    if not published_relpath:
        published_relpath = result.metadata["artifact_manifest"]["publication"]["payload"]["current_version_path"]
    published_path = ctx.conversation_dir / published_relpath
    with zipfile.ZipFile(published_path) as bundle:
        assert "Round 2" in bundle.read("index.html").decode("utf-8")
        assert "Round 3" not in bundle.read("index.html").decode("utf-8")


def test_kind_registry_rejects_mismatched_renderer_and_extension() -> None:
    ok, errors, _spec = validate_kind_contract(
        kind="spreadsheet",
        renderer="html",
        exports=["xlsx"],
        entry="xlsx-prepared/report.py",
    )

    assert ok is False
    assert any("spreadsheet renderer" in error for error in errors)
    assert any(".py files" in error for error in errors)


def test_manifest_tool_inputs_do_not_accept_removed_parameters() -> None:
    with pytest.raises(ValidationError):
        RegisterArtifactInput(
            entry="xlsx-prepared/births.xlsx",
            kind="spreadsheet",
            renderer="file",
            exports=["xlsx"],
        )

    with pytest.raises(ValidationError):
        PublishOutputInput(path="xlsx-prepared/births.xlsx")
