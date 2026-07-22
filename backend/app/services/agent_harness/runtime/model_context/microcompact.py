"""Lazy local compaction of stale tool results — mirrors Claude Code's microCompact.

Instead of summarizing tool output eagerly at assembly time, the full output is
kept verbatim in context and only the *older* compactable tool results are
cleared (content replaced with a neutral marker) once context grows under
pressure. The most recent ``keep_recent`` compactable results are always kept
raw, so the model never loses the working set it is actively reasoning over.

Operates on the OpenAI-flat provider message list (``role="tool"`` messages with
``tool_call_id``); the producing tool name is recovered from the matching
assistant ``tool_calls`` entry, so tool messages need not carry the name.
"""

from __future__ import annotations

from typing import Any

from app.services.agent_harness.capabilities.tools._internal.base import ToolRegistry

CLEARED_MESSAGE = "[Old tool result content cleared]"

DEFAULT_KEEP_RECENT = 5

# Canonical tool names whose results are safe to clear once stale. Mirrors
# Claude Code's COMPACTABLE_TOOLS (Read/Bash/Grep/Glob/WebSearch/WebFetch/Edit/
# Write) plus our exploration tools.
COMPACTABLE_TOOLS: frozenset[str] = frozenset(
    {
        "read_file",
        "exec_command",
        "grep_files",
        "glob_files",
        "list_files",
        "web_search",
        "fetch_webpage",
        "edit_file",
        "write_file",
        "workspace_map",
    }
)

def _canonical(name: str) -> str:
    # Resolve upstream / capitalised aliases (``Bash``/``Grep``/…) to canonical
    # names via the single source of truth on ToolRegistry, so a tool call emitted
    # under an alias still maps to a compactable canonical name.
    return ToolRegistry._normalise_name(name)


def _tool_name_by_call_id(messages: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for call in message.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            call_id = str(call.get("id") or "")
            if not call_id:
                continue
            name = ""
            function = call.get("function")
            if isinstance(function, dict):
                name = str(function.get("name") or "")
            if not name:
                name = str(call.get("name") or "")
            mapping[call_id] = _canonical(name)
    return mapping


def microcompact_messages(
    messages: list[dict[str, Any]],
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Clear all but the most recent ``keep_recent`` compactable tool results.

    Returns ``(messages, cleared_tool_call_ids)``. Message count and ordering are
    preserved, so assistant↔tool pairing invariants downstream are unaffected.
    """

    name_by_id = _tool_name_by_call_id(messages)
    compactable_indices: list[int] = []
    for index, message in enumerate(messages):
        if message.get("role") != "tool":
            continue
        call_id = str(message.get("tool_call_id") or "")
        if name_by_id.get(call_id, "") in COMPACTABLE_TOOLS:
            compactable_indices.append(index)

    keep = max(1, int(keep_recent))
    if len(compactable_indices) <= keep:
        return list(messages), []
    clear_indices = set(compactable_indices[:-keep])

    cleared_ids: list[str] = []
    result: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index in clear_indices and str(message.get("content") or "") != CLEARED_MESSAGE:
            cleared = dict(message)
            cleared["content"] = CLEARED_MESSAGE
            result.append(cleared)
            cleared_ids.append(str(message.get("tool_call_id") or ""))
        else:
            result.append(message)
    return result, cleared_ids
