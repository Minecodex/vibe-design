import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import {
    agentApi,
    streamHarnessSendMessage,
    streamHarnessRespondToAgent,
    streamHarnessConversationEvents,
    type AgentEvent,
    type PlanRead,
    type PendingInteraction,
    type AttachmentData,
    type MediaReferenceData,
    type SendMessageRequest,
    type WorkspaceFileRead,
    type HarnessConversationRead,
    type HarnessSkillRead,
} from '@/api/endpoints/agent'
import { shouldReconnectTurnStream } from './harnessStreamLifecycle'
import { startHarnessStreamSession } from './harnessStreamSession'
import { isTurnCompletedEvent, isTurnDoneForTransport } from './harnessTurnProtocol'
import {
    createCanvasGenerationRuntimeAdapter,
    disposeConversationGenerationTasks,
    recoverGenerationTasksFromSession,
    updateBlocksByGenerationTask,
    updateToolCallsByGenerationTask,
    type CanvasGenerationTaskSnapshot,
} from './canvasGenerationTaskRuntime'
import {
    EMPTY_MESSAGE_BLOCKS,
    CANVAS_MENSWEAR_ECOMMERCE_HERO_SKILL_ID,
    FALLBACK_CANVAS_DEFAULT_SKILL_ID,
    FALLBACK_CANVAS_EXPLICIT_SKILL_IDS,
    normalizeCanvasResolvedSkillId,
    normalizeCanvasSelectedSkillId,
    resolveCanvasRequestSkillId,
    resolveCanvasSkillPolicy,
    type ChatMessage,
    type ChatUiConfig,
    type MessageBlock,
    type ModelPreferences,
    type ToolCallInfo,
} from './canvasAgentTypes'

export type {
    ChatMessage,
    ChatUiConfig,
    MessageBlock,
    ModelPreferences,
    ToolCallInfo,
} from './canvasAgentTypes'

function resolveCanvasSkillArtifactMode(skillId: string | null | undefined): string | null {
    return String(skillId || '').trim() === CANVAS_MENSWEAR_ECOMMERCE_HERO_SKILL_ID ? 'image' : null
}
import {
    applyConversationSessionUpdate,
    buildActiveConversationFields,
    conversationListRequests,
    createEmptyConversationSession,
    getConversationSession,
    getConversationSessionKey,
    getMessagesPage,
    isSameConversationId,
    mergeChatStatePatches,
    normalizeCanvasDefaultSkillId,
    normalizeCanvasExplicitSkillIds,
    normalizeHiddenToolCalls,
    shouldReplaceConversationTitle,
    summarizeConversationTitle,
    type ConversationSessionState,
} from './canvasAgentSession'
import {
    buildCanvasHarnessProjectionFromSnapshot,
    buildHarnessUiMessages,
    buildHarnessUiMessagesForConversation,
    projectionToCanvasSession,
    type HarnessConversationSnapshotDetail,
} from './canvasHarnessProjection'
import {
    applyToolCallUpdatesToBlock,
    upsertStreamingToolResultBlock,
} from './canvasAgentToolCalls'
import {
    finalizeStreamV2,
    handleAgentEventV2,
} from './canvasAgentEventHandler'
import {
    abortAllConversationStreams,
    applyCanvasMissingTurnCompletedProtocolError,
    fetchHarnessConversationSnapshot,
    isHarnessConversationTerminal,
    reconcileCanvasTurnStreamAfterTransportClose,
    refreshHarnessConversationFromServer,
    shouldKeepCanvasLiveSession,
    shouldKeepHarnessConversationTransportAlive,
    stopConversationEventStream,
} from './canvasHarnessLifecycle'
import {
    clearPendingStreamBlockDeltas,
    flushPendingStreamBlockDeltas,
} from './canvasAgentStreamBatching'
import { stripTransientAttachmentFields } from '@/pages/dashboard/agentMedia/agentPendingAttachmentPreview'
import {
    extractMessageText,
    getBlockIdentityKeys,
    hasEquivalentBlock,
} from './canvasAgentBlockNormalize'
import { optimisticInteractionSubmissionOps } from './harnessMessageProjection/optimistic'
import { applyPresentationOpToSession } from './harnessMessageProjection/reducer'
import { withHarnessActiveRunRetry } from './harnessRunSettle'

const HARNESS_STREAM_RECONNECT_DELAY_MS = 750

export interface ChatState {
    // Current conversation
    conversationId: number | string | null
    projectId: number | null
    viewerUserId: number | null
    messages: ChatMessage[]
    activePlan: PlanRead | null
    pendingInteraction: PendingInteraction | null
    isStreaming: boolean
    mode: 'plan' | 'fast'
    activeSkillId: string | null
    webSearchEnabled: boolean
    modelPreferences: ModelPreferences
    uiConfig: ChatUiConfig

    // Streaming state
    currentStreamText: string
    currentToolCalls: ToolCallInfo[]
    streamingBlocks: MessageBlock[]

    // Conversation list
    conversations: HarnessConversationRead[]
    conversationsHasMore: boolean
    conversationsPage: number

    // Harness-specific state
    engineVersion: 'harness'
    workspaceFiles: WorkspaceFileRead[]

    // Abort controller for cancellation
    _abortController: AbortController | null
    conversationSessions: Record<string, ConversationSessionState>
}

export interface ChatActions {
    // Initialization
    setProjectId: (projectId: number) => void
    syncScope: (projectId: number, viewerUserId: number | null) => void
    loadUiConfig: (options?: { force?: boolean }) => Promise<void>

