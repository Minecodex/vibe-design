import asyncio
import json

import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.authoring.preflight.tool_preflight import HarnessPreflightHook
from app.services.agent_harness.runtime.execution_support.reviewer import review_tool_result
from app.services.agent_harness.capabilities.tools.edit_file import EditFileInput, EditFileTool
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult
from app.services.agent_harness.capabilities.tools._internal.command_runner import CommandRunner
from app.services.agent_harness.capabilities.tools.exec_command import _attach_exec_normalization
from app.services.agent_harness.capabilities.tools.exec_command import ExecCommandInput, ExecCommandTool
from app.services.agent_harness.capabilities.tools.list_files import ListFilesInput, ListFilesTool
from app.services.agent_harness.capabilities.tools.read_file import ReadFileInput, ReadFileTool
from app.services.agent_harness.capabilities.tools.write_file import WriteFileInput, WriteFileTool


def _ctx(tmp_path) -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-1",
        run_id="run-1",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    return ctx


@pytest.mark.asyncio
async def test_write_file_writes_project_path(tmp_path):
    ctx = _ctx(tmp_path)
    tool = WriteFileTool()
    params = WriteFileInput.model_validate({"file_path": "project/foo.py", "content": "print('ok')"})

    assert tool.validate_input(params, ctx) is None

    result = await tool.execute(params, ctx)

    assert not result.is_error
    assert (ctx.project_dir / "foo.py").read_text(encoding="utf-8") == "print('ok')"
    assert result.metadata["path"] == "project/foo.py"


@pytest.mark.asyncio
async def test_write_file_allows_project_assets_path(tmp_path):
    ctx = _ctx(tmp_path)
    tool = WriteFileTool()
    params = WriteFileInput.model_validate({"path": "project/assets/hero.txt", "content": "hero"})

    assert tool.validate_input(params, ctx) is None

    result = await tool.execute(params, ctx)

    assert not result.is_error
    assert (ctx.project_dir / "assets" / "hero.txt").read_text(encoding="utf-8") == "hero"
    assert result.metadata["path"] == "project/assets/hero.txt"


@pytest.mark.asyncio
async def test_write_file_normalizes_duplicate_project_prefix(tmp_path):
    ctx = _ctx(tmp_path)
    tool = WriteFileTool()
    params = WriteFileInput.model_validate({"path": "project/project/foo.txt", "content": "ok"})

    assert tool.validate_input(params, ctx) is None

    result = await tool.execute(params, ctx)

    assert not result.is_error
    assert (ctx.project_dir / "foo.txt").read_text(encoding="utf-8") == "ok"
    assert not (ctx.project_dir / "project" / "foo.txt").exists()
    assert result.metadata["path"] == "project/foo.txt"
    assert result.metadata["normalized_path"] == "foo.txt"
    assert result.metadata["original_input"] == "project/project/foo.txt"
    assert result.metadata["path_normalization"]["normalization_kind"] == "duplicate_semantic_root"
    assert result.metadata["path_normalization"]["confidence"] == "high"


@pytest.mark.asyncio
async def test_write_file_normalizes_windows_separators_with_audit_metadata(tmp_path):
    ctx = _ctx(tmp_path)
    tool = WriteFileTool()
    params = WriteFileInput.model_validate({"path": "project\\nested\\foo.txt", "content": "ok"})

    assert tool.validate_input(params, ctx) is None

    result = await tool.execute(params, ctx)

    assert not result.is_error
    assert (ctx.project_dir / "nested" / "foo.txt").read_text(encoding="utf-8") == "ok"
    assert result.metadata["path"] == "project/nested/foo.txt"
    assert result.metadata["path_normalization"]["normalization_kind"] == "separator_normalized"


