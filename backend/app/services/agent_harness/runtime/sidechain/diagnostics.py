from __future__ import annotations

from copy import deepcopy
from typing import Any


def build_sidechain_trace_diagnostic(payload: dict[str, Any]) -> dict[str, Any]:
    """Build a safe, structured diagnostic view for a Sidechain Task event.

    The returned object intentionally carries refs and metadata, not prompt text,
    full tool output, or arbitrary child payloads.
    """

    result = _dict(payload.get("result"))
    output_contract = _output_contract(payload, result)
    diagnostic: dict[str, Any] = {
        "task_id": _text(payload.get("task_id") or payload.get("taskId")),
        "parent_run_id": _text(payload.get("parent_run_id") or payload.get("parentRunId")),
        "parent_tool_call_id": _text(payload.get("tool_call_id") or payload.get("toolCallId")),
        "child_run_id": _text(
            payload.get("agent_run_id")
            or payload.get("agentRunId")
            or payload.get("child_run_id")
            or payload.get("childRunId")
            or payload.get("subagent_run_id")
            or payload.get("subagentRunId")
        ),
        "status": _text(payload.get("status")),
        "transcript_ref": _text(payload.get("transcript_ref") or payload.get("transcriptRef") or result.get("transcript_ref") or result.get("transcriptRef")),
        "result_ref": _text(payload.get("result_ref") or payload.get("resultRef") or result.get("result_ref") or result.get("resultRef")),
        "usage_refs": _safe_usage(payload.get("usage_summary") or payload.get("usageSummary") or result.get("usage_summary") or result.get("usageSummary")),
        "output_contract": output_contract,
        "path_normalizations": _path_normalizations(payload),
        "tool_result_envelopes": _tool_result_envelopes(result),
    }

    failure = _failure(payload, output_contract)
    if failure:
        diagnostic["failure"] = failure

    return {
        key: value
        for key, value in diagnostic.items()
        if value not in (None, "", [], {})
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _safe_usage(value: Any) -> dict[str, Any]:
    source = _dict(value)
    allowed = {
        "multimodal_calls",
        "image_analysis_calls",
        "image_generation_calls",
        "video_generation_calls",
        "context_compression_calls",
        "multimodal_models",
        "image_analysis_models",
        "image_models",
        "video_models",
        "context_compression_models",
        "total_elapsed_ms",
    }
    return {key: deepcopy(source[key]) for key in allowed if key in source}


def _output_contract(payload: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    raw = (
        result.get("output_contract")
        or result.get("outputContract")
        or payload.get("output_contract")
        or payload.get("outputContract")
    )
    contract = _dict(raw)
    if not contract:
        return {}
    allowed = {"status", "checked_outputs", "checkedOutputs", "missing_outputs", "missingOutputs"}
    return {key: deepcopy(contract[key]) for key in allowed if key in contract}


def _path_normalizations(payload: dict[str, Any]) -> list[dict[str, Any]]:
    task_spec = _dict(payload.get("task_spec") or payload.get("taskSpec"))
    inputs = _dict(task_spec.get("inputs"))
    raw_entries = inputs.get("path_normalization") or inputs.get("pathNormalization") or []
    if not isinstance(raw_entries, list):
        return []

    entries: list[dict[str, Any]] = []
    for raw in raw_entries:
        entry = _dict(raw)
        if not entry:
            continue
        entries.append(
            {
                "field": _text(entry.get("field")),
                "original": _text(entry.get("original")),
                "normalized": _text(entry.get("normalized")),
                "action": "applied" if bool(entry.get("applied")) else "rejected",
                "confidence": _text(entry.get("confidence") or _dict(entry.get("normalization")).get("confidence")),
                "reason_code": _text(entry.get("reason_code") or entry.get("reasonCode")),
                "normalization_kind": _text(entry.get("normalization_kind") or entry.get("normalizationKind")),
            }
        )
    return entries


def _tool_result_envelopes(result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_calls = result.get("tool_calls") or result.get("toolCalls") or []
    if not isinstance(raw_calls, list):
        return []

    envelopes: list[dict[str, Any]] = []
    for raw_call in raw_calls:
        call = _dict(raw_call)
        review = _dict(call.get("review"))
        envelope = _dict(review.get("tool_result_envelope") or review.get("toolResultEnvelope"))
        if not envelope:
            continue
        envelopes.append(
            {
                "tool": _text(call.get("tool") or call.get("tool_name") or call.get("toolName")),
                "tool_call_id": _text(call.get("tool_call_id") or call.get("toolCallId")),
                "truncated": bool(envelope.get("truncated")),
                "persisted": bool(envelope.get("persisted")),
                "blob_ref": _text(envelope.get("blob_ref") or envelope.get("blobRef")),
            }
        )
    return [
        {key: value for key, value in entry.items() if value not in (None, "")}
        for entry in envelopes
    ]


def _failure(payload: dict[str, Any], output_contract: dict[str, Any]) -> dict[str, Any]:
    reason_code = _text(payload.get("reason_code") or payload.get("reasonCode"))
    status = _text(payload.get("status"))
    failure: dict[str, Any] = {}
    if not reason_code and (not status or status in {"completed", "running", "queued", "created"}):
        return failure
    if reason_code:
        failure["reason_code"] = reason_code
    if status and status not in {"completed", "running", "queued", "created"}:
        failure["status"] = status
    if output_contract.get("status"):
        failure["output_contract_status"] = output_contract.get("status")
    return failure
