from app.services.agent_harness.runtime.model_context.microcompact import (
    CLEARED_MESSAGE,
    DEFAULT_KEEP_RECENT,
    microcompact_messages,
)


def _assistant(call_id: str, tool_name: str) -> dict:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": tool_name, "arguments": "{}"}}],
    }


def _tool(call_id: str, content: str) -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def _conversation(n: int, tool_name: str = "grep_files") -> list[dict]:
    messages: list[dict] = [{"role": "user", "content": "go"}]
    for i in range(n):
        messages.append(_assistant(f"c{i}", tool_name))
        messages.append(_tool(f"c{i}", f"result-{i}"))
    return messages


def test_keeps_recent_and_clears_older() -> None:
    messages = _conversation(8)
    out, cleared = microcompact_messages(messages, keep_recent=3)

    # 8 compactable results, keep last 3 → clear first 5
    assert len(cleared) == 5
    assert cleared == [f"c{i}" for i in range(5)]
    cleared_set = set(cleared)
    for msg in out:
        if msg.get("role") != "tool":
            continue
        if msg["tool_call_id"] in cleared_set:
            assert msg["content"] == CLEARED_MESSAGE
        else:
            assert msg["content"] != CLEARED_MESSAGE


def test_preserves_message_count_and_order() -> None:
    messages = _conversation(6)
    out, _ = microcompact_messages(messages, keep_recent=2)
    assert len(out) == len(messages)
    assert [m["role"] for m in out] == [m["role"] for m in messages]


def test_no_clear_when_under_keep_recent() -> None:
    messages = _conversation(3)
    out, cleared = microcompact_messages(messages, keep_recent=DEFAULT_KEEP_RECENT)
    assert cleared == []
    assert out == messages


def test_non_compactable_tools_untouched() -> None:
    messages = _conversation(8, tool_name="ask_user")
    out, cleared = microcompact_messages(messages, keep_recent=1)
    assert cleared == []
    assert out == messages


def test_alias_tool_name_is_compactable() -> None:
    messages = _conversation(4, tool_name="Grep")
    _, cleared = microcompact_messages(messages, keep_recent=1)
    assert len(cleared) == 3


def test_already_cleared_not_recounted() -> None:
    messages = _conversation(5)
    # Pre-clear the first result.
    messages[2]["content"] = CLEARED_MESSAGE
    _, cleared = microcompact_messages(messages, keep_recent=2)
    # 5 compactable, keep 2 → 3 candidates to clear, but one is already cleared.
    assert "c0" not in cleared
    assert set(cleared) == {"c1", "c2"}