@pytest.mark.asyncio
async def test_write_file_does_not_treat_inputs_json_as_global_skill_contract(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.active_skill_dir = ctx.skill_dir
    ctx.skill_id = "script-skill"
    (ctx.skill_dir / "inputs.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["brand", "hero"],
                "properties": {
                    "brand": {
                        "type": "object",
                        "required": ["rails"],
                        "properties": {
                            "rails": {
                                "type": "object",
                                "required": ["left", "right"],
                                "properties": {
                                    "left": {"type": "string"},
                                    "right": {"type": "string"},
                                },
                            }
                        },
                    },
                    "hero": {
                        "type": "object",
                        "required": ["index"],
                        "properties": {"index": {"type": "array"}},
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    params = WriteFileInput.model_validate(
        {
            "path": "project/inputs.json",
            "content": json.dumps(
                {"brand": {"rails": {"left": "L"}}, "hero": {"index": "not-array"}}
            ),
        }
    )

    result = await WriteFileTool().execute(params, ctx)

    assert result.is_error is False
    assert json.loads((ctx.project_dir / "inputs.json").read_text(encoding="utf-8")) == {
        "brand": {"rails": {"left": "L"}},
        "hero": {"index": "not-array"},
    }


@pytest.mark.asyncio
async def test_exec_command_does_not_prevalidate_compose_inputs_as_global_contract(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path)
    ctx.active_skill_dir = ctx.skill_dir
    ctx.skill_id = "script-skill"
    (ctx.skill_dir / "scripts").mkdir(parents=True)
    (ctx.skill_dir / "scripts" / "compose.ts").write_text(
        "throw new Error('should not run')",
        encoding="utf-8",
    )
    (ctx.skill_dir / "inputs.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["brand"],
                "properties": {
                    "brand": {
                        "type": "object",
                        "required": ["rails"],
                        "properties": {
                            "rails": {
                                "type": "object",
                                "required": ["right"],
                                "properties": {"right": {"type": "string"}},
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (ctx.project_dir / "inputs.json").write_text(
        json.dumps({"brand": {"rails": {}}}),
        encoding="utf-8",
    )

    from app.services.agent_harness.capabilities.tools import exec_command as exec_command_module
    from app.services.agent_harness.capabilities.tools._internal.command_runner import CommandRunResult

    class _Runner:
        def validate_command(self, command: str) -> None:
            return None

        async def run_once(self, *, ctx, command: str, cwd: str, timeout: int):
            return CommandRunResult(
                exit_code=0,
                stdout="composer ran",
                stderr="",
                timed_out=False,
            )

    monkeypatch.setattr(exec_command_module, "get_command_runner", lambda: _Runner())

    result = await ExecCommandTool().execute(
        ExecCommandInput(
            command="npx tsx $HARNESS_SKILL_ROOT/scripts/compose.ts inputs.json out/index.html"
        ),
        ctx,
    )

    assert result.is_error is False
    assert "composer ran" in result.output


def test_write_file_rejects_encoded_traversal(tmp_path):
    ctx = _ctx(tmp_path)
    tool = WriteFileTool()
    params = WriteFileInput.model_validate({"path": "project/%2e%2e/escape.txt", "content": "x"})

    err = tool.validate_input(params, ctx)

    assert err is not None
    assert "Parent traversal is not allowed" in err


def test_write_file_rejects_non_project_targets(tmp_path):
    ctx = _ctx(tmp_path)
    tool = WriteFileTool()

    assets_params = WriteFileInput.model_validate({"file_path": "references/inputs/x.txt", "content": "x"})
    parent_params = WriteFileInput.model_validate({"file_path": "../x.txt", "content": "x"})

    assert "read-only" in (tool.validate_input(assets_params, ctx) or "")
    assert "Parent traversal is not allowed" in (tool.validate_input(parent_params, ctx) or "")


@pytest.mark.asyncio
async def test_read_file_normalizes_duplicate_project_prefix_and_reports_audit(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.project_dir / "notes.txt").write_text("hello", encoding="utf-8")

    result = await ReadFileTool().execute(
        ReadFileInput.model_validate({"base": "work", "path": "project/project/notes.txt"}),
        ctx,
    )

    # read_file returns line-numbered output (`<6-wide lineno>\t<text>`).
    assert result.output == "     1\thello"
    assert result.metadata["path"] == "project/notes.txt"
    assert result.metadata["file_path"] == "notes.txt"
    assert result.metadata["path_normalization"]["normalization_kind"] == "duplicate_semantic_root"


@pytest.mark.asyncio
async def test_edit_file_edits_project_path(tmp_path):
    ctx = _ctx(tmp_path)
    target = ctx.project_dir / "foo.py"
    target.write_text("hello", encoding="utf-8")
    tool = EditFileTool()
    params = EditFileInput.model_validate({"file_path": "project/foo.py", "edits": [{"old_text": "hello", "new_text": "world"}]})

    assert tool.validate_input(params, ctx) is None

    result = await tool.execute(params, ctx)

    assert not result.is_error
    assert target.read_text(encoding="utf-8") == "world"
    assert result.metadata["changed_files"][0]["file_path"] == "foo.py"


@pytest.mark.asyncio
async def test_edit_file_rejects_non_project_targets(tmp_path):
    ctx = _ctx(tmp_path)
    tool = EditFileTool()
    params = EditFileInput.model_validate({"file_path": "references/inputs/x.txt", "edits": [{"old_text": "hello", "new_text": "world"}]})

    err = tool.validate_input(params, ctx)

    assert err is not None
    assert "read-only" in err


@pytest.mark.asyncio
async def test_edit_file_applies_multiple_replacements_atomically(tmp_path):
    ctx = _ctx(tmp_path)
    target = ctx.work_dir / "foo.py"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    tool = EditFileTool()
    params = EditFileInput.model_validate(
        {
            "file_path": "foo.py",
            "edits": [
                {"old_text": "alpha", "new_text": "one"},
                {"old_text": "gamma", "new_text": "three"},
            ],
        }
    )

    result = await tool.execute(params, ctx)

    assert not result.is_error
    assert target.read_text(encoding="utf-8") == "one\nbeta\nthree\n"
    changed = result.metadata["changed_files"][0]
    assert changed["action"] == "update"
    assert changed["changed"] is True
    assert changed["first_changed_line"] == 1
    assert "-alpha" in changed["diff"]
    assert "+one" in changed["diff"]


@pytest.mark.asyncio
async def test_edit_file_rejects_ambiguous_old_text_without_writing(tmp_path):
    ctx = _ctx(tmp_path)
    target = ctx.work_dir / "foo.py"
    target.write_text("same\nmiddle\nsame\n", encoding="utf-8")
    tool = EditFileTool()
    params = EditFileInput.model_validate({"file_path": "foo.py", "edits": [{"old_text": "same", "new_text": "once"}]})

    result = await tool.execute(params, ctx)

    assert result.is_error
    assert "matched 2 times" in result.output
    assert target.read_text(encoding="utf-8") == "same\nmiddle\nsame\n"


@pytest.mark.asyncio
async def test_edit_file_rolls_back_when_post_write_step_fails(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    target = ctx.work_dir / "foo.py"
    target.write_text("hello", encoding="utf-8")
    tool = EditFileTool()
    params = EditFileInput.model_validate({"file_path": "foo.py", "edits": [{"old_text": "hello", "new_text": "world"}]})

    def boom(_path):
        raise RuntimeError("mark failed")

    monkeypatch.setattr(ctx, "mark_file_read", boom)

    result = await tool.execute(params, ctx)

    assert result.is_error
    assert "rolled back" in result.output
    assert result.metadata["rollback_applied"] is True
    assert target.read_text(encoding="utf-8") == "hello"


def test_exec_preflight_normalizes_duplicate_project_command(tmp_path):
    ctx = _ctx(tmp_path)
    hook = HarnessPreflightHook()
    tool = ExecCommandTool()

    normalized = asyncio.run(
        hook.before(tool, "exec_command", {"command": "python project/foo.py", "base": "work"}, ctx)
    )

    assert isinstance(normalized, dict)
    assert normalized["command"] == "python foo.py"
    assert normalized["normalized_command"] == "python foo.py"
    assert normalized["normalization_kind"] == "redundant_project_prefix"
    assert "Commands already run from project/" in normalized["normalization_warning"]


def test_exec_preflight_normalizes_leading_cd_project(tmp_path):
    ctx = _ctx(tmp_path)
    hook = HarnessPreflightHook()
    tool = ExecCommandTool()

    normalized = asyncio.run(
        hook.before(tool, "exec_command", {"command": "cd project && python foo.py", "base": "work"}, ctx)
    )

    assert isinstance(normalized, dict)
    assert normalized["command"] == "python foo.py"
    assert "project-directory prefixing" in normalized["normalization_warning"]


def test_exec_preflight_normalizes_node_project_script(tmp_path):
    ctx = _ctx(tmp_path)
    hook = HarnessPreflightHook()
    tool = ExecCommandTool()

    normalized = asyncio.run(
        hook.before(tool, "exec_command", {"command": "node project/build.js", "base": "work"}, ctx)
    )

    assert isinstance(normalized, dict)
    assert normalized["command"] == "node build.js"
    assert normalized["normalized_command"] == "node build.js"


def test_command_runner_executes_project_relative_command(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    captured = {}

    class FakeSandboxResult:
        stdout = "ok"
        stderr = ""
        exit_code = 0
        elapsed_ms = 1
        timed_out = False
        denied = False
        denied_reason = None
        truncated = False
        metadata = {}

    class FakeSandboxExecutor:
        async def run(self, request):
            captured["command"] = request.command
            captured["cwd"] = request.cwd
            return FakeSandboxResult()

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.command_runner.get_sandbox_executor",
        lambda: FakeSandboxExecutor(),
    )

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="python foo.py", cwd="project", timeout=1))

    assert not result.is_error
    assert captured["command"] == "python foo.py"
    assert captured["cwd"] == ctx.project_dir.resolve()


def test_command_runner_rewrites_safe_read_project_path_with_diagnostics(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.project_dir / "foo.txt").write_text("ok", encoding="utf-8")
    captured = {}

    class FakeSandboxResult:
        stdout = "ok"
        stderr = ""
        exit_code = 0
        elapsed_ms = 1
        timed_out = False
        denied = False
        denied_reason = None
        truncated = False
        metadata = {}

    class FakeSandboxExecutor:
        async def run(self, request):
            captured["command"] = request.command
            captured["cwd"] = request.cwd
            return FakeSandboxResult()

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.command_runner.get_sandbox_executor",
        lambda: FakeSandboxExecutor(),
    )

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="cat project/foo.txt", cwd="project", timeout=1))

    assert not result.is_error
    assert captured["command"] == "cat foo.txt"
    assert result.metadata["normalization_kind"] == "shell_path_normalization"
    assert result.metadata["shell_path_diagnostic"]["effective_cwd"] == str(ctx.project_dir.resolve())


def test_command_runner_rewrites_safe_redirect_project_path(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    captured = {}

    class FakeSandboxResult:
        stdout = ""
        stderr = ""
        exit_code = 0
        elapsed_ms = 1
        timed_out = False
        denied = False
        denied_reason = None
        truncated = False
        metadata = {}

    class FakeSandboxExecutor:
        async def run(self, request):
            captured["command"] = request.command
            return FakeSandboxResult()

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.command_runner.get_sandbox_executor",
        lambda: FakeSandboxExecutor(),
    )

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="python build.py > project/out.txt", cwd="project", timeout=1))

    assert not result.is_error
    assert captured["command"] == "python build.py > out.txt"
    assert "project/out.txt->out.txt" in result.metadata["normalization_warning"]


def test_command_runner_blocks_ambiguous_shell_path_without_rewrite(tmp_path):
    ctx = _ctx(tmp_path)

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="cat project", cwd="project", timeout=1))

    assert result.denied is True
    assert result.metadata["failure_kind"] == "ambiguous_shell_path"
    assert "ambiguous" in (result.denied_reason or "").lower()


def test_command_runner_blocks_destructive_project_path_rewrite(tmp_path):
    ctx = _ctx(tmp_path)

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="rm project/foo.txt", cwd="project", timeout=1))

    assert result.denied is True
    assert result.metadata["failure_kind"] == "destructive_path_rewrite_blocked"
    assert "will not auto-rewrite destructive commands" in (result.denied_reason or "")


