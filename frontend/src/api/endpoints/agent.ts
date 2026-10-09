import { apiClient } from '../client'
import { normalizeAgentEvent, normalizeHarnessConversationDetailRead, type AgentEventWire } from '../agentWireNormalization'
import {
    extractApiErrorMessageFromText,
    isBillingInsufficientMessage,
    markApiErrorToastShown,
} from '../errorHandling'
import { toast } from 'sonner'
import { storage } from '@/utils/storage'
import i18n from '@/i18n'
import { getApiBaseUrl } from '@/config/runtimeConfig'
import {
    classifyHarnessWorkspacePath,
    isHarnessDirectAssetUrl,
    normalizeHarnessWorkspacePathByPolicy,
} from '@/utils/harnessWorkspacePathPolicy'
import type { MediaGenerationSettings } from '@/types/modelPreferences'
const OFFICE_OPEN_REQUEST_TIMEOUT_MS = 60000
const MARK_RECOGNITION_REQUEST_TIMEOUT_MS = 60000

// ── Types ──────────────────────────────────────────────────────

export interface AttachmentData {
    type: 'image' | 'file'
    url: string
    name?: string
    reference?: MediaReferenceData
    preview_url?: string
    _localFile?: File  // Transient: local file reference for deferred upload
    _previewObjectUrl?: string // Transient: pending composer thumbnail blob URL
    _clientAttachmentId?: string // Transient: stable pending composer id
}

export interface MediaReferenceData {
    id: string
    kind: 'upload_attachment' | 'canvas_item' | 'canvas_mark' | 'home_asset' | 'workspace_file'
    media_type: 'image'
    display_name?: string
    source:
        | {
            type: 'harness_input'
            path: string
        }
        | {
            type: 'home_asset'
            url: string
        }
        | {
            type: 'workspace_file'
            path: string
        }
        | {
            type: 'canvas_item'
            item_id: string
        }
        | {
            type: 'canvas_mark'
            mark_id: string
            image_item_id: string
        }
    mark?: {
        id: string
        image_item_id: string
        number: number
        label: string
        position: {
            x: number
            y: number
        }
    }
}

export interface ModelPreferencesPayload {
    image_model?: string
    image_provider?: string
    video_model?: string
    video_provider?: string
    multimodal_model?: string
    multimodal_provider?: string
    media_generation_settings?: MediaGenerationSettings
    auto?: boolean
}

export interface SendMessageRequest {
    content: string
    input_kind?: 'user_text_message' | 'user_ui_action'
    action_type?: string | null
    attachments?: AttachmentData[] | null
    references?: MediaReferenceData[] | null
    mode?: 'plan' | 'fast' | null
    skill_id?: string | null
    skill_selection_mode?: 'auto' | 'manual' | null
    artifact_mode?: string | null
    design_system_id?: string | null
    skill_decision_reason?: string | null
    skill_decision_confidence?: number | null
    web_search_enabled?: boolean
    model_preferences?: ModelPreferencesPayload | null
    base_file_versions?: Array<{
        file_id: string
        version_id?: string | null
        name?: string | null
    }> | null
}

export interface RespondToAgentRequest {
    request_id: string
    answer: string
    answers?: Record<string, unknown>
    display_label?: string
    approved?: boolean
}

// ── Harness Types ───────────────────────────────────────────────

export interface HarnessSkillRead {
    id: string
    name: string
    name_en: string
    name_zh?: string | null
    description: string
    description_en?: string | null
    description_zh?: string | null
    icon: string
    color: string
    triggers: string[]
    mode: string
    surface?: string | null
    platform?: string | null
    scenario?: string | null
    artifact_mode?: string | null
    default_for: string[]
    featured?: number | null
    preview_type: string
    preview_entry?: string | null
    primary_output?: string | null
    parameters?: Array<Record<string, unknown>>
    outputs_secondary?: Array<Record<string, unknown> | string>
    metadata_health?: Record<string, unknown>
    protocol_provider?: string | null
    protocol_family?: string | null
    protocol_metadata?: Record<string, unknown>
    capabilities?: Record<string, unknown>
    example_prompt?: string | null
    has_example_html?: boolean
}

export interface HarnessDesignSystemRead {
    id: string
    title: string
    description: string
    category?: string | null
    sections: string[]
    palette: string[]
    preview?: string | null
    featured?: number | null
    is_default: boolean
    import_mode?: string | null
    health?: Record<string, unknown> | null
}

export interface HarnessDesignSystemDetailRead extends HarnessDesignSystemRead {
    body: string
    design_md?: string
    usage_md?: string | null
    tokens_css?: string | null
    components_manifest?: string | null
    source_digest?: string | null
}

