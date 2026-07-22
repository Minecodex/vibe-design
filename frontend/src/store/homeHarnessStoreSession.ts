import {
    agentApi,
    type AgentEvent,
    type AgentUiConfigRead,
    type HarnessRuntimeStateRead,
    type WorkspaceFileRead,
    type HarnessConversationRead,
    type HarnessConversationDetailRead,
    type OutlineRuntimeRead,
    type PlanRead,
    type PlanningDraftRead,
    type UserPlanRead,
    type UserProgressRead,
    type PendingInteraction,
    type AttachmentData,
    type SendMessageRequest,
} from '@/api/endpoints/agent'
import type { MediaGenerationSettings } from '@/types/modelPreferences'
import {
    applyHomeHarnessEvent,
    createHomeHarnessProjectionState,
    finalizeHomeHarnessProjection,
    type HomeHarnessProjectionEvent,
    type HomeHarnessProjectionState,
} from './homeHarnessProjection'
import {
    camelizeBlockPayload as sharedCamelizeBlockPayload,
    extractMessageText as sharedExtractMessageText,
    filterHomepageBlocks as sharedFilterHomepageBlocks,
    normalizeBlocks as sharedNormalizeBlocks,
    reorderAnchoredSubagentMessages,
} from './homeHarnessProjectionBlocks'
import { resolveHarnessSnapshotEventSequence } from './harnessEventCursor'
import { resolveHarnessTerminalRunStatus } from './harnessTerminalEvents'
import { resolveHarnessPendingInteraction } from './harnessStreamLifecycle'
import {
    hydrateHomeHarnessCritique,
    type HomeHarnessCritiqueState,
} from './homeHarnessCritiqueProjection'
import { shouldReplayRenderOnlyMessageStandalone } from './harnessRenderOnlyMessages'

export {
    applyHomeHarnessEvent,
    finalizeHomeHarnessProjection,
    type HomeHarnessProjectionEvent,
    type HomeHarnessProjectionState,
}

export interface ChatMessage {
    id: number | string
    role: 'user' | 'assistant' | 'tool'
    content: string | null
    attachments?: Record<string, any>[]
    baseFileVersions?: NonNullable<SendMessageRequest['base_file_versions']>
    toolCalls?: ToolCallInfo[]
    blocks?: MessageBlock[]
    skillId?: string | null
    isHistoryLoaded?: boolean
    localOnly?: boolean
    createdAt: string
}

interface HarnessMessageLike {
    id?: string | number | null
    role: string
    content?: string | null
    attachments?: Record<string, any>[] | null
    metadata?: Record<string, any> | null
    created_at?: string | null
}

export interface MessageBlock {
    id: string
    kind: 'text' | 'tool' | 'interaction' | 'content'
    order: number
    status: string
    visible: boolean
    userVisible?: boolean
    debugOnly?: boolean
    uiKind: string
    payload: Record<string, any>
    renderKey?: string
    taskId?: string
    label?: string
    summary?: string
    expanded?: boolean
    children?: MessageBlock[]
    revision?: number
    sourceSequence?: number
}

export interface ToolCallInfo {
    callId: string
    name: string
    args: Record<string, any>
    result?: Record<string, any>
    error?: string
    status: 'pending' | 'running' | 'completed' | 'failed'
    /** Incremental streaming text for tools that support streaming (e.g., image analysis) */
    streamingText?: string
}

export interface ModelPreferences {
    image_model?: string
    image_provider?: string
    video_model?: string
    video_provider?: string
    multimodal_model?: string
    multimodal_provider?: string
    media_generation_settings?: MediaGenerationSettings
    auto?: boolean
}

export interface ChatUiConfig {
    hiddenToolCalls: string[]
}

export interface ConversationSessionState {
    messages: ChatMessage[]
    activePlan: PlanRead | null
    planningDraft?: PlanningDraftRead | null
    activeUserPlan: UserPlanRead | null
    outlineRuntime?: OutlineRuntimeRead | null
    userProgress: UserProgressRead | null
    userInteraction: PendingInteraction | null
    isStreaming: boolean
    currentStreamText: string
    currentToolCalls: ToolCallInfo[]
    streamingBlocks: MessageBlock[]
    workspaceFiles: WorkspaceFileRead[]
    runtimeState: HarnessRuntimeStateRead | null
    critique?: HomeHarnessCritiqueState | null
    abortController: AbortController | null
    eventStreamController: AbortController | null
    lastSequence: number
    appliedPresentationOps?: string[]
    appliedRuntimeEvents?: string[]
    messagesPage?: {
        hasMore: boolean
        oldestSeq: number | null
        loading: boolean
    }
    runStatus: 'idle' | 'running' | 'waiting_input' | 'completed' | 'failed' | 'blocked' | 'cancelled'
}

export function preserveLocalAssistantMessages(
    existingMessages: ChatMessage[],
    incomingMessages: ChatMessage[],
): ChatMessage[] {
    const localOnlyMessages = existingMessages.filter((message) => (
        message.role === 'assistant' && message.localOnly === true
    ))
    if (localOnlyMessages.length === 0) {
        return incomingMessages
    }

    const preservedIds = new Set(incomingMessages.map((message) => String(message.id)))
    const missingLocalMessages = localOnlyMessages.filter((message) => {
        if (preservedIds.has(String(message.id))) {
            return false
        }
        const content = String(message.content || '').trim()
        if (!content) {
            return true
        }
        return !incomingMessages.some((incomingMessage) => (
            incomingMessage.role === 'assistant'
            && String(incomingMessage.content || '').trim() === content
        ))
    })
    if (missingLocalMessages.length === 0) {
        return incomingMessages
    }

    const lastUserIndex = incomingMessages.reduce((lastIndex, message, index) => (
        message.role === 'user' ? index : lastIndex
    ), -1)

    if (lastUserIndex < 0) {
        return [...missingLocalMessages, ...incomingMessages]
    }

    return [
        ...incomingMessages.slice(0, lastUserIndex + 1),
        ...missingLocalMessages,
        ...incomingMessages.slice(lastUserIndex + 1),
    ]
}

