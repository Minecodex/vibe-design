from __future__ import annotations

import json

import pytest

from app.services.agent_harness.capabilities.subagents.types import SubagentRequest, SubagentResult, SubagentTaskSpec
from app.services.agent_harness.capabilities.tools.agent import AgentInput, AgentTool
from app.services.agent_harness.core.context import HarnessContext


def _ctx(tmp_path) -> HarnessContext:
    ctx = HarnessContext(user_id=1, conversation_id="conv-subagent-contract", run_id="run-parent", workspace_root=tmp_path)
    ctx.ensure_dirs()
    return ctx


async def _noop_publish(*_args, **_kwargs):
    # Subagent lifecycle is emitted via the async presentation publisher now.
    return None


def test_subagent_task_spec_uses_agent_tool_contract_only() -> None:
    spec = SubagentTaskSpec.from_mapping(
        {
            "description": "Prepare artifact",
            "prompt": "Prepare the registered artifact.",
            "objective": "legacy.objective",
            "inputs": {"target_files": ["project/template.html"]},
            "result_contract": {"outputs": ["project/out.html"]},
        }
    )

    assert spec.description == "Prepare artifact"
    assert spec.prompt == "Prepare the registered artifact."
    assert spec.subagent_type == "general-purpose"
    assert spec.to_dict() == {
        "description": "Prepare artifact",
        "prompt": "Prepare the registered artifact.",
        "subagent_type": "general-purpose",
    }


def test_agent_tool_rejects_internal_quality_review_profile(tmp_path) -> None:
    ctx = _ctx(tmp_path)
    params = AgentInput.model_validate(
        {
            "description": "Review artifact",
            "prompt": "Review the artifact.",
            "subagent_type": "QualityReview",
        }
    )

    error = AgentTool().validate_input(params, ctx)

    assert error is not None
    assert "Unsupported subagent_type" in error
    assert "Supported types: general-purpose, Explore, Plan" in error


@pytest.mark.asyncio
async def test_agent_failed_result_becomes_parent_tool_error(tmp_path, monkeypatch) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.agent.publish_presentation_event_async",
        _noop_publish,
    )

    async def handler(request: SubagentRequest, _ctx: HarnessContext):
        return SubagentResult(
            task_id=request.task_id,
            status="failed",
            summary="Child failed.",
            result={"reason": "tool_failed"},
            reason_code="child_failed",
        )

    ctx.run_subagent_handler = handler
    result = await AgentTool().execute(
        AgentInput.model_validate(
            {
                "description": "Prepare artifact",
                "prompt": "Prepare the artifact.",
            }
        ),
        ctx,
    )

    assert result.is_error is True
    assert result.metadata["status"] == "failed"
    assert result.metadata["reason_code"] == "child_failed"
    assert result.metadata["task_spec"] == {
        "description": "Prepare artifact",
        "prompt": "Prepare the artifact.",
        "subagent_type": "general-purpose",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "reason_code", "is_error"),
    [
        ("completed", None, False),
        ("degraded", "child_degraded", True),
        ("failed", "child_failed", True),
        ("refused", "child_refused", True),
        ("cancelled", "user_cancelled", True),
    ],
)
async def test_agent_result_marks_terminal_completion(tmp_path, monkeypatch, status, reason_code, is_error) -> None:
    ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.tools.agent.publish_presentation_event_async",
        _noop_publish,
    )

    async def handler(request: SubagentRequest, _ctx: HarnessContext):
        return SubagentResult(
            task_id=request.task_id,
            status=status,
            summary=f"Child ended as {status}.",
            result={"status": status},
            reason_code=reason_code,
        )

    ctx.run_subagent_handler = handler

    result = await AgentTool().execute(
        AgentInput.model_validate(
            {
                "description": "Inspect files",
                "prompt": "Inspect files and summarize.",
                "subagent_type": "Explore",
            }
        ),
        ctx,
    )

    assert result.is_error is is_error
    assert result.metadata["task_created"] is True
    assert result.metadata["task_completed"] is (status == "completed")
    assert result.metadata["lifecycle_phase"] == "terminal"
    assert result.metadata["subagent_type"] == "Explore"


