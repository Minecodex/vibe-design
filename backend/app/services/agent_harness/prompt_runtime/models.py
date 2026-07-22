from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class PromptMode(str, Enum):
    MAIN_TURN = "main_turn"
    PLANNING_SCHEMA_GENERATION = "planning_schema_generation"
    SKILL_SELECTION = "skill_selection"
    DESIGN_SYSTEM_SELECTION = "design_system_selection"
    RECOVERY_TURN = "recovery_turn"
    PRE_FINAL_GATE = "pre_final_gate"
    FINAL_SUMMARY = "final_summary"
    SIDE_CLASSIFIER = "side_classifier"
    START_EXECUTION = "start_execution"
    PLAN_APPROVAL = "plan_approval"
    USER_PLAN_REPAIR = "user_plan_repair"
    PLAN_REVISION_REQUEST = "plan_revision_request"


class Phase(str, Enum):
    PLANNING = "planning"
    REVISING_PLAN = "revising_plan"
    EXECUTING = "executing"
    FINALIZING = "finalizing"
    RECOVERY = "recovery"


@dataclass(slots=True)
class PromptBlock:
    id: str
    layer: str
    content: str
    rule_family: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PromptFragment:
    id: str
    layer: str
    stability: str
    phase_scope: tuple[str, ...]
    modes: tuple[PromptMode, ...]
    rule_family: str | None
    renderer: Callable[[TurnSpec, PhasePolicyDecision], PromptBlock | None]


@dataclass(slots=True)
class PhasePolicyDecision:
    phase: str
    allowed_tools: list[str] = field(default_factory=list)
    blocked_capabilities: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)
    require_plan_sync: bool = False
    plan_sync_mode: str = "optional"
    require_publish_before_final: bool = False
    recovery_action: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class PreFinalGatePolicyDecision:
    action: str | None = None
    tick_reason: str | None = None
    internal_gate: str | None = None
    last_activity_source: str | None = None


@dataclass(slots=True)
class RecoveryStopActionDecision:
    action: str
    usage_log_status: str
    reason: str


@dataclass(slots=True)
class PromptAssemblyPlan:
    mode: PromptMode
    fragment_ids: list[str]


@dataclass(slots=True)
class TurnSpec:
    mode: PromptMode
    phase: Phase | str
    language: str = "zh"
    conversation: dict[str, Any] | None = None
    message_history: list[dict[str, Any]] = field(default_factory=list)
    extra_messages: list[dict[str, Any]] = field(default_factory=list)
    side_payload: dict[str, Any] | None = None
    base_instructions_override: str | None = None
    planning_directive: str | None = None
    skill: Any | None = None
    skill_id: str | None = None
    skill_prompt: str | None = None
    skill_runtime_dir: Path | None = None
    active_skill_manifest: dict[str, Any] | None = None
    artifact_mode: str | None = None
    mode_contract_text: str | None = None
    prepared_workspace: Any | None = None
    workspace_runtime_session: dict[str, Any] | None = None
    runtime_contract: dict[str, Any] | None = None
    manifest_summary: dict[str, Any] | list[Any] | None = None
    past_context_recall: str | None = None
    current_outline: dict[str, Any] | None = None
    tool_schemas: list[dict[str, Any]] | None = None
    web_search_call_count: int = 0
    recovery_decision: str | None = None
    recovery_review: dict[str, Any] | None = None
    recovery_hint: str | None = None
    builtin_provider: str | None = None

    @property
    def phase_value(self) -> str:
        return self.phase.value if isinstance(self.phase, Phase) else str(self.phase or Phase.EXECUTING.value)


@dataclass(slots=True)
class RenderedPromptBundle:
    mode: PromptMode
    phase: str
    system_blocks: list[PromptBlock] = field(default_factory=list)
    developer_blocks: list[PromptBlock] = field(default_factory=list)
    state_blocks: list[PromptBlock] = field(default_factory=list)
    delta_blocks: list[PromptBlock] = field(default_factory=list)
    message_blocks: list[PromptBlock] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    token_estimate: int = 0
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def all_blocks(self) -> list[PromptBlock]:
        return [
            *self.system_blocks,
            *self.developer_blocks,
            *self.state_blocks,
            *self.delta_blocks,
        ]

    @property
    def rendered_system(self) -> str:
        return "\n\n".join(block.content for block in self.all_blocks if str(block.content or "").strip())

    @property
    def rendered_messages_json(self) -> str:
        return json.dumps(self.messages, ensure_ascii=False, separators=(",", ":"))


@dataclass(slots=True)
class PromptPartitions:
    stable_system_blocks: list[PromptBlock] = field(default_factory=list)
    context_snapshot_blocks: list[PromptBlock] = field(default_factory=list)
    turn_append_blocks: list[PromptBlock] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    trace: dict[str, Any] = field(default_factory=dict)

    @property
    def stable_system_text(self) -> str:
        return "\n\n".join(
            block.content
            for block in self.stable_system_blocks
            if str(block.content or "").strip()
        )