export interface ChatState {
    // Current conversation
    conversationId: number | string | null
    projectId: number | null
    viewerUserId: number | null
    messages: ChatMessage[]
    activePlan: PlanRead | null
    planningDraft?: PlanningDraftRead | null
    activeUserPlan: UserPlanRead | null
    outlineRuntime?: OutlineRuntimeRead | null
    runtimeState: HarnessRuntimeStateRead | null
    critique: HomeHarnessCritiqueState | null
    userProgress: UserProgressRead | null
    userInteraction: PendingInteraction | null
    isStreaming: boolean
    mode: 'plan' | 'fast'
    artifactMode: 'web' | 'document' | 'spreadsheet' | 'slides' | 'image' | 'video'
    interactionProfile: 'home_blocking_preflight' | 'canvas_live_interaction'
    activeSkillId: string | null
    skillSelectionMode: 'auto' | 'manual'
    selectedDesignSystemId: string | null
    skillDecisionReason: string | null
    skillDecisionConfidence: number | null
    decisionLoading: boolean
    webSearchEnabled: boolean
    modelPreferences: ModelPreferences
    uiConfig: ChatUiConfig

    // Streaming state
    currentStreamText: string
    currentToolCalls: ToolCallInfo[]
    streamingBlocks: MessageBlock[]
    runStatus: ConversationSessionState['runStatus']
    olderMessagesHasMore: boolean
    olderMessagesLoading: boolean

    // Conversation list
    conversations: HarnessConversationRead[]
    conversationsHasMore: boolean
    conversationsPage: number

    // Harness-specific state
    engineVersion: 'v2' | 'harness'
    workspaceFiles: WorkspaceFileRead[]

    // Abort controller for cancellation
    _abortController: AbortController | null
    conversationSessions: Record<string, ConversationSessionState>
}

export interface ChatActions {
    // Initialization
    setProjectId: (projectId: number) => void
    syncScope: (projectId: number, viewerUserId: number | null) => void
    loadUiConfig: () => Promise<void>

    // Conversation management
    loadConversations: (projectId: number) => Promise<void>
    loadConversation: (id: number | string) => Promise<void>

    // Message sending
    sendMessage: (
        content: string,
        attachments?: AttachmentData[],
        options?: {
            modelPreferences?: Partial<ModelPreferences>
            baseFileVersions?: SendMessageRequest['base_file_versions']
            actionType?: string | null
        },
    ) => Promise<void>
    stopStreaming: () => void

    // Interaction response
    respondToAgent: (
        requestId: string,
        answer: string,
        displayLabel?: string,
        approved?: boolean,
        answers?: Record<string, any> | null,
    ) => Promise<void>
    startExecution: () => Promise<void>
    revisePlan: (instruction: string) => Promise<void>
    patchCurrentOutline: (plan: UserPlanRead) => Promise<void>
    upsertWorkspaceFile: (conversationId: number | string, file: WorkspaceFileRead) => void

    // Mode/skill
    setMode: (mode: 'plan' | 'fast') => void
    setArtifactMode: (mode: ChatState['artifactMode']) => void
    activateSkill: (skillId: string | null) => void
    selectDesignSystem: (designSystemId: string | null) => void
    setWebSearchEnabled: (enabled: boolean) => void
    setModelPreferences: (prefs: Partial<ModelPreferences>) => void

    // Harness
    createHarnessConversation: (
        skillId?: string | null,
        options?: {
            modelPreferences?: Partial<ModelPreferences>
            artifactMode?: ChatState['artifactMode']
            designSystemId?: string | null
        },
    ) => Promise<void>
    ensureHarnessConversation: (
        skillId?: string | null,
        options?: {
            modelPreferences?: Partial<ModelPreferences>
            artifactMode?: ChatState['artifactMode']
            designSystemId?: string | null
        },
    ) => Promise<string | null>
    loadOlderMessages: () => Promise<void>
    loadMoreConversations: () => Promise<void>

    // Reset
    newChat: () => void
    reset: () => void

    // Canvas item handler (set by CanvasPage)
    onCanvasUpdate: ((action: string, item: Record<string, any>) => void) | null
    setOnCanvasUpdate: (handler: ((action: string, item: Record<string, any>) => void) | null) => void

    // Task & Tool update
    updateToolCall: (messageId: string | number, callId: string, updates: Partial<ToolCallInfo>) => void
}

// ── Store ──────────────────────────────────────────────────────

export const initialState: ChatState = {
    conversationId: null,
    projectId: null,
    viewerUserId: null,
    messages: [],
    activePlan: null,
    planningDraft: null,
    activeUserPlan: null,
    outlineRuntime: null,
    runtimeState: null,
    critique: null,
    userProgress: null,
    userInteraction: null,
    isStreaming: false,
    mode: 'fast',
    artifactMode: 'web',
    interactionProfile: 'home_blocking_preflight',
    activeSkillId: null,
    skillSelectionMode: 'auto',
    selectedDesignSystemId: null,
    skillDecisionReason: null,
    skillDecisionConfidence: null,
    decisionLoading: false,
    currentStreamText: '',
    currentToolCalls: [],
    streamingBlocks: [],
    runStatus: 'idle',
    olderMessagesHasMore: false,
    olderMessagesLoading: false,
    conversations: [],
    conversationsHasMore: false,
    conversationsPage: 1,
    engineVersion: 'harness',
    workspaceFiles: [],
    webSearchEnabled: true,
    modelPreferences: {
        auto: false,
    },
    uiConfig: {
        hiddenToolCalls: [],
    },
    _abortController: null,
    conversationSessions: {},
}

const DEFAULT_CONVERSATION_TITLES = new Set([
    '',
    'New Chat',
    '新会话',
    'Untitled',
])
function normalizeToolName(name: string | null | undefined): string {
    return (name || '').replace(/^lc_/, '')
}

