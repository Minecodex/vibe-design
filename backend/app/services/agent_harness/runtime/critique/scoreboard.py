from __future__ import annotations

from collections.abc import Mapping, Sequence

from .contracts import CritiqueConfig, CritiqueRound, FallbackPolicy, RoundDecision

ROLE_WEIGHTS = {
    "designer": 0.0,
    "critic": 0.4,
    "brand": 0.2,
    "a11y": 0.2,
    "copy": 0.2,
}


def compute_composite(scores: Mapping[str, float]) -> float:
    weighted_total = 0.0
    present_weight = 0.0
    for role, weight in ROLE_WEIGHTS.items():
        if weight <= 0 or role not in scores:
            continue
        weighted_total += float(scores[role]) * weight
        present_weight += weight
    return weighted_total / present_weight if present_weight else 0.0


def decide_round(*, composite: float, must_fix_count: int, cfg: CritiqueConfig) -> RoundDecision:
    return "ship" if composite >= cfg.score_threshold and must_fix_count == 0 else "continue"


def select_fallback_round(
    rounds: Sequence[CritiqueRound],
    policy: FallbackPolicy,
) -> CritiqueRound | None:
    if not rounds or policy == "fail":
        return None
    if policy == "ship_last":
        return rounds[-1]
    return max(rounds, key=lambda item: (item.composite, item.round_number))
