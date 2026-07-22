from app.services.agent_harness.workflow.tool_gating import (
    CONTROL_TOOL_FAILURE_BREAKER_TOOLS,
    is_control_tool_breaker_failure,
)


def test_control_breaker_counts_any_error_outcome_regardless_of_wording():
    # Pre-fix this relied on the English substrings "invalid parameters" /
    # "validation error"; a localized (zh) control-tool rejection slipped past the
    # breaker. The structured fix counts any deterministic failure outcome.
    zh_rejection = {
        "is_error": True,
        "status": "failed",
        "result_payload": {
            "tool": "request_plan_approval",
            "output": "request_plan_approval 需要 planning_draft.draft_outline。",
        },
    }
    assert is_control_tool_breaker_failure(zh_rejection) is True


def test_control_breaker_counts_failed_status_without_is_error():
    assert is_control_tool_breaker_failure({"status": "failed"}) is True


def test_control_breaker_ignores_successful_outcome():
    assert is_control_tool_breaker_failure({"is_error": False, "status": "completed"}) is False
    assert is_control_tool_breaker_failure({}) is False


def test_control_breaker_tool_set_is_stable():
    assert CONTROL_TOOL_FAILURE_BREAKER_TOOLS == {
        "update_planning_draft",
        "request_plan_approval",
        "update_execution_progress",
        "ask_user",
    }


def test_render_context_idempotency_key_disambiguates_transient_payloads():
    from app.services.agent_harness.workflow.handlers import _render_context_idempotency_key

    bare = _render_context_idempotency_key("run-1", turn=3)
    with_a = _render_context_idempotency_key(
        "run-1", turn=3, transient_messages=[{"role": "user", "content": "fix A"}]
    )
    with_b = _render_context_idempotency_key(
        "run-1", turn=3, transient_messages=[{"role": "user", "content": "fix B"}]
    )

    # No-transient key is unchanged (bare form).
    assert bare == "run:run-1:step:render_context:3"
    # Divergent transient payloads must not collide on the same key.
    assert with_a != with_b
    assert with_a != bare
    # Deterministic: the same transient payload yields the same key (retry-stable).
    assert with_a == _render_context_idempotency_key(
        "run-1", turn=3, transient_messages=[{"role": "user", "content": "fix A"}]
    )
