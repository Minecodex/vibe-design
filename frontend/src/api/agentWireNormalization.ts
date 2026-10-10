import type { CompatibleWire } from './types/compatibleWire'
import type {
    AgentEvent, FailureRead, InteractionOption, PendingInteraction, InteractionField,
    InteractionQuestion, InteractionSchema, HarnessRuntimeStateRead, HarnessConversationDetailRead,
    ModelPreferencesPayload, PlanningDraftRead, OutlineRuntimeRead, UserPlanRead,
    UserProgressRead, HarnessMessageRead, WorkspaceFileRead,
} from './endpoints/agent'

export type AgentEventWire = CompatibleWire<AgentEvent> & {
    event_type?: string
    seq?: number | string
    id?: string | null
    timestamp?: string
    ts?: string
    payload?: Record<string, unknown>
}

export function normalizeAgentEvent(rawEvent: AgentEventWire): AgentEvent {
    const eventType = String(rawEvent.type || rawEvent.event_type || '')
    const sequence = Number(rawEvent.sequence ?? rawEvent.seq)
    const lane = rawEvent.lane === 'internal' ? 'internal' : (rawEvent.lane === 'user' ? 'user' : undefined)
    const sourcePayload = rawEvent.data && typeof rawEvent.data === 'object'
        ? rawEvent.data
        : (rawEvent.payload && typeof rawEvent.payload === 'object' ? rawEvent.payload : {})
    const payload = { ...(sourcePayload as Record<string, unknown>) }
    const timestamp = rawEvent.timestamp ?? rawEvent.ts
    if (
        typeof timestamp === 'string'
        && timestamp.trim().length > 0
        && payload.created_at == null
        && payload.createdAt == null
    ) {
        payload.created_at = timestamp
    }

    return {
        type: eventType as AgentEvent['type'],
        lane,
        sequence: Number.isFinite(sequence) ? sequence : undefined,
        event_id: rawEvent.event_id ?? rawEvent.id ?? null,
        idempotency_key: rawEvent.idempotency_key ?? null,
        run_id: rawEvent.run_id ?? null,
        data: payload as AgentEvent['data'],
    }
}

export function normalizeFailureRead(raw: unknown): FailureRead | null {
    if (!raw || typeof raw !== 'object') {
        return null
    }
    const source = raw as CompatibleWire<FailureRead>
    return {
        failure_kind: source.failure_kind ?? source.failureKind ?? null,
        failure_stage: source.failure_stage ?? source.failureStage ?? null,
        user_visible: source.user_visible ?? source.userVisible ?? true,
        summary: source.summary ?? null,
        root_cause_hint: source.root_cause_hint ?? source.rootCauseHint ?? null,
        required_next_action: source.required_next_action ?? source.requiredNextAction ?? null,
        recovery_hint: source.recovery_hint ?? source.recoveryHint ?? null,
        failure_signature: source.failure_signature ?? source.failureSignature ?? null,
        retryable: typeof source.retryable === 'boolean' ? source.retryable : null,
    }
}

function normalizeInteractionOption(raw: unknown): InteractionOption | null {
    if (typeof raw === 'string') {
        const normalized = raw.trim()
        return normalized ? { label: normalized, value: normalized } : null
    }
    if (!raw || typeof raw !== 'object') {
        return null
    }
    const source = raw as CompatibleWire<InteractionOption>
    const label = String(source.label ?? source.value ?? '').trim()
    const value = String(source.value ?? source.label ?? '').trim()
    if (!label || !value) {
        return null
    }
    return {
        label,
        value,
        description: source.description ? String(source.description) : undefined,
        preview_url: source.preview_url ? String(source.preview_url) : undefined,
        metadata: source.metadata && typeof source.metadata === 'object' ? source.metadata as Record<string, unknown> : null,
        option_type: source.option_type ?? source.optionType ?? null,
        is_custom_other: source.is_custom_other ?? source.isCustomOther ?? null,
    }
}

export function normalizePendingInteraction(raw: unknown): PendingInteraction | null {
    if (!raw || typeof raw !== 'object') {
        return null
    }
    const source = raw as CompatibleWire<PendingInteraction>
    return {
        ...source,
        request_id: String(source.request_id ?? source.tool_call_id ?? ''),
        question: typeof source.question === 'string' ? source.question : undefined,
        content: typeof source.content === 'string' ? source.content : null,
        kind: source.kind ? String(source.kind) : undefined,
        schema: normalizeInteractionSchema(source.schema),
        answers: source.answers && typeof source.answers === 'object' ? source.answers as Record<string, unknown> : null,
        status: String(source.status || 'pending') === 'submitted' ? 'submitted' : 'pending',
    }
}

