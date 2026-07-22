from __future__ import annotations

from .models import (
    Phase,
    PhasePolicyDecision,
    PreFinalGatePolicyDecision,
    PromptMode,
    RecoveryStopActionDecision,
    TurnSpec,
)


_MAX_PLAN_WEB_SEARCH_CALLS = 3

PLANNING_TOOL_NAMES = {
    "ask_user",
    "analyze_image",
    "fetch_webpage",
    "generate_image",
    "generate_video",
    "glob_files",
    "grep_files",
    "list_files",
    "read_file",
    "search_harness_history",
    "request_plan_approval",
    "update_planning_draft",
    "workspace_map",
    "web_search",
}

PLAN_REVISION_TOOL_NAMES = {
    "ask_user",
    "analyze_image",
    "fetch_webpage",
    "generate_image",
    "generate_video",
    "glob_files",
    "grep_files",
    "list_files",
    "read_file",
    "search_harness_history",
    "request_plan_approval",
    "update_planning_draft",
    "workspace_map",
    "web_search",
}

PLAN_REPAIR_TOOL_NAMES = {
    "analyze_image",
    "fetch_webpage",
    "generate_image",
    "generate_video",
    "glob_files",
    "grep_files",
    "list_files",
    "read_file",
    "search_harness_history",
    "request_plan_approval",
    "update_planning_draft",
    "web_search",
    "workspace_map",
}


class PolicyEngine:
    def resolve(self, spec: TurnSpec) -> PhasePolicyDecision:
        phase = spec.phase_value
        if phase == Phase.PLANNING.value:
            tools = sorted(PLANNING_TOOL_NAMES)
            if spec.web_search_call_count >= _MAX_PLAN_WEB_SEARCH_CALLS:
                tools = [tool for tool in tools if tool != "web_search"]
            return PhasePolicyDecision(
                phase=phase,
                allowed_tools=tools,
                required_outputs=["deliverable_plan"],
                require_plan_sync=False,
                plan_sync_mode="request_plan_approval_or_ask_user",
                notes=[
                    "Do not modify workspace files during planning; media generation is allowed when it helps validate direction or references.",
                    "Use update_planning_draft for non-approval planning notes, ask_user for unresolved user decisions, and request_plan_approval only when the plan is complete enough for execution approval.",
                    "During planning, call web_search at most 3 times; after that use fetch_webpage or proceed with known information.",
                ],
            )
        if phase == Phase.REVISING_PLAN.value:
            repair_required = bool((spec.conversation or {}).get("user_plan_repair_required"))
            allowed = PLAN_REPAIR_TOOL_NAMES if repair_required else PLAN_REVISION_TOOL_NAMES
            tools = sorted(allowed)
            if spec.web_search_call_count >= _MAX_PLAN_WEB_SEARCH_CALLS:
                tools = [tool for tool in tools if tool != "web_search"]
            return PhasePolicyDecision(
                phase=phase,
                allowed_tools=tools,
                required_outputs=["revised_plan"],
                require_plan_sync=False,
                plan_sync_mode="request_plan_approval_or_ask_user",
                notes=[
                    "Do not modify workspace files during plan revision; media generation is allowed when it helps validate direction or references.",
                    "Use update_planning_draft for revision drafts and request_plan_approval only when the revised plan is approval-ready.",
                    "During revising_plan, call web_search at most 3 times; after that use fetch_webpage or proceed with known information.",
                ],
            )
        if phase == Phase.FINALIZING.value:
            return PhasePolicyDecision(
                phase=phase,
                required_outputs=["final_response"],
                require_publish_before_final=bool((spec.conversation or {}).get("artifact_mode")),
                notes=[
                    "Do not restate global rules during finalization.",
                    "Only summarize the finished work and remaining verification gaps.",
                ],
            )
        if phase == Phase.RECOVERY.value:
            return PhasePolicyDecision(
                phase=phase,
                recovery_action=spec.recovery_decision,
                required_outputs=["recovery_step"],
                notes=[
                    "Use the smallest reliable recovery step.",
                    "Avoid repeating the same failing path.",
                ],
            )
        return PhasePolicyDecision(
            phase=phase,
            require_plan_sync=False,
            notes=[
                "Execute concrete work against the current plan and runtime state.",
                "Narrate as you work: the user sees only your text, not the tool calls. Before each batch of tool calls "
                "write one short line on what you are about to do, and a brief update when you find something key or "
                "change direction. This is separate from update_execution_progress, not a replacement.",
                "Autonomously author complete, professional first-draft content from the user's brief, the loaded skill "
                "(including worked examples), and the selected design system. Fill missing fields with high-quality, "
                "brand-appropriate content; never use lorem ipsum or generic placeholders.",
                "For missing-input collection, do not pause execution to ask the user for content you can reasonably "
                "infer or write yourself. Only ask for business-critical facts that cannot be invented and truly block "
                "delivery (e.g. real contact details or real URLs), and finish everything else you can generate first "
                "instead of stopping the turn.",
                "This does not override canvas or active-skill stage gates: when a stage result, proposal, brief, strategy, "
                "or direction choice needs user confirmation/approval before proceeding, first present the complete "
                "assistant text, then call ask_user for the decision.",
                "Use update_execution_progress only when user-visible execution state changes or major milestones complete.",
                "When a step starts, mark it in_progress; when it finishes, mark it completed.",
                "Normal assistant progress text does not update the plan card.",
                "Before the final reply, if the task is complete, synchronize completed steps with update_execution_progress.",
            ],
        )

    def resolve_pre_final_gate(
        self,
        *,
        tool_calls_present: bool,
        plan_gate_used: bool,
        plan_needs_sync: bool,
        artifact_manifest_action: str | None = None,
    ) -> PreFinalGatePolicyDecision:
        if tool_calls_present:
            return PreFinalGatePolicyDecision()
        if not plan_gate_used and plan_needs_sync:
            return PreFinalGatePolicyDecision(
                action="plan_sync",
                tick_reason="pre_final_plan_sync_gate",
                internal_gate="pre_final_plan_sync",
                last_activity_source="pre_final_plan_sync_gate",
            )
        if artifact_manifest_action:
            return PreFinalGatePolicyDecision(
                action="artifact_manifest",
                tick_reason="pre_final_artifact_manifest_gate",
                internal_gate="pre_final_artifact_manifest",
                last_activity_source="pre_final_artifact_manifest_gate",
            )
        return PreFinalGatePolicyDecision()

    def resolve_recovery_stop_action(
        self,
        *,
        phase: str,
        artifact_available: bool,
        revision_plan_updated: bool,
    ) -> RecoveryStopActionDecision:
        normalized_phase = str(phase or "").strip().lower()
        if artifact_available:
            return RecoveryStopActionDecision(
                action="finalize_after_artifact",
                usage_log_status="success",
                reason="artifact_available_after_no_progress_stop",
            )
        if normalized_phase == Phase.REVISING_PLAN.value and not revision_plan_updated:
            return RecoveryStopActionDecision(
                action="fail_plan_revision",
                usage_log_status="failed",
                reason="plan_revision_recovery_exhausted",
            )
        return RecoveryStopActionDecision(
            action="block",
            usage_log_status="blocked",
            reason="recovery_exhausted_without_artifact",
        )
