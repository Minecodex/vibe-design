"""Pydantic schemas for the Harness agent system.

Harness schemas for directory-based conversation storage.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Request Schemas ──────────────────────────────────────────────────


class CreateHarnessConversationRequest(BaseModel):
    mode: Literal["plan", "fast"] = "fast"
    skill_id: str | None = None
    skill_selection_mode: Literal["auto", "manual"] | None = None
    artifact_mode: str = "web"
    runtime_profile: Literal["home", "canvas"] = "home"
    project_id: int | None = None
    design_system_id: str | None = None
    web_search_enabled: bool = True
    model_preferences: dict | None = None


class HarnessBaseFileVersionRef(BaseModel):
    file_id: str
    version_id: str | None = None
    name: str | None = None


class SendHarnessMessageRequest(BaseModel):
    content: str
    input_kind: Literal["user_text_message", "user_ui_action"] = "user_text_message"
    action_type: str | None = None
    attachments: list[dict] | None = None
    references: list[dict[str, Any]] | None = None
    mode: Literal["plan", "fast"] | None = None
    skill_id: str | None = None
    skill_selection_mode: Literal["auto", "manual"] | None = None
    artifact_mode: str | None = None
    design_system_id: str | None = None
    skill_decision_reason: str | None = None
    skill_decision_confidence: float | None = None
    web_search_enabled: bool = False
    model_preferences: dict | None = None
    base_file_versions: list[HarnessBaseFileVersionRef] | None = None


class ResolveHarnessSelectionRequest(BaseModel):
    conversation_id: str | None = None
    artifact_mode: str = "web"
    prompt: str
    attachments: list[dict] | None = None
    current_skill_id: str | None = None
    resolve_skill: bool = True
    model_preferences: dict | None = None


class ResolvedHarnessSelectionItemRead(BaseModel):
    id: str | None = None
    confidence: float = 0.0
    reasoning_summary: str = ""
    should_replace_current: bool = False


class ResolveHarnessSelectionRead(BaseModel):
    skill: ResolvedHarnessSelectionItemRead | None = None


class RespondToHarnessAgentRequest(BaseModel):
    request_id: str
    answer: str
    answers: dict[str, Any] | None = None
    display_label: str | None = None
    approved: bool | None = None


class PlanRevisionRequest(BaseModel):
    instruction: str


class PlanItemWrite(BaseModel):
    id: str | None = None
    title: str
    summary: str | None = None
    order: int | None = None
    status: Literal["pending", "in_progress", "completed"] | None = None


class OutlineItemWrite(PlanItemWrite):
    progress_message: str | None = None
    artifact_ref: dict | None = None


class OutlineDraftWrite(BaseModel):
    artifact_type: str
    title: str
    summary: str
    items: list[OutlineItemWrite] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)


class PatchHarnessPlanRequest(BaseModel):
    plan: OutlineDraftWrite


class CleanupRequest(BaseModel):
    dry_run: bool = True


class OpenWorkspaceOfficeSessionRequest(BaseModel):
    file_path: str | None = None
    file_id: str | None = None
    version_id: str | None = None


class CloseWorkspaceOfficeSessionRequest(BaseModel):
    session_id: str


class AnalyzeElementRequest(BaseModel):
    image_url: str
    relative_x: float
    relative_y: float
    language: str | None = "zh"
    model_name: str | None = None
    provider_code: str | None = None


class AnalyzeElementResponse(BaseModel):
    labels: list[str]


class AgentUiConfigRead(BaseModel):
    hidden_tool_calls: list[str] = []
    canvas_default_skill_id: str
    canvas_explicit_skill_ids: list[str] = []


class RetryHarnessGenerationArtifactRequest(BaseModel):
    artifact_ref: str


# ── Response Schemas ─────────────────────────────────────────────────


class HarnessSkillRead(BaseModel):
    id: str
    name: str
    name_en: str
    name_zh: str | None = None
    description: str
    description_en: str | None = None
    description_zh: str | None = None
    icon: str
    color: str
    triggers: list[str] = Field(default_factory=list)
    mode: str = "other"
    surface: str | None = None
    platform: str | None = None
    scenario: str | None = None
    artifact_mode: str | None = None
    default_for: list[str] = Field(default_factory=list)
    featured: int | None = None
    preview_type: str = "html"
    preview_entry: str | None = None
    primary_output: str | None = None
    parameters: list[dict[str, Any]] = Field(default_factory=list)
    outputs_secondary: list[dict[str, Any] | str] = Field(default_factory=list)
    metadata_health: dict[str, Any] = Field(default_factory=dict)
    protocol_provider: str | None = None
    protocol_family: str | None = None
    protocol_metadata: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    example_prompt: str | None = None
    has_example_html: bool = False


class HarnessDesignSystemRead(BaseModel):
    id: str
    title: str
    description: str
    category: str | None = None
    sections: list[str] = Field(default_factory=list)
    palette: list[str] = Field(default_factory=list)
    preview: str | None = None
    featured: int | None = None
    is_default: bool = False
    import_mode: str | None = None
    health: dict[str, Any] | None = None


class HarnessDesignSystemDetailRead(HarnessDesignSystemRead):
    body: str = ""
    design_md: str = ""
    usage_md: str | None = None
    tokens_css: str | None = None
    components_manifest: str | None = None
    source_digest: str | None = None


class HarnessMessageRead(BaseModel):
    """Persisted harness message with optional rich render metadata."""
    id: str | int | None = None
    role: str
    content: str | None = None
    blocks: list[dict] | None = None
    attachments: list[dict] | None = None
    tool_calls: list[dict] | None = None
    metadata: dict | None = None
    created_at: str | None = None


class FailureRecoveryHintRead(BaseModel):
    instruction: str | None = None
    constraints: list[str] = Field(default_factory=list)
    preferred_tools: list[str] = Field(default_factory=list)
    avoid_tools: list[str] = Field(default_factory=list)
    ask_user_when: str | None = None
    context_patch: dict | None = None


class FailureRead(BaseModel):
    failure_kind: str | None = None
    failure_stage: str | None = None
    user_visible: bool = True
    summary: str | None = None
    root_cause_hint: str | None = None
    required_next_action: str | None = None
    recovery_hint: FailureRecoveryHintRead | None = None
    failure_signature: str | None = None
    retryable: bool | None = None


class InteractionOptionRead(BaseModel):
    label: str
    value: str
    description: str | None = None
    preview_url: str | None = None
    option_type: str | None = None
    is_custom_other: bool | None = None
    metadata: dict[str, Any] | None = None


class InteractionFieldRead(BaseModel):
    id: str
    label: str
    type: Literal["radio", "checkbox", "text", "textarea", "select", "cards"]
    required: bool = False
    placeholder: str | None = None
    default_value: Any | None = None
    max_selections: int | None = None
    allow_other: bool | None = None
    other_label: str | None = None
    other_placeholder: str | None = None
    options: list[InteractionOptionRead] = Field(default_factory=list)


class InteractionQuestionRead(BaseModel):
    id: str
    header: str
    question: str
    type: Literal["single", "multiple", "input"]
    required: bool = True
    max_selections: int | None = None
    options: list[InteractionOptionRead] = Field(default_factory=list)


class InteractionSchemaRead(BaseModel):
    title: str
    description: str | None = None
    submit_label: str | None = None
    # Non-ask_user interactions such as quick_brief and design_system_picker
    # still use fields. New ask_user pending interactions use questions only.
    fields: list[InteractionFieldRead] = Field(default_factory=list)
    questions: list[InteractionQuestionRead] = Field(default_factory=list)


class PendingInteractionRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    request_id: str
    question: str | None = None
    content: str | None = None
    kind: str | None = None
    schema_: InteractionSchemaRead | None = Field(default=None, alias="schema", serialization_alias="schema")
    answers: dict[str, Any] | None = None
    status: Literal["pending", "submitted"] = "pending"


class HarnessRuntimeSnapshotRead(BaseModel):
    conversation_id: str
    updated_at: str | None = None
    phase: str
    run_status: str
    current_item_id: str | None = None
    current_action: str | None = None
    activity: str | None = None
    item_progress: list[dict] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    failure: FailureRead | None = None
    runtime_status: str | None = None
    turn_status: str | None = None
    run_state: str | None = None
    run_id: str | None = None
    last_tool: str | None = None
    discovery_status: str | None = None
    discovery_started_at: str | None = None
    discovery_completed_at: str | None = None
    discovery_payload: dict[str, Any] | None = None
    discovery_schema: list[dict[str, Any]] | None = None
    prepared_workspace: dict[str, Any] | None = None
    workspace_runtime_session: dict[str, Any] | None = None
    runtime_contract: dict[str, Any] | None = None
    turn_route: dict[str, Any] | None = None
    user_interaction: PendingInteractionRead | None = None


class HarnessConversationRead(BaseModel):
    """Conversation metadata from directory-based conversation.json."""
    id: str
    title: str = ""
    runtime_profile: Literal["home", "canvas"] = "home"
    interaction_profile: Literal["home_blocking_preflight", "canvas_live_interaction"] = "home_blocking_preflight"
    project_id: int | None = None
    skill_id: str | None = None
    resolved_skill_id: str | None = None
    skill_resolution_source: str | None = None
    skill_selection_mode: Literal["auto", "manual"] = "auto"
    artifact_mode: str = "web"
    design_system_id: str | None = None
    last_skill_decision_reason: str | None = None
    last_skill_decision_confidence: float | None = None
    phase: Literal["skill_resolving", "discovery", "visual_lock", "planning", "planning_ready", "awaiting_plan_review", "revising_plan", "executing", "completed", "failed", "blocked"] = "executing"
    mode: str = "fast"
    web_search_enabled: bool = True
    model_preferences: dict | None = None
    protocol_version: int | None = None
    status: str = "active"
    runtime_status: str = "idle"
    display_status: str = "空闲"
    run_state: str = "idle"
    activity: str | None = None
    turn_route: dict[str, Any] | None = None
    stall_reason: str | None = None
    last_tool: str | None = None
    last_error_summary: str | None = None
    last_activity_at: str | None = None
    last_activity_source: str | None = None
    engine_version: str = "harness"
    run_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    planning_draft: dict | None = None
    plan_state: dict | None = None
    outline_runtime: dict | None = None
    user_plan: dict | None = None
    user_progress: dict | None = None
    runtime_state: HarnessRuntimeSnapshotRead | dict | None = None
    recovery_summary: dict | None = None
    created_at: str = ""
    updated_at: str = ""


class HarnessConversationListRead(BaseModel):
    """Paginated conversation list."""
    items: list[HarnessConversationRead]
    total: int
    page: int
    page_size: int
    has_more: bool


class HarnessConversationDetailRead(HarnessConversationRead):
    """Conversation detail snapshot for full UI restoration."""
    messages: list[HarnessMessageRead] = []
    messages_page: dict | None = None
    workspace_files: list["WorkspaceFileRead"] = []
    projection: dict | None = None
    event_stream: dict | None = None


class HarnessGenerationRetryRead(BaseModel):
    task_id: str
    artifact_ref: str
    auto_retry_count: int = 0
    auto_retry_max: int = 3
    manual_retry_count: int = 0
    status: str
    error_message: str | None = None
    canvas_item: dict[str, Any] | None = None
    result_url: str | None = None
    model_name: str | None = None
    model_label: str | None = None
    prompt: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    duration: int | str | None = None


class PlanItemRead(BaseModel):
    id: str
    title: str
    summary: str | None = None
    order: int
    artifact_ref: dict | None = None


class ExecutionStepRead(BaseModel):
    id: str
    type: str
    title: str
    description: str | None = None
    order: int
    status: str
    outline_item_ids: list[str] = Field(default_factory=list)
    progress_message: str | None = None


class OutlineRead(BaseModel):
    outline_id: str
    version: int
    artifact_type: str
    title: str
    summary: str
    status: str
    items: list[PlanItemRead] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)


class ExecutionPlanRead(BaseModel):
    execution_plan_id: str
    outline_id: str | None = None
    outline_version: int
    status: str
    current_item_id: str | None = None
    steps: list[ExecutionStepRead] = Field(default_factory=list)


class OutlineProjectionRead(BaseModel):
    outline_id: str | None = None
    outline_version: int | None = None
    plan_instance_id: str | None = None
    snapshot_status: str | None = None
    execution_plan_id: str | None = None
    status: str
    artifact_type: str
    title: str
    summary: str
    items: list[PlanItemRead] = Field(default_factory=list)
    current_item_id: str | None = None
    execution_steps: list[ExecutionStepRead] = Field(default_factory=list)
    readonly: bool = False


class CurrentPlanRead(BaseModel):
    artifact_type: str
    title: str
    summary: str
    status: str
    plan_instance_id: str | None = None
    snapshot_status: str | None = None
    progress_message: str | None = None
    items: list[PlanItemRead] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    style_notes: list[str] = Field(default_factory=list)


class PlanReviewStateRead(BaseModel):
    current_outline: OutlineRead | None = None
    execution_state: ExecutionPlanRead | None = None
    projection_state: OutlineProjectionRead | None = None
    revision_session: dict | None = None


class WorkspaceFileVersionRead(BaseModel):
    version_id: str
    label: str
    size: int
    sha256: str
    created_at: str
    created_by: str
    run_id: str | None = None
    parent_version_id: str | None = None
    parent_input_asset_ids: list[str] = Field(default_factory=list)
    referenced_asset_ids: list[str] = Field(default_factory=list)
    note: str | None = None
    artifact_metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceFileRead(BaseModel):
    file_id: str
    name: str
    path: str
    type: str
    size: int
    created_at: str
    updated_at: str | None = None
    current_version_id: str
    current_version_path: str | None = None
    artifact_kind: str | None = None
    artifact_metadata: dict[str, Any] = Field(default_factory=dict)
    versions: list[WorkspaceFileVersionRead] = Field(default_factory=list)
    source: str | None = None


class OfficePresentationSlide(BaseModel):
    title: str | None = None
    bullets: list[str] | None = None


class OfficePresentationSnapshot(BaseModel):
    kind: Literal["presentation"]
    slides: list[OfficePresentationSlide] | None = None
    warning: str | None = None


class WorkbookCellValue(BaseModel):
    v: str | int | float | bool | None = None
    t: str | None = None
    f: str | None = None
    styleId: str | None = None
    numFmt: str | None = None


class WorkbookMerge(BaseModel):
    startRow: int
    startCol: int
    endRow: int
    endCol: int


class WorkbookFreeze(BaseModel):
    rowSplit: int | None = None
    colSplit: int | None = None


class WorkbookSheet(BaseModel):
    id: str | None = None
    name: str
    rows: dict[str, dict] | None = None
    cols: dict[str, dict] | None = None
    cells: dict[str, WorkbookCellValue] | None = None
    merges: list[WorkbookMerge] | None = None
    freeze: WorkbookFreeze | None = None


class WorkbookPayload(BaseModel):
    kind: Literal["sheet"]
    sheets: list[WorkbookSheet]
    styles: dict[str, dict] | None = None


OfficeSessionSnapshot = Annotated[
    WorkbookPayload | OfficePresentationSnapshot,
    Field(discriminator="kind"),
]

class OpenWorkspaceOfficeSessionRead(BaseModel):
    session_id: str
    file_path: str
    file_kind: Literal["doc", "sheet", "presentation"]
    engine: Literal["html", "univer"] = "univer"
    unit_id: str | None = None
    snapshot: OfficeSessionSnapshot | None = None
    preview_file_path: str | None = None
    source_blob: str | None = None
    source_mime_type: str | None = None
    source_encoding: Literal["base64"] | None = None
    warnings: list[str] = []
    capabilities: dict | None = None
    readonly: bool = False


class CloseWorkspaceOfficeSessionRead(BaseModel):
    session_id: str
    closed: bool = True


class WorkspaceConversationStats(BaseModel):
    conversation_id: str
    size_bytes: int
    file_count: int


class WorkspaceStatsRead(BaseModel):
    user_id: int
    total_conversations: int
    total_size_bytes: int
    conversations: list[WorkspaceConversationStats] = []


class CleanupResultRead(BaseModel):
    orphan_dirs_removed: int = 0
    expired_dirs_removed: int = 0
    oversized_dirs_trimmed: int = 0
    bytes_freed: int = 0
    errors: list[str] = []
    dry_run: bool = True
