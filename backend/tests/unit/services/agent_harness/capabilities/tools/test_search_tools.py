from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from app.services.agent_harness.capabilities.tools import create_harness_registry
from app.services.agent_harness.capabilities.tools.glob_files import GlobFilesInput, GlobFilesTool
from app.services.agent_harness.capabilities.tools.grep_files import GrepFilesInput, GrepFilesTool
from app.services.agent_harness.core.context import HarnessContext


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-search-tools",
        run_id="run-search-tools",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    return ctx


def test_glob_files_finds_project_files_with_base_logic(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "src").mkdir(parents=True)
    (ctx.work_dir / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
    (ctx.work_dir / "src" / "app.ts").write_text("console.log('ok')", encoding="utf-8")

    result = asyncio.run(
        GlobFilesTool().execute(
            GlobFilesInput(base="work", path="src", pattern="*.py"),
            ctx,
        )
    )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert payload["filenames"] == ["project/src/app.py"]
    assert payload["numFiles"] == 1
    assert payload["truncated"] is False


def test_glob_files_supports_reference_base(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.reference_inputs_dir / "brief.md").write_text("brief", encoding="utf-8")

    result = asyncio.run(
        GlobFilesTool().execute(
            GlobFilesInput(base="references", path="inputs", pattern="*.md"),
            ctx,
        )
    )

    payload = json.loads(result.output)
    assert payload["filenames"] == ["references/inputs/brief.md"]
    assert payload["reference_only"] is True
    assert payload["reference_role"] == "conversation_reference"


def test_grep_files_returns_files_with_matches(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "alpha.txt").write_text("Needle\n", encoding="utf-8")
    (ctx.work_dir / "beta.txt").write_text("nothing\n", encoding="utf-8")

    result = asyncio.run(
        GrepFilesTool().execute(
            GrepFilesInput(base="work", path=".", pattern="needle", case_insensitive=True),
            ctx,
        )
    )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert payload["mode"] == "files_with_matches"
    assert payload["filenames"] == ["project/alpha.txt"]
    assert payload["numFiles"] == 1


def test_grep_files_uses_python_fallback_when_rg_is_missing(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "alpha.txt").write_text("Needle\n", encoding="utf-8")
    (ctx.work_dir / "beta.txt").write_text("nothing\n", encoding="utf-8")
    with patch("app.services.agent_harness.capabilities.tools._internal.search_ops.which", lambda name: None):
        result = asyncio.run(
            GrepFilesTool().execute(
                GrepFilesInput(base="work", path=".", pattern="needle", case_insensitive=True),
                ctx,
            )
        )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert payload["mode"] == "files_with_matches"
    assert payload["filenames"] == ["project/alpha.txt"]
    assert payload["numFiles"] == 1
    assert payload["search_backend"] == "python_fallback"


def test_grep_files_filters_by_file_type(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "schema.ts").write_text("const needle = true\n", encoding="utf-8")
    (ctx.work_dir / "schema.py").write_text("needle = True\n", encoding="utf-8")

    result = asyncio.run(
        GrepFilesTool().execute(
            GrepFilesInput(base="work", path=".", pattern="needle", file_type="ts"),
            ctx,
        )
    )

    payload = json.loads(result.output)
    assert result.is_error is False
    assert payload["filenames"] == ["project/schema.ts"]


def test_grep_files_rejects_unknown_file_type_filter(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "schema.ts").write_text("const rails = true\n", encoding="utf-8")

    message = GrepFilesTool().validate_input(
        GrepFilesInput(
            base="work",
            path=".",
            pattern="rails",
            glob="*.ts",
            file_type="fixed",
        ),
        ctx,
    )

    assert message is not None
    assert "Unsupported ripgrep file_type" in message
    assert "omit file_type for regex or literal text searches" in message


def test_grep_files_content_mode_supports_context_limit_and_offset(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "alpha.txt").write_text(
        "\n".join(["hit one", "miss", "hit two", "hit three"]),
        encoding="utf-8",
    )

    result = asyncio.run(
        GrepFilesTool().execute(
            GrepFilesInput(
                base="work",
                path=".",
                pattern="hit",
                output_mode="content",
                head_limit=1,
                offset=1,
            ),
            ctx,
        )
    )

    payload = json.loads(result.output)
    assert payload["mode"] == "content"
    assert payload["content"] == "project/alpha.txt:3:hit two"
    assert payload["numLines"] == 1
    assert payload["numFiles"] == 1
    assert payload["filenames"] == ["project/alpha.txt"]
    assert payload["appliedLimit"] == 1
    assert payload["appliedOffset"] == 1


def test_grep_files_count_mode_returns_match_totals(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "alpha.txt").write_text("token\ntoken\n", encoding="utf-8")
    (ctx.work_dir / "beta.txt").write_text("token\n", encoding="utf-8")

    result = asyncio.run(
        GrepFilesTool().execute(
            GrepFilesInput(base="work", path=".", pattern="token", output_mode="count"),
            ctx,
        )
    )

    payload = json.loads(result.output)
    lines = set(payload["content"].splitlines())
    assert payload["mode"] == "count"
    assert lines == {"project/alpha.txt:2", "project/beta.txt:1"}
    assert payload["numFiles"] == 2
    assert payload["numMatches"] == 3


def test_search_tools_hide_project_internal_skill_runtime(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    internal = ctx.work_dir / ".skill_runtime" / "xlsx"
    internal.mkdir(parents=True)
    (internal / "secret.md").write_text("needle", encoding="utf-8")
    (ctx.work_dir / "visible.md").write_text("needle", encoding="utf-8")

    glob_result = asyncio.run(
        GlobFilesTool().execute(
            GlobFilesInput(base="work", path=".", pattern="**/*.md"),
            ctx,
        )
    )
    grep_result = asyncio.run(
        GrepFilesTool().execute(
            GrepFilesInput(base="work", path=".", pattern="needle"),
            ctx,
        )
    )

    glob_payload = json.loads(glob_result.output)
    grep_payload = json.loads(grep_result.output)
    assert glob_payload["filenames"] == ["project/visible.md"]
    assert grep_payload["filenames"] == ["project/visible.md"]


def test_registry_accepts_claude_code_tool_aliases(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "notes.txt").write_text("needle", encoding="utf-8")
    registry = create_harness_registry()

    glob_result = asyncio.run(registry.execute("Glob", {"pattern": "*.txt"}, ctx))
    grep_result = asyncio.run(registry.execute("Grep", {"pattern": "needle"}, ctx))

    assert glob_result.is_error is False
    assert grep_result.is_error is False
    assert json.loads(glob_result.output)["filenames"] == ["project/notes.txt"]
    assert json.loads(grep_result.output)["filenames"] == ["project/notes.txt"]
