"""Centralised constants for the agent_harness runtime.

Keep magic numbers here so truncation, limits, and contract values are
discoverable and consistent across engine, hooks, and subagents.
"""

from __future__ import annotations

# --- Tool output truncation ------------------------------------------------
# The three windows compose in this order:
#   raw tool.output  ──OutputTruncationHook──▶  capped at TOOL_OUTPUT_LLM_MAX
#   LLM-visible text ─ slice by RECORD_MAX ───▶ stored in messages.json record
#   LLM-visible text ─ slice by PREVIEW_MAX ──▶ used for audit previews / UI
TOOL_OUTPUT_LLM_MAX = 50_000          # OutputTruncationHook cap (LLM-visible)
TOOL_OUTPUT_RECORD_MAX = 2_000        # messages.json record.result.output cap
TOOL_OUTPUT_PREVIEW_MAX = 500         # audit + UI preview cap

# --- Subagent response contract --------------------------------------------
# Hard cap on the summary the child returns to the parent LLM context.
# Prevents raw assistant_text from a chatty child from drowning the parent.
SUBAGENT_SUMMARY_MAX = 4_000

# --- Subagent nesting depth ------------------------------------------------
# Maximum depth of Agent subagent recursion. Depth 0 = top-level run;
# depth 1 = child; 2 = grandchild. Spawns at depth >= this limit are refused.
SUBAGENT_MAX_DEPTH = 2

# --- Committed execution recovery windows ---------------------------------
# After a successful tool result in committed execution, allow one internal
# continuation retry if the next provider turn stalls before any new activity.
RUN_INACTIVITY_TIMEOUT_SECONDS = 1_800


def truncate_for_llm(text: str) -> str:
    if not text or len(text) <= TOOL_OUTPUT_LLM_MAX:
        return text
    return text[:TOOL_OUTPUT_LLM_MAX] + f"\n\n[Output truncated to {TOOL_OUTPUT_LLM_MAX} chars]"


def truncate_for_record(text: str) -> str:
    if not text:
        return ""
    return text[:TOOL_OUTPUT_RECORD_MAX]


def truncate_for_preview(text: str) -> str:
    if not text:
        return ""
    return text[:TOOL_OUTPUT_PREVIEW_MAX]


def truncate_subagent_summary(text: str) -> str:
    if not text or len(text) <= SUBAGENT_SUMMARY_MAX:
        return text
    return text[:SUBAGENT_SUMMARY_MAX] + f"\n\n[Summary truncated to {SUBAGENT_SUMMARY_MAX} chars]"
