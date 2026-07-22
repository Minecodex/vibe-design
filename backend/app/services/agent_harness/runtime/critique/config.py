from __future__ import annotations

from typing import Any

from .contracts import CritiqueConfig


def load_critique_config(settings: Any) -> CritiqueConfig:
    return CritiqueConfig(
        enabled=bool(getattr(settings, "HARNESS_CRITIQUE_ENABLED", False)),
        max_rounds=int(getattr(settings, "HARNESS_CRITIQUE_MAX_ROUNDS", 3)),
        score_scale=int(getattr(settings, "HARNESS_CRITIQUE_SCORE_SCALE", 10)),
        score_threshold=float(getattr(settings, "HARNESS_CRITIQUE_SCORE_THRESHOLD", 8.0)),
        fallback_policy=str(getattr(settings, "HARNESS_CRITIQUE_FALLBACK_POLICY", "ship_best")),
        per_round_timeout_seconds=float(
            getattr(settings, "HARNESS_CRITIQUE_PER_ROUND_TIMEOUT_SECONDS", 90.0)
        ),
        total_timeout_seconds=float(
            getattr(settings, "HARNESS_CRITIQUE_TOTAL_TIMEOUT_SECONDS", 240.0)
        ),
        parser_max_block_bytes=int(
            getattr(settings, "HARNESS_CRITIQUE_PARSER_MAX_BLOCK_BYTES", 262_144)
        ),
    ).validate()