    // Conversation management
    createConversation: (projectId: number, skillId?: string) => Promise<void>
    loadConversations: (projectId: number) => Promise<void>
    loadConversation: (id: number | string) => Promise<void>
    loadOlderMessages: () => Promise<void>
    deleteConversation: (id: number | string) => Promise<void>

    // Message sending
    sendMessage: (
        content: string,
        attachments?: AttachmentData[],
        options?: { modelPreferences?: Partial<ModelPreferences>; references?: MediaReferenceData[] | null },
    ) => Promise<void>
    stopStreaming: () => void

    // Plan management
    approvePlan: (planId: number) => Promise<void>
    rejectPlan: (planId: number, feedback?: string) => Promise<void>

    // Interaction response
    respondToAgent: (requestId: string, answer: string, displayLabel?: string, answers?: Record<string, any> | null) => Promise<void>

    // Mode/skill
    setMode: (mode: 'plan' | 'fast') => void
    activateSkill: (skillId: string | null) => void
    setWebSearchEnabled: (enabled: boolean) => void
    setModelPreferences: (prefs: Partial<ModelPreferences>) => void

    // Harness
    createHarnessConversation: (
        skillId?: string | null,
        options?: { modelPreferences?: Partial<ModelPreferences>; preserveResolvedSkill?: boolean },
    ) => Promise<void>

    // Reset
    newChat: () => void
    reset: () => void

    // Canvas item handler (set by CanvasPage)
    onCanvasUpdate: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null
    setOnCanvasUpdate: (handler: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null) => void

    // Task & Tool update
    updateToolCall: (messageId: string | number, callId: string, updates: Partial<ToolCallInfo>) => void
    updateToolCallByGenerationTask: (conversationId: string, snapshot: CanvasGenerationTaskSnapshot) => void
    updateCanvasItemByGenerationTask: (conversationId: string, canvasItem: Record<string, any>) => void
    updateCanvasRevisionByAgentPatch: (canvasRevision: number, options?: { canvasItemDeleted?: boolean }) => void
}

// ── Store ──────────────────────────────────────────────────────

const initialState: ChatState = {
    conversationId: null,
    projectId: null,
    viewerUserId: null,
    messages: [],
    activePlan: null,
    pendingInteraction: null,
    isStreaming: false,
    mode: 'fast',
    activeSkillId: null,
    currentStreamText: '',
    currentToolCalls: [],
    streamingBlocks: EMPTY_MESSAGE_BLOCKS,
    conversations: [],
    conversationsHasMore: false,
    conversationsPage: 1,
    engineVersion: 'harness',
    workspaceFiles: [],
    webSearchEnabled: false,
    modelPreferences: {
        auto: false,
    },
    uiConfig: {
        hiddenToolCalls: [],
        canvasDefaultSkillId: FALLBACK_CANVAS_DEFAULT_SKILL_ID,
        canvasExplicitSkillIds: FALLBACK_CANVAS_EXPLICIT_SKILL_IDS,
    },
    _abortController: null,
    conversationSessions: {},
}

let uiConfigRequest: Promise<void> | null = null

async function settleHarnessConversationStream(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
): Promise<boolean> {
    const currentSession = getConversationSession(get(), conversationId)
    if (currentSession.runStatus === 'cancelled') {
        finalizeStreamV2(set, get, conversationId)
        return false
    }
    const detail = await refreshHarnessConversationFromServer(conversationId, set)
    if (detail && shouldReconnectTurnStream(detail)) {
        set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
            ...session,
            abortController: null,
        })))
        return true
    }

    if (detail) {
        if (isTurnDoneForTransport(detail.runtime_status) && detail.runtime_status !== 'waiting_input') {
            applyCanvasMissingTurnCompletedProtocolError(conversationId, detail.runtime_status, set)
        }
        set((state) => stopConversationEventStream(state, conversationId))
        return false
    }

    const nextSession = getConversationSession(get(), conversationId)
    if (shouldKeepHarnessConversationTransportAlive(nextSession)) {
        return true
    }

    set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
        ...session,
        abortController: null,
    })))
    return false
}

function subscribeToHarnessConversationEvents(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
): void {
    const currentSession = getConversationSession(get(), conversationId)
    currentSession.eventStreamController?.abort()

    const streamSession = startHarnessStreamSession<AgentEvent>({
        conversationId,
        lastSequence: currentSession.lastSequence,
        getLastSequence: () => getConversationSession(get(), conversationId).lastSequence,
        skipDuplicateSequences: false,
        reconnectDelayMs: HARNESS_STREAM_RECONNECT_DELAY_MS,
        onTransportClosedWithoutTerminal: () => settleHarnessConversationStream(conversationId, set, get),
        stream: streamHarnessConversationEvents,
        onEvent: (event) => handleAgentEventV2(event, set, get, conversationId),
        onError: (err) => console.error('Failed to resume harness conversation stream:', err),
        onClose: (controller) => {
            set((state) => applyConversationSessionUpdate(state, conversationId, (session) => (
                session.eventStreamController === controller
                    ? { ...session, eventStreamController: null }
                    : session
            )))
        },
    })
    const controller = streamSession.controller
    set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
        ...session,
        isStreaming: session.runStatus === 'running',
        eventStreamController: controller,
    })))
}

