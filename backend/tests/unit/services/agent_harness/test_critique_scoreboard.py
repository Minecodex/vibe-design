import pytest

from app.services.agent_harness.runtime.critique.contracts import CritiqueConfig, CritiqueRound
from app.services.agent_harness.runtime.critique.scoreboard import (
    compute_composite,
    decide_round,
    select_fallback_round,
)


def _round(number: int, composite: float) -> CritiqueRound:
    return CritiqueRound(
        round_number=number,
        active_entry="web-prepared/index.html",
        artifact_work_root="web-prepared",
        composite=composite,
        must_fix_count=1,
    )


def test_composite_uses_open_design_critique_role_weights():
    result = compute_composite(
        {"designer": 10, "critic": 7, "brand": 8, "a11y": 6, "copy": 9}
    )

    assert result == pytest.approx(7.4)


def test_round_only_ships_without_open_must_fix():
    cfg = CritiqueConfig()

    assert decide_round(composite=8.0, must_fix_count=0, cfg=cfg) == "ship"
    assert decide_round(composite=9.0, must_fix_count=1, cfg=cfg) == "continue"
    assert decide_round(composite=7.99, must_fix_count=0, cfg=cfg) == "continue"


def test_ship_best_breaks_tie_with_later_round():
    best = select_fallback_round([_round(1, 7.5), _round(2, 7.5)], "ship_best")

    assert best is not None
    assert best.round_number == 2

