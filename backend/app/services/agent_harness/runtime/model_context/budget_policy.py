from __future__ import annotations

import os

from app.core.config import settings

from .models import ModelContextBudget, ModelContextTokenState

MAX_RESERVED_OUTPUT_TOKENS = 20_000
DEFAULT_TOOL_GROWTH_ESTIMATE = 15_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000
# Lazy microcompact (clear stale tool results) kicks in well before the
# expensive LLM full-summary thresholds, as a cheap first tier of relief.
MICROCOMPACT_THRESHOLD_PCT = 0.6


def build_model_context_budget(*, max_tokens: int) -> ModelContextBudget:
    effective_window = max(1, int(max_tokens or 0))
    reserved_output = _reserved_output_tokens(effective_window)
    predictive_growth = reserved_output + _tool_growth_estimate(effective_window)
    buffer_tokens = _buffer_tokens(effective_window)
    auto_threshold = max(1, effective_window - buffer_tokens)
    override = _autocompact_pct_override()
    if override is not None:
        auto_threshold = min(auto_threshold, max(1, int(effective_window * (override / 100.0))))
    predictive_threshold = max(1, effective_window - predictive_growth)
    blocking_limit = max(1, effective_window - MANUAL_COMPACT_BUFFER_TOKENS)
    microcompact_threshold = max(1, min(predictive_threshold, int(effective_window * MICROCOMPACT_THRESHOLD_PCT)))
    return ModelContextBudget(
        effective_window_tokens=effective_window,
        auto_threshold_tokens=auto_threshold,
        predictive_threshold_tokens=predictive_threshold,
        blocking_limit_tokens=blocking_limit,
        reserved_output_tokens=reserved_output,
        predictive_turn_growth_tokens=predictive_growth,
        buffer_tokens=buffer_tokens,
        auto_compact_enabled=not bool(getattr(settings, "HARNESS_DISABLE_AUTO_COMPACT", False)),
        microcompact_threshold_tokens=microcompact_threshold,
    )


def calculate_token_state(token_usage: int, budget: ModelContextBudget) -> ModelContextTokenState:
    usage = max(0, int(token_usage or 0))
    projected = usage + int(budget.predictive_turn_growth_tokens)
    effective = max(1, int(budget.effective_window_tokens or 1))
    return ModelContextTokenState(
        token_usage=usage,
        projected_token_usage=projected,
        percent_left=max(0, min(100, int(((effective - usage) / effective) * 100))),
        is_above_auto_compact_threshold=budget.auto_compact_enabled
        and usage >= int(budget.auto_threshold_tokens),
        is_above_predictive_threshold=budget.auto_compact_enabled
        and usage > int(budget.predictive_threshold_tokens),
        is_at_blocking_limit=usage >= int(budget.blocking_limit_tokens),
    )


def _autocompact_pct_override() -> float | None:
    value = getattr(settings, "HARNESS_AUTOCOMPACT_PCT_OVERRIDE", None)
    if value is None:
        value = os.getenv("HARNESS_AUTOCOMPACT_PCT_OVERRIDE")
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = float(text)
    except ValueError:
        return None
    if 0 < parsed <= 100:
        return parsed
    return None


def _reserved_output_tokens(effective_window: int) -> int:
    if effective_window >= 400_000:
        return 20_000
    if effective_window >= 100_000:
        return 12_000
    if effective_window >= 16_000:
        return 4_000
    return max(256, min(MAX_RESERVED_OUTPUT_TOKENS, effective_window // 5))


def _buffer_tokens(effective_window: int) -> int:
    if effective_window >= 800_000:
        return 50_000
    if effective_window >= 400_000:
        return 30_000
    if effective_window >= 100_000:
        return 13_000
    return max(512, effective_window // 5)


def _tool_growth_estimate(effective_window: int) -> int:
    return max(512, min(DEFAULT_TOOL_GROWTH_ESTIMATE, effective_window // 6))
