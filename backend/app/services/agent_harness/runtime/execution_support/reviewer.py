from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from app.services.agent_harness.runtime.execution_support.failure_contract import build_failure_payload, normalize_recovery_hint
from app.services.agent_harness.isolation.security.commands import classify_failure_text
from app.services.agent_harness.capabilities.tools._internal.base import ToolResult


def review_tool_result(tool_name: str, raw_args: dict[str, Any], result: ToolResult) -> dict[str, Any]:
    output = result.output or ""
    metadata = result.metadata or {}
    outcome = "error" if result.is_error or metadata.get("semantic_error_type") else "noop" if metadata.get("noop") else "success"
    error_type = metadata.get("semantic_error_type") or _extract_error_type(output) if outcome == "error" else None
    failure_kind = metadata.get("failure_kind") if outcome in {"error", "noop"} else None
    if outcome in {"error", "noop"}:
        failure_kind = _normalize_failure_kind(failure_kind, metadata=metadata, output=output, error_type=error_type)
    if (
        outcome == "success"
        and tool_name == "read_file"
        and metadata.get("repeated_read")
        and metadata.get("unchanged")
    ):
        failure_kind = "no_progress"
    if outcome == "success" and _is_low_signal_exploration(tool_name, raw_args, metadata):
        failure_kind = "no_progress"
    if outcome == "success" and metadata.get("prepared_workspace_entry_overwritten"):
        failure_kind = "prepared_workspace_entry_rewrite"
        outcome = "noop"
    if outcome == "noop" and metadata.get("phase_tool_blocked") and not failure_kind:
        failure_kind = "phase_tool_blocked"
    if outcome == "error" and not failure_kind:
        failure_kind = classify_failure_text(output, error_type)
    file_path = (
        metadata.get("file_path")
        or metadata.get("path")
        or raw_args.get("file_path")
        or raw_args.get("path")
        or _extract_file_path(output)
    )
    line = _extract_line(output)
    root_cause_hint, required_next_action, recovery_hint = (None, None, None)
    if outcome in {"error", "noop"} or failure_kind == "no_progress":
        root_cause_hint, required_next_action, recovery_hint = _guidance(
            tool_name=tool_name,
            failure_kind=failure_kind,
            file_path=file_path,
            line=line,
            phase=str(metadata.get("phase") or "").strip() or None,
        )
    metadata_recovery_hint = normalize_recovery_hint(metadata.get("recovery_hint"))
    if metadata_recovery_hint:
        recovery_hint = metadata_recovery_hint
        instruction = str(metadata_recovery_hint.get("instruction") or "").strip()
        if instruction:
            required_next_action = instruction
        protocol_failure = metadata.get("protocol_failure")
        if isinstance(protocol_failure, dict):
            protocol_message = str(protocol_failure.get("message") or "").strip()
            if protocol_message:
                root_cause_hint = protocol_message
    excerpt = _tool_output_excerpt(tool_name, result, output)
    user_visible = _is_user_visible_review(metadata=metadata, failure_kind=failure_kind)
    failure_stage = str(metadata.get("phase") or "").strip() or None
    signature = None
    no_progress_group = _no_progress_group(tool_name=tool_name, failure_kind=failure_kind, metadata=metadata)
    if failure_kind == "no_progress" and tool_name == "read_file" and file_path:
        signature = f"read_file_repeat:{file_path}"
    elif failure_kind == "no_progress" and tool_name == "workspace_map":
        signature = "workspace_map:consulted"
    elif failure_kind == "no_progress" and tool_name == "list_files":
        signature = _list_files_no_progress_signature(raw_args, metadata)
    elif outcome in {"error", "noop"}:
        signature_payload = {
            "tool": tool_name,
            "failure_kind": failure_kind,
            "error_type": error_type,
            "file_path": file_path,
            "line": line,
            "args_hint": _args_hint(raw_args),
        }
        signature = hashlib.sha256(
            json.dumps(signature_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:20]
    summary = excerpt if user_visible else None
    failure = build_failure_payload(
        failure_kind=failure_kind,
        failure_stage=failure_stage,
        user_visible=user_visible,
        summary=summary,
        root_cause_hint=root_cause_hint,
        required_next_action=required_next_action,
        recovery_hint=recovery_hint,
        failure_signature=signature,
    )
    review_payload = {
        "tool": tool_name,
        "outcome": outcome,
        "error_type": error_type,
        "failure_kind": failure_kind,
        "failure_stage": failure_stage,
        "file_path": file_path,
        "line": line,
        "root_cause_hint": root_cause_hint,
        "required_next_action": required_next_action,
        "recovery_hint": recovery_hint,
        "no_progress_signature": signature,
        "output_excerpt": excerpt,
        "user_visible": user_visible,
        "summary": summary,
        "failure": failure,
    }
    if no_progress_group:
        review_payload["no_progress_group"] = no_progress_group
    envelope = metadata.get("tool_result_envelope")
    if isinstance(envelope, dict):
        review_payload["tool_result_envelope"] = envelope
    return review_payload


def review_user_visible_summary(review: dict[str, Any] | None) -> str | None:
    if not isinstance(review, dict):
        return None
    failure = review.get("failure")
    if isinstance(failure, dict):
        if failure.get("user_visible") is False:
            return None
        summary = str(failure.get("summary") or "").strip()
        return summary or None
    if review.get("user_visible") is False:
        return None
    summary = str(review.get("summary") or review.get("output_excerpt") or "").strip()
    return summary or None


def _extract_error_type(text: str) -> str | None:
    match = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))\b", text or "")
    if match:
        return match.group(1)
    if "Unexpected token" in text and "JSON" in text:
        return "JSONParseError"
    return None


