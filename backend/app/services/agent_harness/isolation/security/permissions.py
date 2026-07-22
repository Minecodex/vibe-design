"""Multi-layer permission system for Harness agent."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from app.services.agent_harness.runtime.state.runtime_policy import allows_plan_non_read_only_tool

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext
    from app.services.agent_harness.runtime.state.runtime_state import RuntimeState


class PermissionMode(str, Enum):
    FULL_AUTO = "full_auto"  # All tools allowed immediately
    PLAN = "plan"            # Read-only auto, writes need confirmation
    DEFAULT = "default"      # All mutations need confirmation


class PermissionDecision(str, Enum):
    ALLOWED = "allowed"
    REQUIRES_CONFIRMATION = "requires_confirmation"
    DENIED = "denied"


@dataclass
class PermissionResult:
    decision: PermissionDecision
    reason: str = ""


# ---------------------------------------------------------------------------
# Always-blocked patterns (cannot be overridden by hooks or mode)
# ---------------------------------------------------------------------------

_ALWAYS_BLOCKED_COMMANDS: list[re.Pattern] = [
    re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+/(?!\S)"),
    re.compile(r"rm\s+-[a-zA-Z]*r[a-zA-Z]*f[a-zA-Z]*\s+~(?:/|\s|$)"),
    re.compile(r"mkfs\."),
    re.compile(r"dd\s+.*of=/dev/"),
    re.compile(r":\(\)\{.*\}"),  # Fork bomb
    re.compile(r"\b(?:curl|wget)\b[^\n\r|;&]*\|\s*(?:sh|bash|zsh|python|python3|node)\b", re.I),
    re.compile(r"\b(?:irm|iwr|invoke-restmethod|invoke-webrequest)\b[^\n\r|;&]*\|\s*(?:iex|invoke-expression|powershell|pwsh)\b", re.I),
    re.compile(r"\b(?:sudo|su|runas)\b", re.I),
    re.compile(r"\b(?:format|diskpart|bcdedit)\b", re.I),
    re.compile(r"\b(?:reg\s+delete|net\s+user|sc\s+(?:delete|stop|config))\b", re.I),
    re.compile(r"\b(?:shutdown|reboot|poweroff)\b", re.I),
    re.compile(r"\bSet-ExecutionPolicy\b", re.I),
    re.compile(r"\b(?:curl|wget|irm|iwr|invoke-restmethod|invoke-webrequest)\b.*(?:&&|;)\s*(?:sh|bash|zsh|python|python3|node|powershell|pwsh)\b", re.I | re.S),
]

_ALWAYS_BLOCKED_PATHS = frozenset({
    "~/.ssh",
    "~/.aws",
    "~/.gnupg",
    "~/.config/gcloud",
    "~/.azure",
    "~/.docker/config.json",
})

def _iter_sensitive_path_values(tool_name: str, args: dict[str, Any]):
    yield args.get("file_path", "")
    yield args.get("command", "")


class PermissionChecker:
    """Evaluate whether a tool call should be allowed."""

    def __init__(
        self,
        mode: PermissionMode = PermissionMode.FULL_AUTO,
        *,
        runtime_state: RuntimeState | None = None,
    ) -> None:
        self.mode = mode
        self.runtime_state = runtime_state

    def set_runtime_state(self, runtime_state: RuntimeState | None) -> None:
        self.runtime_state = runtime_state

    def evaluate(
        self,
        tool_name: str,
        args: dict[str, Any],
        *,
        is_read_only: bool = False,
        ctx: HarnessContext | None = None,
    ) -> PermissionResult:
        """Run multi-layer permission check.

        Layer 1: Always-blocked patterns (not overridable)
        Layer 2: Path protection
        Layer 3: Permission mode check
        """
        # Layer 1: Always-blocked commands
        if tool_name == "exec_command":
            command = args.get("command", "")
            for pattern in _ALWAYS_BLOCKED_COMMANDS:
                if pattern.search(command):
                    return PermissionResult(
                        PermissionDecision.DENIED,
                        "Blocked: dangerous command pattern detected",
                    )

        # Layer 2: Sensitive path protection
        for path_val in _iter_sensitive_path_values(tool_name, args):
            if not path_val:
                continue
            for blocked in _ALWAYS_BLOCKED_PATHS:
                expanded = blocked.replace("~", "")
                if expanded in path_val:
                    return PermissionResult(
                        PermissionDecision.DENIED,
                        "Blocked: access to sensitive path",
                    )

        runtime_state = getattr(ctx, "runtime_state", None) or self.runtime_state
        if runtime_state is not None:
            return runtime_state.evaluate_tool_access(
                tool_name,
                args,
                is_read_only=is_read_only,
            )

        # Layer 3: Permission mode
        if self.mode == PermissionMode.FULL_AUTO:
            return PermissionResult(PermissionDecision.ALLOWED)

        if self.mode == PermissionMode.PLAN:
            if tool_name == "ask_user":
                return PermissionResult(PermissionDecision.ALLOWED)
            if tool_name in {"update_planning_draft", "request_plan_approval", "update_execution_progress"}:
                return PermissionResult(PermissionDecision.ALLOWED)
            if is_read_only:
                return PermissionResult(PermissionDecision.ALLOWED)
            if allows_plan_non_read_only_tool(tool_name, args):
                return PermissionResult(PermissionDecision.ALLOWED)
            return PermissionResult(
                PermissionDecision.DENIED,
            f"PLAN phase only allows read/search/analyze tools, approved media generation, planning drafts, and plan approval requests; blocked '{tool_name}'",
            )

        # DEFAULT mode
        if is_read_only:
            return PermissionResult(PermissionDecision.ALLOWED)
        return PermissionResult(
            PermissionDecision.REQUIRES_CONFIRMATION,
            f"DEFAULT mode: '{tool_name}' requires confirmation",
        )
