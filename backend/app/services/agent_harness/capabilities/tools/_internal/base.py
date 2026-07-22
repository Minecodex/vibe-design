"""Base tool classes and registry for Harness agent."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel
from .i18n import localize_tool_schema, tool_description

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext
    from app.services.agent_harness.capabilities.subagents.types import SubagentDefinition


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ToolResult:
    output: str = ""
    is_error: bool = False
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ToolCallClassification:
    tool_name: str
    call_id: str
    raw_args: dict[str, Any]
    parsed_args: BaseModel | None
    is_concurrency_safe: bool
    error: str | None = None


# ---------------------------------------------------------------------------
# BaseTool
# ---------------------------------------------------------------------------

class BaseTool(ABC):
    """Abstract base for all harness tools."""

    # Maximum number of characters of this tool's raw output that are sent to
    # the model verbatim. Mirrors Claude Code's per-tool ``maxResultSizeChars``:
    # the full output is always persisted to a blob, but only up to this many
    # characters reach the prompt — anything beyond is truncated with a pointer
    # to the persisted blob. Subclasses override for larger/unbounded results.
    max_result_size_chars: int = 30_000

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

    @property
    @abstractmethod
    def input_model(self) -> type[BaseModel]: ...

    @abstractmethod
    async def execute(self, params: BaseModel, ctx: "HarnessContext") -> ToolResult: ...

    # -- Safety flags (fail-closed defaults) --------------------------------

    def is_read_only(self, params: BaseModel) -> bool:
        """Override to return True for read-only invocations."""
        return False

    def is_concurrency_safe(self, params: BaseModel) -> bool:
        """Return True only if this tool is safe to run in parallel."""
        return False

    def validate_input(self, params: BaseModel, ctx: "HarnessContext") -> str | None:
        """Return an error string if input is invalid, else None."""
        return None

    # -- Schema conversion --------------------------------------------------

    def get_description(self, language: str = "zh") -> str:
        return tool_description(self.name, language, self.description)

    def get_input_schema(self, language: str = "zh") -> dict:
        schema = self.input_model.model_json_schema()
        return localize_tool_schema(self.name, schema, language)

    def to_api_schema(self, fmt: str = "openai", language: str = "zh") -> dict:
        """Convert to LLM-compatible tool definition."""
        schema = self.get_input_schema(language)
        # Strip pydantic metadata keys
        schema.pop("title", None)

        if fmt == "openai":
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.get_description(language),
                    "parameters": schema,
                },
            }
        # Anthropic native format
        return {
            "name": self.name,
            "description": self.get_description(language),
            "input_schema": schema,
        }


# ---------------------------------------------------------------------------
# ToolHook
# ---------------------------------------------------------------------------

class ToolHook(ABC):
    """Pre/post execution hook."""

    async def before(self, tool: BaseTool, name: str, args: dict, ctx: "HarnessContext") -> dict | ToolResult | None:
        """Called before tool execution. Return modified args, a blocking ToolResult, or None."""
        return None

    async def after(self, tool: BaseTool, name: str, args: dict, result: ToolResult, ctx: "HarnessContext") -> ToolResult | None:
        """Called after tool execution. Return modified result or None."""
        return None


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Manages tool registration, lookup and execution with hooks.

    Accepts upstream anthropics/skills tool names (``Bash``/``EditFile``)
    as aliases that resolve to the current harness canonical names.
    """

    # Maps upstream capitalised tool names to harness canonical names.
    # Any skill body that references e.g. ``Bash`` will resolve to ``exec_command``.
    _ALIASES: dict[str, str] = {
        "Bash": "exec_command",
        "bash": "exec_command",
        "EditFile": "edit_file",
        "edit_file": "edit_file",
        "file_edit": "edit_file",
        "Glob": "glob_files",
        "GlobTool": "glob_files",
        "glob": "glob_files",
        "Grep": "grep_files",
        "GrepTool": "grep_files",
        "grep": "grep_files",
        "ListFiles": "list_files",
    }

    def __init__(self) -> None:
        self._base_tools: dict[str, BaseTool] = {}
        self._tools: dict[str, BaseTool] = {}
        self._hidden_tools: set[str] = set()
        # Hidden-by-default tools that a skill may surface by naming them in its
        # ``tools:`` list (e.g. a domain tool that must not leak into generic sessions).
        self._skill_surfaceable: set[str] = set()
        self._hooks: list[ToolHook] = []

    def register(
        self,
        tool: BaseTool,
        *,
        base: bool = False,
        hidden: bool = False,
        skill_surfaceable: bool = False,
    ) -> None:
        target = self._base_tools if base else self._tools
        target[tool.name] = tool
        if hidden or skill_surfaceable:
            self._hidden_tools.add(tool.name)
        else:
            self._hidden_tools.discard(tool.name)
        if skill_surfaceable:
            self._skill_surfaceable.add(tool.name)
        else:
            self._skill_surfaceable.discard(tool.name)

    def add_hook(self, hook: ToolHook) -> None:
        self._hooks.append(hook)

    @classmethod
    def _normalise_name(cls, name: str) -> str:
        """Resolve an alias to its canonical name (no-op if not aliased)."""
        return cls._ALIASES.get(name, name)

    def get(self, name: str) -> BaseTool | None:
        # Try exact match first (canonical lower-case names), then alias.
        canonical = self._normalise_name(name)
        return (
            self._base_tools.get(name)
            or self._tools.get(name)
            or self._base_tools.get(canonical)
            or self._tools.get(canonical)
        )

    def get_tools_for_skill(self, skill_tool_names: list[str] | None) -> list[BaseTool]:
        """Return tools filtered by skill + all base tools, sorted by name.

        Skill declarations may use upstream (capitalised) tool names; they are
        normalised to harness canonical names before filtering.
        """
        tools: list[BaseTool] = list(self._base_tools.values())
        if not skill_tool_names:
            tools.extend(t for t in self._tools.values() if t.name not in self._hidden_tools)
        else:
            names = {self._normalise_name(n) for n in skill_tool_names}
            # A skill surfaces a tool by naming it: ordinary non-hidden tools, plus
            # any hidden-by-default tool that explicitly opted in via skill_surfaceable.
            tools.extend(
                t
                for t in self._tools.values()
                if t.name in names
                and (t.name not in self._hidden_tools or t.name in self._skill_surfaceable)
            )
        return sorted(tools, key=lambda t: t.name)

    def get_tools_by_names(
        self,
        tool_names: list[str] | tuple[str, ...],
        *,
        include_hidden: bool = False,
    ) -> list[BaseTool]:
        """Return exactly the named tools, without automatically adding base tools."""
        names = {self._normalise_name(name) for name in tool_names}
        tools: list[BaseTool] = []
        for name in names:
            if not include_hidden and name in self._hidden_tools:
                continue
            tool = self.get(name)
            if tool is not None:
                tools.append(tool)
        return sorted(tools, key=lambda t: t.name)

    def get_tools_for_subagent(
        self,
        definition: "SubagentDefinition",
        skill_tool_names: list[str] | None = None,
    ) -> list[BaseTool]:
        """Return a child-safe tool list for a subagent definition."""
        allowed = {self._normalise_name(name) for name in definition.allowed_tools}
        if allowed:
            tools = self.get_tools_by_names(tuple(allowed), include_hidden=True)
        else:
            tools = self.get_tools_for_skill(skill_tool_names)
        disallowed = {self._normalise_name(name) for name in definition.disallowed_tools}

        filtered: list[BaseTool] = []
        for tool in tools:
            if tool.name in self._hidden_tools and not definition.internal:
                continue
            if tool.name in disallowed:
                continue
            if allowed and tool.name not in allowed:
                continue
            filtered.append(tool)
        return filtered

    def clone_for_subagent(
        self,
        definition: "SubagentDefinition",
        skill_tool_names: list[str] | None = None,
    ) -> "ToolRegistry":
        """Create a child registry with the same visible tools and hook pipeline.

        Subagents run with a narrower task contract, but they must keep the same
        preflight/postflight machinery as the parent agent. Otherwise path
        normalization, security checks, and result enveloping silently diverge.
        """
        child = ToolRegistry()
        for tool in self.get_tools_for_subagent(definition, skill_tool_names):
            child.register(tool, base=tool.name in self._base_tools, hidden=False)
        child._hooks = list(self._hooks)  # noqa: SLF001 - registry clone owns the hook pipeline copy
        return child

    def to_api_schemas(
        self,
        tools: list[BaseTool] | None = None,
        fmt: str = "openai",
        language: str = "zh",
    ) -> list[dict]:
        if tools is None:
            tools = self.get_tools_for_skill(None)
        return [t.to_api_schema(fmt, language=language) for t in tools]

    def classify_tool_call(self, raw_call: dict[str, Any], absolute_index: int) -> ToolCallClassification:
        """Classify whether a model-emitted tool call is safe to execute concurrently."""
        raw_call = dict(raw_call or {})
        tool_name = str(raw_call.get("name") or "")
        call_id = str(raw_call.get("id") or f"tool-index:{int(absolute_index)}")
        raw_args = raw_call.get("arguments")
        if isinstance(raw_args, str):
            normalized_args: dict[str, Any] = {"raw": raw_args}
        elif isinstance(raw_args, dict):
            normalized_args = dict(raw_args)
        else:
            normalized_args = {}
            return ToolCallClassification(
                tool_name=tool_name,
                call_id=call_id,
                raw_args=normalized_args,
                parsed_args=None,
                is_concurrency_safe=False,
                error="tool arguments must be an object",
            )

        tool = self.get(tool_name)
        if tool is None:
            return ToolCallClassification(
                tool_name=tool_name,
                call_id=call_id,
                raw_args=normalized_args,
                parsed_args=None,
                is_concurrency_safe=False,
                error=f"Unknown tool: {tool_name}",
            )
        expanded_args, raw_error = _expand_raw_tool_args(normalized_args)
        if raw_error:
            return ToolCallClassification(
                tool_name=tool.name,
                call_id=call_id,
                raw_args=normalized_args,
                parsed_args=None,
                is_concurrency_safe=False,
                error=f"Invalid parameters: {raw_error}",
            )
        try:
            parsed_args = tool.input_model.model_validate(expanded_args)
            is_safe = bool(tool.is_read_only(parsed_args) and tool.is_concurrency_safe(parsed_args))
        except Exception as exc:
            return ToolCallClassification(
                tool_name=tool.name,
                call_id=call_id,
                raw_args=expanded_args,
                parsed_args=None,
                is_concurrency_safe=False,
                error=f"Invalid parameters: {exc}",
            )
        return ToolCallClassification(
            tool_name=tool.name,
            call_id=call_id,
            raw_args=expanded_args,
            parsed_args=parsed_args,
            is_concurrency_safe=is_safe,
        )

    async def execute(self, name: str, raw_args: dict, ctx: "HarnessContext") -> ToolResult:
        """Execute a tool by name with hook pipeline."""
        tool = self.get(name)
        if tool is None:
            return ToolResult(output=f"Unknown tool: {name}", is_error=True)

        normalized_args, raw_error = _expand_raw_tool_args(raw_args)
        if raw_error:
            return ToolResult(output=f"Invalid parameters: {raw_error}", is_error=True, metadata={"failure_kind": "invalid_parameters"})

        # Parse input through Pydantic model
        try:
            params = tool.input_model.model_validate(normalized_args)
        except Exception as e:
            return ToolResult(output=f"Invalid parameters: {e}", is_error=True, metadata={"failure_kind": "invalid_parameters"})

        # Pre-hooks
        args = normalized_args
        for hook in self._hooks:
            modified = await hook.before(tool, name, args, ctx)
            if isinstance(modified, ToolResult):
                return modified
            if modified is not None:
                args, raw_error = _expand_raw_tool_args(modified)
                if raw_error:
                    return ToolResult(output=f"Invalid parameters: {raw_error}", is_error=True, metadata={"failure_kind": "invalid_parameters"})
                params = tool.input_model.model_validate(args)

        # Tool-level validation
        err = tool.validate_input(params, ctx)
        if err:
            return ToolResult(output=err, is_error=True, metadata={"failure_kind": "invalid_parameters"})

        # Execute
        try:
            from app.services.agent_harness.agent_resources.labels import resource_for_tool
            from app.services.agent_harness.agent_resources.scheduler import get_agent_resource_scheduler

            async with get_agent_resource_scheduler().acquire(
                resource_for_tool(tool.name),
                tool_name=tool.name,
            ):
                result = await tool.execute(params, ctx)
        except Exception as e:
            result = ToolResult(output=f"Tool error: {e}", is_error=True)

        # Post-hooks
        for hook in self._hooks:
            modified = await hook.after(tool, name, args, result, ctx)
            if modified is not None:
                result = modified

        return result