export function shouldReplaceConversationTitle(title: string | null | undefined): boolean {
    const normalizedTitle = String(title || '').trim()
    return DEFAULT_CONVERSATION_TITLES.has(normalizedTitle)
}

export function summarizeConversationTitle(content: string): string {
    return content.trim().replace(/\s+/g, ' ').slice(0, 80)
}

export function createEmptyConversationSession(): ConversationSessionState {
    return {
        messages: [],
        activePlan: null,
        planningDraft: null,
        activeUserPlan: null,
        outlineRuntime: null,
        userProgress: null,
        userInteraction: null,
        isStreaming: false,
        currentStreamText: '',
        currentToolCalls: [],
        streamingBlocks: [],
        workspaceFiles: [],
        runtimeState: null,
        critique: null,
        abortController: null,
        eventStreamController: null,
        lastSequence: 0,
        appliedPresentationOps: [],
        appliedRuntimeEvents: [],
        messagesPage: {
            hasMore: false,
            oldestSeq: null,
            loading: false,
        },
        runStatus: 'idle',
    }
}

export function getConversationSessionKey(conversationId: number | string): string {
    return String(conversationId)
}

export function defaultMessagesPage(): NonNullable<ConversationSessionState['messagesPage']> {
    return {
        hasMore: false,
        oldestSeq: null,
        loading: false,
    }
}

export function getMessagesPage(session: ConversationSessionState): NonNullable<ConversationSessionState['messagesPage']> {
    return session.messagesPage ?? defaultMessagesPage()
}

export function getConversationSession(
    state: ChatState,
    conversationId: number | string,
): ConversationSessionState {
    const existing = state.conversationSessions[getConversationSessionKey(conversationId)]
    if (existing) {
        return existing
    }
    if (state.conversationId === conversationId) {
        return {
            messages: state.messages,
            activePlan: state.activePlan,
            planningDraft: state.planningDraft,
            activeUserPlan: state.activeUserPlan,
            outlineRuntime: state.outlineRuntime ?? null,
            runtimeState: state.runtimeState,
            critique: state.critique,
            userProgress: state.userProgress,
            userInteraction: state.userInteraction,
            isStreaming: state.isStreaming,
            currentStreamText: state.currentStreamText,
            currentToolCalls: state.currentToolCalls,
            streamingBlocks: state.streamingBlocks,
            workspaceFiles: state.workspaceFiles,
            abortController: state._abortController,
            eventStreamController: null,
            lastSequence: 0,
            appliedPresentationOps: [],
            appliedRuntimeEvents: [],
            messagesPage: {
                hasMore: state.olderMessagesHasMore,
                oldestSeq: null,
                loading: state.olderMessagesLoading,
            },
            runStatus: state.runStatus,
        }
    }
    return createEmptyConversationSession()
}

export function buildActiveConversationFields(
    session: ConversationSessionState,
): Pick<ChatState, 'messages' | 'activePlan' | 'planningDraft' | 'activeUserPlan' | 'outlineRuntime' | 'runtimeState' | 'critique' | 'userProgress' | 'userInteraction' | 'isStreaming' | 'currentStreamText' | 'currentToolCalls' | 'streamingBlocks' | 'workspaceFiles' | '_abortController' | 'runStatus' | 'olderMessagesHasMore' | 'olderMessagesLoading'> {
    return {
        messages: session.messages,
        activePlan: session.activePlan,
        planningDraft: session.planningDraft,
        activeUserPlan: session.activeUserPlan,
        outlineRuntime: session.outlineRuntime ?? null,
        runtimeState: session.runtimeState,
        critique: session.critique ?? null,
        userProgress: session.userProgress,
        userInteraction: session.userInteraction,
        isStreaming: session.isStreaming,
        currentStreamText: session.currentStreamText,
        currentToolCalls: session.currentToolCalls,
        streamingBlocks: session.streamingBlocks,
        workspaceFiles: session.workspaceFiles,
        _abortController: session.abortController,
        runStatus: session.runStatus,
        olderMessagesHasMore: getMessagesPage(session).hasMore,
        olderMessagesLoading: getMessagesPage(session).loading,
    }
}

export function buildProjectionStateFromSession(
    session: ConversationSessionState,
): HomeHarnessProjectionState {
    return {
        messages: session.messages,
        activePlan: session.activePlan,
        planningDraft: session.planningDraft,
        activeUserPlan: session.activeUserPlan,
        outlineRuntime: session.outlineRuntime ?? null,
        runtimeState: session.runtimeState,
        critique: session.critique ?? null,
        userProgress: session.userProgress,
        userInteraction: session.userInteraction,
        isStreaming: session.isStreaming,
        currentStreamText: session.currentStreamText,
        currentToolCalls: session.currentToolCalls,
        streamingBlocks: session.streamingBlocks,
        workspaceFiles: session.workspaceFiles,
        lastSequence: session.lastSequence,
        runStatus: session.runStatus,
    }
}

export function applyProjectionStateToSession(
    session: ConversationSessionState,
    projection: HomeHarnessProjectionState,
): ConversationSessionState {
    // Note: abortController / eventStreamController are deliberately NOT
    // touched here. They belong to the network/transport layer, not the
    // projection. Letting the projection null abortController on terminal
    // events (e.g. turn_completed) caused sendMessage's for-await loop to
    // short-circuit via isActiveHarnessSend before draining the remaining
    // remaining durable events. Terminal cleanup of these handles
    // is done explicitly in finalizeStreamV2 / stopStreaming.
    return {
        ...session,
        messages: projection.messages,
        activePlan: projection.activePlan,
        planningDraft: projection.planningDraft,
        activeUserPlan: projection.activeUserPlan,
        outlineRuntime: projection.outlineRuntime ?? null,
        runtimeState: projection.runtimeState,
        critique: projection.critique ?? null,
        userProgress: projection.userProgress,
        userInteraction: projection.userInteraction,
        isStreaming: projection.isStreaming,
        currentStreamText: projection.currentStreamText,
        currentToolCalls: projection.currentToolCalls,
        streamingBlocks: projection.streamingBlocks,
        workspaceFiles: projection.workspaceFiles,
        lastSequence: projection.lastSequence,
        appliedPresentationOps: session.appliedPresentationOps,
        appliedRuntimeEvents: session.appliedRuntimeEvents,
        runStatus: projection.runStatus,
    }
}