@pytest.mark.asyncio
async def test_subagent_runner_inherits_parent_registry_hooks(tmp_path) -> None:
    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolHook, ToolRegistry, ToolResult
    from pydantic import BaseModel

    class Input(BaseModel):
        value: str

    class EchoTool(BaseTool):
        @property
        def name(self) -> str:
            return "echo_tool"

        @property
        def description(self) -> str:
            return "Echo value"

        @property
        def input_model(self):
            return Input

        async def execute(self, params: BaseModel, ctx: HarnessContext) -> ToolResult:
            return ToolResult(output=params.value)

    class RewriteHook(ToolHook):
        async def before(self, tool, name, args, ctx):
            if name == "echo_tool":
                return {"value": "rewritten"}
            return None

    parent_registry = ToolRegistry()
    parent_registry.register(EchoTool())
    parent_registry.add_hook(RewriteHook())
    parent_ctx = _ctx(tmp_path)
    runner = HarnessSubagentRunner(
        provider=object(),
        conversation={},
        parent_context=parent_ctx,
        parent_registry=parent_registry,
        language="en",
    )
    request = SubagentRequest(
        task_id="sub-hook-1",
        spec=SubagentTaskSpec.from_mapping(
            {
                "description": "Check hook",
                "prompt": "Use echo tool",
                "subagent_type": "general-purpose",
            }
        ),
    )

    child_ctx = runner._child_context(parent_ctx, request)
    child_registry = runner._child_registry("general-purpose")
    result = await child_registry.execute("echo_tool", {"value": "raw"}, child_ctx)

    assert result.output == "rewritten"


@pytest.mark.asyncio
async def test_subagent_runner_envelopes_large_child_tool_output_like_parent(tmp_path, monkeypatch) -> None:
    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolRegistry, ToolResult
    from app.services.llm_runtime import LlmStreamChunk
    from pydantic import BaseModel

    class EmptyInput(BaseModel):
        pass

    class HugeTool(BaseTool):
        @property
        def name(self) -> str:
            return "huge_tool"

        @property
        def description(self) -> str:
            return "Return a large output"

        @property
        def input_model(self):
            return EmptyInput

        async def execute(self, params: BaseModel, ctx: HarnessContext) -> ToolResult:
            return ToolResult(output="c" * 5000, metadata={})

    class ToolThenStopProvider:
        def __init__(self) -> None:
            self.calls = 0

        async def chat_stream(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                yield LlmStreamChunk(
                    tool_calls=[
                        {
                            "id": "call-huge",
                            "name": "huge_tool",
                            "arguments": "{}",
                        }
                    ],
                    finish_reason="tool_calls",
                )
                return
            yield LlmStreamChunk(content="done")
            yield LlmStreamChunk(finish_reason="stop")

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.subagents.runner.publish_presentation_event_async",
        _noop_publish,
    )
    parent_ctx = _ctx(tmp_path)
    parent_registry = ToolRegistry()
    parent_registry.register(HugeTool())
    runner = HarnessSubagentRunner(
        provider=ToolThenStopProvider(),
        conversation={"model_preferences": {"multimodal_model": "fake-model"}},
        parent_context=parent_ctx,
        parent_registry=parent_registry,
        language="en",
    )
    request = SubagentRequest(
        task_id="sub-large-output-1",
        spec=SubagentTaskSpec.from_mapping(
            {
                "description": "Large output",
                "prompt": "Call huge tool",
                "subagent_type": "general-purpose",
            }
        ),
    )

    result = await runner.run(request, parent_ctx)

    tool_record = result.result["tool_calls"][0]
    envelope = tool_record["review"]["tool_result_envelope"]
    assert result.status == "completed"
    assert envelope["truncated"] is True
    assert envelope["persisted"] is True
    assert envelope["blob_ref"].startswith(".agent/blobs/tool-results/")
    assert (parent_ctx.conversation_dir / envelope["blob_ref"]).read_text(encoding="utf-8") == "c" * 5000

    transcript_path = parent_ctx.conversation_dir / result.result["transcript_ref"]
    tool_rows = [
        json.loads(line)
        for line in transcript_path.read_text(encoding="utf-8").splitlines()
        if json.loads(line).get("role") == "tool"
    ]
    assert "preview only" in tool_rows[0]["content"]
    assert tool_rows[0]["review"]["tool_result_envelope"]["blob_ref"] == envelope["blob_ref"]