export interface HarnessMessageRead {
    id: string | null
    role: 'user' | 'assistant' | 'tool'
    content: string | null
    blocks?: Record<string, unknown>[] | null
    attachments?: Record<string, unknown>[] | null
    tool_calls?: Record<string, unknown>[] | null
    metadata?: Record<string, unknown> | null
    created_at: string | null
}

export interface FailureRecoveryHintRead {
    instruction?: string | null
    constraints?: string[]
    preferred_tools?: string[]
    avoid_tools?: string[]
    ask_user_when?: string | null
    context_patch?: Record<string, unknown> | null
}

export interface FailureRead {
    failure_kind?: string | null
    failure_stage?: string | null
    user_visible: boolean
    summary?: string | null
    root_cause_hint?: string | null
    required_next_action?: string | null
    recovery_hint?: FailureRecoveryHintRead | null
    failure_signature?: string | null
    retryable?: boolean | null
}

export interface InteractionOption {
    label: string
    value: string
    description?: string
    preview_url?: string
    metadata?: Record<string, unknown> | null
    option_type?: string | null
    is_custom_other?: boolean | null
}

export interface InteractionField {
    id: string
    label: string
    type: 'radio' | 'checkbox' | 'text' | 'textarea' | 'select' | 'cards'
    required?: boolean
    placeholder?: string | null
    default_value?: unknown
    max_selections?: number | null
    allow_other?: boolean | null
    other_label?: string | null
    other_placeholder?: string | null
    options?: InteractionOption[]
}

export interface InteractionQuestion {
    id: string
    header: string
    question: string
    type: 'single' | 'multiple' | 'input'
    required?: boolean
    max_selections?: number | null
    options?: InteractionOption[]
}

export interface InteractionSchema {
    title: string
    description?: string | null
    submit_label?: string | null
    fields?: InteractionField[]
    questions?: InteractionQuestion[]
}

export interface PendingInteraction {
    request_id: string
    question?: string
    content?: string | null
    kind?: string
    schema?: InteractionSchema | null
    answers?: Record<string, unknown> | null
    status?: 'pending' | 'submitted' | 'processing' | 'failed'
    [key: string]: unknown
}

export interface HarnessRuntimeStateRead {
    critique?: Record<string, unknown> | null
    conversation_id: string
    updated_at?: string | null
    phase: string
    run_status: string
    current_item_id?: string | null
    current_action?: string | null
    activity?: string | null
    item_progress?: Array<Record<string, unknown>>
    artifacts?: Array<Record<string, unknown>>
    artifact_manifest?: {
        version?: number
        kind?: string
        entry?: string
        title?: string
        renderer?: string
        exports?: string[]
        status?: string
        supporting_files?: string[]
        validation?: Record<string, unknown> | null
        publication?: Record<string, unknown> | null
        metadata?: Record<string, unknown> | null
    } | null
    failure?: FailureRead | null
    runtime_status?: string | null
    turn_status?: string | null
    run_state?: string | null
    run_id?: string | null
    last_tool?: string | null
    discovery_status?: string | null
    discovery_started_at?: string | null
    discovery_completed_at?: string | null
    discovery_payload?: Record<string, unknown> | null
    discovery_schema?: Array<Record<string, unknown>> | null
    prepared_workspace?: Record<string, unknown> | null
    workspace_runtime_session?: Record<string, unknown> | null
    runtime_contract?: Record<string, unknown> | null
    turn_route?: Record<string, unknown> | null
    user_interaction?: PendingInteraction | null
}

export interface HarnessConversationRead {
    id: string  // string ID (directory-based)
    title: string
    runtime_profile?: 'home' | 'canvas'
    interaction_profile?: 'home_blocking_preflight' | 'canvas_live_interaction'
    project_id?: number | null
    skill_id: string | null
    resolved_skill_id?: string | null
    skill_resolution_source?: string | null
    skill_selection_mode?: 'auto' | 'manual'
    artifact_mode?: string
    design_system_id?: string | null
    last_skill_decision_reason?: string | null
    last_skill_decision_confidence?: number | null
    phase: 'skill_resolving' | 'discovery' | 'visual_lock' | 'planning' | 'planning_ready' | 'awaiting_plan_review' | 'revising_plan' | 'executing' | 'completed' | 'failed' | 'blocked'
    mode: string
    web_search_enabled?: boolean
    model_preferences?: ModelPreferencesPayload | null
    protocol_version?: number | null
    status: string
    runtime_status: string
    display_status?: string | null
    run_state?: string
    activity?: string | null
    turn_route?: Record<string, unknown> | null
    stall_reason?: string | null
    last_tool?: string | null
    last_error_summary?: string | null
    last_activity_at?: string | null
    last_activity_source?: string | null
    engine_version: 'harness'
    run_id: string | null
    started_at: string | null
    finished_at: string | null
    plan_state?: Record<string, unknown> | null
    planning_draft?: PlanningDraftRead | null
    outline_runtime?: OutlineRuntimeRead | null
    user_plan?: UserPlanRead | null
    user_progress?: UserProgressRead | null
    runtime_state?: HarnessRuntimeStateRead | null
    // Pending interaction lives at the conversation top level; the nested
    // runtime_state copy is often absent, so consumers that need to detect a
    // pending form (e.g. the stream-reconnect gate) must read this field.
    user_interaction?: PendingInteraction | null
    recovery_summary?: Record<string, unknown> | null
    created_at: string
    updated_at: string
}