async function resumeHarnessConversationEventsAfterPostClose(
    conversationId: string,
    commandSignal: AbortSignal,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
): Promise<boolean> {
    if (commandSignal.aborted) {
        return false
    }

    const shouldResume = await reconcileCanvasTurnStreamAfterTransportClose(conversationId, set)
    if (commandSignal.aborted || !shouldResume) {
        return false
    }

    const session = getConversationSession(get(), conversationId)
    if (!session.eventStreamController) {
        subscribeToHarnessConversationEvents(conversationId, set, get)
    }
    return true
}

function parseOptimisticInteractionAnswer(answer: string): Record<string, any> | null {
    const normalizedAnswer = String(answer || '').trim()
    if (!normalizedAnswer) {
        return null
    }

    try {
        const parsed = JSON.parse(normalizedAnswer)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            return parsed as Record<string, any>
        }
    } catch {
        // Plain string answers are expected for legacy interaction cards.
    }

    return null
}

function buildOptimisticInteractionAnswers(
    block: MessageBlock,
    answer?: string,
    displayLabel?: string,
): Record<string, any> | null {
    if (answer === undefined) {
        return null
    }

    const parsedAnswer = parseOptimisticInteractionAnswer(answer)
    if (parsedAnswer) {
        return parsedAnswer
    }

    const schema = block.payload.schema && typeof block.payload.schema === 'object'
        ? block.payload.schema as { fields?: Array<{ id?: string, type?: string, options?: Array<{ value?: string, label?: string }> }> }
        : null
    const primaryField = Array.isArray(schema?.fields) ? schema?.fields[0] : null
    const fieldId = String(primaryField?.id || 'response').trim() || 'response'
    const optionLabel = Array.isArray(primaryField?.options)
        ? primaryField.options.find((option) => String(option?.value || '').trim() === answer)?.label
        : undefined
    const resolvedLabel = String(displayLabel || optionLabel || answer).trim()
    const fieldType = String(primaryField?.type || '').trim()

    if (fieldType === 'radio' || fieldType === 'cards' || fieldType === 'select') {
        return {
            [fieldId]: {
                type: 'option',
                value: answer,
                label: resolvedLabel,
            },
        }
    }

    return {
        [fieldId]: answer,
    }
}

function optimisticInteractionKind(
    pendingKind: string | null | undefined,
): string | null {
    const normalizedPendingKind = String(pendingKind || '').trim()
    if (normalizedPendingKind) {
        return normalizedPendingKind
    }
    return null
}

function markInteractionSubmittedWithAnswer(
    messages: ChatMessage[],
    requestId: string,
    answer?: string,
    displayLabel?: string,
    answers?: Record<string, any> | null,
): ChatMessage[] {
    return messages.map((message) => {
        if (!message.blocks?.length) {
            return message
        }

        let didUpdate = false
        const nextBlocks = message.blocks.map((block) => {
            if (
                block.kind !== 'interaction'
                || !['choice_prompt', 'interaction_form'].includes(block.uiKind)
                || String(block.payload.requestId || block.payload.request_id || '').trim() !== requestId
            ) {
                return block
            }

            didUpdate = true
            const optimisticAnswers = answers && typeof answers === 'object'
                ? answers
                : buildOptimisticInteractionAnswers(block, answer, displayLabel)
            return {
                ...block,
                payload: {
                    ...block.payload,
                    status: 'submitted',
                    submitted_value: answer ?? block.payload.submitted_value,
                    submittedValue: answer ?? block.payload.submittedValue,
                    submitted_label: displayLabel ?? block.payload.submitted_label,
                    submittedLabel: displayLabel ?? block.payload.submittedLabel,
                    ...(optimisticAnswers ? { answers: optimisticAnswers } : {}),
                },
            }
        })

        return didUpdate ? { ...message, blocks: nextBlocks } : message
    })
}

function buildScopedReset(overrides: Partial<ChatState> = {}): Partial<ChatState> {
    return {
        conversationId: null,
        messages: [],
        activePlan: null,
        pendingInteraction: null,
        isStreaming: false,
        currentStreamText: '',
        currentToolCalls: [],
        streamingBlocks: EMPTY_MESSAGE_BLOCKS,
        conversations: [],
        conversationsHasMore: false,
        conversationsPage: 1,
        _abortController: null,
        conversationSessions: {},
        ...overrides,
    }
}

function isCurrentScope(
    state: ChatState,
    projectId: number,
    viewerUserId: number | null,
): boolean {
    return state.projectId === projectId && state.viewerUserId === viewerUserId
}