export function applyConversationSessionUpdate(
    state: ChatState,
    conversationId: number | string,
    updater: (session: ConversationSessionState) => ConversationSessionState,
): Partial<ChatState> {
    const sessionKey = getConversationSessionKey(conversationId)
    const previousSession = getConversationSession(state, conversationId)
    const nextSession = updater(previousSession)
    const conversationSessions = {
        ...state.conversationSessions,
        [sessionKey]: {
            ...nextSession,
            messages: preserveLocalAssistantMessages(previousSession.messages, nextSession.messages),
        },
    }
    const resolvedSession = conversationSessions[sessionKey]
    return {
        conversationSessions,
        conversations: updateConversationMetaFromSession(state, conversationId, resolvedSession),
        ...(state.conversationId === conversationId
            ? buildActiveConversationFields(resolvedSession)
        : {}),
    }
}

export function upsertWorkspaceFileInSession(
    session: ConversationSessionState,
    file: WorkspaceFileRead,
): ConversationSessionState {
    const normalizedPath = String(file.path || '').trim()
    const normalizedFileId = String(file.file_id || normalizedPath || file.name || '').trim()
    const existingIndex = session.workspaceFiles.findIndex((entry) => (
        (normalizedPath && String(entry.path || '') === normalizedPath)
        || (normalizedFileId && String(entry.file_id || '') === normalizedFileId)
    ))
    const workspaceFiles = [...session.workspaceFiles]
    if (existingIndex >= 0) {
        workspaceFiles[existingIndex] = file
    } else {
        workspaceFiles.push(file)
    }
    return {
        ...session,
        workspaceFiles,
    }
}

export function normalizeHiddenToolCalls(config: AgentUiConfigRead): string[] {
    return Array.from(
        new Set(
            (config.hidden_tool_calls || [])
                .map(normalizeToolName)
                .filter(Boolean),
        ),
    )
}

export function resolveTerminalRunStatus(
    runStatus: ConversationSessionState['runStatus'],
): ConversationSessionState['runStatus'] {
    return resolveHarnessTerminalRunStatus(runStatus)
}

export function camelizeBlockPayload(value: unknown): unknown {
    return sharedCamelizeBlockPayload(value)
}

export function filterHomepageBlocks(blocks: MessageBlock[]): MessageBlock[] {
    return sharedFilterHomepageBlocks(blocks)
}

export function normalizeBlocks(rawBlocks: unknown): MessageBlock[] {
    return sharedNormalizeBlocks(rawBlocks)
}

export function extractMessageText(blocks: MessageBlock[]): string | null {
    return sharedExtractMessageText(blocks)
}

export function buildHarnessUiMessages(rawMessages: HarnessMessageLike[]): ChatMessage[] {
  const messages: ChatMessage[] = []
  let pendingRenderBlocks: MessageBlock[] = []
  let pendingRenderCreatedAt: string | null = null

    const flushPendingRenderBlocks = () => {
        if (pendingRenderBlocks.length === 0) {
            return
        }

        messages.push({
            id: `render-only-${pendingRenderCreatedAt || Date.now()}`,
            role: 'assistant',
            content: extractMessageText(pendingRenderBlocks),
            blocks: pendingRenderBlocks,
            createdAt: pendingRenderCreatedAt || new Date().toISOString(),
            isHistoryLoaded: true,
        })
        pendingRenderBlocks = []
        pendingRenderCreatedAt = null
    }

    rawMessages.forEach((message, index) => {
        const metadata = (message.metadata || {}) as Record<string, any>
        const renderBlocks = normalizeBlocks((message as Record<string, any>).blocks)
        const isRenderOnly = Boolean(metadata.render_only)
        const isExcludedFromHistory = Boolean(metadata.exclude_from_history)
        const isInternalOnly = String(metadata.message_kind || '') === 'internal_model_prompt'
        const createdAt = message.created_at || new Date().toISOString()
        const messageId = message.id || `msg-${index}`
        // Presentation-v2 persists user-visible messages under a hashed
        // `stored_message_id`, but the live presentation reducer keys messages by
        // the raw `message_key`. Reuse that durable key here so a snapshot reload
        // followed by a resumed live stream targets the same message instead of
        // forking a duplicate bubble. (Short keys hash to themselves, so this is a
        // no-op for them.)
        const presentationMessageKey = String(metadata.render_kind || '') === 'presentation_v2'
            && typeof metadata.message_key === 'string'
            && metadata.message_key.trim()
            ? String(metadata.message_key)
            : ''
        const stableMessageId = presentationMessageKey || messageId
        const renderKey = typeof metadata.render_key === 'string'
            ? metadata.render_key
            : (
                renderBlocks.length === 1
                    && (renderBlocks[0]?.uiKind === 'user_plan_card' || renderBlocks[0]?.uiKind === 'user_progress_card')
                    ? String(
                        renderBlocks[0]?.renderKey
                        || renderBlocks[0]?.payload?.renderKey
                        || renderBlocks[0]?.payload?.render_key
                        || (renderBlocks[0]?.uiKind === 'user_plan_card' ? 'home-user-plan' : 'home-user-progress'),
                    )
                    : ''
            )

        if (message.role === 'assistant' && isRenderOnly) {
            if (
                (renderKey === 'home-user-progress'
                    || renderKey === 'home-planning-draft'
                    || renderKey.startsWith('home-user-plan:')
                    || renderKey === 'home-user-plan')
                && renderBlocks.length > 0
            ) {
                flushPendingRenderBlocks()
                messages.push({
                    id: `render:${renderKey}`,
                    role: 'assistant',
                    content: null,
                    blocks: renderBlocks,
                    createdAt,
                    isHistoryLoaded: true,
                })
                return
            }
            if (renderBlocks.some((block) => block.uiKind === 'subagent_card')) {
                flushPendingRenderBlocks()
                messages.push({
                    id: `render:${renderKey || messageId}`,
                    role: 'assistant',
                    content: extractMessageText(renderBlocks),
                    blocks: renderBlocks,
                    createdAt,
                    isHistoryLoaded: true,
                })
                return
            }
            if (renderBlocks.length > 0) {
                if (shouldReplayRenderOnlyMessageStandalone(renderBlocks)) {
                    flushPendingRenderBlocks()
                    messages.push({
                        id: stableMessageId,
                        role: 'assistant',
                        content: extractMessageText(renderBlocks),
                        blocks: [...renderBlocks].sort((a, b) => a.order - b.order),
                        createdAt,
                        isHistoryLoaded: true,
                    })
                    return
                }
                pendingRenderBlocks = [...pendingRenderBlocks, ...renderBlocks].sort((a, b) => a.order - b.order)
                pendingRenderCreatedAt = pendingRenderCreatedAt || createdAt
            }
            return
        }

        if (isExcludedFromHistory || isInternalOnly) {
            return
        }

        if (message.role === 'assistant') {
            const mergedBlocks = [...pendingRenderBlocks, ...renderBlocks].sort((a, b) => a.order - b.order)
            messages.push({
                id: stableMessageId,
                role: 'assistant',
                content: message.content ?? extractMessageText(mergedBlocks),
                attachments: message.attachments || undefined,
                blocks: mergedBlocks.length > 0 ? mergedBlocks : undefined,
                createdAt,
                isHistoryLoaded: true,
            })
            pendingRenderBlocks = []
            pendingRenderCreatedAt = null
            return
        }

        flushPendingRenderBlocks()
        messages.push({
            id: stableMessageId,
            role: message.role as 'user' | 'assistant' | 'tool',
            content: message.content || null,
            attachments: message.attachments || undefined,
            baseFileVersions: Array.isArray(metadata.base_file_versions)
                ? metadata.base_file_versions
                : undefined,
            createdAt,
            isHistoryLoaded: true,
        })
    })

    flushPendingRenderBlocks()
    return reorderAnchoredSubagentMessages(dedupeHomepageMediaMessages(dedupePlanArtifactMessages(messages)))
}

