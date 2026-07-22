from __future__ import annotations

from pathlib import Path

import pytest

from app.services.agent_harness.capabilities.tools._internal.base import ToolResult
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.execution_support.reviewer import review_tool_result
from app.services.agent_harness.runtime.sidechain.tool_result_envelope import envelope_tool_result


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(user_id=1, conversation_id="conv-envelope", run_id="run-envelope", workspace_root=tmp_path)
    ctx.ensure_dirs()
    return ctx


def test_tool_result_envelope_passes_small_output_without_blob(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = envelope_tool_result(
        ctx=ctx,
        tool_name="read_file",
        tool_call_id="call-1",
        result=ToolResult(output="small output", metadata={}),
        preview_chars=100,
    )

    assert result.output == "small output"
    assert result.metadata["tool_result_envelope"]["persisted"] is False
    assert result.metadata["tool_result_envelope"]["truncated"] is False


def test_tool_result_envelope_persists_large_output_and_returns_model_visible_preview(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = envelope_tool_result(
        ctx=ctx,
        tool_name="exec_command",
        tool_call_id="call-2",
        result=ToolResult(output="x" * 200, metadata={"stdout": "x" * 200}),
        preview_chars=40,
    )

    envelope = result.metadata["tool_result_envelope"]
    assert envelope["persisted"] is True
    assert envelope["truncated"] is True
    assert envelope["original_size"] == 200
    assert envelope["preview_size"] == 40
    assert "preview only" in result.output
    assert envelope["blob_ref"].startswith(".agent/blobs/tool-results/")
    assert (ctx.conversation_dir / envelope["blob_ref"]).read_text(encoding="utf-8") == "x" * 200
    assert result.metadata["stdout"] == "x" * 40


def test_tool_result_envelope_marks_tool_reported_partial_output_without_claiming_full_blob(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = envelope_tool_result(
        ctx=ctx,
        tool_name="read_file",
        tool_call_id="call-window",
        result=ToolResult(
            output="line 1\nline 2",
            metadata={"truncated_by_window": True, "has_more": True, "next_offset": 2, "total_lines": 10},
        ),
        preview_chars=100,
    )

    envelope = result.metadata["tool_result_envelope"]
    assert envelope["persisted"] is False
    assert envelope["truncated"] is True
    assert envelope["reason"] == "tool_reported_partial_output"
    assert envelope["next_offset"] == 2
    assert "preview only" in result.output
    assert "full output was not returned by this tool" in result.output
    assert "offset=2" in result.output


def test_tool_result_envelope_replay_uses_stable_blob_reference(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    first = envelope_tool_result(
        ctx=ctx,
        tool_name="exec_command",
        tool_call_id="same-call",
        result=ToolResult(output="y" * 200, metadata={}),
        preview_chars=20,
    )
    second = envelope_tool_result(
        ctx=ctx,
        tool_name="exec_command",
        tool_call_id="same-call",
        result=ToolResult(output="y" * 200, metadata={}),
        preview_chars=20,
    )

    assert first.metadata["tool_result_envelope"]["blob_ref"] == second.metadata["tool_result_envelope"]["blob_ref"]
    assert first.output == second.output


def test_reviewer_preserves_tool_envelope_instead_of_bare_excerpt(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    result = envelope_tool_result(
        ctx=ctx,
        tool_name="exec_command",
        tool_call_id="call-3",
        result=ToolResult(output="z" * 200, metadata={}),
        preview_chars=40,
    )

    review = review_tool_result("exec_command", {}, result)

    assert "preview only" in review["output_excerpt"]
    assert review["tool_result_envelope"]["truncated"] is True


def test_tool_result_envelope_reports_persistence_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = _ctx(tmp_path)

    def fail_write_text(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    result = envelope_tool_result(
        ctx=ctx,
        tool_name="exec_command",
        tool_call_id="call-4",
        result=ToolResult(output="x" * 200, metadata={}),
        preview_chars=40,
    )

    assert result.is_error is True
    assert "Could not persist full tool output" in result.output
    assert result.metadata["failure_kind"] == "tool_result_blob_persistence_failed"

