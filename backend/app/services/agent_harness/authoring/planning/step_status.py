from __future__ import annotations

from copy import deepcopy
from typing import Any


TERMINAL_STEP_STATUS = "completed"
ACTIVE_STEP_STATUS = "in_progress"


def derive_active_step(steps: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    normalized_steps = [step for step in list(steps or []) if isinstance(step, dict)]
    active_steps = [step for step in normalized_steps if str(step.get("status") or "") == ACTIVE_STEP_STATUS]
    if len(active_steps) == 1:
        return active_steps[0]
    if active_steps:
        return None
    return next((step for step in normalized_steps if str(step.get("status") or "") != TERMINAL_STEP_STATUS), None)


def normalize_execution_step_statuses(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [deepcopy(step) for step in list(steps or []) if isinstance(step, dict)]
    active_count = sum(1 for step in normalized if str(step.get("status") or "") == ACTIVE_STEP_STATUS)
    if active_count != 0:
        return normalized
    first_unfinished = derive_active_step(normalized)
    if first_unfinished is None:
        return normalized
    first_id = str(first_unfinished.get("id") or "")
    for step in normalized:
        if str(step.get("id") or "") == first_id:
            step["status"] = ACTIVE_STEP_STATUS
            break
    return normalized