def _extract_file_path(text: str) -> str | None:
    match = re.search(r"\b((?:code|files|\.meta)/[^\s:'\"]+)", text or "")
    return match.group(1) if match else None


def _extract_line(text: str) -> int | None:
    for pattern in (r"\bline\s+(\d+)\b", r":(\d+):\d+", r":(\d+)\n"):
        match = re.search(pattern, text or "")
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None

def _guidance(
    *,
    tool_name: str,
    failure_kind: str | None,
    file_path: str | None,
    line: int | None,
    phase: str | None,
) -> tuple[str | None, str | None, dict[str, Any] | None]:
    loc = f"{file_path} around line {line}" if file_path and line else file_path or "the failing file"
    if failure_kind == "data_serialization_error":
        return (
            "Structured data contains invalid escaping or syntax.",
            f"Read {loc}, regenerate the data with json.dump/JSON.stringify, then rerun the command.",
            {
                "instruction": "Repair the serialization issue with the smallest reliable edit.",
                "preferred_tools": ["read_file", "edit_file", "exec_command"],
            },
        )
    if failure_kind == "syntax_error":
        return (
            "The generated code has a syntax error.",
            f"Read {loc}, apply a minimal patch, then rerun the failing command.",
            {
                "instruction": "Patch the syntax error in place before retrying.",
                "preferred_tools": ["read_file", "edit_file", "exec_command"],
            },
        )
    if failure_kind == "missing_dependency":
        return (
            "The current runtime is missing a dependency required by the generated command.",
            f"Read {loc}, remove the unnecessary dependency or switch to an available library/runtime, then rerun the command.",
            {
                "instruction": "Repair the dependency issue in the smallest reliable way before rerunning.",
                "preferred_tools": ["read_file", "edit_file", "exec_command"],
            },
        )
    if failure_kind == "runtime_dependency_missing":
        return (
            "The shell command depends on a command-line tool that is not available in this runtime.",
            "Switch to an available execution strategy, such as a checked-in script, Python stdlib, or an already available package.",
            {
                "instruction": "Use an available execution strategy instead of retrying the missing shell tool.",
                "preferred_tools": ["read_file", "edit_file", "write_file"],
                "avoid_tools": ["exec_command"],
            },
        )
    if failure_kind == "command_policy_blocked":
        return (
            "The command was blocked by shell safety policy before execution.",
            "Do not retry the blocked shell form. Use a structured file tool or a simpler allowed command.",
            {
                "instruction": "Use a structured tool or simpler allowed command instead of retrying the blocked shell form.",
                "preferred_tools": ["read_file", "write_file", "edit_file", "exec_command"],
            },
        )
    if failure_kind == "write_effect_policy":
        return (
            "The command attempted to write outside the active allowed write root.",
            "Keep generated outputs inside the allowed write root and copy readonly inputs into the candidate assets directory before referencing them.",
            {
                "instruction": "Move effects back under the allowed write root before retrying.",
                "preferred_tools": ["read_file", "edit_file", "write_file", "exec_command"],
            },
        )
    if failure_kind == "path_outside_workspace":
        return (
            "The requested operation was blocked by the workspace boundary.",
            "Stop this execution path instead of retrying an escaped or unsafe path.",
            {
                "instruction": "Do not retry the unsafe path. Explain the workspace boundary or choose a safe work-relative path only if one is clearly equivalent.",
                "constraints": ["Do not use .., absolute paths, or dangerous shell commands to bypass the workspace."],
            },
        )
    if failure_kind == "html_dependency_error":
        return (
            "The HTML candidate references local dependencies that are not valid publishable bundle members yet.",
            "copy the required files from the read-only skill/ or references/ roots into the candidate directory under project/, then reference those copied files with candidate-relative paths.",
            {
                "instruction": "Repair the candidate so every local HTML dependency lives inside the candidate directory tree before retrying.",
                "preferred_tools": ["exec_command", "write_file", "register_artifact", "publish_output"],
            },
        )
    if failure_kind == "artifact_lint_failed":
        return (
            "The open-design HTML lint gate found P0 anti-slop or design-token issues in the registered artifact.",
            "Read the registered HTML, repair every P0 finding from <artifact-lint>, then register_artifact and publish_output again.",
            {
                "instruction": "Repair P0 findings in the registered HTML, then call register_artifact and publish_output again.",
                "preferred_tools": ["read_file", "edit_file", "exec_command", "register_artifact", "publish_output"],
            },
        )
    if failure_kind == "patch_target_not_found":
        return (
            "The patch target does not match current file contents.",
            f"Read {file_path or 'the file'} again and patch using a larger exact context.",
            {
                "instruction": "Re-read the file and patch against fresh context.",
                "preferred_tools": ["read_file", "edit_file"],
            },
        )
    if failure_kind == "timeout":
        return (
            "The command timed out.",
            "Run a narrower command, add progress output, or split the work into smaller steps.",
            {
                "instruction": "Retry with a narrower and more observable step.",
                "preferred_tools": ["exec_command", "read_file"],
            },
        )
    if failure_kind == "no_progress" and tool_name == "read_file":
        return (
            "The same unchanged file was read again without advancing the task.",
            "Do not read the same unchanged file again. Use the latest contents to take a different concrete next step.",
            {
                "instruction": "Use the latest file contents you already have and change strategy instead of rereading the same file.",
                "preferred_tools": ["edit_file", "exec_command", "register_artifact", "publish_output"],
                "avoid_tools": ["read_file"],
            },
        )
    if failure_kind == "no_progress" and tool_name in {"workspace_map", "list_files"}:
        return (
            "The tool call only repeated low-signal workspace exploration.",
            "Stop repeating workspace discovery. Use the current context to take a concrete deliverable step.",
            {
                "instruction": "Take a concrete deliverable step from the current context instead of repeating workspace discovery.",
                "preferred_tools": ["write_file", "edit_file", "exec_command", "register_artifact", "publish_output"],
                "avoid_tools": ["workspace_map", "list_files"],
            },
        )
    if failure_kind == "revision_search_budget_exhausted":
        return (
            "Plan revision search budget is exhausted.",
            "Do not expand the search scope with web_search. Use fetch_webpage on discovered sources or update_planning_draft with known information and mark missing data for follow-up.",
            {
                "instruction": "Continue revising the draft without expanding the search scope.",
                "constraints": ["Do not call web_search again in this revision turn."],
                "preferred_tools": ["fetch_webpage", "update_planning_draft"],
                "avoid_tools": ["web_search"],
                "context_patch": {"phase": phase or "revising_plan"},
            },
        )
    if failure_kind == "phase_tool_blocked":
        return (
            "The selected tool is not allowed in the current phase.",
            "Stay in plan revision mode. Use update_planning_draft or request_plan_approval with the known information instead of execution tools.",
            {
                "instruction": "Stay within the current planning phase and continue with allowed tools only.",
                "constraints": ["Do not create files or run execution tools in this phase."],
                "preferred_tools": ["update_planning_draft", "request_plan_approval", "read_file", "fetch_webpage"],
                "avoid_tools": ["exec_command", "write_file", "register_artifact", "publish_output"],
                "context_patch": {"phase": phase or "revising_plan"},
            },
        )
    if failure_kind == "prepared_workspace_entry_rewrite":
        return (
            "The prepared workspace entry was rewritten wholesale instead of being edited in place.",
            "Re-read the prepared entry file, then patch the existing structure instead of replacing the whole file.",
            {
                "instruction": "Treat the prepared workspace entry as an existing template file and make the smallest in-place edit.",
                "preferred_tools": ["read_file", "edit_file"],
                "avoid_tools": ["write_file"],
            },
        )
    if failure_kind == "home_execution_input_required":
        return (
            "Home execution requested user input after execution had already started.",
            "Stop the run and tell the user exactly which required inputs are missing instead of asking another question card.",
            {
                "instruction": "Do not call ask_user again in this home execution turn. End the run with a direct missing-input explanation.",
                "avoid_tools": ["ask_user"],
            },
        )
    if failure_kind:
        return (
            "The tool failed.",
            "Use the error output to choose a different concrete next action.",
            {
                "instruction": "Choose the smallest reliable next step based on the latest tool failure.",
            },
        )
    if tool_name == "publish_output":
        return (
            "Artifact validation did not pass.",
            "Fix or regenerate the artifact, then validate it again.",
            {
                "instruction": "Repair the artifact and validate it again before publishing.",
                "preferred_tools": ["read_file", "edit_file", "exec_command", "register_artifact"],
            },
        )
    return None, None, None


