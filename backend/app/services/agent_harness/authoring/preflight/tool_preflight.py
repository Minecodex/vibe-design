from __future__ import annotations

import re
import shlex
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolHook, ToolResult
from app.services.agent_harness.isolation.security.paths import resolve_tool_base
from app.services.agent_harness.isolation.security.service import get_security_service

if TYPE_CHECKING:
    from app.services.agent_harness.core.context import HarnessContext


_PROJECT_PREFIX_RUNNER_RE = re.compile(
    r"(?:^|[;&|]\s*)(?:python(?:3)?|node)\s+(?:['\"])?project[\\/][^\s'\"]+",
    re.IGNORECASE,
)
_CD_PROJECT_RE = re.compile(r"(?:^|[;&|]\s*)cd\s+(?:['\"])?project(?:['\"])?(?:\s|$)", re.IGNORECASE)
_NODE_REQUIRE_RE = re.compile(
    r"(?:require\(|import\()\s*['\"]([^.'\"/][^'\"]*)['\"]|from\s+['\"]([^.'\"/][^'\"]*)['\"]",
    re.MULTILINE,
)
_OFFICE_NODE_PACKAGES = frozenset({"docx", "pptxgenjs", "exceljs"})
_BARE_REFERENCE_PATH_RE = re.compile(r"(?<!CONVERSATION_DIR/)(?:^|[\s'\"=])references[\\/](?:inputs|sources|generated)[\\/]", re.IGNORECASE)
_SCRIPT_FILE_RE = re.compile(
    r"(?:^|[;&|\s])(?:python|python3|py|node)\s+(?:-[a-zA-Z]+\s+)*['\"]?([^'\"\s]+?\.(?:py|js|mjs|cjs))['\"]?"
)
_LEADING_CD_PROJECT_RE = re.compile(r"^\s*cd\s+(['\"]?)project\1\s*(?:&&|;)\s*(.+?)\s*$", re.IGNORECASE)
_LEADING_PROJECT_SCRIPT_RE = re.compile(
    r"^\s*(python(?:3)?|py|node)\s+(['\"]?)project[\\/](.+?)\2(\s+.*)?$",
    re.IGNORECASE,
)


class HarnessPreflightHook(ToolHook):
    """Fast checks that catch avoidable workspace/runtime mistakes before execution."""

    async def before(
        self,
        tool: BaseTool,
        name: str,
        args: dict,
        ctx: "HarnessContext",
    ) -> dict | ToolResult | None:
        canonical_name = tool.name
        if canonical_name == "exec_command":
            return _preflight_shell_command(args, ctx)
        return None


def _preflight_shell_command(args: dict, ctx: "HarnessContext") -> ToolResult | None:
    action = str(args.get("action") or "run").strip().lower()
    if action not in {"run", "start"}:
        return None

    command = str(args.get("command") or "").strip()
    if not command:
        return None
    cwd = str(args.get("base") or "work").replace("\\", "/").strip().strip("/") or "work"
    command_decision = get_security_service().check_command(ctx, command=command, cwd=cwd)
    if not command_decision.allowed:
        return _blocked(
            command_decision.reason_code or "command_denied",
            f"Preflight blocked this command. {command_decision.reason}",
            {"command": command, "cwd": cwd},
        )
    if _is_project_cwd(cwd) and _BARE_REFERENCE_PATH_RE.search(command.replace("\\", "/")):
        return _blocked(
            "bare_reference_path_under_project",
            (
                "Preflight blocked this command because it reads references/... relative to the project directory. "
                "Use HARNESS_REFERENCES_DIR or a specific HARNESS_REFERENCE_*_DIR variable before rerunning."
            ),
            {"command": command, "base": cwd or "work"},
        )

    if _is_project_cwd(cwd):
        script_text = _extract_shell_script_text(command, args, ctx)
        if script_text and _BARE_REFERENCE_PATH_RE.search(script_text.replace("\\", "/")):
            return _blocked(
                "bare_reference_path_under_project",
                (
                    "Preflight blocked this script because it reads references/... relative to project/. "
                    "Update the script to use HARNESS_REFERENCES_DIR or a specific HARNESS_REFERENCE_*_DIR variable."
                ),
                {"command": command, "base": cwd or "work"},
            )

    if command_decision.normalized_value and command_decision.normalized_value != command:
        updated = dict(args)
        updated["command"] = command_decision.normalized_value
        updated["normalization_warning"] = command_decision.warnings[0].warning if command_decision.warnings else None
        updated["normalized_command"] = command_decision.normalized_value
        updated["normalization_kind"] = command_decision.warnings[0].kind if command_decision.warnings else "normalization"
        return updated
    executable = _first_executable(command)
    if executable in {"node", "npm", "npx"} and shutil.which(executable) is None:
        return _blocked(
            "missing_runtime_dependency",
            f"Preflight blocked this command because {executable} is not available. Install the missing runtime or use a provisioned dependency, then rerun.",
            {"command": command, "executable": executable},
        )
    if executable in {"soffice", "libreoffice"} and shutil.which(executable) is None:
        return _blocked(
            "missing_runtime_dependency",
            "Preflight blocked this command because LibreOffice is not available. Install the missing runtime or use a provisioned dependency, then rerun.",
            {"command": command, "executable": executable},
        )
    if executable == "node":
        missing_package = _first_missing_node_package(command, args, ctx)
        if missing_package:
            return _blocked(
                "missing_node_package",
                (
                    f"Preflight blocked this Node command because package '{missing_package}' "
                    "is not available in the workspace. Install the dependency or switch to an available runtime, then rerun."
                ),
                {"command": command, "package": missing_package},
            )
    return None


