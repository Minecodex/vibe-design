"""Runtime execution state and policy helpers for Harness."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from app.services.agent_harness.isolation.security.permissions import PermissionDecision, PermissionMode, PermissionResult
from .runtime_policy import (
    PLANNING_VISIBLE_TOOLS,
    allows_plan_non_read_only_tool,
)

if TYPE_CHECKING:
    from app.services.agent_harness.capabilities.tools._internal.base import BaseTool


class RuntimeStage(str, Enum):
    PLANNING = "planning"
    EXECUTING = "executing"

@dataclass(frozen=True, slots=True)
class RuntimeState:
    """Normalized runtime state shared across prompting and tool gating."""

    phase: str = "executing"
    plan_policy: str | None = None
    execution_policy: str = "default"

    @classmethod
    def from_conversation(
        cls,
        *,
        phase: str | None,
        skill_id: str | None,
        plan_policy: str | None,
    ) -> "RuntimeState":
        resolved_phase = str(phase or ("planning" if skill_id else "executing"))
        approved = resolved_phase == "executing" and bool(skill_id)
        execution_policy = "committed" if approved else "default"
        return cls(
            phase=resolved_phase,
            plan_policy=plan_policy,
            execution_policy=execution_policy,
        )

    @property
    def is_committed_execution(self) -> bool:
        return self.execution_policy == "committed"

    @property
    def stage(self) -> RuntimeStage:
        if self.phase in {"planning", "planning_ready", "revising_plan"}:
            return RuntimeStage.PLANNING
        return RuntimeStage.EXECUTING

    @property
    def permission_mode(self) -> PermissionMode:
        if self.stage == RuntimeStage.PLANNING:
            return PermissionMode.PLAN
        return PermissionMode.FULL_AUTO

    def visible_tool_names(self) -> set[str] | None:
        if self.stage == RuntimeStage.PLANNING:
            return set(PLANNING_VISIBLE_TOOLS)
        return None

    def is_tool_visible(self, tool_name: str) -> bool:
        visible = self.visible_tool_names()
        return visible is None or tool_name in visible

    def evaluate_tool_access(
        self,
        tool_name: str,
        args: dict[str, object],
        *,
        is_read_only: bool = False,
    ) -> PermissionResult:
        if not self.is_tool_visible(tool_name):
            return PermissionResult(
                PermissionDecision.DENIED,
                f"Runtime state '{self.stage.value}' blocks tool '{tool_name}'",
            )

        if self.permission_mode == PermissionMode.FULL_AUTO:
            return PermissionResult(PermissionDecision.ALLOWED)

        if self.permission_mode == PermissionMode.PLAN:
            if tool_name in {"ask_user", "update_planning_draft", "request_plan_approval", "update_execution_progress"}:
                return PermissionResult(PermissionDecision.ALLOWED)
            if is_read_only:
                return PermissionResult(PermissionDecision.ALLOWED)
            if allows_plan_non_read_only_tool(tool_name, args):
                return PermissionResult(PermissionDecision.ALLOWED)
            return PermissionResult(
                PermissionDecision.DENIED,
                f"PLAN phase only allows read/search/analyze tools, approved media generation, planning drafts, and plan approval requests; blocked '{tool_name}'",
            )

        if is_read_only:
            return PermissionResult(PermissionDecision.ALLOWED)
        return PermissionResult(
            PermissionDecision.REQUIRES_CONFIRMATION,
            f"DEFAULT mode: '{tool_name}' requires confirmation",
        )

    def filter_tools(self, tools: list["BaseTool"]) -> list["BaseTool"]:
        visible = self.visible_tool_names()
        if visible is None:
            return list(tools)
        return [tool for tool in tools if tool.name in visible]