function applySubmittedInteractionMetadataToUiMessages(
    messages: ChatMessage[],
    rawMessages: HarnessMessageLike[],
): ChatMessage[] {
    let nextMessages = messages

    rawMessages.forEach((message) => {
        if (message.role !== 'user' || !message.metadata || typeof message.metadata !== 'object') {
            return
        }

        const metadata = message.metadata as Record<string, any>
        const requestId = String(metadata.request_id || metadata.requestId || '').trim()
        if (!requestId) {
            return
        }

        const submittedLabel = String(
            metadata.display_label
            ?? metadata.displayLabel
            ?? metadata.answer
            ?? '',
        ).trim()
        const submittedAnswer = String(metadata.answer || '').trim()
        const answers = metadata.answers && typeof metadata.answers === 'object' && !Array.isArray(metadata.answers)
            ? metadata.answers as Record<string, any>
            : null

        let didUpdate = false
        nextMessages = nextMessages.map((uiMessage) => {
            if (!uiMessage.blocks?.length) {
                return uiMessage
            }

            const nextBlocks = uiMessage.blocks.map((block) => {
                if (
                    block.uiKind !== 'interaction_form'
                    || String(block.payload?.requestId || block.payload?.request_id || '').trim() !== requestId
                ) {
                    return block
                }

                didUpdate = true
                return {
                    ...block,
                    payload: {
                        ...block.payload,
                        status: 'submitted',
                        answers: answers ?? block.payload.answers ?? null,
                        submitted_label: submittedLabel || block.payload.submitted_label,
                        submittedLabel: submittedLabel || block.payload.submittedLabel,
                        submitted_answer: submittedAnswer || block.payload.submitted_answer,
                        submittedAnswer: submittedAnswer || block.payload.submittedAnswer,
                    },
                }
            })

            return didUpdate ? { ...uiMessage, blocks: nextBlocks } : uiMessage
        })
    })

    return nextMessages
}

function getPlanArtifactKey(block: MessageBlock): string | null {
    if (block.uiKind !== 'plan_artifact') {
        return null
    }

    const renderKey = block.renderKey
        ?? block.payload.renderKey
        ?? block.payload.render_key
    if (renderKey) {
        return `render:${String(renderKey)}`
    }

    const filePath = String(block.payload.filePath || block.payload.file_path || '').trim().toLowerCase()
    if (filePath.endsWith('plan.md')) {
        return `plan-file:${filePath}`
    }

    return 'plan-artifact'
}

function pruneDuplicatePlanBlocks(
    blocks: MessageBlock[] | undefined,
    seenKeys: Set<string>,
): MessageBlock[] | undefined {
    if (!blocks?.length) {
        return blocks
    }

    const nextBlocks = blocks.flatMap((block) => {
        const nextChildren = pruneDuplicatePlanBlocks(block.children, seenKeys)
        const planKey = getPlanArtifactKey(block)
        if (planKey) {
            if (seenKeys.has(planKey)) {
                return []
            }
            seenKeys.add(planKey)
        }
        return [{
            ...block,
            children: nextChildren,
        }]
    })

    return nextBlocks.length > 0 ? nextBlocks : undefined
}

export function dedupePlanArtifactMessages(messages: ChatMessage[]): ChatMessage[] {
    const seenKeys = new Set<string>()
    const dedupedReversed = [...messages].reverse().flatMap((message) => {
        const nextBlocks = pruneDuplicatePlanBlocks(message.blocks, seenKeys)
        if (
            message.role === 'assistant'
            && !message.content
            && (!nextBlocks || nextBlocks.length === 0)
            && (!message.attachments || message.attachments.length === 0)
        ) {
            return []
        }

        return [{
            ...message,
            blocks: nextBlocks,
        }]
    })

    return dedupedReversed.reverse()
}

