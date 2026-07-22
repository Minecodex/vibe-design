from __future__ import annotations

import json

from .base_fragments import build_base_instructions
from .delta_fragments import build_planning_delta
from .environment_fragments import (
    build_artifact_manifest_workflow,
    build_artifact_mode_contract,
    build_canvas_media_operation_contract,
    build_prepared_workspace_contract,
    build_runtime_capabilities,
    build_workspace_contract,
)
from .message_fragments import (
    build_design_system_request,
    build_discovery_request,
    build_failure_state,
    build_final_summary_message,
    build_plan_approval_message,
    build_plan_revision_request_message,
    build_pre_final_message,
    build_recovery_delta,
    build_runtime_time_payload,
    build_selection_request,
    build_side_classifier_request,
    build_start_execution_message,
    build_user_plan_repair_message,
)
from .models import (
    PhasePolicyDecision,
    PromptAssemblyPlan,
    PromptBlock,
    PromptFragment,
    PromptMode,
    PromptPartitions,
    RenderedPromptBundle,
    TurnSpec,
)
from .observability import build_trace, estimate_block_tokens, estimate_messages_tokens
from .policy_engine import PolicyEngine
from .state_fragments import (
    build_active_craft_references,
    build_active_design_system_body,
    build_active_design_system_components,
    build_active_design_system_pull_index,
    build_active_design_system_tokens,
    build_active_design_system_usage,
    build_active_skill_body,
    build_manifest_summary,
    build_past_context_recall,
    build_phase_policy,
    build_plan_state,
    build_workspace_runtime_state,
)
from .summary_providers import ProtocolSummaryProvider, SkillSummaryProvider