export interface HarnessConversationListRead {
    items: HarnessConversationRead[]
    total: number
    page: number
    page_size: number
    has_more: boolean
}

export interface HarnessConversationDetailRead extends HarnessConversationRead {
    messages: HarnessMessageRead[]
    messages_page?: {
        has_more?: boolean
        oldest_seq?: number | null
        limit?: number
    } | null
    workspace_files?: WorkspaceFileRead[]
    projection?: Record<string, unknown> | null
    event_stream?: Record<string, unknown> | null
}

export interface HarnessConversationMessagesPageRead {
    messages: HarnessMessageRead[]
    messages_page?: {
        has_more?: boolean
        oldest_seq?: number | null
        limit?: number
    } | null
}

export interface ResolvedHarnessSelectionItemRead {
    id?: string | null
    confidence: number
    reasoning_summary: string
    should_replace_current: boolean
}

export interface ResolveHarnessSelectionRead {
    skill?: ResolvedHarnessSelectionItemRead | null
}

export interface WorkspaceFileVersionRead {
    version_id: string
    label: string
    size: number
    sha256: string
    created_at: string
    created_by: string
    run_id?: string | null
    parent_version_id?: string | null
    parent_input_asset_ids?: string[]
    referenced_asset_ids?: string[]
    note?: string | null
    artifact_metadata?: Record<string, unknown>
}

export interface WorkspaceFileRead {
    file_id?: string
    name: string
    path: string
    type: string
    size: number
    created_at: string
    updated_at?: string | null
    current_version_id?: string
    current_version_path?: string | null
    artifact_kind?: string | null
    artifact_metadata?: Record<string, unknown> | null
    versions?: WorkspaceFileVersionRead[]
    source?: 'versioned_file' | 'input_asset' | 'reference_asset' | 'plan_asset' | string | null
}

export interface OfficePresentationSnapshot {
    kind: 'presentation'
    slides?: Array<{
        title?: string | null
        bullets?: string[] | null
    }> | null
    warning?: string | null
}

export interface WorkbookCellValue {
    v?: string | number | boolean | null
    t?: string | null
    f?: string | null
    styleId?: string | null
    numFmt?: string | null
}

export interface WorkbookMerge {
    startRow: number
    startCol: number
    endRow: number
    endCol: number
}

export interface WorkbookFreeze {
    rowSplit?: number | null
    colSplit?: number | null
}

export interface WorkbookSheet {
    id?: string | null
    name: string
    rows?: Record<string, Record<string, unknown>> | null
    cols?: Record<string, Record<string, unknown>> | null
    cells?: Record<string, WorkbookCellValue> | null
    merges?: WorkbookMerge[] | null
    freeze?: WorkbookFreeze | null
}

export interface WorkbookPayload {
    kind: 'sheet'
    sheets: WorkbookSheet[]
    styles?: Record<string, Record<string, unknown>> | null
}

export interface WorkbookSnapshotSheet {
    id: string
    name: string
    rows: Record<string, Record<string, unknown>>
    cols: Record<string, Record<string, unknown>>
    cells: Record<string, WorkbookCellValue>
    merges: WorkbookMerge[]
    freeze: WorkbookFreeze | null
}

export interface WorkbookSnapshotPayload {
    kind: 'sheet'
    sheetOrder: string[]
    activeSheetId: string
    sheets: Record<string, WorkbookSnapshotSheet>
    styles?: Record<string, Record<string, unknown>> | null
    warning?: string | null
}

export type OfficeSessionSnapshot =
    | WorkbookPayload
    | WorkbookSnapshotPayload
    | OfficePresentationSnapshot

export interface OpenWorkspaceOfficeSessionRequest {
    file_path?: string | null
    file_id?: string | null
    version_id?: string | null
}

export interface OpenWorkspaceOfficeSessionResponse {
    session_id: string
    file_path: string
    file_kind: 'doc' | 'sheet' | 'presentation'
    engine: 'html' | 'univer'
    unit_id?: string | null
    snapshot?: OfficeSessionSnapshot | null
    preview_file_path?: string | null
    source_blob?: string | null
    source_mime_type?: string | null
    source_encoding?: 'base64' | null
    warnings?: string[]
    capabilities?: Record<string, unknown> | null
    readonly?: boolean
}

export interface CloseWorkspaceOfficeSessionRequest {
    session_id: string
}

