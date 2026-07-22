from app.services.agent_harness.runtime.execution_support.tool_result_projection import (
    apply_char_budget,
    build_model_tool_content,
)


def test_full_output_under_budget() -> None:
    text, truncated, total = apply_char_budget("hello world", max_chars=100)
    assert text == "hello world"
    assert truncated is False
    assert total == 11


def test_truncates_over_budget_with_blob_pointer() -> None:
    output = "x" * 100
    text, truncated, total = apply_char_budget(output, max_chars=10, blob_artifact={"ref": "blob://abc"})
    assert truncated is True
    assert total == 100
    assert text.startswith("x" * 10)
    assert "output truncated: 10/100 chars" in text
    assert "blob://abc" in text


def test_success_payload_carries_raw_output() -> None:
    payload = build_model_tool_content(
        tool_name="grep_files",
        output='{"mode":"content","content":"src/a.py:1:def f()"}',
        review={"outcome": "success", "summary": "ignored excerpt"},
        outcome={"is_error": False, "status": "completed"},
        blob_artifact={"ref": "blob://x"},
        max_chars=30_000,
    )
    assert payload["status"] == "completed"
    assert payload["output"] == '{"mode":"content","content":"src/a.py:1:def f()"}'
    assert "output_truncated" not in payload


def test_success_payload_ignores_non_actionable_failure_summary() -> None:
    payload = build_model_tool_content(
        tool_name="web_search",
        output='{"query":"尼采","results":[{"title":"Friedrich Nietzsche"}]}',
        review={
            "outcome": "success",
            "summary": '{"query":"尼采","results":[{"title":"Friedrich Nietzsche"}]}',
            "failure": {
                "failure_kind": None,
                "summary": '{"query":"尼采","results":[{"title":"Friedrich Nietzsche"}]}',
                "user_visible": True,
            },
        },
        outcome={"is_error": False, "status": "completed"},
        blob_artifact=None,
        max_chars=30_000,
    )
    assert payload == {
        "status": "completed",
        "output": '{"query":"尼采","results":[{"title":"Friedrich Nietzsche"}]}',
    }


def test_failure_payload_keeps_guidance_fields() -> None:
    payload = build_model_tool_content(
        tool_name="exec_command",
        output="Traceback ... SyntaxError",
        review={
            "outcome": "error",
            "failure_kind": "syntax_error",
            "root_cause_hint": "bad syntax",
            "required_next_action": "fix it",
            "recovery_hint": {"instruction": "patch"},
            "no_progress_signature": "sig123",
            "summary": "should not leak as sole view",
        },
        outcome={"is_error": True, "status": "failed"},
        blob_artifact=None,
        max_chars=30_000,
    )
    assert payload["status"] == "failed"
    assert payload["failure_kind"] == "syntax_error"
    assert payload["root_cause_hint"] == "bad syntax"
    assert payload["required_next_action"] == "fix it"
    assert payload["recovery_hint"] == {"instruction": "patch"}
    assert payload["no_progress_signature"] == "sig123"
    assert payload["output"] == "Traceback ... SyntaxError"


def test_oversized_output_marks_truncated() -> None:
    payload = build_model_tool_content(
        tool_name="exec_command",
        output="y" * 50_000,
        review=None,
        outcome={"is_error": False},
        blob_artifact={"ref": "blob://big"},
        max_chars=30_000,
    )
    assert payload["output_truncated"] is True
    assert payload["output_total_chars"] == 50_000
    assert payload["blob_artifact"] == {"ref": "blob://big"}
