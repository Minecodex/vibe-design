from __future__ import annotations

import asyncio
import json

import pytest

from app.services.agent_harness.runtime.model_context import ModelContextLimitExceeded
from app.services.agent_harness.runtime.model_context.assembler import build_model_context
from app.services.agent_harness.runtime.model_context.boundary_store import load_latest_boundary_v2
from app.services.agent_harness.runtime.model_context.compactor import compact_if_needed
from app.services.agent_harness.workspace.conversation.conversation_service import (
    create_conversation,
)
from app.services.agent_harness.workspace.session_v2.db_store import (
    append_message_record as append_message,
)


class _Adapter:
    def __init__(self, content: str = "compact summary") -> None:
        self.content = content
        self.calls = 0

    def compact(self, history, *, model=None):
        self.calls += 1
        return [{"role": "assistant", "content": self.content}]


class _CapturingAdapter:
    def __init__(self, content: str = "compact summary") -> None:
        self.content = content
        self.histories = []

    @property
    def calls(self) -> int:
        return len(self.histories)

    def compact(self, history, *, model=None):
        self.histories.append(list(history))
        return [{"role": "assistant", "content": self.content}]


class _PromptTooLongOnceAdapter:
    def __init__(self) -> None:
        self.histories = []

    def compact(self, history, *, model=None):
        self.histories.append(list(history))
        if len(self.histories) == 1:
            raise RuntimeError("maximum context length exceeded")
        return [{"role": "assistant", "content": "retry summary"}]


class _PromptTooLongThreeTimesAdapter:
    def __init__(self) -> None:
        self.histories = []

    def compact(self, history, *, model=None):
        self.histories.append(list(history))
        if len(self.histories) <= 3:
            raise RuntimeError("maximum context length exceeded")
        return [{"role": "assistant", "content": "<analysis>done</analysis><summary>final retry summary</summary>"}]


def _assert_continuation_summary(content: str, summary_text: str) -> None:
    assert "This session is being continued from a previous conversation" in content
    assert "Summary:" in content
    assert summary_text in content
    assert "Continue the conversation from where it left off" in content


def test_compactor_does_not_compact_below_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "small"})
    adapter = _Adapter()

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )

    assert result is None
    assert adapter.calls == 0
    assert load_latest_boundary_v2(7, conversation["id"]) is None


def test_compactor_writes_v2_boundary_at_threshold_without_recent_tail(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "old " * 400})
    append_message(7, conversation["id"], {"role": "assistant", "content": "tail that must not survive"})
    adapter = _Adapter("summarized only")

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=700,
        llm_compact_adapter=adapter,
        model="test-model",
    )
    rebuilt = build_model_context(7, conversation["id"])

    assert result is not None
    assert result.boundary.payload["schema_version"] == 2
    assert result.boundary.compact_type == "auto_full"
    assert adapter.calls == 1
    assert len(rebuilt.messages) == 1
    assert rebuilt.messages[0]["role"] == "user"
    _assert_continuation_summary(rebuilt.messages[0]["content"], "summarized only")
    assert "tail that must not survive" not in "\n".join(message["content"] for message in rebuilt.messages)


def test_compactor_uses_predictive_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "medium " * 320})
    adapter = _Adapter("predictive summary")

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=2_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )

    assert result is not None
    assert load_latest_boundary_v2(7, conversation["id"]) is not None


def test_compactor_excludes_transient_extra_messages_from_summary_source(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "persisted"})
    adapter = _CapturingAdapter("summary without transient")
    bundle = build_model_context(
        7,
        conversation["id"],
        extra_messages=[{"role": "user", "content": "transient should not be compacted"}],
    )

    result = compact_if_needed(
        7,
        conversation["id"],
        bundle,
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )
    rebuilt = build_model_context(
        7,
        conversation["id"],
        extra_messages=[{"role": "user", "content": "transient should not be compacted"}],
    )

    assert result is not None
    compact_text = "\n".join(str(message.get("content") or "") for message in adapter.histories[0])
    assert "persisted" in compact_text
    assert "transient should not be compacted" not in compact_text
    assert len(rebuilt.messages) == 2
    _assert_continuation_summary(rebuilt.messages[0]["content"], "summary without transient")
    assert rebuilt.messages[1] == {"role": "user", "content": "transient should not be compacted"}