def _is_project_cwd(cwd: str) -> bool:
    normalized = str(cwd or "").replace("\\", "/").strip().strip("/")
    return normalized in {"", ".", "work", "project"} or normalized.startswith("project:")


def _extract_shell_script_text(command: str, args: dict, ctx: "HarnessContext") -> str | None:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not parts:
        return None
    if _strip_shell_quotes(parts[0]).lower() == "node":
        return _extract_node_code(command, args, ctx)
    match = _SCRIPT_FILE_RE.search(command)
    if not match:
        return None
    script_path = _resolve_node_script_path(match.group(1), args, ctx)
    if script_path and script_path.exists() and script_path.is_file():
        try:
            return script_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    return None


def _normalize_duplicate_project_command(command: str) -> dict[str, str] | None:
    current = str(command or "").strip()
    if not current:
        return None

    cd_match = _LEADING_CD_PROJECT_RE.match(current)
    if cd_match:
        remainder = cd_match.group(2).strip()
        nested = _normalize_duplicate_project_command(remainder)
        normalized_command = nested["command"] if nested else remainder
        return {
            "command": normalized_command,
            "warning": (
                "Removed redundant project-directory prefixing from the command. "
                "Commands already run from project/ by default; use project-cwd-relative paths such as 'python foo.py'."
            ),
        }

    runner_match = _LEADING_PROJECT_SCRIPT_RE.match(current)
    if not runner_match:
        return None
    executable, quote, script_path, trailing = runner_match.groups()
    normalized_command = f"{executable} {quote}{script_path}{quote}{trailing or ''}".strip()
    return {
        "command": normalized_command,
        "warning": (
            f"Removed redundant project/ prefix from command path '{executable} {quote}project/{script_path}{quote}'. "
            "Commands already run from project/ by default; use project-cwd-relative paths such as 'python foo.py'."
        ),
    }


def _first_executable(command: str) -> str | None:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not parts:
        return None
    candidate = parts[0].strip().lower()
    if candidate in {"python", "python3", "py"}:
        return "python"
    if candidate in {"node", "npm", "npx", "soffice", "libreoffice"}:
        return candidate
    return None


def _first_missing_node_package(command: str, args: dict, ctx: "HarnessContext") -> str | None:
    code = _extract_node_code(command, args, ctx)
    if not code:
        return None
    packages = _extract_office_node_packages(code)
    if not packages:
        return None
    cwd = _resolve_command_cwd(args, ctx)
    for package in sorted(packages):
        if not _node_package_available(package, cwd, ctx):
            return package
    return None


def _extract_node_code(command: str, args: dict, ctx: "HarnessContext") -> str | None:
    try:
        parts = shlex.split(command, posix=False)
    except ValueError:
        return None
    if not parts or parts[0].strip().lower() != "node":
        return None
    index = 1
    while index < len(parts):
        part = _strip_shell_quotes(parts[index])
        if part in {"-e", "--eval", "--print", "-p"}:
            return _strip_shell_quotes(parts[index + 1]) if index + 1 < len(parts) else None
        if part.startswith("-e") and len(part) > 2:
            return _strip_shell_quotes(part[2:])
        if part.startswith("-"):
            index += 1
            continue
        script_path = _resolve_node_script_path(part, args, ctx)
        if script_path and script_path.exists() and script_path.is_file():
            try:
                return script_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return None
        return None
    return None


def _extract_office_node_packages(code: str) -> set[str]:
    packages: set[str] = set()
    for match in _NODE_REQUIRE_RE.finditer(code):
        raw = match.group(1) or match.group(2) or ""
        package = _normalize_package_name(raw)
        if package in _OFFICE_NODE_PACKAGES:
            packages.add(package)
    return packages


def _normalize_package_name(value: str) -> str:
    text = value.strip()
    if text.startswith("@"):
        parts = text.split("/")
        return "/".join(parts[:2]) if len(parts) >= 2 else text
    return text.split("/", 1)[0]


def _resolve_command_cwd(args: dict, ctx: "HarnessContext") -> Path:
    base = str(args.get("base") or "work").replace("\\", "/").strip().strip("/") or "work"
    resolved = resolve_tool_base(ctx, base)
    return resolved if resolved is not None else ctx.project_dir


def _resolve_node_script_path(script: str, args: dict, ctx: "HarnessContext") -> Path | None:
    candidate = Path(_strip_shell_quotes(script))
    if candidate.is_absolute():
        resolved = ctx.resolve_workspace_path(str(candidate), default_scope="code")
        return resolved
    return (_resolve_command_cwd(args, ctx) / candidate).resolve()


def _node_package_available(package: str, cwd: Path, ctx: "HarnessContext") -> bool:
    package_parts = package.split("/")
    search_roots = [cwd, ctx.project_dir, ctx.conversation_dir]
    for root in search_roots:
        current = root.resolve()
        conversation_root = ctx.conversation_dir.resolve()
        while _is_within_path(current, conversation_root):
            if (current / "node_modules" / Path(*package_parts)).exists():
                return True
            if current == conversation_root:
                break
            current = current.parent
    return False


def _is_within_path(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _strip_shell_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _blocked(reason: str, message: str, details: dict) -> ToolResult:
    payload = {
        "status": "blocked",
        "reason": reason,
        "message": message,
        "details": details,
        # Surface the block as a denied command with a concrete failure_kind so the
        # reviewer emits the targeted recovery guidance (e.g. path_outside_workspace,
        # command_policy_blocked) instead of falling back to "unknown_failure".
        "denied": True,
        "failure_kind": reason or "command_denied",
    }
    return ToolResult(output=message, is_error=True, metadata=payload)