@pytest.mark.asyncio
async def test_subagent_runner_records_prompt_cache_debug_usage(tmp_path, monkeypatch) -> None:
    from app.core.config import settings
    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry
    from app.services.llm_runtime import LlmStreamChunk

    class UsageProvider:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def chat_stream(self, **kwargs):
            self.calls.append(kwargs)
            yield LlmStreamChunk(content="done")
            yield LlmStreamChunk(
                usage={
                    "input_tokens": 100,
                    "output_tokens": 8,
                    "cached_tokens": 80,
                    "cache_read_tokens": 64,
                    "cache_creation_tokens": 16,
                }
            )
            yield LlmStreamChunk(finish_reason="stop")

    monkeypatch.setattr(settings, "HARNESS_PROMPT_CACHE_DEBUG", True)
    parent_ctx = _ctx(tmp_path)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.prompt_cache_debug.ensure_harness_meta",
        lambda *_args: parent_ctx.meta_dir,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.subagents.runner.publish_presentation_event_async",
        _noop_publish,
    )
    provider = UsageProvider()
    runner = HarnessSubagentRunner(
        provider=provider,
        conversation={"model_preferences": {"multimodal_model": "fake-model"}},
        parent_context=parent_ctx,
        parent_registry=ToolRegistry(),
        language="en",
    )
    request = SubagentRequest(
        task_id="sub-cache-1",
        spec=SubagentTaskSpec.from_mapping(
            {
                "description": "Cache trace",
                "prompt": "Return done.",
                "subagent_type": "general-purpose",
            }
        ),
    )

    result = await runner.run(request, parent_ctx)

    assert result.status == "completed"
    assert provider.calls[0]["prompt_cache_key"] == "subagent:conv-subagent-contract:run-parent:sub-cache-1"
    trace_paths = sorted((parent_ctx.conversation_dir / ".meta" / "prompt_cache_debug").glob("usage-*.json"))
    assert len(trace_paths) == 1
    trace = json.loads(trace_paths[0].read_text(encoding="utf-8"))
    assert trace["trace_scope"] == "subagent"
    assert trace["run_id"] == "sub-cache-1"
    assert trace["parent_run_id"] == "run-parent"
    assert trace["subagent_task_id"] == "sub-cache-1"
    assert trace["subagent_type"] == "general-purpose"
    assert trace["prompt_cache_key"] == provider.calls[0]["prompt_cache_key"]
    assert trace["usage"]["cached_tokens"] == 80
    assert trace["usage"]["cache_read_tokens"] == 64


