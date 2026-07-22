from __future__ import annotations

import json

from app.services.agent_harness.runtime.sidechain.diagnostics import build_sidechain_trace_diagnostic
from app.services.agent_harness.runtime.eventing.trace_export import _build_trace_event


def test_sidechain_diagnostic_correlates_lifecycle_refs_usage_and_tool_envelopes() -> None:
    diagnostic = build_sidechain_trace_diagnostic(
        {
            "task_id": "sub-artifact-1",
            "parent_run_id": "run-parent",
            "agent_run_id": "run-child",
            "tool_call_id": "call-spawn",
            "status": "completed",
            "transcript_ref": ".agent/sidechains/sub-artifact-1/transcript.jsonl",
            "result_ref": ".agent/sidechains/sub-artifact-1/result.json",
            "usage_summary": {"multimodal_calls": 1, "multimodal_models": ["fake-model"]},
            "task_spec": {
                "inputs": {
                    "path_normalization": [
                        {
                            "field": "output_path",
                            "original": "project/project/out.html",
                            "normalized": "project/out.html",
                            "applied": True,
                            "normalization_kind": "duplicate_semantic_root",
                            "confidence": "high",
                        }
                    ]
                }
            },
            "result": {
                "output_contract": {"status": "satisfied", "checked_outputs": ["project/out.html"]},
                "tool_calls": [
                    {
                        "tool": "write_file",
                        "tool_call_id": "call-write",
                        "metadata": {"path": "project/out.html"},
                        "review": {
                            "tool_result_envelope": {
                                "truncated": True,
                                "persisted": True,
                                "blob_ref": ".agent/blobs/tool-results/call-write.txt",
                                "full_text": "must not leak",
                            },
                            "output_excerpt": "must not leak either",
                        },
                    }
                ],
            },
        }
    )

    assert diagnostic == {
        "task_id": "sub-artifact-1",
        "parent_run_id": "run-parent",
        "parent_tool_call_id": "call-spawn",
        "child_run_id": "run-child",
        "status": "completed",
        "transcript_ref": ".agent/sidechains/sub-artifact-1/transcript.jsonl",
        "result_ref": ".agent/sidechains/sub-artifact-1/result.json",
        "usage_refs": {"multimodal_calls": 1, "multimodal_models": ["fake-model"]},
        "output_contract": {"status": "satisfied", "checked_outputs": ["project/out.html"]},
        "path_normalizations": [
            {
                "field": "output_path",
                "original": "project/project/out.html",
                "normalized": "project/out.html",
                "action": "applied",
                "confidence": "high",
                "reason_code": None,
                "normalization_kind": "duplicate_semantic_root",
            }
        ],
        "tool_result_envelopes": [
            {
                "tool": "write_file",
                "tool_call_id": "call-write",
                "truncated": True,
                "persisted": True,
                "blob_ref": ".agent/blobs/tool-results/call-write.txt",
            }
        ],
    }
    assert "must not leak" not in json.dumps(diagnostic, ensure_ascii=False)


def test_sidechain_diagnostic_surfaces_failure_reason_and_contract_status() -> None:
    diagnostic = build_sidechain_trace_diagnostic(
        {
            "task_id": "sub-failed",
            "parent_run_id": "run-parent",
            "agent_run_id": "run-child",
            "status": "failed",
            "reason_code": "child_failed",
            "result": {"reason": "tool_failed"},
        }
    )

    assert diagnostic["status"] == "failed"
    assert diagnostic["failure"]["reason_code"] == "child_failed"


def test_sidechain_diagnostic_covers_cancelled_trace_without_sensitive_content() -> None:
    diagnostic = build_sidechain_trace_diagnostic(
        {
            "task_id": "sub-cancelled",
            "parent_run_id": "run-parent",
            "status": "cancelled",
            "reason_code": "user_cancelled",
            "instructions": "Authorization: Bearer secret-token",
            "api_key": "sk-super-secret",
        }
    )

    assert diagnostic["status"] == "cancelled"
    assert diagnostic["failure"]["reason_code"] == "user_cancelled"
    assert "instructions" not in diagnostic
    assert "api_key" not in diagnostic


def test_trace_export_embeds_sidechain_diagnostic_summary() -> None:
    trace_event = _build_trace_event(
        {
            "seq": 9,
            "event_type": "subagent_failed",
            "run_id": "run-parent",
            "payload": {
                "task_id": "sub-failed",
                "parent_run_id": "run-parent",
                "agent_run_id": "run-child",
                "status": "failed",
                "reason_code": "child_failed",
                "result": {"reason": "tool_failed"},
                "secret": "sk-should-not-leak",
            },
        },
        profile="diagnostic",
    )

    assert trace_event["sidechain"]["task_id"] == "sub-failed"
    assert trace_event["sidechain"]["child_run_id"] == "run-child"
    assert trace_event["sidechain"]["failure"]["reason_code"] == "child_failed"
    assert json.dumps(trace_event["sidechain"], ensure_ascii=False).find("sk-should-not-leak") == -1
