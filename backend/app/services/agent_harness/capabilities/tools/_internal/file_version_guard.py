from __future__ import annotations

import re
from typing import Any

from app.services.agent_harness.agent_resources.file_io import run_file_io
from app.services.agent_harness.capabilities.tools._internal.base import BaseTool, ToolHook, ToolResult
from app.services.agent_harness.isolation.security.paths import resolve_tool_base


_PROTECTED_RE = re.compile(
    r"(^|[\\s'\"`])(?:file_versions|files(?:/|$)|published(?:/|$))",
    re.IGNORECASE,
)
_LEGACY_ENV_RE = re.compile(r"\bFILES_DIR\b")
_SCRIPT_RE = re.compile(r"(?:^|[;&|\s])(?:python|python3|py|node)\s+(?:-[a-zA-Z]+\s+)*['\"]?([^'\"\s]+?\.(?:py|js|mjs|cjs))['\"]?")


class FileVersionGuardHook(ToolHook):
    """Prevent tools from bypassing the versioned file publishing path."""

    async def before(
        self,
        tool: BaseTool,
        name: str,
        args: dict,
        ctx,
    ) -> dict | ToolResult | None:
        if tool.name not in {"edit_file", "exec_command", "write_file"}:
            return None
        if _args_touch_protected_generated_file(args):
            message = (
                "User-visible generated files are versioned. Keep deliverables under project/, register the final entry with register_artifact, and publish through publish_output; "
                "direct writes to files/, file_versions/, or published/ are blocked."
            )
            return ToolResult(
                output=message,
                is_error=True,
                metadata={"reason": "versioned_file_publish_required"},
            )
        if tool.name == "exec_command":
            script_error = await _legacy_script_error(args, ctx)
            if script_error:
                return ToolResult(
                    output=script_error,
                    is_error=True,
                    metadata={"reason": "legacy_files_dir_usage"},
                )
        return None


def _args_touch_protected_generated_file(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.replace("\\", "/")
        return bool(_PROTECTED_RE.search(normalized) or _LEGACY_ENV_RE.search(normalized))
    if isinstance(value, dict):
        return any(_args_touch_protected_generated_file(item) for item in value.values())
    if isinstance(value, list):
        return any(_args_touch_protected_generated_file(item) for item in value)
    return False


async def _legacy_script_error(args: dict, ctx) -> str | None:
    command = str(args.get("command") or "")
    if not command:
        return None
    cwd = str(args.get("base") or "work")
    resolved_cwd = resolve_tool_base(ctx, cwd)
    for match in _SCRIPT_RE.finditer(command):
        script_path = match.group(1).replace("\\", "/")
        resolved = ctx.resolve_workspace_path(script_path, default_scope="code", allow_fallback_to_files=False)
        if resolved is None and not script_path.startswith(("project/", "references/", "published/", "skill/")):
            resolved = (resolved_cwd / script_path).resolve() if resolved_cwd is not None else None
        if resolved is None or not resolved.exists() or not resolved.is_file():
            continue
        try:
            text = await run_file_io(resolved.read_text, encoding="utf-8", errors="replace")
        except Exception:
            continue
        normalized = text.replace("\\", "/")
        if "FILES_DIR" in normalized or re.search(r"(^|[^\w])files/", normalized):
            return (
                f"Legacy file output pattern detected in script {script_path}. "
                "Do not use FILES_DIR or write to removed files/. Write the final deliverable under project/, "
                "register it with register_artifact, and publish it with publish_output."
            )
    return None
