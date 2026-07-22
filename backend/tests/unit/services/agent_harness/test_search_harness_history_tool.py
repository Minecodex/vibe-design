from __future__ import annotations

import json

import pytest

from app.services.agent_harness.capabilities.tools.search_harness_history import (
    SearchHarnessHistoryInput,
    SearchHarnessHistoryTool,
)
from app.services.agent_harness.core.context import HarnessContext
from app.services.agent_harness.runtime.eventing.persistence import persist_tool_result
from app.services.agent_harness.runtime.context_recall.store import append_collapse_commit
from app.services.agent_harness.runtime.model_context.boundary_store import append_boundary_v2
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
    load_messages,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    append_message_record as append_message,
)


@pytest.mark.asyncio
async def test_search_harness_history_finds_session_and_tool_sources(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Recall")
    conversation_id = conversation["id"]

    append_message(
        7,
        conversation_id,
        {"role": "user", "content": "请记住后面要修复 backend/app/demo.py 里的 FrobnicatorError"},
    )
    result_ref = persist_tool_result(
        7,
        conversation_id,
        tool_call_id="call-1",
        payload={
            "tool": "exec_command",
            "output": "Traceback: FrobnicatorError in backend/app/demo.py line 12",
            "metadata": {"safe": True},
        },
    )

    ctx = HarnessContext(user_id=7, conversation_id=conversation_id, run_id="run-1", workspace_root=tmp_path)
    tool = SearchHarnessHistoryTool()
    result = await tool.execute(
        SearchHarnessHistoryInput(query="FrobnicatorError", sources=None, limit=8),
        ctx,
    )

    payload = json.loads(result.output)
    sources = {match["source"] for match in payload["matches"]}
    snippets = "\n".join(match["snippet"] for match in payload["matches"])

    assert {"conversation", "tool_results"}.issubset(sources)
    assert "FrobnicatorError" in snippets
    assert result_ref in json.dumps(payload, ensure_ascii=False)
    assert "trace.jsonl" not in json.dumps(payload, ensure_ascii=False)


@pytest.mark.asyncio
async def test_search_harness_history_finds_collapse_commits(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Collapse")
    append_collapse_commit(
        7,
        conversation["id"],
        source_item_count=20,
        replacement_item_count=5,
        estimated_tokens_before=90000,
        estimated_tokens_after=12000,
        levels_applied=["budget_reduction", "snip", "microcompact", "context_collapse"],
        searchable_sources=["conversation", "collapse_commits"],
        preserved_recent_groups=4,
    )

    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    result = await SearchHarnessHistoryTool().execute(
        SearchHarnessHistoryInput(query="context_collapse", sources=["collapse_commits"], limit=8),
        ctx,
    )

    payload = json.loads(result.output)
    assert payload["matches"][0]["source"] == "collapse_commits"
    assert "context_collapse" in payload["matches"][0]["snippet"]


@pytest.mark.asyncio
async def test_search_harness_history_does_not_cross_conversation_boundaries(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    first = create_conversation(7, title="First")
    second = create_conversation(7, title="Second")
    append_message(7, first["id"], {"role": "user", "content": "private needle only in first conversation"})

    ctx = HarnessContext(user_id=7, conversation_id=second["id"], run_id="run-1", workspace_root=tmp_path)
    result = await SearchHarnessHistoryTool().execute(
        SearchHarnessHistoryInput(query="private needle", sources=None, limit=8),
        ctx,
    )

    payload = json.loads(result.output)
    assert payload["matches"] == []


@pytest.mark.asyncio
async def test_search_harness_history_redacts_sensitive_snippets(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Secrets")
    append_message(
        7,
        conversation["id"],
        {
            "role": "user",
            "content": "Debug Authorization Bearer sk-secret-token and cookie=sessionid",
        },
    )

    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    result = await SearchHarnessHistoryTool().execute(
        SearchHarnessHistoryInput(query="Authorization", sources=["conversation"], limit=4),
        ctx,
    )

    payload = json.loads(result.output)
    text = json.dumps(payload, ensure_ascii=False)
    assert "sk-secret-token" not in text
    assert "sessionid" not in text
    assert "[REDACTED" in text


@pytest.mark.asyncio
async def test_search_harness_history_honors_before_seq_for_conversation_matches(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Seq filter")
    append_message(7, conversation["id"], {"role": "user", "content": "needle in the older message"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "needle in the newer message"})
    messages = load_messages(7, conversation["id"])
    newer_seq = int(messages[-1]["_seq"])

    ctx = HarnessContext(user_id=7, conversation_id=conversation["id"], run_id="run-1", workspace_root=tmp_path)
    result = await SearchHarnessHistoryTool().execute(
        SearchHarnessHistoryInput(
            query="needle",
            sources=["conversation"],
            limit=8,
            before_seq=newer_seq,
        ),
        ctx,
    )

    payload = json.loads(result.output)
    assert len(payload["matches"]) == 1
    assert payload["matches"][0]["snippet"].startswith("needle in the older")
    assert payload["matches"][0]["seq"] is not None
    assert int(payload["matches"][0]["seq"]) < newer_seq


@pytest.mark.asyncio
async def test_search_harness_history_recovers_exact_historical_references(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    conversation = create_conversation(7, title="Exact recall")
    conversation_id = conversation["id"]
    message = append_message(
        7,
        conversation_id,
        {"role": "user", "content": "Exact message content that does not include its id."},
    )
    result_ref = persist_tool_result(
        7,
        conversation_id,
        tool_call_id="call-exact",
        payload={"tool": "read_file", "output": "Exact tool output", "metadata": {"safe": True}},
    )
    boundary = append_boundary_v2(
        7,
        conversation_id,
        run_id="run-boundary",
        compact_type="auto_full",
        covered={"message_row_id_end": int(message["_seq"]), "event_sequence_end": 1, "message_count": 1},
        summary_message={"role": "user", "content": "Conversation summary:\nBoundary exact recovery summary"},
        restore_messages=[{"role": "user", "content": "Restore file backend/app/exact_boundary.py"}],
        token_counts={"pre": 1000, "post": 10, "effective_window": 2000, "auto_threshold": 1500},
        method={"source": "llm_full_compact", "levels_applied": ["full_summary"]},
    )

    ctx = HarnessContext(user_id=7, conversation_id=conversation_id, run_id="run-1", workspace_root=tmp_path)
    tool = SearchHarnessHistoryTool()

    message_payload = json.loads(
        (
            await tool.execute(
                SearchHarnessHistoryInput(query=f"message_id:{message['id']}", sources=None, limit=4),
                ctx,
            )
        ).output
    )
    result_payload = json.loads(
        (
            await tool.execute(
                SearchHarnessHistoryInput(query=f"result_ref:{result_ref}", sources=None, limit=4),
                ctx,
            )
        ).output
    )
    compaction_payload = json.loads(
        (
            await tool.execute(
                SearchHarnessHistoryInput(query=f"compaction_id:{boundary.boundary_id}", sources=None, limit=4),
                ctx,
            )
        ).output
    )
    boundary_payload = json.loads(
        (
            await tool.execute(
                SearchHarnessHistoryInput(query=f"boundary_id:{boundary.boundary_id}", sources=None, limit=4),
                ctx,
            )
        ).output
    )

    assert message_payload["matches"][0]["source"] == "conversation"
    assert message_payload["matches"][0]["id"] == message["id"]
    assert message_payload["matches"][0]["match_type"] == "exact_reference"
    assert result_payload["matches"][0]["result_ref"] == result_ref
    assert result_payload["matches"][0]["match_type"] == "exact_reference"
    assert compaction_payload["matches"][0]["compaction_id"] == boundary.boundary_id
    assert compaction_payload["matches"][0]["match_type"] == "exact_reference"
    assert boundary_payload["matches"][0]["boundary_id"] == boundary.boundary_id
    assert boundary_payload["matches"][0]["covered"]["message_row_id_end"] == int(message["_seq"])
    assert boundary_payload["matches"][0]["compact_type"] == "auto_full"
    assert boundary_payload["matches"][0]["match_type"] == "exact_reference"