function getHomepageMediaArtifactKey(block: MessageBlock): string | null {
    if (block.uiKind !== 'media_card') {
        return null
    }

    const artifactRef = String(
        block.payload.artifactRef
        ?? block.payload.artifact_ref
        ?? block.payload.result?.artifactRef
        ?? block.payload.result?.artifact_ref
        ?? '',
    ).trim()
    if (artifactRef) {
        return `artifact:${artifactRef}`
    }

    const renderKey = String(
        block.renderKey
        ?? block.payload.renderKey
        ?? block.payload.render_key
        ?? '',
    ).trim()
    if (renderKey) {
        return `render:${renderKey}`
    }

    const taskId = String(
        block.taskId
        ?? block.payload.taskId
        ?? block.payload.task_id
        ?? block.payload.result?.taskId
        ?? block.payload.result?.task_id
        ?? '',
    ).trim()
    return taskId ? `task:${taskId}` : null
}

function getHomepageMediaStatusRank(block: MessageBlock): number {
    const status = String(block.payload.status || block.status || '').trim().toLowerCase()
    if (status === 'completed') {
        return 3
    }
    if (status === 'failed') {
        return 2
    }
    if (status === 'processing' || status === 'running' || status === 'pending') {
        return 1
    }
    return 0
}

function collectWinningHomepageMediaBlocks(messages: ChatMessage[]): Map<string, { messageIndex: number, blockId: string, rank: number, order: number }> {
    const winners = new Map<string, { messageIndex: number, blockId: string, rank: number, order: number }>()

    const visit = (blocks: MessageBlock[] | undefined, messageIndex: number) => {
        if (!blocks?.length) {
            return
        }
        blocks.forEach((block) => {
            const mediaKey = getHomepageMediaArtifactKey(block)
            if (mediaKey) {
                const candidate = {
                    messageIndex,
                    blockId: block.id,
                    rank: getHomepageMediaStatusRank(block),
                    order: Number(block.order ?? 0),
                }
                const existing = winners.get(mediaKey)
                if (
                    !existing
                    || candidate.rank > existing.rank
                    || (
                        candidate.rank === existing.rank
                        && (
                            candidate.messageIndex > existing.messageIndex
                            || (
                                candidate.messageIndex === existing.messageIndex
                                && candidate.order >= existing.order
                            )
                        )
                    )
                ) {
                    winners.set(mediaKey, candidate)
                }
            }
            visit(block.children, messageIndex)
        })
    }

    messages.forEach((message, messageIndex) => {
        visit(message.blocks, messageIndex)
    })

    return winners
}

function pruneDuplicateHomepageMediaBlocks(
    blocks: MessageBlock[] | undefined,
    options: {
        messageIndex: number
        winners: Map<string, { messageIndex: number, blockId: string }>
    },
): MessageBlock[] | undefined {
    const { messageIndex, winners } = options
    if (!blocks?.length) {
        return blocks
    }

    const nextBlocks = blocks.flatMap((block) => {
        const nextChildren = pruneDuplicateHomepageMediaBlocks(block.children, { messageIndex, winners })
        const mediaKey = getHomepageMediaArtifactKey(block)
        if (mediaKey) {
            const winner = winners.get(mediaKey)
            if (!winner || winner.messageIndex !== messageIndex || winner.blockId !== block.id) {
                return []
            }
        }
        return [{
            ...block,
            children: nextChildren,
        }]
    })

    return nextBlocks.length > 0 ? nextBlocks : undefined
}

function dedupeHomepageMediaMessages(messages: ChatMessage[]): ChatMessage[] {
    const winners = collectWinningHomepageMediaBlocks(messages)
    return messages.flatMap((message, messageIndex) => {
        const nextBlocks = pruneDuplicateHomepageMediaBlocks(message.blocks, { messageIndex, winners })
        if (
            message.role === 'assistant'
            && !message.content
            && (!nextBlocks || nextBlocks.length === 0)
            && (!message.attachments || message.attachments.length === 0)
        ) {
            return []
        }

        return [{
            ...message,
            blocks: nextBlocks,
        }]
    })
}

export function buildSnapshotProjectionFromDetail(
    detail: HarnessConversationDetailRead,
): HomeHarnessProjectionState {
    const rawRuntimeStatus = String(detail.runtime_status || detail.status || '').toLowerCase()
    const runtimeUserInteraction = resolveHarnessPendingInteraction(detail) as PendingInteraction | null
    const rawMessages = Array.isArray(detail.messages) ? detail.messages : []
    const messages = applySubmittedInteractionMetadataToUiMessages(
        buildHarnessUiMessages(rawMessages),
        rawMessages,
    )
    return {
        ...createHomeHarnessProjectionState(),
        messages,
        planningDraft: detail.planning_draft ?? null,
        activeUserPlan: detail.user_plan ?? null,
        outlineRuntime: detail.outline_runtime ?? null,
        runtimeState: detail.runtime_state ?? null,
        critique: hydrateHomeHarnessCritique(detail.runtime_state as Record<string, any> | null),
        userProgress: detail.user_progress ?? null,
        userInteraction: runtimeUserInteraction ?? null,
        workspaceFiles: Array.isArray(detail.workspace_files) ? detail.workspace_files : [],
        lastSequence: resolveHarnessSnapshotEventSequence(detail),
        isStreaming: rawRuntimeStatus === 'running',
        runStatus: rawRuntimeStatus === 'failed'
            ? 'failed'
            : rawRuntimeStatus === 'blocked'
                ? 'blocked'
                : rawRuntimeStatus === 'waiting_input'
                    ? 'waiting_input'
                    : rawRuntimeStatus === 'cancelled'
                        ? 'cancelled'
                        : rawRuntimeStatus === 'completed'
                            ? 'completed'
                            : rawRuntimeStatus === 'running'
                                ? 'running'
                                : 'idle',
    }
}