@pytest.mark.asyncio
async def test_subagent_runner_finalizes_after_tool_turn_exhaustion_and_uses_profile_summary_limit(
    tmp_path,
    monkeypatch,
) -> None:
    import copy

    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.subagents.types import SubagentDefinition
    from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolRegistry, ToolResult
    from app.services.llm_runtime import LlmStreamChunk
    from pydantic import BaseModel

    class EmptyInput(BaseModel):
        pass

    class HugeTool(BaseTool):
        @property
        def name(self) -> str:
            return "huge_tool"

        @property
        def description(self) -> str:
            return "Return a large output"

        @property
        def input_model(self):
            return EmptyInput

        async def execute(self, params: BaseModel, ctx: HarnessContext) -> ToolResult:
            return ToolResult(output="q" * 3000, metadata={})

    class ToolUntilFinalProvider:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def chat_stream(self, **kwargs):
            self.calls.append(copy.deepcopy(kwargs))
            if len(self.calls) <= 2:
                yield LlmStreamChunk(
                    tool_calls=[
                        {
                            "id": f"call-huge-{len(self.calls)}",
                            "name": "huge_tool",
                            "arguments": "{}",
                        }
                    ],
                    finish_reason="tool_calls",
                )
                return
            yield LlmStreamChunk(content='{"ok": true}')
            yield LlmStreamChunk(finish_reason="stop")

    quality_definition = SubagentDefinition(
        name="QualityReview",
        description="Review",
        system_prompt="Review.",
        allowed_tools=("huge_tool",),
        max_turns=2,
        tool_result_summary_chars=2500,
        internal=True,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.subagents.runner.get_subagent_definition",
        lambda name: quality_definition if name == "QualityReview" else None,
    )
    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.subagents.runner.publish_presentation_event_async",
        _noop_publish,
    )

    provider = ToolUntilFinalProvider()
    parent_ctx = _ctx(tmp_path)
    parent_registry = ToolRegistry()
    parent_registry.register(HugeTool())
    runner = HarnessSubagentRunner(
        provider=provider,
        conversation={"model_preferences": {"multimodal_model": "fake-model"}},
        parent_context=parent_ctx,
        parent_registry=parent_registry,
        language="en",
    )
    request = SubagentRequest(
        task_id="sub-finalize-1",
        spec=SubagentTaskSpec.from_mapping(
            {
                "description": "Quality review",
                "prompt": "Use tools until asked to finalize.",
                "subagent_type": "QualityReview",
            }
        ),
    )

    result = await runner.run(request, parent_ctx)

    assert result.status == "completed"
    assert result.result["assistant_text"] == '{"ok": true}'
    assert len(provider.calls) == 3
    assert provider.calls[-1]["tools"] == []
    assert provider.calls[-1]["tool_choice"] == "none"

    second_call_tool_message = provider.calls[1]["messages"][-1]
    tool_payload = json.loads(second_call_tool_message["content"])
    assert len(tool_payload["summary"]) == 2500
    assert tool_payload["summary"] == "q" * 2500


@pytest.mark.asyncio
async def test_subagent_runner_caller_validated_mode_defers_terminal_event(tmp_path, monkeypatch) -> None:
    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry
    from app.services.llm_runtime import LlmStreamChunk

    events: list = []

    async def capture_event(*_args, draft=None, **_kwargs):
        events.append(draft)

    def _subagent_card_statuses() -> list:
        return [
            draft.payload.get("status")
            for draft in events
            if draft is not None
            and str(draft.payload.get("block_key") or "").startswith("subagent:")
        ]

    class StopProvider:
        async def chat_stream(self, **_kwargs):
            yield LlmStreamChunk(content="raw review")
            yield LlmStreamChunk(finish_reason="stop")

    monkeypatch.setattr(
        "app.services.agent_harness.capabilities.subagents.runner.publish_presentation_event_async",
        capture_event,
    )
    parent_ctx = _ctx(tmp_path)
    runner = HarnessSubagentRunner(
        provider=StopProvider(),
        conversation={"model_preferences": {"multimodal_model": "fake-model"}},
        parent_context=parent_ctx,
        parent_registry=ToolRegistry(),
        language="en",
    )
    request = SubagentRequest(
        task_id="sub-caller-validated-1",
        spec=SubagentTaskSpec.from_mapping(
            {
                "description": "Quality review",
                "prompt": "Return raw review.",
                "subagent_type": "QualityReview",
            }
        ),
        auto_finalize_terminal=False,
    )

    result = await runner.run(request, parent_ctx)

    assert result.status == "completed"
    assert _subagent_card_statuses() == ["running"]
    finalized = await runner.finalize_terminal_result(
        parent_ctx=parent_ctx,
        request=request,
        result=SubagentResult(
            task_id=result.task_id,
            status="degraded",
            summary=result.summary,
            result=result.result,
            reason_code="quality_review_invalid_output",
        ),
    )

    assert finalized.status == "degraded"
    assert _subagent_card_statuses() == ["running", "degraded"]
    assert (parent_ctx.conversation_dir / finalized.result["result_ref"]).is_file()
    assert finalized.result["transcript_ref"] == result.result["transcript_ref"]