def test_compactor_retries_prompt_too_long_by_dropping_oldest_message_group(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "old"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "middle"})
    append_message(7, conversation["id"], {"role": "user", "content": "latest"})
    adapter = _PromptTooLongOnceAdapter()

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )

    assert result is not None
    assert len(adapter.histories) == 2
    assert [message["content"] for message in adapter.histories[0]] == ["old", "middle", "latest"]
    assert [message["content"] for message in adapter.histories[1]] == [
        "[earlier conversation truncated for compaction retry]",
        "middle",
        "latest",
    ]


def test_compactor_prompt_too_long_retries_three_api_rounds(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "u1"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "a1"})
    append_message(7, conversation["id"], {"role": "user", "content": "u2"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "a2"})
    append_message(7, conversation["id"], {"role": "user", "content": "u3"})
    append_message(7, conversation["id"], {"role": "assistant", "content": "a3"})
    append_message(7, conversation["id"], {"role": "user", "content": "u4"})
    adapter = _PromptTooLongThreeTimesAdapter()

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )
    rebuilt = build_model_context(7, conversation["id"])

    assert result is not None
    assert len(adapter.histories) == 4
    assert [message["content"] for message in adapter.histories[1]] == [
        "[earlier conversation truncated for compaction retry]",
        "a1",
        "u2",
        "a2",
        "u3",
        "a3",
        "u4",
    ]
    assert [message["content"] for message in adapter.histories[2]] == [
        "[earlier conversation truncated for compaction retry]",
        "a2",
        "u3",
        "a3",
        "u4",
    ]
    assert [message["content"] for message in adapter.histories[3]] == [
        "[earlier conversation truncated for compaction retry]",
        "a3",
        "u4",
    ]
    _assert_continuation_summary(rebuilt.messages[0]["content"], "final retry summary")


def test_compactor_honors_abort_check_before_llm_call(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "needs compact"})
    adapter = _Adapter("should not run")

    with pytest.raises(asyncio.CancelledError):
        compact_if_needed(
            7,
            conversation["id"],
            build_model_context(7, conversation["id"]),
            max_tokens=100_000,
            llm_compact_adapter=adapter,
            model="test-model",
            compact_abort_check=lambda: True,
        )

    assert adapter.calls == 0
    assert load_latest_boundary_v2(7, conversation["id"]) is None


def test_compactor_does_not_write_boundary_for_empty_llm_output(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "needs compact"})
    adapter = _Adapter("")

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )

    assert result is None
    assert adapter.calls == 1
    assert load_latest_boundary_v2(7, conversation["id"]) is None


def test_compactor_does_not_write_boundary_for_api_error_llm_output(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "needs compact"})
    adapter = _Adapter("API Error: The model has reached its context window limit.")

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )

    assert result is None
    assert adapter.calls == 1
    assert load_latest_boundary_v2(7, conversation["id"]) is None


def test_compactor_opens_circuit_breaker_after_three_failures(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.model_context.compactor.estimate_messages_tokens",
        lambda _messages: 90_000,
    )
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "needs compact"})
    failing_adapter = _Adapter("")

    for _ in range(3):
        assert (
            compact_if_needed(
                7,
                conversation["id"],
                build_model_context(7, conversation["id"]),
                max_tokens=100_000,
                llm_compact_adapter=failing_adapter,
                model="test-model",
            )
            is None
        )

    succeeding_adapter = _Adapter("should not run while breaker is open")
    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=succeeding_adapter,
        model="test-model",
    )

    assert result is None
    assert failing_adapter.calls == 3
    assert succeeding_adapter.calls == 0
    assert load_latest_boundary_v2(7, conversation["id"]) is None


def test_compactor_respects_disable_auto_compact_before_blocking_limit(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", True)
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "old " * 400})
    adapter = _Adapter()

    result = compact_if_needed(
        7,
        conversation["id"],
        build_model_context(7, conversation["id"]),
        max_tokens=100_000,
        llm_compact_adapter=adapter,
        model="test-model",
    )

    assert result is None
    assert adapter.calls == 0
    assert load_latest_boundary_v2(7, conversation["id"]) is None


def test_compactor_raises_limit_error_when_auto_compact_disabled_at_blocking_limit(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.settings.HARNESS_WORKSPACE_ROOT", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", True)
    conversation = create_conversation(7, title="Context")
    append_message(7, conversation["id"], {"role": "user", "content": "old " * 400})
    adapter = _Adapter()

    with pytest.raises(ModelContextLimitExceeded):
        compact_if_needed(
            7,
            conversation["id"],
            build_model_context(7, conversation["id"]),
            max_tokens=700,
            llm_compact_adapter=adapter,
            model="test-model",
        )

    assert adapter.calls == 0
    assert load_latest_boundary_v2(7, conversation["id"]) is None
