from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(slots=True)
class ExecutionContract:
    kind: str = "free_web"
    requires_seed_template: bool = False
    requires_deck_framework: bool = False
    requires_media_contract: bool = False
    preflight_paths: list[str] = field(default_factory=list)
    prompt_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WritePolicy:
    kind: str = "none"
    protected_entry_paths: list[str] = field(default_factory=list)
    required_selectors: list[str] = field(default_factory=list)
    required_asset_refs: list[str] = field(default_factory=list)
    hard_block: bool = False


@dataclass(slots=True)
class ValidationProfile:
    kind: str = "html_dependency"
    required_selectors: list[str] = field(default_factory=list)
    required_asset_refs: list[str] = field(default_factory=list)
    side_files: list[str] = field(default_factory=list)
    checklist_path: str | None = None
    checklist_source_path: str | None = None
    hard_block: bool = False


@dataclass(slots=True)
class PublishProfile:
    kind: str = "html_bundle"
    skip_html_validation: bool = False


@dataclass(slots=True)
class RuntimeExecutionContract:
    active_entry: str | None = None
    artifact_work_root: str | None = None
    writable_roots: list[str] = field(default_factory=list)
    readonly_roots: list[str] = field(default_factory=list)
    validation_profile: str | None = None
    artifact_input_path: str | None = None
    artifact_input_example_path: str | None = None
    recovery_hints: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "active_entry": self.active_entry,
            "artifact_work_root": self.artifact_work_root,
            "writable_roots": list(self.writable_roots),
            "readonly_roots": list(self.readonly_roots),
            "validation_profile": self.validation_profile,
            "artifact_input_path": self.artifact_input_path,
            "artifact_input_example_path": self.artifact_input_example_path,
            "recovery_hints": dict(self.recovery_hints),
        }


@dataclass(slots=True)
class ProtocolFailure:
    failure_kind: str
    message: str
    expected_active_entry: str | None = None
    allowed_artifact_work_root: str | None = None
    suggested_next_tool: str | None = None
    suggested_action: str | None = None
    protocol_family: str | None = None
    recovery_hint_override: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            "failure_kind": self.failure_kind,
            "message": self.message,
            "expected_active_entry": self.expected_active_entry,
            "allowed_artifact_work_root": self.allowed_artifact_work_root,
            "suggested_next_tool": self.suggested_next_tool,
            "suggested_action": self.suggested_action,
            "protocol_family": self.protocol_family,
        }

    def recovery_hint(self) -> dict[str, Any]:
        if self.recovery_hint_override is not None:
            return dict(self.recovery_hint_override)
        constraints: list[str] = []
        if self.allowed_artifact_work_root:
            constraints.append(f"Keep deliverable writes inside the current artifact work directory: project/{self.allowed_artifact_work_root}/.")
        if self.expected_active_entry:
            constraints.append(f"Register and publish the manifest entry only after the deliverable is inside project/{self.allowed_artifact_work_root or self.expected_active_entry.split('/', 1)[0]}/.")
        preferred_tools: list[str] = []
        if self.suggested_next_tool:
            preferred_tools.append(self.suggested_next_tool)
        for tool in ("write_file", "edit_file", "exec_command", "register_artifact", "publish_output"):
            if tool not in preferred_tools:
                preferred_tools.append(tool)
        return {
            "instruction": self.suggested_action or self.message,
            "constraints": constraints,
            "preferred_tools": preferred_tools,
        }


@dataclass(slots=True)
class SkillProtocol:
    provider: str
    family: str
    mode: str | None = None
    surface: str | None = None
    execution_contract: ExecutionContract = field(default_factory=ExecutionContract)
    write_policy: WritePolicy = field(default_factory=WritePolicy)
    validation_profile: ValidationProfile = field(default_factory=ValidationProfile)
    publish_profile: PublishProfile = field(default_factory=PublishProfile)
    runtime_execution_contract: RuntimeExecutionContract | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProtocolRuntimeContext:
    artifact_mode: str | None = None
    project_kind: str | None = None
    prepared_workspace: Any | None = None
    workspace_runtime_session: dict[str, Any] | None = None
    work_dir: Path | None = None


