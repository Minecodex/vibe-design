from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_harness.capabilities.tools.write_file import WriteFileInput, WriteFileTool
from app.services.agent_harness.core.context import HarnessContext


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(
        user_id=1,
        conversation_id="conv-write-json",
        run_id="run-write-json",
        workspace_root=tmp_path,
    )
    ctx.ensure_dirs()
    return ctx


@pytest.mark.asyncio
async def test_write_file_json_parses_json_object_string_without_double_encoding(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    params = WriteFileInput.model_validate(
        {
            "path": "inputs.json",
            "kind": "json",
            "content": '{"template_path":"project/template.html","output_path":"project/out.html"}',
        }
    )

    result = await WriteFileTool().execute(params, ctx)

    assert result.is_error is False
    written = json.loads((ctx.project_dir / "inputs.json").read_text(encoding="utf-8"))
    assert written == {
        "template_path": "project/template.html",
        "output_path": "project/out.html",
    }
    assert result.metadata["json_normalization"] == "parsed_json_string"


@pytest.mark.asyncio
async def test_write_file_json_rejects_invalid_string_instead_of_writing_double_encoded_json(
    tmp_path: Path,
) -> None:
    ctx = _ctx(tmp_path)
    params = WriteFileInput.model_validate(
        {"path": "inputs.json", "kind": "json", "content": '{"template_path":'}
    )

    result = await WriteFileTool().execute(params, ctx)

    assert result.is_error is True
    assert "valid JSON object or array" in result.output
    assert not (ctx.project_dir / "inputs.json").exists()