def test_command_runner_leaves_unrelated_commands_unchanged(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)
    captured = {}

    class FakeSandboxResult:
        stdout = "hello"
        stderr = ""
        exit_code = 0
        elapsed_ms = 1
        timed_out = False
        denied = False
        denied_reason = None
        truncated = False
        metadata = {}

    class FakeSandboxExecutor:
        async def run(self, request):
            captured["command"] = request.command
            return FakeSandboxResult()

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.command_runner.get_sandbox_executor",
        lambda: FakeSandboxExecutor(),
    )

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="echo hello", cwd="project", timeout=1))

    assert not result.is_error
    assert captured["command"] == "echo hello"
    assert "normalization_kind" not in result.metadata


def test_command_runner_truncates_large_stdout(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)

    class FakeSandboxResult:
        stdout = "x" * 20_000
        stderr = ""
        exit_code = 0
        elapsed_ms = 1
        timed_out = False
        denied = False
        denied_reason = None
        truncated = True
        metadata = {
            "stdout_truncated": True,
            "stderr_truncated": False,
            "max_output_bytes": 16_384,
        }

    class FakeSandboxExecutor:
        async def run(self, request):
            from app.services.agent_harness.isolation.sandbox.output_truncation import truncate_stream_output

            stdout, stdout_truncated = truncate_stream_output(FakeSandboxResult.stdout.encode("utf-8"), request.policy.max_output_bytes)
            FakeSandboxResult.stdout = stdout
            FakeSandboxResult.truncated = stdout_truncated
            return FakeSandboxResult()

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.command_runner.get_sandbox_executor",
        lambda: FakeSandboxExecutor(),
    )

    result = asyncio.run(CommandRunner().run_once(ctx=ctx, command="python foo.py", cwd="project", timeout=1))

    assert result.truncated is True
    assert result.stdout.endswith("[output truncated - exceeded 16384 bytes]")
    assert len(result.stdout) < 20_000
    assert result.metadata["stdout_truncated"] is True