export const useChatStore = create<ChatState & ChatActions>()(
    devtools(
        (set, get) => ({
            ...initialState,
            onCanvasUpdate: null,

            setProjectId: (projectId) => {
                const state = get()
                const { projectId: currentProjectId } = state
                if (currentProjectId === projectId) {
                    set({ projectId })
                    return
                }

                abortAllConversationStreams(state)
                set(buildScopedReset({ projectId }))
            },

            syncScope: (projectId, viewerUserId) => {
                const state = get()
                const scopeChanged = state.projectId !== projectId || state.viewerUserId !== viewerUserId
                if (!scopeChanged) {
                    return
                }

                abortAllConversationStreams(state)
                set(buildScopedReset({ projectId, viewerUserId }))
            },

            loadUiConfig: async (options) => {
                if (uiConfigRequest && !options?.force) {
                    return uiConfigRequest
                }

                uiConfigRequest = (async () => {
                    const res = await agentApi.getUiConfig()
                    let canvasSkills: HarnessSkillRead[] = []
                    try {
                        const skillsRes = await agentApi.listHarnessSkills()
                        const canvasExplicitSkillIds = normalizeCanvasExplicitSkillIds(res.data)
                        const canvasExplicitSkillIdSet = new Set(canvasExplicitSkillIds)
                        canvasSkills = skillsRes.data.filter(skill => canvasExplicitSkillIdSet.has(String(skill.id || '').trim()))
                    } catch (err) {
                        console.error('Failed to load canvas harness skills:', err)
                    }
                    set({
                        uiConfig: {
                            hiddenToolCalls: normalizeHiddenToolCalls(res.data),
                            canvasDefaultSkillId: normalizeCanvasDefaultSkillId(res.data),
                            canvasExplicitSkillIds: normalizeCanvasExplicitSkillIds(res.data),
                            canvasSkills,
                        },
                    })
                })().finally(() => {
                    uiConfigRequest = null
                })

                return uiConfigRequest
            },

            createConversation: async (projectId, skillId) => {
                const { mode, viewerUserId, activeSkillId, modelPreferences, webSearchEnabled, uiConfig } = get()
                const effectiveSkillId = skillId === undefined ? activeSkillId : skillId
                const requestSkillId = resolveCanvasRequestSkillId(effectiveSkillId, uiConfig)
                const artifactMode = resolveCanvasSkillArtifactMode(requestSkillId)
                const res = await agentApi.createHarnessConversation({
                    mode,
                    runtime_profile: 'canvas',
                    project_id: projectId,
                    skill_id: requestSkillId,
                    ...(requestSkillId ? { skill_selection_mode: 'manual' as const } : {}),
                    ...(artifactMode ? { artifact_mode: artifactMode } : {}),
                    web_search_enabled: webSearchEnabled,
                    model_preferences: modelPreferences,
                })
                if (!isCurrentScope(get(), projectId, viewerUserId)) {
                    return
                }
                const newConv = res.data
                const nextSession = createEmptyConversationSession()
                set((s) => ({
                    conversationId: newConv.id,
                    projectId,
                    messages: [],
                    activePlan: null,
                    pendingInteraction: null,
                    activeSkillId: normalizeCanvasResolvedSkillId(newConv.skill_id ?? effectiveSkillId ?? null, uiConfig),
                    engineVersion: 'harness',
                    conversationSessions: {
                        ...s.conversationSessions,
                        [getConversationSessionKey(newConv.id)]: nextSession,
                    },
                    conversations: [newConv, ...s.conversations],
                }))
            },

            loadConversations: async (projectId) => {
                const { viewerUserId } = get()
                const requestKey = `harness:${projectId}:${viewerUserId ?? 'anonymous'}`
                const existingRequest = conversationListRequests.get(requestKey)
                if (existingRequest) {
                    return existingRequest
                }

                const request = (async () => {
                    const res = await agentApi.listHarnessConversations(1, 20, {
                        runtime_profile: 'canvas',
                        project_id: projectId,
                    })
                    if (!isCurrentScope(get(), projectId, viewerUserId)) return
                    set({
                        conversations: res.data.items,
                        conversationsPage: 1,
                        conversationsHasMore: res.data.has_more,
                        engineVersion: 'harness',
                    })
                })().finally(() => {
                    conversationListRequests.delete(requestKey)
                })

                conversationListRequests.set(requestKey, request)
                return request
            },

            loadConversation: async (id) => {
                const { projectId: scopeProjectId, viewerUserId } = get()
                const detail = await fetchHarnessConversationSnapshot(String(id))
                if (!detail) {
                    return
                }
                const expectedProjectId = scopeProjectId ?? detail.project_id ?? null
                if (expectedProjectId != null && !isCurrentScope(get(), expectedProjectId, viewerUserId)) {
                    return
                }
                const snapshotProjection = buildCanvasHarnessProjectionFromSnapshot(detail)

                set((s) => {
                    const existingIdx = s.conversations.findIndex(c => c.id === detail.id)
                    let newConversations = [...s.conversations]
                    const convMeta: HarnessConversationRead = {
                        id: detail.id,
                        title: detail.title,
                        skill_id: detail.skill_id,
                        runtime_profile: detail.runtime_profile,
                        project_id: detail.project_id,
                        phase: detail.phase,
                        mode: detail.mode,
                        web_search_enabled: detail.web_search_enabled ?? false,
                        status: detail.status,
                        runtime_status: detail.runtime_status,
                        engine_version: 'harness',
                        run_id: detail.run_id,
                        started_at: detail.started_at,
                        finished_at: detail.finished_at,
                        created_at: detail.created_at,
                        updated_at: detail.updated_at,
                    }
                    if (existingIdx >= 0) {
                        newConversations[existingIdx] = convMeta
                    } else {
                        newConversations = [convMeta, ...newConversations]
                    }
                    const existingSession = getConversationSession(s, detail.id)
                    const keepLiveSession = shouldKeepCanvasLiveSession(existingSession, snapshotProjection)
                    const projectedSession = projectionToCanvasSession(snapshotProjection, existingSession, detail)
                    const nextSession: ConversationSessionState = keepLiveSession
                        ? {
                            ...existingSession,
                            lastSequence: existingSession.lastSequence,
                        }
                        : isHarnessConversationTerminal(snapshotProjection.runStatus)
                            ? {
                                ...projectedSession,
                                isStreaming: false,
                                streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                                currentStreamText: '',
                                currentToolCalls: [],
                                abortController: null,
                            }
                            : projectedSession
                    const conversationSessions = {
                        ...s.conversationSessions,
                        [getConversationSessionKey(detail.id)]: nextSession,
                    }
                    return {
                        conversationId: detail.id,
                        projectId: detail.project_id ?? expectedProjectId,
                        ...buildActiveConversationFields(nextSession),
                        mode: detail.mode as 'plan' | 'fast',
                        activeSkillId: normalizeCanvasSelectedSkillId(detail.skill_id, s.uiConfig),
                        webSearchEnabled: detail.web_search_enabled ?? false,
                        modelPreferences: detail.model_preferences ?? s.modelPreferences,
                        engineVersion: 'harness',
                        conversations: newConversations,
                        conversationSessions,
                    }
                })
                const resolvedSession = getConversationSession(get(), detail.id)
                recoverGenerationTasksFromSession(String(detail.id), resolvedSession, createCanvasGenerationRuntimeAdapter(get))
                if (
                    shouldReconnectTurnStream(detail)
                    && !resolvedSession.eventStreamController
                ) {
                    subscribeToHarnessConversationEvents(String(detail.id), set, get)
                } else if (!shouldReconnectTurnStream(detail)) {
                    set((state) => stopConversationEventStream(state, detail.id))
                }
            },

            deleteConversation: async (id) => {
                await agentApi.deleteHarnessConversation(String(id))
                const { conversations, conversationId } = get()
                disposeConversationGenerationTasks(String(id))
                set({
                    conversations: conversations.filter((c) => c.id !== id),
                    ...(isSameConversationId(conversationId, id) ? { conversationId: null, messages: [], activePlan: null } : {}),
                })
            },

            // Scroll-up pagination, mirroring the home agent. The initial snapshot only
            // carries a recent window (messages_page cursor); this prepends older pages on
            // demand. Safe for canvas because generated media lives on the persisted canvas,
            // not in chat history, so trimming/lazy-loading old messages loses nothing.
            loadOlderMessages: async () => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)
                const session = getConversationSession(get(), targetConversationId)
                const messagesPage = getMessagesPage(session)
                if (!messagesPage.hasMore || messagesPage.loading) {
                    return
                }
                set((state) => applyConversationSessionUpdate(state, targetConversationId, (currentSession) => ({
                    ...currentSession,
                    messagesPage: { ...getMessagesPage(currentSession), loading: true },
                })))
                try {
                    const response = await agentApi.listHarnessConversationMessages(
                        targetConversationId,
                        messagesPage.oldestSeq,
                        80,
                    )
                    const olderMessages = buildHarnessUiMessagesForConversation(
                        response.data.messages || [],
                    )
                    set((state) => applyConversationSessionUpdate(state, targetConversationId, (currentSession) => {
                        const existingIds = new Set(currentSession.messages.map((message) => String(message.id)))
                        const prependedMessages = olderMessages.filter((message) => !existingIds.has(String(message.id)))
                        return {
                            ...currentSession,
                            messages: [...prependedMessages, ...currentSession.messages],
                            messagesPage: {
                                hasMore: Boolean(response.data.messages_page?.has_more),
                                oldestSeq: typeof response.data.messages_page?.oldest_seq === 'number'
                                    ? response.data.messages_page.oldest_seq
                                    : null,
                                loading: false,
                            },
                        }
                    }))
                } catch (error) {
                    console.error('Failed to load older canvas messages:', error)
                    set((state) => applyConversationSessionUpdate(state, targetConversationId, (currentSession) => ({
                        ...currentSession,
                        messagesPage: { ...getMessagesPage(currentSession), loading: false },
                    })))
                }
            },

            sendMessage: async (content, attachments, options) => {
                const { conversationId, projectId, mode, activeSkillId, modelPreferences } = get()
                const effectiveModelPreferences = {
                    ...modelPreferences,
                    ...(options?.modelPreferences || {}),
                }

                // Auto-create conversation if none exists
                let convId = conversationId
                if (!convId) {
                    if (projectId) {
                        await get().createHarnessConversation(activeSkillId || undefined, {
                            modelPreferences: effectiveModelPreferences,
                            preserveResolvedSkill: true,
                        })
                    }
                    convId = get().conversationId
                }
                if (!convId) return

                const currentState = get()
                const effectiveSkillId = normalizeCanvasResolvedSkillId(currentState.activeSkillId, currentState.uiConfig)
                const canvasSkillPolicy = resolveCanvasSkillPolicy(currentState.uiConfig)
                const requestSkillId = effectiveSkillId === canvasSkillPolicy.defaultSkillId
                    ? effectiveSkillId
                    : resolveCanvasRequestSkillId(effectiveSkillId, currentState.uiConfig)
                const artifactMode = resolveCanvasSkillArtifactMode(requestSkillId)
                const effectiveWebSearchEnabled = currentState.webSearchEnabled

                const targetConversationId = convId
                const existingMessages = get().messages
                const isFirstUserMessageInConversation = existingMessages.length === 0
                const nextConversationTitle = summarizeConversationTitle(content)

                // Add user message to UI immediately
                const userMsg: ChatMessage = {
                    id: `temp-${Date.now()}`,
                    role: 'user',
                    content,
                    attachments: attachments?.map((a) => ({
                        type: a.type,
                        url: a.url,
                        name: a.name,
                        reference: a.reference,
                        preview_url: a.preview_url,
                    })),
                    skillId: activeSkillId,
                    createdAt: new Date().toISOString(),
                }
                const abortController = new AbortController()
                set((s) => {
                    const sessionPatch = applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                        ...session,
                        messages: [...session.messages, userMsg],
                        runStatus: 'running',
                        isStreaming: true,
                        currentStreamText: '',
                        currentToolCalls: [],
                        streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                        abortController,
                    }))
                    return mergeChatStatePatches(
                        s,
                        sessionPatch,
                        {
                            conversations: isFirstUserMessageInConversation
                                ? s.conversations.map((conversation) => (
                                    isSameConversationId(conversation.id, targetConversationId) && shouldReplaceConversationTitle(conversation.title)
                                        ? { ...conversation, title: nextConversationTitle }
                                        : conversation
                                ))
                                : s.conversations,
                        },
                    )
                })

                let sawTurnCompleted = false
                let sendError: any = null
                try {
                    // Strip _localFile from attachments before sending to API
                    const cleanAttachments = attachments?.map(stripTransientAttachmentFields)
                    const data: SendMessageRequest = {
                        content,
                        attachments: cleanAttachments,
                        references: options?.references ?? null,
                        mode,
                        skill_id: requestSkillId,
                        ...(requestSkillId ? { skill_selection_mode: 'manual' as const } : {}),
                        ...(artifactMode ? { artifact_mode: artifactMode } : {}),
                        web_search_enabled: effectiveWebSearchEnabled,
                        model_preferences: effectiveModelPreferences,
                    }

                    // If the user stopped a run and immediately re-submitted, the
                    // backend may still be tearing the previous run down and reject
                    // this send with a 409; recover it instead of getting stuck.
                    const stream = withHarnessActiveRunRetry(
                        String(targetConversationId),
                        abortController.signal,
                        () => streamHarnessSendMessage(
                            String(targetConversationId),
                            data,
                            abortController.signal,
                            getConversationSession(get(), targetConversationId).lastSequence,
                        ),
                    )
                    for await (const event of stream) {
                        if (isTurnCompletedEvent(event)) {
                            sawTurnCompleted = true
                        }
                        handleAgentEventV2(event, set, get, targetConversationId)
                    }
                } catch (err: any) {
                    if (err.name !== 'AbortError') {
                        sendError = err
                        set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                            ...session,
                            messages: [...session.messages, {
                                id: `error-${Date.now()}`,
                                role: 'assistant',
                                content: `Error: ${err.message}`,
                                createdAt: new Date().toISOString(),
                            }],
                        })))
                    }
                } finally {
                    const settleConversationStream = async () => {
                        const currentSession = getConversationSession(get(), targetConversationId)
                        if (currentSession.runStatus === 'cancelled') {
                            finalizeStreamV2(set, get, targetConversationId)
                            return
                        }
                        if (sawTurnCompleted) {
                            finalizeStreamV2(set, get, targetConversationId)
                            return
                        }
                        const resumed = await resumeHarnessConversationEventsAfterPostClose(
                            String(targetConversationId),
                            abortController.signal,
                            set,
                            get,
                        )
                        if (abortController.signal.aborted || resumed) {
                            return
                        }
                        if (sendError) {
                            // The send failed before a turn could start (e.g. a 409 while a
                            // prior run was still cancelling). Reset the streaming state so the
                            // UI does not stay stuck on "thinking" and the user can retry.
                            set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                                ...session,
                                runStatus: 'failed',
                                isStreaming: false,
                                streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                                currentStreamText: '',
                                currentToolCalls: [],
                                abortController: null,
                            })))
                            return
                        }
                        set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                            ...session,
                            abortController: null,
                        })))
                    }
                    await settleConversationStream()
                }
            },

            stopStreaming: () => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)
                const session = getConversationSession(get(), targetConversationId)
                const cancelledAt = new Date().toISOString()

                session.abortController?.abort()
                session.eventStreamController?.abort()

                set((state) => {
                    const sessionPatch = applyConversationSessionUpdate(state, targetConversationId, (currentSession) => ({
                        ...currentSession,
                        runStatus: 'cancelled',
                        isStreaming: false,
                        abortController: null,
                        eventStreamController: null,
                    }))
                    return mergeChatStatePatches(
                        state,
                        sessionPatch,
                        {
                            conversations: state.conversations.map((conversation) => (
                                isSameConversationId(conversation.id, targetConversationId)
                                    ? {
                                        ...conversation,
                                        runtime_status: 'cancelled',
                                        run_state: 'cancelled',
                                        finished_at: conversation.finished_at ?? cancelledAt,
                                    }
                                    : conversation
                            )),
                        },
                    )
                })
                finalizeStreamV2(set, get, targetConversationId)

                void agentApi.cancelHarnessConversationRun(targetConversationId)
                    .then((response) => {
                        const detail = response.data
                        if (!detail || detail.runtime_status !== 'cancelled') {
                            return
                        }
                        const snapshotProjection = buildCanvasHarnessProjectionFromSnapshot(detail as HarnessConversationSnapshotDetail)
                        set((state) => {
                            const currentSession = getConversationSession(state, targetConversationId)
                            if (currentSession.runStatus !== 'cancelled') {
                                return state
                            }
                            const existingIdx = state.conversations.findIndex((conversation) => isSameConversationId(conversation.id, detail.id))
                            let newConversations = [...state.conversations]
                            const convMeta: HarnessConversationRead = {
                                id: detail.id,
                                title: detail.title,
                                skill_id: detail.skill_id,
                                phase: detail.phase,
                                mode: detail.mode,
                                web_search_enabled: detail.web_search_enabled ?? false,
                                status: detail.status,
                                runtime_status: detail.runtime_status,
                                engine_version: 'harness',
                                run_id: detail.run_id,
                                started_at: detail.started_at,
                                finished_at: detail.finished_at,
                                created_at: detail.created_at,
                                updated_at: detail.updated_at,
                            }
                            if (existingIdx >= 0) {
                                newConversations[existingIdx] = convMeta
                            } else {
                                newConversations = [convMeta, ...newConversations]
                            }

                            const sessionPatch = applyConversationSessionUpdate(state, targetConversationId, (sessionToUpdate) => {
                                    const nextSession = projectionToCanvasSession(snapshotProjection, sessionToUpdate, detail)
                                    return {
                                        ...nextSession,
                                        messages: snapshotProjection.messages.length > 0
                                            ? nextSession.messages
                                            : sessionToUpdate.messages,
                                        abortController: null,
                                        eventStreamController: null,
                                    }
                            })
                            return mergeChatStatePatches(
                                state,
                                sessionPatch,
                                { conversations: newConversations },
                            )
                        })
                    })
                    .catch((err) => {
                        console.error('Failed to cancel harness conversation:', err)
                    })
            },

            approvePlan: async (planId) => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)

                const abortController = new AbortController()
                set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                    ...session,
                    isStreaming: true,
                    abortController,
                })))

                try {
                    void planId
                } catch (err: any) {
                    if (err.name !== 'AbortError') {
                        console.error('Plan execution error:', err)
                    }
                } finally {
                    finalizeStreamV2(set, get, targetConversationId)
                }
            },

            rejectPlan: async (planId, feedback) => {
                void planId
                void feedback
            },

            respondToAgent: async (requestId, answer, displayLabel?, answers?) => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = conversationId
                const replyLabel = displayLabel || answer

                const abortController = new AbortController()
                set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => {
                    const baseSession = {
                        ...session,
                        messages: markInteractionSubmittedWithAnswer(
                            session.messages,
                            requestId,
                            answer,
                            displayLabel,
                            answers,
                        ),
                    }
                    const projected = optimisticInteractionSubmissionOps({
                        requestId,
                        answer,
                        answers: answers || session.pendingInteraction?.answers || null,
                        displayLabel: replyLabel,
                        kind: optimisticInteractionKind(session.pendingInteraction?.kind),
                    }).reduce(
                        (current, op) => applyPresentationOpToSession(current, op),
                        baseSession,
                    )
                    return {
                        ...projected,
                        pendingInteraction: null,
                        runStatus: 'running',
                        isStreaming: true,
                        currentStreamText: '',
                        currentToolCalls: [],
                        streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                        abortController,
                    }
                }))

                let sawTurnCompleted = false
                let sendError: any = null
                try {
                    const respondStream = withHarnessActiveRunRetry(
                        String(targetConversationId),
                        abortController.signal,
                        () => streamHarnessRespondToAgent(
                            String(targetConversationId),
                            {
                                request_id: requestId,
                                answer,
                                answers: answers || undefined,
                                display_label: replyLabel,
                            },
                            abortController.signal,
                            getConversationSession(get(), targetConversationId).lastSequence,
                        ),
                    )
                    for await (const event of respondStream) {
                        if (isTurnCompletedEvent(event)) {
                            sawTurnCompleted = true
                        }
                        handleAgentEventV2(event, set, get, targetConversationId)
                    }
                } catch (err: any) {
                    if (err.name !== 'AbortError') {
                        sendError = err
                        console.error('Agent resume error:', err)
                    }
                } finally {
                    const settleConversationStream = async () => {
                        const currentSession = getConversationSession(get(), targetConversationId)
                        if (currentSession.runStatus === 'cancelled') {
                            finalizeStreamV2(set, get, targetConversationId)
                            return
                        }
                        if (sawTurnCompleted) {
                            finalizeStreamV2(set, get, targetConversationId)
                            return
                        }
                        const resumed = await resumeHarnessConversationEventsAfterPostClose(
                            String(targetConversationId),
                            abortController.signal,
                            set,
                            get,
                        )
                        if (abortController.signal.aborted || resumed) {
                            return
                        }
                        if (sendError) {
                            // The action failed before a turn could start (e.g. a 409 while a
                            // prior run was still cancelling). Reset the streaming state so the
                            // UI does not stay stuck on "thinking" and the user can retry.
                            set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                                ...session,
                                runStatus: 'failed',
                                isStreaming: false,
                                streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                                currentStreamText: '',
                                currentToolCalls: [],
                                abortController: null,
                            })))
                            return
                        }
                        set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                            ...session,
                            abortController: null,
                        })))
                    }
                    await settleConversationStream()
                }
            },

            setMode: (mode) => set({ mode }),
            activateSkill: (skillId) => set((s) => ({
                activeSkillId: normalizeCanvasSelectedSkillId(skillId, s.uiConfig),
            })),
            setWebSearchEnabled: (enabled) => set({ webSearchEnabled: enabled }),
            setModelPreferences: (prefs) => set((s) => ({
                modelPreferences: { ...s.modelPreferences, ...prefs }
            })),

            updateToolCall: (messageId, callId, updates) => {
                set((s) => {
                    const applyToolCallUpdates = (messages: ChatMessage[], currentToolCalls: ToolCallInfo[], streamingBlocks: MessageBlock[]) => ({
                        messages: messages.map((m) =>
                            m.id === messageId
                                ? {
                                    ...m,
                                    toolCalls: m.toolCalls?.map((tc) =>
                                        tc.callId === callId ? { ...tc, ...updates } : tc
                                    ),
                                    blocks: m.blocks?.map((block) =>
                                        applyToolCallUpdatesToBlock(block, String(callId), updates)
                                    ),
                                }
                                : m
                        ),
                        currentToolCalls: currentToolCalls.map((tc) =>
                            tc.callId === callId ? { ...tc, ...updates } : tc
                        ),
                        streamingBlocks: streamingBlocks.map((block) =>
                            applyToolCallUpdatesToBlock(block, String(callId), updates)
                        ),
                    })

                    if (s.conversationId != null) {
                        return applyConversationSessionUpdate(s, s.conversationId, (session) => ({
                            ...session,
                            ...applyToolCallUpdates(session.messages, session.currentToolCalls, session.streamingBlocks),
                        }))
                    }

                    return applyToolCallUpdates(s.messages, s.currentToolCalls, s.streamingBlocks)
                })
            },

            updateToolCallByGenerationTask: (conversationId, snapshot) => {
                set((s) => applyConversationSessionUpdate(s, conversationId, (session) => ({
                    ...session,
                    messages: updateToolCallsByGenerationTask(session.messages, snapshot),
                    currentToolCalls: updateToolCallsByGenerationTask([{
                        id: '__current_generation_calls__',
                        role: 'assistant',
                        content: null,
                        createdAt: new Date().toISOString(),
                        toolCalls: session.currentToolCalls,
                    }], snapshot)[0]?.toolCalls || session.currentToolCalls,
                    streamingBlocks: updateBlocksByGenerationTask(session.streamingBlocks, snapshot),
                })))
            },

            updateCanvasItemByGenerationTask: (conversationId, canvasItem) => {
                const state = get()
                if (
                    state.conversationId == null
                    || conversationId == null
                    || String(state.conversationId) !== String(conversationId)
                ) {
                    return
                }
                state.onCanvasUpdate?.('update', {
                    ...canvasItem,
                    conversationId: canvasItem.conversationId ?? conversationId,
                })
            },

            updateCanvasRevisionByAgentPatch: (canvasRevision, options) => {
                const state = get()
                state.onCanvasUpdate?.('sync_canvas_revision', {}, {
                    canvasRevision,
                    canvasItemDeleted: options?.canvasItemDeleted === true,
                })
            },

            createHarnessConversation: async (skillId, options) => {
                const { mode, activeSkillId, modelPreferences, webSearchEnabled, projectId, uiConfig } = get()
                if (!projectId) {
                    return
                }
                const effectiveSkillId = skillId === undefined ? activeSkillId : skillId
                const requestSkillId = resolveCanvasRequestSkillId(effectiveSkillId, uiConfig)
                const artifactMode = resolveCanvasSkillArtifactMode(requestSkillId)
                const effectiveModelPreferences = {
                    ...modelPreferences,
                    ...(options?.modelPreferences || {}),
                }
                const res = await agentApi.createHarnessConversation({
                    mode,
                    runtime_profile: 'canvas',
                    project_id: projectId,
                    skill_id: requestSkillId,
                    ...(requestSkillId ? { skill_selection_mode: 'manual' as const } : {}),
                    ...(artifactMode ? { artifact_mode: artifactMode } : {}),
                    web_search_enabled: webSearchEnabled,
                    model_preferences: effectiveModelPreferences,
                })
                const newConv = res.data
                const nextSession = createEmptyConversationSession()
                set((s) => ({
                    conversationId: newConv.id,
                    engineVersion: 'harness',
                    messages: [],
                    activePlan: null,
                    pendingInteraction: null,
                    projectId,
                    activeSkillId: options?.preserveResolvedSkill
                        ? normalizeCanvasResolvedSkillId(newConv.skill_id ?? effectiveSkillId ?? null, uiConfig)
                        : normalizeCanvasSelectedSkillId(newConv.skill_id ?? effectiveSkillId ?? null, uiConfig),
                    webSearchEnabled: newConv.web_search_enabled ?? webSearchEnabled,
                    modelPreferences: effectiveModelPreferences,
                    workspaceFiles: [],
                    conversationSessions: {
                        ...s.conversationSessions,
                        [getConversationSessionKey(newConv.id)]: nextSession,
                    },
                    conversations: [newConv, ...s.conversations],
                }))
            },

            newChat: () => {
                const currentConversationId = get().conversationId
                abortAllConversationStreams(get())
                if (currentConversationId != null) {
                    disposeConversationGenerationTasks(String(currentConversationId))
                }
                set({
                    conversationId: null,
                    messages: [],
                    activePlan: null,
                    pendingInteraction: null,
                    isStreaming: false,
                    currentStreamText: '',
                    currentToolCalls: [],
                    streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                    workspaceFiles: [],
                    engineVersion: 'harness',
                    _abortController: null,
                })
            },

            reset: () => {
                const currentConversationId = get().conversationId
                abortAllConversationStreams(get())
                if (currentConversationId != null) {
                    disposeConversationGenerationTasks(String(currentConversationId))
                }
                set({
                    ...initialState,
                    onCanvasUpdate: get().onCanvasUpdate
                })
            },
            setOnCanvasUpdate: (handler) => set({ onCanvasUpdate: handler }),
        }),
        { name: 'ChatStore' }
    )
)

export const __chatStoreTestUtils = {
    normalizeCanvasSelectedSkillId,
    normalizeCanvasResolvedSkillId,
    resolveCanvasRequestSkillId,
    applyToolCallUpdatesToBlock,
    upsertStreamingToolResultBlock,
    extractMessageText,
    buildHarnessUiMessages,
    getBlockIdentityKeys,
    hasEquivalentBlock,
    handleAgentEventV2,
    flushPendingStreamBlockDeltas,
    clearPendingStreamBlockDeltas,
}