def _is_user_visible_review(*, metadata: dict[str, Any], failure_kind: str | None) -> bool:
    if metadata.get("phase_tool_blocked"):
        return False
    if failure_kind == "phase_tool_blocked":
        return False
    if failure_kind == "plan_search_budget_exhausted":
        return False
    return True


def _is_low_signal_exploration(tool_name: str, raw_args: dict[str, Any], metadata: dict[str, Any]) -> bool:
    normalized = str(tool_name or "").strip()
    if normalized == "workspace_map":
        return True
    if normalized != "list_files":
        return False
    if metadata.get("truncated"):
        return False
    entry_count = metadata.get("entry_count")
    if entry_count is None:
        entries = metadata.get("entries")
        entry_count = len(entries) if isinstance(entries, list) else None
    try:
        normalized_entry_count = int(entry_count or 0)
    except (TypeError, ValueError):
        return False
    if normalized_entry_count != 0:
        return False
    base = str(raw_args.get("base") or "work").strip() or "work"
    path = str(raw_args.get("path") or raw_args.get("file_path") or metadata.get("root") or ".").strip() or "."
    return bool(base and path is not None)


def _no_progress_group(*, tool_name: str, failure_kind: str | None, metadata: dict[str, Any]) -> str | None:
    if failure_kind != "no_progress":
        return None
    if tool_name in {"workspace_map", "list_files"}:
        return "low_signal_exploration"
    return None