def test_exec_command_envelopes_large_stdout_for_model_visible_preview(monkeypatch, tmp_path):
    ctx = _ctx(tmp_path)

    class FakeSandboxResult:
        stdout = "x" * 20_000
        stderr = ""
        exit_code = 0
        elapsed_ms = 1
        timed_out = False
        denied = False
        denied_reason = None
        truncated = True
        metadata = {
            "stdout_truncated": True,
            "stderr_truncated": False,
            "max_output_bytes": 16_384,
        }

    class FakeSandboxExecutor:
        async def run(self, request):
            return FakeSandboxResult()

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools._internal.command_runner.get_sandbox_executor",
        lambda: FakeSandboxExecutor(),
    )

    result = asyncio.run(
        ExecCommandTool().execute(
            ExecCommandInput.model_validate({"command": "python foo.py"}),
            ctx,
        )
    )

    assert not result.is_error
    assert "preview only" in result.output
    envelope = result.metadata["tool_result_envelope"]
    assert envelope["truncated"] is True
    assert envelope["blob_ref"].startswith(".agent/blobs/tool-results/")
    assert (ctx.conversation_dir / envelope["blob_ref"]).exists()


def test_exec_normalization_warning_stays_success():
    params = ExecCommandInput.model_validate(
        {
            "command": "python foo.py",
            "normalization_warning": "Removed redundant project/ prefix.",
            "normalized_command": "python foo.py",
            "normalization_kind": "redundant_project_prefix",
        }
    )
    raw_result = ToolResult(output="[exit code: 0]\n[stdout]\nok", metadata={"stdout": "ok", "exit_code": 0})

    result = _attach_exec_normalization(raw_result, params)
    review = review_tool_result("exec_command", {"command": "python project/foo.py"}, result)

    assert not result.is_error
    assert result.metadata["normalized_command"] == "python foo.py"
    assert result.metadata["normalization_kind"] == "redundant_project_prefix"
    assert review["outcome"] == "success"
    assert review["failure_kind"] is None
    assert review["required_next_action"] is None