export interface CloseWorkspaceOfficeSessionResponse {
    session_id: string
    closed: boolean
}

export interface WorkspaceStats {
    user_id: number
    total_conversations: number
    total_size_bytes: number
    conversations: Array<{
        conversation_id: string
        size_bytes: number
        file_count: number
    }>
}

export interface CleanupResult {
    freed_bytes: number
    removed_conversations: number
    errors: string[]
    dry_run: boolean
}

export interface MessageRead {
    id: number
    role: 'user' | 'assistant' | 'tool'
    content: string | null
    attachments: Record<string, unknown>[] | null
    tool_calls: Record<string, unknown>[] | null
    metadata: Record<string, unknown> | null
    created_at: string
}

export interface PlanStepRead {
    id: number
    step_number: number
    description: string
    tool_name: string
    status: string
    started_at?: string | null
    last_activity_at?: string | null
    completed_at?: string | null
    elapsed_ms?: number | null
    result: Record<string, unknown> | null
    error_message: string | null
    generation_task_id: number | null
    created_at: string
}

export interface PlanRead {
    id: number
    plan_id?: string | null
    plan_name?: string | null
    summary: string
    status: string
    steps: PlanStepRead[]
    created_at: string
}

export interface UserPlanOutlineItemRead {
    id?: string | null
    title: string
    summary?: string | null
    description?: string | null
    order?: number | null
    file_path?: string | null
    file_name?: string | null
    artifact_ref?: Record<string, unknown> | null
}

export interface ExecutionStepRead {
    id: string
    type?: string | null
    title: string
    description?: string | null
    order?: number | null
    status: string
    outline_item_ids?: string[]
    progress_message?: string | null
}

export interface ExecutionPlanRead {
    execution_plan_id?: string | null
    outline_id?: string | null
    outline_version?: number | null
    status?: string | null
    current_item_id?: string | null
    steps?: ExecutionStepRead[]
}

export interface OutlineProjectionRead {
    outline_id?: string | null
    outline_version?: number | null
    plan_instance_id?: string | null
    snapshot_status?: string | null
    execution_plan_id?: string | null
    status?: string | null
    artifact_type?: string | null
    title?: string | null
    summary?: string | null
    items?: UserPlanOutlineItemRead[]
    current_item_id?: string | null
    execution_steps?: ExecutionStepRead[]
    readonly?: boolean
}

export interface UserPlanRead {
    artifact_type: string
    title: string
    summary: string
    status: string
    plan_instance_id?: string | null
    snapshot_status?: string | null
    progress_message?: string | null
    items?: UserPlanOutlineItemRead[] | null
    outline?: UserPlanOutlineItemRead[] | null
    constraints?: string[] | null
    style_notes?: string[] | null
    file_path?: string | null
    file_name?: string | null
    outline_id?: string | null
    version?: number | null
    readonly?: boolean
    outline_state?: Record<string, unknown> | null
    projection_state?: OutlineProjectionRead | null
    execution_state?: ExecutionPlanRead | null
}

export interface PlanningDraftRead {
    summary?: string | null
    confirmed_inputs?: Record<string, unknown>
    assumptions?: string[]
    draft_outline?: UserPlanOutlineItemRead[]
    open_questions?: string[]
    updated_at?: string | null
}

export interface OutlineRuntimeRead {
    current_outline?: UserPlanRead | null
    execution_state?: ExecutionPlanRead | null
    projection_state?: OutlineProjectionRead | null
    execution_run?: Record<string, unknown> | null
    last_revision?: Record<string, unknown> | null
}

export interface UserProgressRead {
    status: string
    message: string
    completed_message?: string | null
    artifact_label?: string | null
}

type PresentationEventType = `presentation.${string}`

type AgentRuntimeEventType =
    | 'artifact_plan_updated'
    | 'asset_added'
    | 'asset_registered'
    | 'asset_removed'
    | 'canvas_update'
    | 'critique.below_threshold'
    | 'critique.degraded'
    | 'critique.failed'
    | 'critique.protocol_rejected'
    | 'critique.round_completed'
    | 'critique.shipped'
    | 'critique.started'
    | 'current_outline_created'
    | 'current_outline_updated'
    | 'design_system_selected'
    | 'direction_selected'
    | 'discovery_completed'
    | 'discovery_started'
    | 'execution_plan_compiled'
    | 'execution_progress_updated'
    | 'execution_projection_updated'
    | 'execution_started'
    | 'execution_step_updated'
    | 'file_created'
    | 'file_current_version_changed'
    | 'file_published'
    | 'file_updated'
    | 'file_version_created'
    | 'generation_completed'
    | 'generation_failed'
    | 'generation_started'
    | 'item_completed'
    | 'item_started'
    | 'item_updated'
    | 'message_error'
    | 'outline_projection_updated'
    | 'plan'
    | 'plan_abandoned'
    | 'plan_revision_applied'
    | 'plan_revision_started'
    | 'planning_draft_updated'
    | 'prepared_workspace_updated'
    | 'protocol_error'
    | 'run_preparing'
    | 'run_started'
    | 'selection_resolved'
    | 'tool_completed'
    | 'tool_result'
    | 'tool_started'
    | 'turn_completed'
    | 'turn_started'
    | 'user_artifact_updated'
    | 'user_message'
    | 'user_progress_updated'
    | 'workspace_file_upserted'
    | 'workspace_runtime_session_updated'