function normalizeInteractionField(raw: unknown): InteractionField | null {
    if (!raw || typeof raw !== 'object') {
        return null
    }
    const source = raw as CompatibleWire<InteractionField>
    const id = String(source.id ?? '').trim()
    const label = String(source.label ?? '').trim()
    const type = String(source.type ?? '').trim() as InteractionField['type']
    if (!id || !label || !type) {
        return null
    }
    return {
        id,
        label,
        type,
        required: source.required === true,
        placeholder: source.placeholder ? String(source.placeholder) : null,
        default_value: source.default_value ?? source.defaultValue,
        max_selections: typeof source.max_selections === 'number' ? source.max_selections : (typeof source.maxSelections === 'number' ? source.maxSelections : null),
        allow_other: source.allow_other === true || source.allowOther === true,
        other_label: source.other_label ? String(source.other_label) : (source.otherLabel ? String(source.otherLabel) : null),
        other_placeholder: source.other_placeholder ? String(source.other_placeholder) : (source.otherPlaceholder ? String(source.otherPlaceholder) : null),
        options: Array.isArray(source.options)
            ? source.options.map(normalizeInteractionOption).filter((option): option is InteractionOption => !!option)
            : [],
    }
}

function normalizeInteractionQuestion(raw: unknown): InteractionQuestion | null {
    if (!raw || typeof raw !== 'object') {
        return null
    }
    const source = raw as CompatibleWire<InteractionQuestion>
    const id = String(source.id ?? '').trim()
    const header = String(source.header ?? '').trim()
    const question = String(source.question ?? '').trim()
    const type = String(source.type ?? '').trim() as InteractionQuestion['type']
    if (!id || !header || !question || (type !== 'single' && type !== 'multiple' && type !== 'input')) {
        return null
    }
    return {
        id,
        header,
        question,
        type,
        max_selections: typeof source.max_selections === 'number' ? source.max_selections : (typeof source.maxSelections === 'number' ? source.maxSelections : null),
        options: Array.isArray(source.options)
            ? source.options.map(normalizeInteractionOption).filter((option): option is InteractionOption => !!option)
            : [],
    }
}

export function normalizeInteractionSchema(raw: unknown): InteractionSchema | null {
    if (!raw || typeof raw !== 'object') {
        return null
    }
    const source = raw as CompatibleWire<InteractionSchema>
    const title = String(source.title ?? '').trim()
    if (!title) {
        return null
    }
    return {
        title,
        description: source.description ? String(source.description) : null,
        submit_label: source.submit_label ? String(source.submit_label) : (source.submitLabel ? String(source.submitLabel) : null),
        fields: Array.isArray(source.fields)
            ? source.fields.map(normalizeInteractionField).filter((field): field is InteractionField => !!field)
            : [],
        questions: Array.isArray(source.questions)
            ? source.questions.map(normalizeInteractionQuestion).filter((question): question is InteractionQuestion => !!question)
            : [],
    }
}

function normalizeRuntimeState(raw: unknown): HarnessRuntimeStateRead | null {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
        return null
    }
    const source = raw as CompatibleWire<HarnessRuntimeStateRead>
    const conversationId = String(source.conversation_id ?? source.conversationId ?? '').trim()
    const phase = String(source.phase ?? '').trim()
    const runStatus = String(source.run_status ?? source.runStatus ?? '').trim()
    if (!conversationId || !phase || !runStatus) {
        return null
    }
    return {
        conversation_id: conversationId,
        updated_at: source.updated_at ?? source.updatedAt ?? null,
        phase,
        run_status: runStatus,
        current_item_id: source.current_item_id ?? source.currentItemId ?? null,
        current_action: source.current_action ?? source.currentAction ?? null,
        item_progress: Array.isArray(source.item_progress ?? source.itemProgress)
            ? (source.item_progress ?? source.itemProgress) as Array<Record<string, unknown>>
            : [],
        artifacts: Array.isArray(source.artifacts) ? source.artifacts as Array<Record<string, unknown>> : [],
        artifact_manifest: source.artifact_manifest ?? source.artifactManifest ?? null,
        failure: normalizeFailureRead(source.failure),
        runtime_status: source.runtime_status ?? source.runtimeStatus ?? null,
        turn_status: source.turn_status ?? source.turnStatus ?? null,
        run_state: source.run_state ?? source.runState ?? null,
        run_id: source.run_id ?? source.runId ?? null,
        last_tool: source.last_tool ?? source.lastTool ?? null,
        prepared_workspace: source.prepared_workspace ?? source.preparedWorkspace ?? null,
        workspace_runtime_session: source.workspace_runtime_session ?? source.workspaceRuntimeSession ?? null,
        runtime_contract: source.runtime_contract ?? source.runtimeContract ?? null,
        user_interaction: normalizePendingInteraction(source.user_interaction ?? source.userInteraction),
    }
}

