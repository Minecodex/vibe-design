from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
from app.services.agent_harness.capabilities.subagents.types import SubagentRequest, SubagentTaskSpec
from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry
from app.services.agent_harness.core.context import HarnessContext
from app.services.llm_runtime import LlmStreamChunk


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(user_id=1, conversation_id="conv-subagent-artifacts", run_id="run-parent", workspace_root=tmp_path)
    ctx.ensure_dirs()
    return ctx


class FakeProvider:
    async def chat_stream(self, **_kwargs):
        yield LlmStreamChunk(content="child done")
        yield LlmStreamChunk(finish_reason="stop")


@pytest.mark.asyncio
async def test_subagent_runner_persists_transcript_and_terminal_result_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_ctx = _ctx(tmp_path)
    events: list = []

    async def _capture(*_args, draft=None, **_kwargs):
        events.append(draft)

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.subagents.runner.publish_presentation_event_async",
        _capture,
    )
    runner = HarnessSubagentRunner(
        provider=FakeProvider(),
        conversation={"model_preferences": {"multimodal_model": "fake-model"}},
        parent_context=parent_ctx,
        parent_registry=ToolRegistry(),
        language="zh",
    )
    request = SubagentRequest(
        task_id="sub-artifact-1",
        spec=SubagentTaskSpec.from_mapping(
            {
                "description": "Artifact worker",
                "prompt": "Prepare artifact",
                "subagent_type": "general-purpose",
            }
        ),
    )

    result = await runner.run(request, parent_ctx)

    assert result.status == "completed"
    assert result.result["transcript_ref"] == ".agent/sidechains/sub-artifact-1/transcript.jsonl"
    assert result.result["result_ref"] == ".agent/sidechains/sub-artifact-1/result.json"
    transcript_path = parent_ctx.conversation_dir / result.result["transcript_ref"]
    result_path = parent_ctx.conversation_dir / result.result["result_ref"]
    assert transcript_path.exists()
    assert result_path.exists()
    transcript_rows = [json.loads(line) for line in transcript_path.read_text(encoding="utf-8").splitlines()]
    assert any(row.get("role") == "assistant" and row.get("content") == "child done" for row in transcript_rows)
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert result_payload["status"] == "completed"
    assert result_payload["summary"] == "child done"
    assert events[-1].payload["payload"]["transcript_ref"] == result.result["transcript_ref"]
    assert events[-1].payload["payload"]["result_ref"] == result.result["result_ref"]
