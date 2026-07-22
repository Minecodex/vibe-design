from __future__ import annotations

from typing import Any


def _resolution_rank(value: str) -> float:
    normalized = str(value).strip().lower()
    if normalized.endswith("k"):
        try:
            return float(normalized[:-1]) * 1000
        except ValueError:
            return -1
    if normalized.endswith("p"):
        digits = "".join(ch for ch in normalized if ch.isdigit())
        return float(digits) if digits else -1
    return -1


def _parse_aspect_ratio(value: str | None) -> float | None:
    if not value or ":" not in value:
        return None
    left, right = value.split(":", 1)
    try:
        left_value = float(left)
        right_value = float(right)
    except ValueError:
        return None
    if left_value <= 0 or right_value <= 0:
        return None
    return left_value / right_value


def _pick_closest_resolution(
    allowed_values: list[str],
    requested_value: str | None,
    *,
    default_to_highest: bool = True,
) -> str | None:
    if not allowed_values:
        return requested_value
    if requested_value in allowed_values:
        return requested_value
    if requested_value is None:
        return max(allowed_values, key=_resolution_rank) if default_to_highest else allowed_values[0]
    requested_rank = _resolution_rank(requested_value)
    if requested_rank < 0:
        return max(allowed_values, key=_resolution_rank) if default_to_highest else allowed_values[0]
    return min(
        allowed_values,
        key=lambda candidate: (
            abs(_resolution_rank(candidate) - requested_rank),
            -_resolution_rank(candidate),
        ),
    )


def pick_closest_aspect_ratio(
    allowed_ratios: list[str],
    requested_ratio: str | None,
    *,
    preferred_ratio: str,
) -> str:
    if not allowed_ratios:
        return requested_ratio or preferred_ratio
    if requested_ratio in allowed_ratios:
        return requested_ratio
    if preferred_ratio in allowed_ratios:
        return preferred_ratio
    requested_value = _parse_aspect_ratio(requested_ratio)
    if requested_value is None:
        return allowed_ratios[0]
    return min(
        allowed_ratios,
        key=lambda candidate: abs((_parse_aspect_ratio(candidate) or requested_value) - requested_value),
    )


def pick_closest_duration(allowed_durations: list[int], requested_duration: int | None) -> int | None:
    if not allowed_durations:
        return requested_duration
    if requested_duration in allowed_durations:
        return requested_duration
    if requested_duration is None:
        return min(allowed_durations)
    return min(allowed_durations, key=lambda candidate: (abs(candidate - requested_duration), candidate))