@dataclass(slots=True)
class PreparedWorkspace:
    family: str
    artifact_work_root: str
    entry_file: str
    skill_id: str | None = None
    selected_template: str | None = None
    source_root: str | None = None
    strategy: str | None = None
    copied_files: list[str] = field(default_factory=list)
    copied_assets: list[str] = field(default_factory=list)
    fragment_roots: list[str] = field(default_factory=list)
    authoring_guides: list[str] = field(default_factory=list)

    @property
    def entry_path(self) -> str:
        return f"{self.artifact_work_root}/{self.entry_file}".replace("\\", "/").strip("/")

    def to_payload(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "strategy": self.strategy or self.family,
            "skill_id": self.skill_id,
            "artifact_work_root": self.artifact_work_root,
            "entry_file": self.entry_file,
            "entry_path": self.entry_path,
            "selected_template": self.selected_template,
            "source_root": self.source_root,
            "copied_files": list(self.copied_files),
            "copied_assets": list(self.copied_assets),
            "fragment_roots": list(self.fragment_roots),
            "authoring_guides": list(self.authoring_guides),
        }



def prepared_workspace_from_payload(raw: Any) -> PreparedWorkspace | None:
    if not isinstance(raw, dict):
        return None
    artifact_work_root = str(raw.get("artifact_work_root") or "").replace("\\", "/").strip().strip("/")
    entry_file = str(raw.get("entry_file") or "").replace("\\", "/").strip().strip("/")
    family = str(raw.get("family") or raw.get("strategy") or "").strip()
    if not artifact_work_root or not entry_file or not family:
        return None
    return PreparedWorkspace(
        family=family,
        strategy=str(raw.get("strategy") or family).strip() or family,
        skill_id=str(raw.get("skill_id") or "").strip() or None,
        artifact_work_root=artifact_work_root,
        entry_file=entry_file,
        selected_template=str(raw.get("selected_template") or "").strip() or None,
        source_root=str(raw.get("source_root") or "").replace("\\", "/").strip().strip("/") or None,
        copied_files=[
            str(item).replace("\\", "/").strip().strip("/")
            for item in list(raw.get("copied_files") or [])
            if str(item).strip()
        ],
        copied_assets=[
            str(item).replace("\\", "/").strip().strip("/")
            for item in list(raw.get("copied_assets") or [])
            if str(item).strip()
        ],
        fragment_roots=[
            str(item).replace("\\", "/").strip().strip("/")
            for item in list(raw.get("fragment_roots") or [])
            if str(item).strip()
        ],
        authoring_guides=[
            str(item).replace("\\", "/").strip().strip("/")
            for item in list(raw.get("authoring_guides") or [])
            if str(item).strip()
        ],
    )


@dataclass(slots=True)
class RuntimePrepareRequest:
    skill: Any
    conversation: dict[str, Any]
    latest_user_request: str
    work_dir: Path
    active_skill_dir: Path | None
    artifact_mode: str | None = None
    workspace_runtime_session: dict[str, Any] | None = None


@dataclass(slots=True)
class RuntimePrepareResult:
    family: str
    active_entry: str
    prepared_workspace: dict[str, Any]
    runtime_contract_patch: dict[str, Any] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)


class SkillProtocolAdapter(Protocol):
    provider: str

    def can_handle(self, skill: Any, runtime_context: ProtocolRuntimeContext) -> bool:
        ...

    def resolve(self, skill: Any, runtime_context: ProtocolRuntimeContext) -> SkillProtocol:
        ...

    def prepare_runtime(self, request: RuntimePrepareRequest) -> RuntimePrepareResult | None:
        ...