export function normalizeHarnessConversationDetailRead(
    raw: HarnessConversationDetailRead | CompatibleWire<HarnessConversationDetailRead>,
): HarnessConversationDetailRead {
    const runtimeState = normalizeRuntimeState(raw.runtime_state)
    const runtimeContract = runtimeState?.runtime_contract
    const designSystemId = String(
        raw.design_system_id
        ?? (runtimeContract && typeof runtimeContract === 'object' ? runtimeContract.design_system_id : '')
        ?? '',
    ).trim() || null
    return {
        id: String(raw.id || ''),
        title: String(raw.title || ''),
        runtime_profile: raw.runtime_profile === 'canvas' ? 'canvas' : 'home',
        interaction_profile: raw.interaction_profile === 'canvas_live_interaction'
            ? 'canvas_live_interaction'
            : 'home_blocking_preflight',
        skill_id: raw.skill_id ?? null,
        resolved_skill_id: raw.resolved_skill_id ?? null,
        skill_resolution_source: raw.skill_resolution_source ?? null,
        skill_selection_mode: raw.skill_selection_mode === 'manual' ? 'manual' : 'auto',
        artifact_mode: String(raw.artifact_mode || 'web'),
        design_system_id: designSystemId,
        last_skill_decision_reason: raw.last_skill_decision_reason ?? null,
        last_skill_decision_confidence: raw.last_skill_decision_confidence ?? null,
        phase: raw.phase === 'skill_resolving'
            ? 'skill_resolving'
            : raw.phase === 'discovery'
                ? 'discovery'
                : raw.phase === 'visual_lock'
                    ? 'visual_lock'
                    : raw.phase === 'planning'
            ? 'planning'
            : raw.phase === 'planning_ready'
                ? 'planning_ready'
                : raw.phase === 'awaiting_plan_review'
                    ? 'awaiting_plan_review'
                : raw.phase === 'revising_plan'
                    ? 'revising_plan'
                    : raw.phase === 'completed'
                        ? 'completed'
                        : raw.phase === 'failed'
                            ? 'failed'
                            : raw.phase === 'blocked'
                                ? 'blocked'
                                : 'executing',
        mode: String(raw.mode || ''),
        web_search_enabled: raw.web_search_enabled ?? true,
        model_preferences: (raw.model_preferences ?? null) as ModelPreferencesPayload | null,
        protocol_version: typeof raw.protocol_version === 'number'
            ? raw.protocol_version as number
            : null,
        status: String(raw.status || ''),
        runtime_status: String(raw.runtime_status || ''),
        display_status: raw.display_status ?? null,
        run_state: raw.run_state ?? undefined,
        stall_reason: raw.stall_reason ?? null,
        last_tool: raw.last_tool ?? null,
        last_error_summary: raw.last_error_summary ?? null,
        last_activity_at: raw.last_activity_at ?? null,
        last_activity_source: raw.last_activity_source ?? null,
        engine_version: 'harness',
        run_id: raw.run_id ?? null,
        started_at: raw.started_at ?? null,
        finished_at: raw.finished_at ?? null,
        plan_state: (raw.plan_state as Record<string, unknown> | null | undefined) ?? null,
        planning_draft: (raw.planning_draft as PlanningDraftRead | null | undefined) ?? null,
        outline_runtime: (raw.outline_runtime as OutlineRuntimeRead | null | undefined) ?? null,
        user_plan: (raw.user_plan as UserPlanRead | null | undefined) ?? null,
        user_progress: (raw.user_progress as UserProgressRead | null | undefined) ?? null,
        runtime_state: runtimeState,
        // Preserve the top-level pending interaction (dropped otherwise). Prefer
        // the nested runtime_state copy when present, else fall back to the
        // top-level field the workflow actually persists.
        user_interaction: runtimeState?.user_interaction
            ?? normalizePendingInteraction(raw.user_interaction),
        recovery_summary: (raw.recovery_summary as Record<string, unknown> | null | undefined) ?? null,
        created_at: String(raw.created_at || ''),
        updated_at: String(raw.updated_at || ''),
        messages: Array.isArray(raw.messages)
            ? raw.messages
                .filter((message): message is HarnessMessageRead => !!message && typeof message === 'object')
                .map((message) => ({
                    ...message,
                    blocks: Array.isArray(message.blocks)
                        ? message.blocks as Record<string, unknown>[]
                        : undefined,
                }))
            : [],
        workspace_files: Array.isArray(raw.workspace_files)
            ? raw.workspace_files as WorkspaceFileRead[]
            : [],
        messages_page: raw.messages_page ?? null,
        projection: raw.projection ?? null,
        event_stream: raw.event_stream ?? null,
    } as HarnessConversationDetailRead
}

