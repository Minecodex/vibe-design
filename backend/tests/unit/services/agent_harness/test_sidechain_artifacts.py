from __future__ import annotations

import json
from pathlib import Path

from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.sidechain.artifacts import SidechainArtifactStore


def _ctx(tmp_path: Path) -> HarnessContext:
    ctx = HarnessContext(user_id=1, conversation_id="conv-sidechain-artifacts", run_id="run-parent", workspace_root=tmp_path)
    ctx.ensure_dirs()
    return ctx


def test_sidechain_artifact_store_creates_and_appends_transcript(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    store = SidechainArtifactStore(ctx)

    transcript_ref = store.start_transcript("sub-1", metadata={"label": "Worker"})
    store.append_transcript("sub-1", {"role": "assistant", "content": "hello"})
    store.append_transcript("sub-1", {"role": "tool", "content": "ok"})

    assert transcript_ref == ".agent/sidechains/sub-1/transcript.jsonl"
    rows = [
        json.loads(line)
        for line in (ctx.conversation_dir / transcript_ref).read_text(encoding="utf-8").splitlines()
    ]
    assert rows[0]["type"] == "transcript_started"
    assert rows[1]["role"] == "assistant"
    assert rows[2]["role"] == "tool"


def test_sidechain_artifact_store_writes_terminal_result_and_reads_back(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    store = SidechainArtifactStore(ctx)

    result_ref = store.write_result(
        "sub-1",
        status="failed",
        summary="Child failed.",
        output_refs=[],
        failure_details={"reason_code": "child_failed"},
        usage_summary={"multimodal_calls": 1},
        transcript_ref=".agent/sidechains/sub-1/transcript.jsonl",
    )

    assert result_ref == ".agent/sidechains/sub-1/result.json"
    payload = store.read_result("sub-1")
    assert payload["status"] == "failed"
    assert payload["failure_details"]["reason_code"] == "child_failed"
    assert payload["usage_summary"] == {"multimodal_calls": 1}


def test_sidechain_artifact_store_sanitizes_task_id_into_sidechain_root(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    store = SidechainArtifactStore(ctx)

    ref = store.start_transcript("../bad/task")

    assert ref == ".agent/sidechains/task/transcript.jsonl"
    assert (ctx.conversation_dir / ref).resolve().is_relative_to(ctx.agent_dir.resolve())