export function buildHarnessConversationMeta(detail: HarnessConversationRead): HarnessConversationRead {
    const runtimeContract = (
        detail.runtime_state?.runtime_contract
        && typeof detail.runtime_state.runtime_contract === 'object'
        && !Array.isArray(detail.runtime_state.runtime_contract)
    ) ? detail.runtime_state.runtime_contract as Record<string, any> : null
    const designSystemId = String(
        detail.design_system_id
        ?? runtimeContract?.design_system_id
        ?? '',
    ).trim() || null
    return {
        id: detail.id,
        title: detail.title,
        runtime_profile: detail.runtime_profile === 'canvas' ? 'canvas' : 'home',
        interaction_profile: detail.interaction_profile === 'canvas_live_interaction'
            ? 'canvas_live_interaction'
            : 'home_blocking_preflight',
        skill_id: detail.skill_id,
        resolved_skill_id: detail.resolved_skill_id ?? detail.skill_id ?? null,
        skill_resolution_source: detail.skill_resolution_source ?? null,
        skill_selection_mode: detail.skill_selection_mode === 'manual' ? 'manual' : 'auto',
        phase: detail.phase,
        artifact_mode: detail.artifact_mode ?? 'web',
        design_system_id: designSystemId,
        last_skill_decision_reason: detail.last_skill_decision_reason ?? null,
        last_skill_decision_confidence: detail.last_skill_decision_confidence ?? null,
        mode: detail.mode,
        web_search_enabled: detail.web_search_enabled ?? true,
        status: detail.status,
        runtime_status: detail.runtime_status,
        display_status: detail.display_status ?? null,
        protocol_version: detail.protocol_version ?? null,
        run_state: detail.run_state || detail.runtime_status || 'idle',
        stall_reason: detail.stall_reason ?? null,
        last_tool: detail.last_tool ?? null,
        last_error_summary: detail.runtime_state?.failure?.summary ?? detail.last_error_summary ?? null,
        last_activity_at: detail.last_activity_at ?? null,
        last_activity_source: detail.last_activity_source ?? null,
        engine_version: 'harness',
        run_id: detail.run_id,
        started_at: detail.started_at,
        finished_at: detail.finished_at,
        plan_state: detail.plan_state ?? null,
        planning_draft: detail.planning_draft ?? null,
        outline_runtime: detail.outline_runtime ?? null,
        user_plan: detail.user_plan ?? null,
        user_progress: detail.user_progress ?? null,
        runtime_state: detail.runtime_state ?? null,
        recovery_summary: detail.recovery_summary ?? null,
        created_at: detail.created_at,
        updated_at: detail.updated_at,
    }
}


const LIVE_PROGRESS_RUN_STATES = new Set([
    'planning',
    'executing',
    'waiting_model',
    'waiting_tool',
    'recovering',
])

function buildConversationPlanState(
    activePlan: PlanRead | null,
    previousPlanState?: Record<string, any> | null,
): Record<string, any> | null {
    if (!activePlan) {
        return previousPlanState ?? null
    }
    return {
        ...(previousPlanState || {}),
        plan_id: activePlan.plan_id ?? activePlan.id,
        summary: activePlan.summary,
        status: activePlan.status,
        steps: activePlan.steps,
        created_at: activePlan.created_at,
    }
}

function deriveConversationRuntimeState(
    existing: HarnessConversationRead,
    session: ConversationSessionState,
): Pick<HarnessConversationRead, 'runtime_status' | 'display_status' | 'run_state' | 'activity'> {
    const previousRunState = String(existing.run_state || existing.runtime_status || '').trim()
    const runtimeActivity = String(session.runtimeState?.activity || existing.activity || '').trim()
    const runtimeRunState = String(session.runtimeState?.run_state || '').trim()

    switch (session.runStatus) {
        case 'running':
            {
                const nextRunState = runtimeActivity === 'planning_outline'
                    ? 'planning'
                    : LIVE_PROGRESS_RUN_STATES.has(runtimeRunState) && runtimeRunState !== 'planning'
                        ? runtimeRunState
                        : 'executing'
                return {
                    runtime_status: 'running',
                    display_status: runtimeActivity === 'planning_outline' ? '规划中' : '进行中',
                    run_state: nextRunState,
                    activity: runtimeActivity || (nextRunState === 'planning' ? 'planning_outline' : 'executing'),
                }
            }
        case 'waiting_input':
            return {
                runtime_status: 'waiting_input',
                display_status: '等待输入',
                run_state: 'waiting_input',
                activity: 'waiting_input',
            }
        case 'completed':
            return {
                runtime_status: 'completed',
                display_status: '已完成',
                run_state: 'completed',
                activity: 'completed',
            }
        case 'failed':
            return {
                runtime_status: 'failed',
                display_status: '失败',
                run_state: 'failed',
                activity: 'failed',
            }
        case 'blocked':
            return {
                runtime_status: 'blocked',
                display_status: '阻塞',
                run_state: previousRunState === 'stalled' ? 'stalled' : 'blocked',
                activity: 'blocked',
            }
        case 'cancelled':
            return {
                runtime_status: 'cancelled',
                display_status: '已取消',
                run_state: 'cancelled',
                activity: 'cancelled',
            }
        case 'idle':
        default:
            return {
                runtime_status: existing.runtime_status,
                display_status: existing.display_status ?? null,
                run_state: existing.run_state || existing.runtime_status,
                activity: existing.activity ?? null,
            }
    }
}

