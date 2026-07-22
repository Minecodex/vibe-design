from __future__ import annotations

from app.services.agent_harness.runtime.model_context.budget_policy import (
    build_model_context_budget,
    calculate_token_state,
)


def test_model_context_budget_uses_override(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", False)
    monkeypatch.setattr("app.core.config.settings.HARNESS_AUTOCOMPACT_PCT_OVERRIDE", "50")

    budget = build_model_context_budget(max_tokens=10_000)

    assert budget.effective_window_tokens == 10_000
    assert budget.auto_threshold_tokens == 5_000


def test_model_context_budget_respects_disable_auto_compact(monkeypatch):
    monkeypatch.setattr("app.core.config.settings.HARNESS_DISABLE_AUTO_COMPACT", True)
    monkeypatch.setattr("app.core.config.settings.HARNESS_AUTOCOMPACT_PCT_OVERRIDE", None)

    budget = build_model_context_budget(max_tokens=10_000)
    state = calculate_token_state(9_000, budget)

    assert budget.auto_compact_enabled is False
    assert state.is_above_auto_compact_threshold is False
    assert state.is_above_predictive_threshold is False
    assert state.is_at_blocking_limit is True