def _raw_json_error_message(exc: json.JSONDecodeError, *, truncated: bool) -> str:
    if truncated or "Unterminated string" in (exc.msg or ""):
        return (
            f"tool arguments are not valid JSON ({exc.msg}); they appear truncated because the "
            "inline content is too large for a single call. Write a smaller skeleton first and use "
            "edit_file to append the remaining sections (or reduce the content), then retry."
        )
    return f"raw must be valid JSON object: {exc.msg}"


def _expand_raw_tool_args(raw_args: dict | Any) -> tuple[dict[str, Any], str | None]:
    """Normalize provider-emitted ``{"raw": ...}`` arguments before validation."""
    if not isinstance(raw_args, dict):
        return {}, "tool arguments must be an object"
    if set(raw_args.keys()) != {"raw"}:
        return raw_args, None
    raw_value = raw_args.get("raw")
    if isinstance(raw_value, dict):
        return raw_value, None
    if not isinstance(raw_value, str):
        return {}, "raw must be a JSON object string"
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        truncated = exc.pos >= len(raw_value) - 2
        if truncated:
            repaired = _append_missing_json_closers(raw_value)
            if repaired is not None:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError as repaired_exc:
                    return {}, _raw_json_error_message(repaired_exc, truncated=True)
            else:
                return {}, _raw_json_error_message(exc, truncated=True)
        else:
            return {}, _raw_json_error_message(exc, truncated=False)
    if not isinstance(parsed, dict):
        return {}, "raw must decode to a JSON object"
    return parsed, None


def _append_missing_json_closers(raw: str) -> str | None:
    stack: list[str] = []
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            stack.append(char)
            continue
        if char == "}":
            if not stack or stack[-1] != "{":
                return None
            stack.pop()
            continue
        if char == "]":
            if not stack or stack[-1] != "[":
                return None
            stack.pop()
    if in_string or not stack:
        return None
    closing_map = {"{": "}", "[": "]"}
    return f"{raw}{''.join(closing_map[token] for token in reversed(stack))}"