export interface AgentEvent {
    type: AgentRuntimeEventType | PresentationEventType
    transient?: boolean
    payload?: Record<string, unknown>
    lane?: 'user' | 'internal'
    sequence?: number
    event_id?: number | string | null
    idempotency_key?: string | null
    run_id?: string | null
    data: Record<string, unknown>
}

export interface AgentUiConfigRead {
    hidden_tool_calls: string[]
    canvas_default_skill_id?: string
    canvas_explicit_skill_ids?: string[]
}

export function isHarnessWorkspaceRelativePath(filePath: string | null | undefined): boolean {
    return classifyHarnessWorkspacePath(filePath).workspaceRelative
}

export function normalizeHarnessWorkspacePath(filePath: string): string {
    return normalizeHarnessWorkspacePathByPolicy(filePath)
}

export {
    classifyHarnessWorkspacePath,
}

export function isHtmlWorkspaceFilePath(filePath: string | null | undefined): boolean {
    const normalized = normalizeHarnessWorkspacePath(String(filePath || ''))
    const extension = normalized.split('.').pop()?.toLowerCase() || ''
    return extension === 'html' || extension === 'htm'
}

export function resolveHarnessWorkspaceUrl(
    conversationId: string | number | null | undefined,
    filePath: string | null | undefined,
): string | undefined {
    const normalized = normalizeHarnessWorkspacePath(String(filePath || ''))
    if (!normalized) {
        return undefined
    }
    if (isHarnessDirectAssetUrl(normalized)) {
        return normalized
    }
    if (conversationId == null || conversationId === '') {
        return normalized
    }
    return agentApi.getWorkspaceFileUrl(String(conversationId), normalized)
}

// ── API Client ─────────────────────────────────────────────────