def test_subagent_child_context_inherits_parent_perspective_but_forks_read_state(tmp_path) -> None:
    import asyncio

    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry

    parent_ctx = _ctx(tmp_path)
    parent_ctx.active_skill_dir = tmp_path / "skill-src"
    parent_ctx.skill_runtime_dir = parent_ctx.skill_dir
    parent_ctx.runtime_state = {"phase": "working"}  # type: ignore[assignment]
    parent_ctx.history_summary = {"summary": "prior context"}
    parent_ctx.conversation_state = {"facts": ["known"]}  # type: ignore[assignment]
    parent_ctx.event_queue = asyncio.Queue()
    parent_ctx.workspace_runtime_session = {"cwd": "project"}
    setattr(parent_ctx, "_read_window_snapshots_cache", {"project/a.txt:0:EOF"})

    runner = HarnessSubagentRunner(
        provider=object(),
        conversation={},
        parent_context=parent_ctx,
        parent_registry=ToolRegistry(),
        language="en",
    )
    request = SubagentRequest(
        task_id="sub-perspective-1",
        spec=SubagentTaskSpec.from_mapping({"description": "Check context", "prompt": "Inspect context"}),
    )

    child_ctx = runner._child_context(parent_ctx, request)

    assert child_ctx.conversation_dir == parent_ctx.conversation_dir
    assert child_ctx.project_dir == parent_ctx.project_dir
    assert child_ctx.active_skill_dir == parent_ctx.active_skill_dir
    assert child_ctx.skill_runtime_dir == parent_ctx.skill_runtime_dir
    assert child_ctx.runtime_state == parent_ctx.runtime_state
    assert child_ctx.history_summary == parent_ctx.history_summary
    assert child_ctx.conversation_state == parent_ctx.conversation_state
    assert child_ctx.event_queue is parent_ctx.event_queue
    assert child_ctx.workspace_runtime_session == parent_ctx.workspace_runtime_session
    assert child_ctx.workspace_runtime_session is not parent_ctx.workspace_runtime_session
    assert child_ctx.parent_run_id == parent_ctx.run_id
    assert child_ctx.is_subagent is True

    child_cache = getattr(child_ctx, "_read_window_snapshots_cache")
    child_cache.add("project/b.txt:0:EOF")
    assert "project/b.txt:0:EOF" not in getattr(parent_ctx, "_read_window_snapshots_cache")


def test_subagent_system_prompt_uses_v2_workspace_paths_not_location_relative_dialect(tmp_path) -> None:
    from app.services.agent_harness.capabilities.subagents.runner import HarnessSubagentRunner
    from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry

    runner = HarnessSubagentRunner(
        provider=object(),
        conversation={},
        parent_context=_ctx(tmp_path),
        parent_registry=ToolRegistry(),
        language="en",
    )

    prompt = runner._system_prompt("Review the requested files.", ToolRegistry())

    assert "project/report.html" in prompt
    assert "references/inputs/brief.txt" in prompt
    assert "file_path relative to the selected location" not in prompt
    assert "selected location" not in prompt
    assert "not `python project/foo.py`" not in prompt
    assert "location=" not in prompt
