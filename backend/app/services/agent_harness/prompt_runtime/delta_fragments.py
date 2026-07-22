from __future__ import annotations

from .models import PromptBlock, PromptMode, TurnSpec


def build_planning_delta(spec: TurnSpec) -> PromptBlock | None:
    if spec.mode != PromptMode.MAIN_TURN or not str(spec.planning_directive or "").strip():
        return None
    return PromptBlock(
        id="delta.planning",
        layer="delta",
        content="Planning gate:\n" + str(spec.planning_directive).strip(),
    )
