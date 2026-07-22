from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolResult
from app.services.agent_harness.capabilities.skill_protocols.tool_guard import ProtocolToolGuard, tool_result_from_protocol_failure
from app.services.agent_harness.capabilities.tools._internal.file_ops import add_normalization_warning
from app.services.agent_harness.capabilities.tools._internal.command_runner import (
    DEFAULT_MAX_OUTPUT_BYTES,
    CommandRunResult,
    format_run_output,
    format_session_output,
    get_command_runner,
)
from app.services.agent_harness.capabilities.tools._internal.terminal_session_registry import (
    TerminalOwnershipStatus,
    TerminalSessionOwnershipRegistry,
)
from app.services.agent_harness.isolation.security.paths import normalize_tool_base
from app.services.agent_harness.runtime.sidechain.tool_result_envelope import envelope_tool_result

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


_PROTOCOL_SESSION_EFFECTS: dict[str, dict[str, tuple[int, int]]] = {}


class ExecCommandInput(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, validate_default=True)

    command: str | None = Field(None, description="Command to run or start. Required for action=run/start.")
    timeout: int = Field(120, ge=1, le=300)
    base: str = Field("work", description="Semantic execution root: work, project, skill, references, published, or project:<relative-dir>.")
    action: Literal["run", "start", "read", "stop", "write"] = Field("run")
    session_id: str | None = None
    input: str | None = None
    normalization_warning: str | None = None
    normalized_command: str | None = None
    normalization_kind: str | None = None

    @field_validator("base")
    @classmethod
    def validate_base(cls, value: str | None) -> str:
        return normalize_tool_base(value, default="work")


