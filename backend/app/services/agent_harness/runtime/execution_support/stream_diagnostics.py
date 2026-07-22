from __future__ import annotations

from typing import Any


def new_stream_diagnostics_state() -> dict[str, Any]:
    return {
        "provider_event_counts": {},
        "tool_argument_streams": {},
        "last_tool_argument_delta": None,
        "sample_diagnostics": [],
        "last_event_kind": None,
    }


def record_stream_chunk_diagnostics(
    state: dict[str, Any],
    diagnostics: dict[str, Any],
) -> None:
    event_kind = str(diagnostics.get("provider_event_kind") or "unknown")
    state["last_event_kind"] = event_kind
    event_counts = state["provider_event_counts"]
    event_counts[event_kind] = int(event_counts.get(event_kind) or 0) + 1

    if event_kind == "tool_call_arguments_delta":
        tool_call_id = str(
            diagnostics.get("tool_call_id")
            or f"index:{diagnostics.get('tool_call_index', 'unknown')}"
        )
        tool_streams = state["tool_argument_streams"]
        entry = tool_streams.setdefault(
            tool_call_id,
            {
                "tool_call_id": diagnostics.get("tool_call_id"),
                "tool_call_index": diagnostics.get("tool_call_index"),
                "tool_name": diagnostics.get("tool_name") or "",
                "delta_chunk_count": 0,
                "total_argument_delta_chars": 0,
                "argument_chars": 0,
            },
        )
        entry["delta_chunk_count"] += 1
        entry["total_argument_delta_chars"] += int(diagnostics.get("argument_delta_chars") or 0)
        entry["argument_chars"] = max(
            int(entry.get("argument_chars") or 0),
            int(diagnostics.get("argument_chars") or 0),
        )
        if diagnostics.get("tool_name"):
            entry["tool_name"] = diagnostics.get("tool_name") or ""
        if diagnostics.get("tool_call_id") is not None:
            entry["tool_call_id"] = diagnostics.get("tool_call_id")
        if diagnostics.get("tool_call_index") is not None:
            entry["tool_call_index"] = diagnostics.get("tool_call_index")
        state["last_tool_argument_delta"] = {
            "tool_call_id": diagnostics.get("tool_call_id"),
            "tool_call_index": diagnostics.get("tool_call_index"),
            "tool_name": diagnostics.get("tool_name") or "",
            "argument_delta_chars": int(diagnostics.get("argument_delta_chars") or 0),
            "argument_chars": int(diagnostics.get("argument_chars") or 0),
            "argument_chunk_count": int(diagnostics.get("argument_chunk_count") or 0),
        }
        return

    samples = state["sample_diagnostics"]
    if len(samples) < 10:
        samples.append(diagnostics)


def build_stream_diagnostics_payload(
    *,
    chunk_count: int,
    content_chunk_count: int,
    tool_call_chunk_count: int,
    usage_chunk_count: int,
    usage_only_chunk_count: int,
    finish_reason_chunk_count: int,
    provider_usage_only_without_choices_count: int,
    provider_tool_call_argument_delta_count: int,
    provider_diagnostics_state: dict[str, Any],
) -> dict[str, Any]:
    tool_argument_streams = sorted(
        provider_diagnostics_state["tool_argument_streams"].values(),
        key=lambda item: (
            str(item.get("tool_name") or ""),
            str(item.get("tool_call_id") or ""),
            int(item.get("tool_call_index") or -1),
        ),
    )
    return {
        "chunk_count": chunk_count,
        "content_chunk_count": content_chunk_count,
        "tool_call_chunk_count": tool_call_chunk_count,
        "usage_chunk_count": usage_chunk_count,
        "usage_only_chunk_count": usage_only_chunk_count,
        "finish_reason_chunk_count": finish_reason_chunk_count,
        "provider_usage_only_without_choices_count": provider_usage_only_without_choices_count,
        "tool_call_argument_delta_count": provider_tool_call_argument_delta_count,
        "provider_diagnostics_summary": {
            "event_counts": dict(provider_diagnostics_state["provider_event_counts"]),
            "tool_argument_stream_count": len(tool_argument_streams),
            "tool_argument_streams": tool_argument_streams,
            "sample_diagnostics": list(provider_diagnostics_state["sample_diagnostics"]),
            "last_event_kind": provider_diagnostics_state["last_event_kind"],
        },
        "last_tool_argument_delta": provider_diagnostics_state["last_tool_argument_delta"],
    }