export const agentApi = {
    getUiConfig: () =>
        apiClient.get<AgentUiConfigRead>('/agent/harness/ui-config'),

    analyzeElement: (data: {
        image_url: string
        relative_x: number
        relative_y: number
        language?: string
        model_name?: string
        provider_code?: string
    }) =>
        apiClient.post<{ labels: string[] }>('/agent/harness/analyze-element', data, {
            timeout: MARK_RECOGNITION_REQUEST_TIMEOUT_MS,
        }),

    // ── Harness APIs (directory-based, string IDs) ─────────────

    listHarnessConversations: (
        page = 1,
        pageSize = 20,
        options?: {
            runtime_profile?: 'home' | 'canvas'
            project_id?: number | null
        },
    ) =>
        apiClient.get<HarnessConversationListRead>('/agent/harness/conversations', {
            params: {
                page,
                page_size: pageSize,
                runtime_profile: options?.runtime_profile,
                project_id: options?.project_id ?? undefined,
            },
        }),

    createHarnessConversation: (data: {
        mode?: string
        runtime_profile?: 'home' | 'canvas'
        project_id?: number | null
        skill_id?: string | null
        skill_selection_mode?: 'auto' | 'manual'
        artifact_mode?: string
        design_system_id?: string | null
        web_search_enabled?: boolean
        model_preferences?: ModelPreferencesPayload | null
    }) =>
        apiClient.post<HarnessConversationRead>('/agent/harness/conversations', data),

    resolveHarnessSelection: (data: {
        conversation_id?: string | null
        artifact_mode?: string
        prompt: string
        attachments?: AttachmentData[] | null
        current_skill_id?: string | null
        resolve_skill?: boolean
        model_preferences?: ModelPreferencesPayload | null
    }) =>
        apiClient.post<ResolveHarnessSelectionRead>('/agent/harness/resolve-selection', data),

    getHarnessConversation: async (id: string, signal?: AbortSignal) => {
        const response = await apiClient.get<HarnessConversationDetailRead>(`/agent/harness/conversations/${id}`, { signal })
        return {
            ...response,
            data: normalizeHarnessConversationDetailRead(response.data as HarnessConversationDetailRead),
        }
    },

    listHarnessConversationMessages: (id: string, beforeSeq?: number | null, limit = 80) =>
        apiClient.get<HarnessConversationMessagesPageRead>(`/agent/harness/conversations/${id}/messages`, {
            params: { before_seq: beforeSeq ?? undefined, limit },
        }),

    deleteHarnessConversation: (id: string) =>
        apiClient.delete(`/agent/harness/conversations/${id}`),

    cancelHarnessConversationRun: (id: string) =>
        apiClient.post<HarnessConversationDetailRead>(`/agent/harness/conversations/${id}/cancel`, {}),

    startHarnessPlanExecution: (conversationId: string) =>
        apiClient.post(`/agent/harness/conversations/${conversationId}/plan/start`, {}),

    reviseHarnessPlan: (conversationId: string, instruction: string) =>
        apiClient.post(`/agent/harness/conversations/${conversationId}/plan/revise`, { instruction }),

    patchHarnessPlan: async (conversationId: string, plan: UserPlanRead) => {
        const response = await apiClient.post<HarnessConversationDetailRead>(
            `/agent/harness/conversations/${conversationId}/plan/patch`,
            { plan },
        )
        return {
            ...response,
            data: normalizeHarnessConversationDetailRead(response.data as HarnessConversationDetailRead),
        }
    },

    listHarnessSkills: () =>
        apiClient.get<HarnessSkillRead[]>('/agent/harness/skills'),

    getHarnessSkillExampleHtml: (skillId: string) =>
        apiClient.get<string>(`/agent/harness/skills/${encodeURIComponent(skillId)}/example-html`, {
            responseType: 'text',
        }),

    listHarnessDesignSystems: () =>
        apiClient.get<HarnessDesignSystemRead[]>('/agent/harness/design-systems'),

    getHarnessDesignSystem: (designSystemId: string) =>
        apiClient.get<HarnessDesignSystemDetailRead>(`/agent/harness/design-systems/${encodeURIComponent(designSystemId)}`),

    getHarnessDesignSystemPreviewHtmlUrl: (designSystemId: string) =>
        `${getApiBaseUrl()}/agent/harness/design-systems/${encodeURIComponent(designSystemId)}/preview-html`,

    listWorkspaceFiles: (conversationId: string) =>
        apiClient.get<WorkspaceFileRead[]>(`/agent/harness/conversations/${conversationId}/files`),

    getWorkspaceFileUrl: (conversationId: string, filePath: string) =>
        `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(normalizeHarnessWorkspacePath(filePath))}`,

    getWorkspaceFileVersionUrl: (conversationId: string, fileId: string, versionId: string) =>
        `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(fileId)}/versions/${encodeURIComponent(versionId)}/download`,

    fetchWorkspaceFileBlob: async (conversationId: string, filePath: string) => {
        const response = await apiClient.get<Blob>(
            `/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(normalizeHarnessWorkspacePath(filePath))}`,
            { responseType: 'blob' },
        )
        return response.data
    },

    fetchWorkspaceFileVersionBlob: async (conversationId: string, fileId: string, versionId: string) => {
        const response = await apiClient.get<Blob>(
            `/agent/harness/conversations/${conversationId}/files/${encodeURIComponent(fileId)}/versions/${encodeURIComponent(versionId)}/download`,
            { responseType: 'blob' },
        )
        return response.data
    },

    openWorkspaceOfficeSession: (conversationId: string, data: OpenWorkspaceOfficeSessionRequest) =>
        apiClient.post<OpenWorkspaceOfficeSessionResponse>(
            `/agent/harness/conversations/${conversationId}/office/open`,
            data,
            { timeout: OFFICE_OPEN_REQUEST_TIMEOUT_MS },
        ),

    closeWorkspaceOfficeSession: (conversationId: string, data: CloseWorkspaceOfficeSessionRequest) =>
        apiClient.post<CloseWorkspaceOfficeSessionResponse>(
            `/agent/harness/conversations/${conversationId}/office/close`,
            data,
        ),

    getWorkspaceHtmlBundleUrl: (conversationId: string, filePath: string) =>
        `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/file-bundles/${encodeURIComponent(filePath)}`,

    fetchWorkspaceHtmlBundleBlob: async (conversationId: string, filePath: string) => {
        const response = await apiClient.get<Blob>(
            `/agent/harness/conversations/${conversationId}/file-bundles/${encodeURIComponent(filePath)}`,
            { responseType: 'blob' },
        )
        return response.data
    },

    createWorkspacePreviewToken: async (conversationId: string) => {
        const response = await apiClient.post<{
            preview_token: string
            expires_in_seconds: number
        }>(`/agent/harness/conversations/${conversationId}/preview-token`, {})
        return response.data
    },

    getWorkspaceHtmlPreviewUrl: (conversationId: string, filePath: string, previewToken: string) =>
        `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/preview-html/${encodeURIComponent(normalizeHarnessWorkspacePath(filePath))}?preview_token=${encodeURIComponent(previewToken)}`,

    getWorkspaceHtmlVersionPreviewUrl: (conversationId: string, fileId: string, versionId: string, previewToken: string) =>
        `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/preview-html-version/${encodeURIComponent(fileId)}/${encodeURIComponent(versionId)}?preview_token=${encodeURIComponent(previewToken)}`,

    getWorkspacePreviewFileUrl: (conversationId: string, filePath: string, previewToken: string, options?: { width?: number }) => {
        const width = Number(options?.width || 0)
        const widthParam = Number.isFinite(width) && width > 0 ? `&w=${encodeURIComponent(String(Math.round(width)))}` : ''
        return `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/preview-files/${encodeURIComponent(normalizeHarnessWorkspacePath(filePath))}?preview_token=${encodeURIComponent(previewToken)}${widthParam}`
    },

    getWorkspacePreviewFileVersionUrl: (conversationId: string, fileId: string, versionId: string, previewToken: string, fileName?: string) => {
        const downloadName = fileName ? `/${encodeURIComponent(fileName)}` : ''
        return `${getApiBaseUrl()}/agent/harness/conversations/${conversationId}/preview-file-version/${encodeURIComponent(fileId)}/${encodeURIComponent(versionId)}${downloadName}?preview_token=${encodeURIComponent(previewToken)}`
    },

    getWorkspaceStats: () =>
        apiClient.get<WorkspaceStats>('/agent/harness/workspace-stats'),

    cleanupWorkspaces: (dryRun = true) =>
        apiClient.post<CleanupResult>('/agent/harness/cleanup', { dry_run: dryRun }),

    uploadHarnessAttachment: (conversationId: string, file: File) => {
        const form = new FormData()
        form.append('file', file)
        return apiClient.post<{ url: string; filename: string; type: string; size: number; asset_id?: string }>(
            `/agent/harness/conversations/${conversationId}/upload`,
            form,
            { headers: { 'Content-Type': 'multipart/form-data' } },
        )
    },

    getHarnessGenerationTask: (conversationId: string, taskId: string | number) =>
        apiClient.get<{
            task_id: string | number
            artifact_ref?: string | null
            status: string
            progress?: number | null
            result_url: string | null
            result_urls?: string[] | null
            planned_result_url?: string | null
            artifact?: {
                absolute_path?: string | null
                relative_path?: string | null
                base_dir?: string | null
            } | null
            error_message: string | null
            model_name?: string | null
            model_label?: string | null
            resolution?: string | null
            duration?: string | number | null
            quality?: string | null
        }>(
            `/agent/harness/conversations/${conversationId}/generation-tasks/${taskId}`,
        ),

    getHarnessGenerationArtifactTask: (conversationId: string, artifactRef: string) =>
        apiClient.get<{
            task_id: string | number
            artifact_ref?: string | null
            status: string
            kind?: string | null
            progress?: number | null
            result_url: string | null
            result_urls?: string[] | null
            planned_result_url?: string | null
            artifact?: {
                absolute_path?: string | null
                relative_path?: string | null
                base_dir?: string | null
            } | null
            error_message: string | null
            model_name?: string | null
            model_label?: string | null
            prompt?: string | null
            params?: Record<string, unknown> | null
            provider_code?: string | null
            resolution?: string | null
            duration?: string | number | null
            quality?: string | null
            canvas_item?: Record<string, unknown> | null
        }>(
            `/agent/harness/conversations/${conversationId}/generation-artifacts/${encodeURIComponent(artifactRef)}/task`,
        ),

    retryHarnessGenerationArtifact: (conversationId: string, artifactRef: string) =>
        apiClient.post<{
            task_id: string
            artifact_ref: string
            auto_retry_count: number
            auto_retry_max: number
            manual_retry_count: number
            status: string
            error_message: string | null
            canvas_item?: Record<string, unknown> | null
            result_url?: string | null
            model_name?: string | null
            model_label?: string | null
            prompt?: string | null
            aspect_ratio?: string | null
            resolution?: string | null
            duration?: string | number | null
        }>(
            `/agent/harness/conversations/${conversationId}/generation-artifacts/retry`,
            { artifact_ref: artifactRef },
        ),
}