class ExecCommandTool(BaseTool):
    MAX_OUTPUT_BYTES = DEFAULT_MAX_OUTPUT_BYTES

    @property
    def name(self) -> str:
        return "exec_command"

    @property
    def description(self) -> str:
        return (
            "Run commands from a semantic base under CONVERSATION_DIR. Use this tool to execute or verify "
            "existing commands/scripts, not to create or edit files. base sets the working directory. "
            "Multi-line commands, pipelines, heredocs and redirects (including 2>&1 and >/dev/null) are "
            "supported and judged structurally. Safety is the workspace boundary: writes/reads must stay "
            "inside the workspace (never use ../ to cross workspace roots — reach other roots via the matching "
            "base or a $HARNESS_* path). To run a skill script, copy it into the work directory first, then run it."
        )

    @property
    def input_model(self) -> type[BaseModel]:
        return ExecCommandInput

    def is_read_only(self, params: BaseModel) -> bool:
        return isinstance(params, ExecCommandInput) and params.action in {"read"}

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        assert isinstance(params, ExecCommandInput)
        runner = get_command_runner()
        if params.action in {"run", "start"}:
            if not params.command:
                return f"command is required when action={params.action}"
            return runner.validate_command(params.command)
        if not params.session_id:
            return f"session_id is required when action={params.action}"
        if params.action == "write" and params.input is None:
            return "input is required when action=write"
        return None

    async def execute(self, params: ExecCommandInput, ctx: "HarnessContext") -> ToolResult:
        runner = get_command_runner()
        ownership_registry = TerminalSessionOwnershipRegistry()
        cwd = _execution_base(params)
        if params.action == "run":
            guard = ProtocolToolGuard(ctx)
            before = guard.snapshot_effects()
            result = await runner.run_once(ctx=ctx, command=params.command or "", cwd=cwd, timeout=params.timeout)
            tool_result = _attach_exec_normalization(_run_result(result), params)
            guard_failure = guard.check_command_effects(before)
            if guard_failure is not None:
                return tool_result_from_protocol_failure(
                    guard_failure,
                    metadata={
                        "command": params.command,
                        "exit_code": result.exit_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
            )
            return _envelope_exec_tool_result(ctx, params, tool_result)
        if params.action == "start":
            guard = ProtocolToolGuard(ctx)
            before = guard.snapshot_effects()
            result = await runner.start(ctx=ctx, command=params.command or "", cwd=cwd, timeout=params.timeout)
            if isinstance(result, CommandRunResult):
                tool_result = _attach_exec_normalization(_run_result(result, force_error=True), params)
                guard_failure = guard.check_command_effects(before)
                if guard_failure is not None:
                    return tool_result_from_protocol_failure(
                        guard_failure,
                        metadata={
                            "command": params.command,
                            "exit_code": result.exit_code,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        },
                    )
                return _envelope_exec_tool_result(ctx, params, tool_result)
            tool_result = _attach_exec_normalization(_snapshot_result(result), params)
            guard_failure = guard.check_command_effects(before)
            if guard_failure is not None:
                if result.running:
                    await runner.stop(session_id=result.session_id)
                return tool_result_from_protocol_failure(
                    guard_failure,
                    metadata={
                        "command": params.command,
                        "session_id": result.session_id,
                        "exit_code": result.exit_code,
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                    },
                )
            if before is not None and result.running:
                _PROTOCOL_SESSION_EFFECTS[result.session_id] = before
            if result.running:
                await ownership_registry.register(ctx=ctx, session_id=result.session_id)
            return _envelope_exec_tool_result(ctx, params, tool_result)
        if params.action == "read":
            if not runner.has_session(params.session_id):
                status = await ownership_registry.describe(ctx=ctx, session_id=params.session_id or "")
                return _envelope_exec_tool_result(ctx, params, _ownership_result(status))
            snapshot = await runner.read(session_id=params.session_id or "", timeout=params.timeout)
            tool_result = _snapshot_result(snapshot)
            guard_failure = ProtocolToolGuard(ctx).check_command_effects(_PROTOCOL_SESSION_EFFECTS.get(snapshot.session_id))
            if not snapshot.running:
                _PROTOCOL_SESSION_EFFECTS.pop(snapshot.session_id, None)
                await ownership_registry.complete(ctx=ctx, session_id=snapshot.session_id)
            else:
                await ownership_registry.renew(ctx=ctx, session_id=snapshot.session_id)
            if guard_failure is not None:
                return tool_result_from_protocol_failure(
                    guard_failure,
                    metadata={
                        "session_id": snapshot.session_id,
                        "exit_code": snapshot.exit_code,
                        "stdout": snapshot.stdout,
                        "stderr": snapshot.stderr,
                    },
                )
            return _envelope_exec_tool_result(ctx, params, tool_result)
        if params.action == "stop":
            if not runner.has_session(params.session_id):
                status = await ownership_registry.describe(ctx=ctx, session_id=params.session_id or "")
                return _envelope_exec_tool_result(ctx, params, _ownership_result(status))
            snapshot = await runner.stop(session_id=params.session_id or "")
            await ownership_registry.complete(ctx=ctx, session_id=snapshot.session_id)
            before = _PROTOCOL_SESSION_EFFECTS.pop(snapshot.session_id, None)
            tool_result = _snapshot_result(snapshot)
            guard_failure = ProtocolToolGuard(ctx).check_command_effects(before)
            if guard_failure is not None:
                return tool_result_from_protocol_failure(
                    guard_failure,
                    metadata={
                        "session_id": snapshot.session_id,
                        "exit_code": snapshot.exit_code,
                        "stdout": snapshot.stdout,
                        "stderr": snapshot.stderr,
                    },
                )
            return _envelope_exec_tool_result(ctx, params, tool_result)
        if not runner.has_session(params.session_id):
            status = await ownership_registry.describe(ctx=ctx, session_id=params.session_id or "")
            return _envelope_exec_tool_result(ctx, params, _ownership_result(status))
        written = await runner.write(session_id=params.session_id or "", text=params.input or "")
        await ownership_registry.renew(ctx=ctx, session_id=params.session_id or "")
        payload = {"session_id": params.session_id, "written": written}
        return ToolResult(output=json.dumps(payload, ensure_ascii=False), metadata=payload)


def _run_result(result: CommandRunResult, *, force_error: bool = False) -> ToolResult:
    output = result.denied_reason or format_run_output(result.stdout, result.stderr, result.exit_code)
    metadata = {
        "exit_code": result.exit_code,
        "elapsed_ms": result.elapsed_ms,
        "timed_out": result.timed_out,
        "denied": result.denied,
        "denied_reason": result.denied_reason,
        "truncated": result.truncated,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "semantic_error_type": None if result.semantic_error is None else result.semantic_error["error_type"],
        "failure_kind": None if result.semantic_error is None else result.semantic_error["failure_kind"],
        **result.metadata,
    }
    return ToolResult(output=output, is_error=force_error or result.is_error, metadata=metadata)


def _snapshot_result(snapshot) -> ToolResult:
    metadata = {
        "session_id": snapshot.session_id,
        "running": snapshot.running,
        "exit_code": snapshot.exit_code,
        "elapsed_ms": snapshot.elapsed_ms,
        "cwd": snapshot.cwd,
        "truncated": bool(snapshot.stdout_truncated or snapshot.stderr_truncated),
        "stdout_truncated": snapshot.stdout_truncated,
        "stderr_truncated": snapshot.stderr_truncated,
        "stdout": snapshot.stdout,
        "stderr": snapshot.stderr,
        "semantic_error_type": None if snapshot.semantic_error is None else snapshot.semantic_error["error_type"],
        "failure_kind": None if snapshot.semantic_error is None else snapshot.semantic_error["failure_kind"],
    }
    return ToolResult(output=format_session_output(snapshot), is_error=snapshot.is_error, metadata=metadata)


def _execution_base(params: ExecCommandInput) -> str:
    return params.base or "work"


def _ownership_result(status: TerminalOwnershipStatus) -> ToolResult:
    ownership_status = "owner_unhealthy" if status.status == "local_owner" else status.status
    payload = {
        "session_id": status.session_id,
        "ownership_status": ownership_status,
        "owner_id": status.owner_id,
        "capabilities": list(status.capabilities),
        "expires_at": status.expires_at,
    }
    return ToolResult(
        output=json.dumps(payload, ensure_ascii=False),
        is_error=True,
        metadata=payload,
    )


def _attach_exec_normalization(result: ToolResult, params: ExecCommandInput) -> ToolResult:
    output, metadata = add_normalization_warning(
        output=result.output or "",
        metadata=result.metadata or {},
        warning=params.normalization_warning,
        normalized_command=params.normalized_command,
        original=params.command,
        kind=params.normalization_kind or "path_normalization",
    )
    return ToolResult(output=output, is_error=result.is_error, metadata=metadata)


def _envelope_exec_tool_result(ctx: "HarnessContext", params: ExecCommandInput, result: ToolResult) -> ToolResult:
    command_identity = params.session_id or params.normalized_command or params.command or params.action
    return envelope_tool_result(
        ctx=ctx,
        tool_name="exec_command",
        tool_call_id=command_identity,
        result=result,
    )