def test_file_tools_return_structured_path_metadata(tmp_path):
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "notes.txt").write_text("hello", encoding="utf-8")

    read_result = asyncio.run(
        ReadFileTool().execute(
            ReadFileInput.model_validate({"base": "work", "file_path": "notes.txt"}),
            ctx,
        )
    )
    list_result = asyncio.run(
        ListFilesTool().execute(
            ListFilesInput.model_validate({"base": "work", "file_path": "."}),
            ctx,
        )
    )

    assert read_result.metadata["path"] == "project/notes.txt"
    assert read_result.metadata["location"] == "project"
    assert read_result.metadata["file_path"] == "notes.txt"
    assert read_result.metadata["conversation_path"] == "project/notes.txt"
    entry = next(item for item in list_result.metadata["entries"] if item["file_path"] == "notes.txt")
    assert entry["path"] == "project/notes.txt"
    assert entry["location"] == "project"
    assert entry["conversation_path"] == "project/notes.txt"



def test_write_file_normalizes_kind_aliases():
    # Common shorthands the model reaches for must canonicalize instead of
    # failing pydantic validation with a literal_error and forcing a retry.
    assert WriteFileInput.model_validate({"path": "fix.js", "content": "x", "kind": "js"}).kind == "js_module"
    assert WriteFileInput.model_validate({"path": "a.jsx", "content": "x", "kind": "jsx"}).kind == "js_module"
    assert WriteFileInput.model_validate({"path": "a.ts", "content": "x", "kind": "TypeScript"}).kind == "ts"
    assert WriteFileInput.model_validate({"path": "a.py", "content": "x", "kind": "py"}).kind == "python"
    assert WriteFileInput.model_validate({"path": "a.htm", "content": "x", "kind": "htm"}).kind == "html"
    # Canonical values still pass through untouched.
    assert WriteFileInput.model_validate({"path": "a.css", "content": "x", "kind": "css"}).kind == "css"


@pytest.mark.asyncio
async def test_edit_file_missing_old_text_reports_status_and_nearest_text(tmp_path):
    ctx = _ctx(tmp_path)
    target = ctx.work_dir / "foo.css"
    target.write_text(".btn-primary:hover { background: #e25e4f; }\n", encoding="utf-8")
    tool = EditFileTool()
    params = EditFileInput.model_validate(
        {
            "file_path": "foo.css",
            "edits": [{"old_text": ".btn-primary:hover { background: #ffffff; }", "new_text": "x"}],
        }
    )

    result = await tool.execute(params, ctx)

    assert result.is_error
    # The file is untouched and the error tells the model what is actually there.
    assert target.read_text(encoding="utf-8") == ".btn-primary:hover { background: #e25e4f; }\n"
    assert "could not be applied" in result.output
    assert "Closest existing text is at line 1" in result.output
    assert "#e25e4f" in result.output