def _list_files_no_progress_signature(raw_args: dict[str, Any], metadata: dict[str, Any]) -> str:
    base = str(raw_args.get("base") or "work").strip() or "work"
    path = str(raw_args.get("path") or raw_args.get("file_path") or metadata.get("root") or ".").strip() or "."
    recursive = bool(raw_args.get("recursive") or metadata.get("recursive"))
    return f"list_files_empty:{base}:{path}:recursive={str(recursive).lower()}"


def _normalize_failure_kind(
    failure_kind: Any,
    *,
    metadata: dict[str, Any],
    output: str,
    error_type: str | None,
) -> str | None:
    normalized = str(failure_kind or "").strip() or None
    protocol_failure = metadata.get("protocol_failure")
    protocol_kind = None
    if isinstance(protocol_failure, dict):
        protocol_kind = str(protocol_failure.get("failure_kind") or "").strip()
    if protocol_kind in {"readonly_input_write", "hidden_root_write", "system_root_write"}:
        return "write_effect_policy"
    if metadata.get("denied") and normalized in {
        "dangerous_command",
        "command_too_complex",
        "shell_parse_error",
        "large_shell_write_blocked",
        "destructive_path_rewrite_blocked",
        "ambiguous_shell_path",
    }:
        return "command_policy_blocked"
    if normalized in {"dangerous_command", "command_too_complex", "shell_parse_error"} and metadata.get("risk_tags"):
        return "command_policy_blocked"
    if normalized in {"traceback", None, ""}:
        classified = classify_failure_text(output, error_type)
        return classified if classified != "unknown_failure" else normalized
    if normalized == "missing_dependency":
        classified = classify_failure_text(output, error_type)
        if classified == "runtime_dependency_missing":
            return classified
    return normalized


