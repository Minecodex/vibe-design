from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.agent_harness.runtime.execution_support.interaction_controller import InteractionController
@dataclass(frozen=True, slots=True)
class ResumeInteractionDecision:
    model_message: str
    next_phase: str
    run_state: str
    pending_kind: str


class InteractionGate:
    @staticmethod
    def ask_user_pending(call_id: str, result_metadata: dict[str, Any] | None, output: str) -> dict[str, Any]:
        return InteractionController.ask_user_pending(call_id, result_metadata, output)

    @staticmethod
    def resume_after_interaction(
        *,
        conversation: dict[str, Any],
        answer: str,
        approved: bool | None,
    ) -> ResumeInteractionDecision:
        current_phase = str((conversation or {}).get("phase") or "").strip()
        runtime_state = conversation.get("runtime_state") if isinstance(conversation, dict) else None
        pending = (
            runtime_state.get("user_interaction")
            if isinstance(runtime_state, dict) and isinstance(runtime_state.get("user_interaction"), dict)
            else conversation.get("user_interaction")
            if isinstance(conversation, dict)
            else None
        )
        pending_kind = str((pending or {}).get("kind") or "")
        del approved
        next_phase = "executing"
        run_state = "executing"
        if pending_kind == "ask_user":
            if current_phase == "planning":
                next_phase = "planning"
                run_state = "planning"
            elif current_phase == "revising_plan":
                next_phase = "revising_plan"
                run_state = "revising"
        elif pending_kind in {"discovery_inputs_required", "quick_brief", "visual_direction_picker", "design_system_picker"}:
            next_phase = "planning"
            run_state = "planning"
        return ResumeInteractionDecision(
            model_message=answer,
            next_phase=next_phase,
            run_state=run_state,
            pending_kind=pending_kind,
        )

