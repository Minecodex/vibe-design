from __future__ import annotations

from typing import Any

from app.services.agent_harness.authoring.prompt.sections import PromptSections
from app.services.agent_harness.workspace.conversation.home_turn_router import normalize_turn_route


class PlanGateController:
    PLAN_WORKFLOW_PHASES = {"planning", "planning_ready", "awaiting_plan_review", "revising_plan"}

    @staticmethod
    def _has_existing_plan(conversation: dict[str, Any]) -> bool:
        if isinstance(conversation.get("plan_state"), dict):
            return True
        outline_runtime = conversation.get("outline_runtime")
        if isinstance(outline_runtime, dict) and isinstance(outline_runtime.get("current_outline"), dict):
            return True
        return False

    @classmethod
    def requires_initial_plan(cls, conversation: dict[str, Any]) -> bool:
        runtime_profile = str(conversation.get("runtime_profile") or "").strip().lower()
        if runtime_profile == "canvas":
            return False
        turn_route = normalize_turn_route(conversation.get("turn_route"), conversation=conversation)
        if turn_route is not None:
            return bool(turn_route.get("requires_plan_gate"))
        current_phase = str(conversation.get("phase") or "").strip().lower()
        return cls._has_existing_plan(conversation) and current_phase in {"planning", "revising_plan"}

    @staticmethod
    def initial_phase(conversation: dict[str, Any]) -> str:
        runtime_profile = str(conversation.get("runtime_profile") or "").strip().lower()
        if runtime_profile == "canvas":
            return "executing"
        current_phase = str(conversation.get("phase") or "").strip().lower()
        has_plan = PlanGateController._has_existing_plan(conversation)
        turn_route = normalize_turn_route(conversation.get("turn_route"), conversation=conversation)
        if turn_route is not None:
            if bool(turn_route.get("requires_plan_gate")) and not has_plan:
                return "planning"
            if not bool(turn_route.get("requires_plan_gate")) and not has_plan:
                return "executing"
        if has_plan and current_phase in PlanGateController.PLAN_WORKFLOW_PHASES | {"executing"}:
            return current_phase
        if has_plan and not current_phase:
            return "planning_ready"
        return "executing"

    @staticmethod
    def directive(conversation: dict[str, Any], *, phase: str, skill_id: str | None) -> str:
        return PromptSections.plan_gate(
            phase=phase,
            language=str(conversation.get("language") or "zh"),
            has_skill=bool(skill_id),
            has_plan=isinstance(conversation.get("plan_state"), dict),
            execution_locked=str(conversation.get("phase") or "") == "executing",
        )

    @staticmethod
    def update_requires_approval(conversation: dict[str, Any], *, phase: str) -> bool:
        if (
            phase == "revising_plan"
            and bool(conversation.get("user_plan_repair_required"))
            and str(conversation.get("phase") or "") == "executing"
        ):
            return False
        if phase in {"planning", "revising_plan"}:
            return True
        if str(conversation.get("phase") or "") == "planning_ready":
            return True
        return str(conversation.get("phase") or "") != "executing"
