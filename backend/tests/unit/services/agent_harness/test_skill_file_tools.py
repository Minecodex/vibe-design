from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.capabilities.tools.list_files import ListFilesInput, ListFilesTool
from app.services.agent_harness.capabilities.tools.read_file import ReadFileInput, ReadFileTool


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-skill-files",
        run_id="run-skill-files",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    skill_dir = ctx.work_dir / ".skill_runtime" / "xlsx"
    skill_dir.mkdir(parents=True)
    references_dir = skill_dir / "references"
    references_dir.mkdir()
    (references_dir / "financial-model.md").write_text("finance notes", encoding="utf-8")
    ctx.active_skill_dir = skill_dir
    ctx.skill_runtime_dir = skill_dir
    return ctx


@pytest.mark.asyncio
async def test_read_file_can_read_active_skill_reference(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    result = await ReadFileTool().execute(
        ReadFileInput(base="skill", file_path="references/financial-model.md"),
        ctx,
    )

    assert result.output == "     1\tfinance notes"
    assert result.metadata["path"] == "skill/references/financial-model.md"


@pytest.mark.asyncio
async def test_read_file_marks_repeated_reads_for_unchanged_file(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    tool = ReadFileTool()

    first = await tool.execute(
        ReadFileInput(base="skill", file_path="references/financial-model.md"),
        ctx,
    )
    second = await tool.execute(
        ReadFileInput(base="skill", file_path="references/financial-model.md"),
        ctx,
    )

    assert first.metadata["repeated_read"] is False
    assert second.metadata["repeated_read"] is True


@pytest.mark.asyncio
async def test_read_file_reads_to_eof_when_limit_is_omitted(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    path = ctx.work_dir / "long.txt"
    path.write_text("\n".join(f"line {index}" for index in range(1, 406)), encoding="utf-8")

    result = await ReadFileTool().execute(
        ReadFileInput(base="work", file_path="long.txt"),
        ctx,
    )

    assert result.output.startswith("     1\tline 1\n     2\tline 2")
    assert "   405\tline 405" in result.output
    assert result.metadata["start_line"] == 1
    assert result.metadata["num_lines"] == 405
    assert result.metadata["total_lines"] == 405
    assert result.metadata["truncated_by_window"] is False


@pytest.mark.asyncio
async def test_read_file_supports_explicit_offset_and_limit(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    path = ctx.work_dir / "paged.txt"
    path.write_text("\n".join(f"line {index}" for index in range(1, 11)), encoding="utf-8")

    result = await ReadFileTool().execute(
        ReadFileInput(base="work", file_path="paged.txt", offset=3, limit=2),
        ctx,
    )

    assert result.output.startswith("[read_file window: lines 4-5 of 10; continue with offset=5]\n")
    assert result.output.endswith("     4\tline 4\n     5\tline 5")
    assert result.metadata["start_line"] == 4
    assert result.metadata["num_lines"] == 2
    assert result.metadata["total_lines"] == 10
    assert result.metadata["truncated_by_window"] is True
    assert result.metadata["has_more"] is True
    assert result.metadata["next_offset"] == 5


@pytest.mark.asyncio
async def test_list_files_can_list_active_skill_reference_dir(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)

    result = await ListFilesTool().execute(
        ListFilesInput(base="skill", file_path="references", recursive=True),
        ctx,
    )

    payload = json.loads(result.output)
    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["path"] == "skill/references/financial-model.md"
    assert entry["location"] == "skill"
    assert entry["file_path"] == "references/financial-model.md"
    assert entry["conversation_path"].endswith("project/.skill_runtime/xlsx/references/financial-model.md")
    assert entry["type"] == "file"
    assert entry["size"] == len("finance notes")


@pytest.mark.asyncio
async def test_list_files_hides_internal_skill_runtime_from_project_location(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    (ctx.work_dir / "report.py").write_text("print('ok')", encoding="utf-8")

    result = await ListFilesTool().execute(
        ListFilesInput(base="work", file_path=".", recursive=True),
        ctx,
    )

    payload = json.loads(result.output)

    assert "project/.skill_runtime" not in {str(entry.get("path")) for entry in payload["entries"]}
    assert any(str(entry.get("path")) == "project/report.py" for entry in payload["entries"])


@pytest.mark.asyncio
async def test_list_files_bounds_recursive_skill_listing_noise(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    schema_dir = ctx.skill_runtime_dir / "scripts" / "office" / "schemas" / "ecma"
    schema_dir.mkdir(parents=True)
    for index in range(40):
        (schema_dir / f"schema-{index}.xsd").write_text("x", encoding="utf-8")

    result = await ListFilesTool().execute(
        ListFilesInput(base="skill", file_path="scripts", recursive=True, max_entries=200),
        ctx,
    )

    payload = json.loads(result.output)

    assert payload["entry_count"] < 200
    assert any(item.get("reason") in {"depth_limit", "child_limit", "low_signal_dir"} for item in payload["omitted"])