def _args_hint(args: dict[str, Any]) -> str:
    if "command" in args:
        return str(args.get("command") or "").splitlines()[0][:160]
    if "file_path" in args or "path" in args:
        return str(args.get("file_path") or args.get("path"))
    return ""


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _tool_output_excerpt(tool_name: str, result: ToolResult, output: str) -> str:
    normalized_name = str(tool_name or "").replace("lc_", "")
    metadata = result.metadata or {}
    if isinstance(metadata.get("tool_result_envelope"), dict):
        return _truncate(output, 1200)
    if normalized_name == "web_search":
        results = metadata.get("results") or []
        if isinstance(results, list):
            compact = []
            for item in results[:3]:
                if not isinstance(item, dict):
                    continue
                compact_item = {
                    "title": item.get("title"),
                }
                local_image_path = item.get("local_image_path")
                image_url = item.get("image_url")
                source_url = item.get("source_url")
                if local_image_path or image_url:
                    compact_item["local_image_path"] = local_image_path
                    compact_item["image_url"] = image_url
                    if source_url:
                        compact_item["source_url"] = source_url
                else:
                    compact_item["url"] = item.get("url")
                    compact_item["snippet"] = _truncate(str(item.get("snippet") or ""), 80)
                compact.append(compact_item)
            payload = {
                "query": metadata.get("query"),
                "results": compact,
            }
            return _truncate(json.dumps(payload, ensure_ascii=False), 500)
    if normalized_name == "fetch_webpage":
        payload = {
            "url": metadata.get("url"),
            "code": metadata.get("code"),
            "codeText": metadata.get("codeText"),
            "blocked_reason": metadata.get("blocked_reason"),
            "result": _truncate(str(metadata.get("result") or output or ""), 220),
        }
        return _truncate(json.dumps(payload, ensure_ascii=False), 500)
    return _truncate(output, 500)