// ── SSE Streaming ──────────────────────────────────────────────

function getAuthToken(): string {
    return storage.getToken() || ''
}

function getBaseUrl(): string {
    return getApiBaseUrl()
}

/**
 * POST-based SSE stream. Returns an async generator of AgentEvents.
 */
export async function* fetchSSE(
    path: string,
    body: object | null,
    signal?: AbortSignal,
    options?: { method?: 'GET' | 'POST' },
): AsyncGenerator<AgentEvent> {
    const url = `${getBaseUrl()}${path}`
    const token = getAuthToken()
    const method = options?.method || 'POST'

    let response = await fetch(url, {
        method,
        headers: {
            'Authorization': `Bearer ${token}`,
            'Accept-Language': i18n.language,
            ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
        },
        ...(method === 'POST' ? { body: JSON.stringify(body || {}) } : {}),
        signal,
    })

    if (response.status === 401) {
        // Try refresh token once
        try {
            const refreshToken = storage.getRefreshToken()
            if (refreshToken) {
                const refreshRes = await apiClient.post('/auth/refresh', { refresh_token: refreshToken })
                const newToken = refreshRes.data.access_token
                storage.setToken(newToken)
                storage.setRefreshToken(refreshRes.data.refresh_token)

                // Retry original request
                response = await fetch(url, {
                    method,
                    headers: {
                        'Authorization': `Bearer ${newToken}`,
                        'Accept-Language': i18n.language,
                        ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}),
                    },
                    ...(method === 'POST' ? { body: JSON.stringify(body || {}) } : {}),
                    signal,
                })
            }
        } catch (refreshErr) {
            console.error('SSE token refresh failed:', refreshErr)
            // If refresh fails, let the original 401 be handled below
        }
    }

    if (!response.ok) {
        const text = await response.text()
        const message = extractApiErrorMessageFromText(text, `SSE request failed: ${response.status}`)
        const error = new Error(message)
        Object.assign(error, { status: response.status })
        if (isBillingInsufficientMessage(message)) {
            toast.error(message)
            markApiErrorToastShown(error)
        }
        throw error
    }

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let completed = false

    try {
        while (true) {
            const { done, value } = await reader.read()
            if (done) {
                completed = true
                break
            }
            buffer += decoder.decode(value, { stream: true })

            const lines = buffer.split('\n\n')
            buffer = lines.pop() || ''

            for (const line of lines) {
                const trimmed = line.trim()
                if (trimmed.startsWith('data: ')) {
                    try {
                        yield normalizeAgentEvent(JSON.parse(trimmed.slice(6)) as AgentEventWire)
                    } catch {
                        // Skip malformed events
                    }
                }
            }
        }

        // Process remaining buffer
        if (buffer.trim().startsWith('data: ')) {
            try {
                yield normalizeAgentEvent(JSON.parse(buffer.trim().slice(6)) as AgentEventWire)
            } catch {
                // Ignore a malformed trailing SSE fragment, as for complete lines above.
            }
        }
    } finally {
        try {
            if (!completed && !signal?.aborted) {
                await reader.cancel()
            }
        } catch {
            // Ignore cancellation races.
        }
        reader.releaseLock?.()
    }
}