class PromptRuntime:
    _MAIN_TURN_STABLE_SYSTEM_IDS = frozenset(
        {
            "base.instructions",
            "environment.workspace_contract",
            "environment.runtime_capabilities",
            "environment.artifact_mode",
            "environment.canvas_media_operation",
            "environment.artifact_manifest_workflow",
        }
    )
    _MAIN_TURN_TURN_APPEND_IDS = frozenset({"delta.planning"})

    def __init__(self, *, policy_engine: PolicyEngine | None = None) -> None:
        self.policy_engine = policy_engine or PolicyEngine()
        self.skill_summary_provider = SkillSummaryProvider()
        self.protocol_summary_provider = ProtocolSummaryProvider()
        self._registry = self._build_registry()

    def build_bundle(self, spec: TurnSpec) -> RenderedPromptBundle:
        decision = self.policy_engine.resolve(spec)
        plan = self._assembly_plan(spec.mode)
        included_blocks: list[PromptBlock] = []
        omitted_fragments: list[dict[str, str]] = []

        for fragment_id in plan.fragment_ids:
            fragment = self._registry[fragment_id]
            self._validate_fragment(spec, fragment)
            block = fragment.renderer(spec, decision)
            if block is None or not str(block.content or "").strip():
                omitted_fragments.append({"id": fragment_id, "reason": "not_applicable"})
                continue
            block.metadata = {
                **(block.metadata if isinstance(block.metadata, dict) else {}),
                "fragment_stability": fragment.stability,
                "fragment_phase_scope": list(fragment.phase_scope),
                "fragment_modes": [mode.value for mode in fragment.modes],
            }
            included_blocks.append(block)

        message_blocks = [block for block in included_blocks if block.layer == "message"]
        messages = self._render_messages(spec, message_blocks)
        trace = build_trace(
            spec=spec,
            included_blocks=included_blocks,
            omitted_fragments=omitted_fragments,
            messages=messages,
        )
        system_blocks = [block for block in included_blocks if block.layer == "system"]
        developer_blocks = [block for block in included_blocks if block.layer == "developer"]
        state_blocks = [block for block in included_blocks if block.layer == "state"]
        delta_blocks = [block for block in included_blocks if block.layer == "delta"]
        message_blocks = [block for block in included_blocks if block.layer == "message"]
        token_estimate = sum(estimate_block_tokens(block) for block in included_blocks) + estimate_messages_tokens(messages)
        return RenderedPromptBundle(
            mode=spec.mode,
            phase=spec.phase_value,
            system_blocks=system_blocks,
            developer_blocks=developer_blocks,
            state_blocks=state_blocks,
            delta_blocks=delta_blocks,
            message_blocks=message_blocks,
            messages=messages,
            token_estimate=token_estimate,
            trace=trace,
        )

    def build_partitions(self, spec: TurnSpec) -> PromptPartitions:
        bundle = self.build_bundle(spec)
        if spec.mode != PromptMode.MAIN_TURN:
            return PromptPartitions(
                stable_system_blocks=[*bundle.system_blocks, *bundle.developer_blocks, *bundle.state_blocks, *bundle.delta_blocks],
                messages=bundle.messages,
                trace=bundle.trace,
            )

        blocks = [*bundle.system_blocks, *bundle.developer_blocks, *bundle.state_blocks, *bundle.delta_blocks]
        stable_system_blocks: list[PromptBlock] = []
        context_snapshot_blocks: list[PromptBlock] = []
        turn_append_blocks: list[PromptBlock] = []
        for block in blocks:
            if block.id in self._MAIN_TURN_STABLE_SYSTEM_IDS:
                stable_system_blocks.append(block)
            elif block.id in self._MAIN_TURN_TURN_APPEND_IDS:
                turn_append_blocks.append(block)
            else:
                context_snapshot_blocks.append(block)
        return PromptPartitions(
            stable_system_blocks=stable_system_blocks,
            context_snapshot_blocks=context_snapshot_blocks,
            turn_append_blocks=turn_append_blocks,
            messages=bundle.messages,
            trace=bundle.trace,
        )

    def _render_messages(self, spec: TurnSpec, message_blocks: list[PromptBlock]) -> list[dict]:
        if message_blocks:
            if spec.mode in {
                PromptMode.PLANNING_SCHEMA_GENERATION,
                PromptMode.SKILL_SELECTION,
                PromptMode.DESIGN_SYSTEM_SELECTION,
                PromptMode.SIDE_CLASSIFIER,
            }:
                payload: dict[str, object] = {}
                for block in message_blocks:
                    fragment = block.metadata.get("payload_fragment") if isinstance(block.metadata, dict) else None
                    if isinstance(fragment, dict):
                        payload.update(fragment)
                return [{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
            return [{"role": "user", "content": "\n\n".join(block.content for block in message_blocks if str(block.content or "").strip())}]
        if spec.side_payload is not None:
            return [{"role": "user", "content": json.dumps(spec.side_payload, ensure_ascii=False)}]
        return [*list(spec.message_history or []), *list(spec.extra_messages or [])]

    @staticmethod
    def _validate_fragment(spec: TurnSpec, fragment: PromptFragment) -> None:
        if spec.mode not in fragment.modes:
            raise ValueError(f"Fragment {fragment.id} does not support mode {spec.mode.value}")
        if fragment.phase_scope and spec.phase_value not in fragment.phase_scope:
            raise ValueError(f"Fragment {fragment.id} does not support phase {spec.phase_value}")

    def _assembly_plan(self, mode: PromptMode) -> PromptAssemblyPlan:
        if mode == PromptMode.MAIN_TURN:
            return PromptAssemblyPlan(
                mode=mode,
                fragment_ids=[
                    "base.instructions",
                    "environment.workspace_contract",
                    "environment.runtime_capabilities",
                    "environment.artifact_mode",
                    "environment.canvas_media_operation",
                    "state.active_design_system_usage",
                    "state.active_design_system_body",
                    "state.active_design_system_tokens",
                    "state.active_design_system_components",
                    "state.active_design_system_pull_index",
                    "state.active_craft_refs",
                    "state.active_skill_body",
                    "environment.artifact_manifest_workflow",
                    "summary.protocol",
                    "summary.skill",
                    "state.manifest_summary",
                    "state.past_context_recall",
                    "state.plan",
                    "environment.prepared_workspace",
                    "phase.policy",
                    "delta.planning",
                    # workspace_runtime is the most volatile cross-run block, so it
                    # sits last to keep the cacheable prefix as long as possible.
                    "state.workspace_runtime",
                ],
            )
        if mode == PromptMode.PLANNING_SCHEMA_GENERATION:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["base.instructions", "state.runtime_time_payload", "state.discovery_request"])
        if mode == PromptMode.SKILL_SELECTION:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["base.instructions", "state.runtime_time_payload", "state.selection_request"])
        if mode == PromptMode.DESIGN_SYSTEM_SELECTION:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["base.instructions", "state.runtime_time_payload", "state.design_system_request"])
        if mode == PromptMode.RECOVERY_TURN:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "state.failure_state", "delta.recovery"])
        if mode == PromptMode.PRE_FINAL_GATE:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "delta.pre_final"])
        if mode == PromptMode.FINAL_SUMMARY:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "delta.final_summary"])
        if mode == PromptMode.START_EXECUTION:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "delta.start_execution"])
        if mode == PromptMode.PLAN_APPROVAL:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "delta.plan_approval"])
        if mode == PromptMode.USER_PLAN_REPAIR:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "delta.user_plan_repair"])
        if mode == PromptMode.PLAN_REVISION_REQUEST:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["phase.policy", "delta.plan_revision_request"])
        if mode == PromptMode.SIDE_CLASSIFIER:
            return PromptAssemblyPlan(mode=mode, fragment_ids=["base.instructions", "state.side_classifier_request"])
        return PromptAssemblyPlan(
            mode=mode,
            fragment_ids=[
                "base.instructions",
            ],
        )

    def _build_registry(self) -> dict[str, PromptFragment]:
        return {
            "base.instructions": PromptFragment(
                id="base.instructions",
                layer="system",
                stability="stable",
                phase_scope=(),
                modes=tuple(PromptMode),
                rule_family="identity",
                renderer=lambda spec, _decision: build_base_instructions(spec),
            ),
            "environment.workspace_contract": PromptFragment(
                id="environment.workspace_contract",
                layer="system",
                stability="stable",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family="filesystem_runtime_publish",
                renderer=lambda spec, _decision: build_workspace_contract(spec),
            ),
            "environment.runtime_capabilities": PromptFragment(
                id="environment.runtime_capabilities",
                layer="system",
                stability="stable",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_runtime_capabilities(spec),
            ),
            "environment.artifact_mode": PromptFragment(
                id="environment.artifact_mode",
                layer="system",
                stability="semi_stable",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_artifact_mode_contract(spec),
            ),
            "environment.canvas_media_operation": PromptFragment(
                id="environment.canvas_media_operation",
                layer="system",
                stability="semi_stable",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family="canvas_media_operation",
                renderer=lambda spec, _decision: build_canvas_media_operation_contract(spec),
            ),
            "environment.prepared_workspace": PromptFragment(
                id="environment.prepared_workspace",
                layer="system",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_prepared_workspace_contract(spec),
            ),
            "environment.artifact_manifest_workflow": PromptFragment(
                id="environment.artifact_manifest_workflow",
                layer="state",
                stability="stable",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family="artifact_manifest_workflow",
                renderer=lambda spec, _decision: build_artifact_manifest_workflow(spec),
            ),
            "phase.policy": PromptFragment(
                id="phase.policy",
                layer="system",
                stability="dynamic",
                phase_scope=(),
                modes=(
                    PromptMode.MAIN_TURN,
                    PromptMode.RECOVERY_TURN,
                    PromptMode.PRE_FINAL_GATE,
                    PromptMode.FINAL_SUMMARY,
                    PromptMode.START_EXECUTION,
                    PromptMode.PLAN_APPROVAL,
                    PromptMode.USER_PLAN_REPAIR,
                    PromptMode.PLAN_REVISION_REQUEST,
                ),
                rule_family="phase_behavior",
                renderer=lambda spec, decision: build_phase_policy(spec, decision),
            ),
            "state.workspace_runtime": PromptFragment(
                id="state.workspace_runtime",
                layer="delta",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_workspace_runtime_state(spec),
            ),
            "state.plan": PromptFragment(
                id="state.plan",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_plan_state(spec),
            ),
            "state.manifest_summary": PromptFragment(
                id="state.manifest_summary",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_manifest_summary(spec),
            ),
            "state.past_context_recall": PromptFragment(
                id="state.past_context_recall",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_past_context_recall(spec),
            ),
            "state.active_skill_body": PromptFragment(
                id="state.active_skill_body",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_skill_body(spec),
            ),
            "state.active_craft_refs": PromptFragment(
                id="state.active_craft_refs",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_craft_references(spec),
            ),
            "state.active_design_system_usage": PromptFragment(
                id="state.active_design_system_usage",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_design_system_usage(spec),
            ),
            "state.active_design_system_body": PromptFragment(
                id="state.active_design_system_body",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_design_system_body(spec),
            ),
            "state.active_design_system_tokens": PromptFragment(
                id="state.active_design_system_tokens",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_design_system_tokens(spec),
            ),
            "state.active_design_system_components": PromptFragment(
                id="state.active_design_system_components",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_design_system_components(spec),
            ),
            "state.active_design_system_pull_index": PromptFragment(
                id="state.active_design_system_pull_index",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_active_design_system_pull_index(spec),
            ),
            "summary.protocol": PromptFragment(
                id="summary.protocol",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=self._render_protocol_summary,
            ),
            "summary.skill": PromptFragment(
                id="summary.skill",
                layer="state",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=self._render_skill_summary,
            ),
            "delta.planning": PromptFragment(
                id="delta.planning",
                layer="delta",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.MAIN_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_planning_delta(spec),
            ),
            "state.runtime_time_payload": PromptFragment(
                id="state.runtime_time_payload",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.PLANNING_SCHEMA_GENERATION, PromptMode.SKILL_SELECTION, PromptMode.DESIGN_SYSTEM_SELECTION),
                rule_family=None,
                renderer=lambda spec, _decision: build_runtime_time_payload(spec),
            ),
            "state.discovery_request": PromptFragment(
                id="state.discovery_request",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.PLANNING_SCHEMA_GENERATION,),
                rule_family=None,
                renderer=lambda spec, _decision: build_discovery_request(spec),
            ),
            "state.selection_request": PromptFragment(
                id="state.selection_request",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.SKILL_SELECTION,),
                rule_family=None,
                renderer=lambda spec, _decision: build_selection_request(spec),
            ),
            "state.design_system_request": PromptFragment(
                id="state.design_system_request",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.DESIGN_SYSTEM_SELECTION,),
                rule_family=None,
                renderer=lambda spec, _decision: build_design_system_request(spec),
            ),
            "state.side_classifier_request": PromptFragment(
                id="state.side_classifier_request",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.SIDE_CLASSIFIER,),
                rule_family=None,
                renderer=lambda spec, _decision: build_side_classifier_request(spec),
            ),
            "state.failure_state": PromptFragment(
                id="state.failure_state",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.RECOVERY_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_failure_state(spec),
            ),
            "delta.recovery": PromptFragment(
                id="delta.recovery",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.RECOVERY_TURN,),
                rule_family=None,
                renderer=lambda spec, _decision: build_recovery_delta(spec),
            ),
            "delta.pre_final": PromptFragment(
                id="delta.pre_final",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.PRE_FINAL_GATE,),
                rule_family=None,
                renderer=lambda spec, _decision: build_pre_final_message(spec),
            ),
            "delta.final_summary": PromptFragment(
                id="delta.final_summary",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.FINAL_SUMMARY,),
                rule_family=None,
                renderer=lambda spec, _decision: build_final_summary_message(spec),
            ),
            "delta.start_execution": PromptFragment(
                id="delta.start_execution",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.START_EXECUTION,),
                rule_family=None,
                renderer=lambda spec, _decision: build_start_execution_message(spec),
            ),
            "delta.plan_approval": PromptFragment(
                id="delta.plan_approval",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.PLAN_APPROVAL,),
                rule_family=None,
                renderer=lambda spec, _decision: build_plan_approval_message(spec),
            ),
            "delta.user_plan_repair": PromptFragment(
                id="delta.user_plan_repair",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.USER_PLAN_REPAIR,),
                rule_family=None,
                renderer=lambda spec, _decision: build_user_plan_repair_message(spec),
            ),
            "delta.plan_revision_request": PromptFragment(
                id="delta.plan_revision_request",
                layer="message",
                stability="dynamic",
                phase_scope=(),
                modes=(PromptMode.PLAN_REVISION_REQUEST,),
                rule_family=None,
                renderer=lambda spec, _decision: build_plan_revision_request_message(spec),
            ),
        }

    def _render_skill_summary(self, spec: TurnSpec, _decision: PhasePolicyDecision) -> PromptBlock | None:
        if spec.skill is None and not str(spec.skill_prompt or "").strip():
            return None
        content, metadata = self.skill_summary_provider.summarize(
            language=spec.language,
            phase=spec.phase_value,
            skill=spec.skill,
            skill_id=spec.skill_id,
            prompt_body=spec.skill_prompt,
            runtime_profile=(spec.conversation or {}).get("runtime_profile"),
            artifact_mode=spec.artifact_mode,
            prepared_workspace=spec.prepared_workspace,
            workspace_runtime_session=spec.workspace_runtime_session,
            runtime_skill_dir=spec.skill_runtime_dir,
            active_skill_manifest=spec.active_skill_manifest,
            runtime_contract=spec.runtime_contract,
        )
        return PromptBlock(
            id="summary.skill",
            layer="state",
            content=content,
            metadata=metadata,
        )

    def _render_protocol_summary(self, spec: TurnSpec, _decision: PhasePolicyDecision) -> PromptBlock | None:
        if spec.skill is None:
            return None
        content, metadata = self.protocol_summary_provider.summarize(
            language=spec.language,
            skill=spec.skill,
            artifact_mode=spec.artifact_mode,
            prepared_workspace=spec.prepared_workspace,
            workspace_runtime_session=spec.workspace_runtime_session,
        )
        if not str(content or "").strip():
            return None
        return PromptBlock(
            id="summary.protocol",
            layer="state",
            content=content,
            metadata=metadata,
        )