function mergeConversationMetaFromSession(
    existing: HarnessConversationRead,
    session: ConversationSessionState,
    overrides: Partial<HarnessConversationRead> = {},
): HarnessConversationRead {
    const runtimeState = deriveConversationRuntimeState(existing, session)
    return buildHarnessConversationMeta({
        ...existing,
        ...runtimeState,
        plan_state: buildConversationPlanState(session.activePlan, existing.plan_state),
        planning_draft: session.planningDraft ?? existing.planning_draft ?? null,
        outline_runtime: session.outlineRuntime ?? existing.outline_runtime ?? null,
        user_plan: session.activeUserPlan ?? existing.user_plan ?? null,
        user_progress: session.userProgress ?? existing.user_progress ?? null,
        ...overrides,
    })
}

export function updateConversationMetaFromSession(
    state: ChatState,
    conversationId: number | string,
    session: ConversationSessionState,
    overrides: Partial<HarnessConversationRead> = {},
): HarnessConversationRead[] {
    const conversationKey = String(conversationId)
    const existingIdx = state.conversations.findIndex((conversation) => String(conversation.id) === conversationKey)
    if (existingIdx < 0) {
        return state.conversations
    }
    const nextConversations = [...state.conversations]
    nextConversations[existingIdx] = mergeConversationMetaFromSession(
        nextConversations[existingIdx],
        session,
        overrides,
    )
    return nextConversations
}

function resolveHarnessEventTimestamp(event: AgentEvent): string {
    const candidates = [
        event.data?.created_at,
        event.data?.updated_at,
        event.data?.finished_at,
        event.data?.started_at,
    ]
    const resolved = candidates.find((value) => typeof value === 'string' && value.trim().length > 0)
    return resolved ? String(resolved) : new Date().toISOString()
}

export function buildConversationMetaOverridesFromEvent(
    existing: HarnessConversationRead | null,
    session: ConversationSessionState,
    event: AgentEvent,
): Partial<HarnessConversationRead> {
    const timestamp = resolveHarnessEventTimestamp(event)
    const eventType = event.type
    const existingRuntimeState = (
        existing?.runtime_state
        && typeof existing.runtime_state === 'object'
        && !Array.isArray(existing.runtime_state)
    ) ? existing.runtime_state : null
    const overrides: Partial<HarnessConversationRead> = {
        last_activity_at: timestamp,
        updated_at: timestamp,
    }

    if (eventType === 'turn_started') {
        const activity = typeof event.data.activity === 'string' ? event.data.activity : session.runtimeState?.activity ?? null
        overrides.phase = typeof event.data.phase === 'string' ? event.data.phase as any : existing?.phase
        overrides.runtime_status = 'running'
        overrides.run_state = typeof event.data.run_state === 'string'
            ? event.data.run_state
            : activity === 'planning_outline'
                ? 'planning'
                : 'executing'
        overrides.activity = activity
        overrides.turn_route = event.data.turn_route && typeof event.data.turn_route === 'object'
            ? event.data.turn_route as Record<string, any>
            : existing?.turn_route ?? null
        overrides.display_status = activity === 'planning_outline' ? '规划中' : '进行中'
    } else if (eventType === 'run_started') {
        overrides.turn_route = event.data.turn_route && typeof event.data.turn_route === 'object'
            ? event.data.turn_route as Record<string, any>
            : existing?.turn_route ?? null
    } else if (eventType === 'turn_completed') {
        const status = String(event.data.status || 'completed') as HarnessConversationRead['runtime_status']
        const error = event.data.error && typeof event.data.error === 'object'
            ? event.data.error as Record<string, any>
            : null
        const runtimeSnapshot = event.data.runtime_snapshot && typeof event.data.runtime_snapshot === 'object'
            ? event.data.runtime_snapshot as Record<string, any>
            : {}
        overrides.runtime_status = status
        overrides.display_status = status === 'failed'
            ? '失败'
            : status === 'blocked'
                ? '阻塞'
                : status === 'cancelled'
                    ? '已取消'
                    : status === 'waiting_input'
                        ? '等待输入'
                        : '已完成'
        overrides.run_state = status
        overrides.activity = status
        overrides.last_error_summary = error?.summary ? String(error.summary) : null
        overrides.recovery_summary = status === 'completed' ? null : existing?.recovery_summary ?? null
        overrides.runtime_state = {
            ...(existingRuntimeState || {}),
            ...runtimeSnapshot,
            run_state: status,
            runtime_status: status,
            activity: status,
            failure: error,
        } as any
    }

    return overrides
}

export function buildActiveConversationMetadataUpdates(
    state: ChatState,
    detail: Pick<
        HarnessConversationRead,
        | 'id'
        | 'skill_id'
        | 'interaction_profile'
        | 'skill_selection_mode'
        | 'last_skill_decision_reason'
        | 'last_skill_decision_confidence'
        | 'mode'
        | 'web_search_enabled'
        | 'artifact_mode'
        | 'design_system_id'
    >,
): Partial<ChatState> {
    if (String(state.conversationId || '') !== String(detail.id || '')) {
        return {}
    }

    const nextSelectedDesignSystemId = detail.design_system_id == null
        ? state.selectedDesignSystemId
        : detail.design_system_id

    return {
        interactionProfile: detail.interaction_profile === 'canvas_live_interaction'
            ? 'canvas_live_interaction'
            : 'home_blocking_preflight',
        activeSkillId: detail.skill_id ?? null,
        skillSelectionMode: detail.skill_selection_mode === 'manual' ? 'manual' : 'auto',
        selectedDesignSystemId: nextSelectedDesignSystemId,
        skillDecisionReason: detail.last_skill_decision_reason ?? null,
        skillDecisionConfidence: detail.last_skill_decision_confidence ?? null,
        artifactMode: (detail.artifact_mode as ChatState['artifactMode']) || 'web',
        mode: detail.mode as 'plan' | 'fast',
        webSearchEnabled: detail.web_search_enabled ?? true,
    }
}

export async function fetchHarnessConversationDetailSnapshot(
    conversationId: string,
    signal?: AbortSignal,
): Promise<HarnessConversationDetailRead | null> {
    const response = await agentApi.getHarnessConversation(conversationId, signal)
    return response?.data || null
}