/**
 * Helper to stream a harness message send (string conversation ID).
 */
export function streamHarnessSendMessage(
    conversationId: string | number,
    data: SendMessageRequest,
    signal?: AbortSignal,
    afterSequence?: number,
) {
    return fetchSSE(`/agent/harness/conversations/${conversationId}/messages${buildAfterSequenceQuery(afterSequence)}`, data, signal)
}

/**
 * Helper to stream response to harness agent question (string conversation ID).
 */
export function streamHarnessRespondToAgent(
    conversationId: string | number,
    data: RespondToAgentRequest,
    signal?: AbortSignal,
    afterSequence?: number,
) {
    return fetchSSE(`/agent/harness/conversations/${conversationId}/respond${buildAfterSequenceQuery(afterSequence)}`, data, signal)
}

export function streamHarnessStartExecution(
    conversationId: string | number,
    signal?: AbortSignal,
    afterSequence?: number,
) {
    return fetchSSE(`/agent/harness/conversations/${conversationId}/plan/start${buildAfterSequenceQuery(afterSequence)}`, {}, signal)
}

export function streamHarnessRevisePlan(
    conversationId: string | number,
    instruction: string,
    signal?: AbortSignal,
    afterSequence?: number,
) {
    return fetchSSE(`/agent/harness/conversations/${conversationId}/plan/revise${buildAfterSequenceQuery(afterSequence)}`, { instruction }, signal)
}

export function streamHarnessConversationEvents(
    conversationId: string | number,
    afterSequenceOrSignal?: number | AbortSignal,
    signal?: AbortSignal,
): AsyncGenerator<AgentEvent>
export function streamHarnessConversationEvents(
    conversationId: string | number,
    afterSequenceOrSignal?: number | AbortSignal,
    signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
    const afterSequence = typeof afterSequenceOrSignal === 'number' ? afterSequenceOrSignal : undefined
    const resolvedSignal = (
        typeof AbortSignal !== 'undefined' && afterSequenceOrSignal instanceof AbortSignal
    ) ? afterSequenceOrSignal : signal
    const query = buildAfterSequenceQuery(afterSequence)
    return fetchSSE(
        `/agent/harness/conversations/${conversationId}/stream${query}`,
        null,
        resolvedSignal,
        { method: 'GET' },
    )
}

function buildAfterSequenceQuery(afterSequence: number | undefined): string {
    return typeof afterSequence === 'number' && Number.isFinite(afterSequence) && afterSequence > 0
        ? `?after_sequence=${afterSequence}`
        : ''
}
