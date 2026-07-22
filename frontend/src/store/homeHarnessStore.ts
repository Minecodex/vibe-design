import { create } from 'zustand'
import { devtools } from 'zustand/middleware'
import { toast } from 'sonner'
import i18n from '@/i18n'
import {
    agentApi,
    streamHarnessSendMessage,
    streamHarnessRespondToAgent,
    streamHarnessStartExecution,
    streamHarnessRevisePlan,
    streamHarnessConversationEvents,
    type AgentEvent,
    type SendMessageRequest,
    type HarnessConversationRead,
    type HarnessConversationDetailRead,
} from '@/api/endpoints/agent'
import {
    applyConversationSessionUpdate,
    buildActiveConversationMetadataUpdates,
    buildConversationMetaOverridesFromEvent,
    applyHomeHarnessEvent,
    applyProjectionStateToSession,
    buildActiveConversationFields,
    buildHarnessConversationMeta,
    buildHarnessUiMessages,
    buildProjectionStateFromSession,
    buildSnapshotProjectionFromDetail,
    createEmptyConversationSession,
    dedupePlanArtifactMessages,
    extractMessageText,
    fetchHarnessConversationDetailSnapshot,
    filterHomepageBlocks,
    finalizeHomeHarnessProjection,
    getConversationSession,
    getConversationSessionKey,
    getMessagesPage,
    initialState,
    normalizeHiddenToolCalls,
    preserveLocalAssistantMessages,
    shouldReplaceConversationTitle,
    summarizeConversationTitle,
    updateConversationMetaFromSession,
    upsertWorkspaceFileInSession,
    type ChatActions,
    type ChatMessage,
    type ChatState,
    type ConversationSessionState,
    type HomeHarnessProjectionEvent,
    type HomeHarnessProjectionState,
    type MessageBlock,
    type ToolCallInfo,
} from './homeHarnessStoreSession'
import { buildHomeMediaReferences } from './homeMessageReferences'
import { stripTransientAttachmentFields } from '@/pages/dashboard/agentMedia/agentPendingAttachmentPreview'
import { shouldReconnectTurnStream } from './harnessStreamLifecycle'
import { withHarnessActiveRunRetry } from './harnessRunSettle'
import { startHarnessStreamSession } from './harnessStreamSession'
import { isTurnCompletedEvent, isTurnDoneForTransport } from './harnessTurnProtocol'
import {
    isHarnessConversationActiveStatus,
    isHarnessConversationTerminalStatus,
    resolveHarnessTerminalRunStatus,
} from './harnessTerminalEvents'
import { isPresentationOpEvent } from './harnessMessageProjection/cursor'
import { optimisticInteractionSubmissionOps } from './harnessMessageProjection/optimistic'
import {
    applyPresentationConversationPatchToMeta,
    extractPresentationConversationPatch,
    hasPresentationSkillPatch,
} from './harnessMessageProjection/conversationPatch'
import { shouldApplyRuntimeAdapterEvent } from './harnessMessageProjection/protocol'
import { applyPresentationOpToSession } from './harnessMessageProjection/reducer'

export type {
    ChatMessage,
    MessageBlock,
    ModelPreferences,
    ToolCallInfo,
} from './homeHarnessStoreSession'

let loadHarnessUiConfigRequest: Promise<void> | null = null
let loadHarnessConversationsRequest: Promise<void> | null = null
let loadHarnessConversationRequestSeq = 0
let loadHarnessConversationAbortController: AbortController | null = null
const HARNESS_STREAM_RECONNECT_DELAY_MS = 750

function buildMessagesPageState(detail: HarnessConversationDetailRead): ConversationSessionState['messagesPage'] {
    return {
        hasMore: Boolean(detail.messages_page?.has_more),
        oldestSeq: typeof detail.messages_page?.oldest_seq === 'number' ? detail.messages_page.oldest_seq : null,
        loading: false,
    }
}

function findSubmittedInteractionBlock(messages: ChatMessage[], requestId: string): MessageBlock | null {
    for (const message of messages) {
        for (const block of message.blocks || []) {
            if (
                block.uiKind === 'interaction_form'
                && String(block.payload?.requestId || block.payload?.request_id || '').trim() === requestId
                && String(block.payload?.status || '').trim() === 'submitted'
            ) {
                return block
            }
        }
    }
    return null
}

function findPendingInteractionRequestIds(messages: ChatMessage[]): string[] {
    const requestIds: string[] = []
    const seen = new Set<string>()
    for (const message of messages) {
        for (const block of message.blocks || []) {
            if (
                block.uiKind !== 'interaction_form'
                || String(block.payload?.status || '').trim() !== 'pending'
            ) {
                continue
            }
            const requestId = String(block.payload?.requestId || block.payload?.request_id || '').trim()
            if (!requestId || seen.has(requestId)) {
                continue
            }
            seen.add(requestId)
            requestIds.push(requestId)
        }
    }
    return requestIds
}

function restoreSubmittedInteractionBlock(
    messages: ChatMessage[],
    requestId: string,
    submittedBlock: MessageBlock,
): ChatMessage[] {
    let didUpdate = false
    const nextMessages = messages.map((message) => {
        if (!message.blocks?.length) {
            return message
        }
        let messageUpdated = false
        const nextBlocks = message.blocks.map((block) => {
            if (
                block.uiKind !== 'interaction_form'
                || String(block.payload?.requestId || block.payload?.request_id || '').trim() !== requestId
            ) {
                return block
            }
            didUpdate = true
            messageUpdated = true
            return {
                ...block,
                payload: {
                    ...block.payload,
                    ...submittedBlock.payload,
                    request_id: block.payload.request_id ?? submittedBlock.payload.request_id,
                    requestId: block.payload.requestId ?? submittedBlock.payload.requestId,
                },
            }
        })
        return messageUpdated ? { ...message, blocks: nextBlocks } : message
    })
    return didUpdate ? nextMessages : messages
}

function preserveSubmittedInteractionAfterSnapshot(
    existingSession: ConversationSessionState,
    snapshotProjection: HomeHarnessProjectionState,
    incomingMessages: ChatMessage[],
): Pick<HomeHarnessProjectionState, 'messages' | 'userInteraction'> {
    const requestId = String(
        snapshotProjection.userInteraction?.request_id
        || (snapshotProjection.userInteraction as any)?.requestId
        || '',
    ).trim()
    const requestIds = requestId ? [requestId] : findPendingInteractionRequestIds(incomingMessages)
    if (!requestIds.length) {
        return {
            messages: incomingMessages,
            userInteraction: snapshotProjection.userInteraction,
        }
    }

    let messages = incomingMessages
    let userInteraction = snapshotProjection.userInteraction
    for (const candidateRequestId of requestIds) {
        const submittedBlock = findSubmittedInteractionBlock(existingSession.messages, candidateRequestId)
        if (!submittedBlock) {
            continue
        }
        messages = restoreSubmittedInteractionBlock(messages, candidateRequestId, submittedBlock)
        if (candidateRequestId === requestId) {
            userInteraction = null
        }
    }

    return {
        messages,
        userInteraction,
    }
}

function resolveDesignSystemIdFromInteractionAnswer(
    kind: string | null | undefined,
    answer: string,
    answers?: Record<string, any> | null,
): string | null {
    const normalizedKind = String(kind || '').trim()
    if (normalizedKind !== 'design_system_picker') {
        return null
    }

    let payload = answers && typeof answers === 'object' ? answers : null
    if (!payload) {
        try {
            const parsed = JSON.parse(String(answer || ''))
            payload = parsed && typeof parsed === 'object' && !Array.isArray(parsed)
                ? parsed as Record<string, any>
                : null
        } catch {
            payload = null
        }
    }

    return String(payload?.design_system_id ?? '').trim() || null
}

function buildSnapshotConversationMeta(
    detail: HarnessConversationRead,
    state: ChatState,
): HarnessConversationRead {
    const meta = buildHarnessConversationMeta(detail)
    const activeSelectedDesignSystemId = String(state.selectedDesignSystemId || '').trim()
    if (
        meta.design_system_id
        || String(state.conversationId || '') !== String(detail.id || '')
        || !activeSelectedDesignSystemId
    ) {
        return meta
    }
    return {
        ...meta,
        design_system_id: activeSelectedDesignSystemId,
    }
}

async function refreshHarnessConversationFromServer(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
): Promise<HarnessConversationRead | null> {
    try {
        const detail = await fetchHarnessConversationDetailSnapshot(conversationId)
        if (!detail) {
            return null
        }
        const snapshotProjection = buildSnapshotProjectionFromDetail(detail)
        set((s) => {
            const existingIdx = s.conversations.findIndex(c => c.id === detail.id)
            let newConversations = [...s.conversations]
            const convMeta = buildSnapshotConversationMeta(detail, s)
            if (existingIdx >= 0) {
                newConversations[existingIdx] = convMeta
            } else {
                newConversations = [convMeta, ...newConversations]
            }

            return {
                    ...applyConversationSessionUpdate(s, conversationId, (session) => {
                        const keepLiveSession = shouldKeepHomeHarnessLiveSession(session, snapshotProjection)
                        const snapshotIsTerminal = isHarnessConversationTerminalStatus(snapshotProjection.runStatus)
                        const keepSnapshotlessMessages = snapshotProjection.messages.length === 0 && session.messages.length > 0
                        const incomingMessages = keepLiveSession || keepSnapshotlessMessages
                            ? session.messages
                            : preserveLocalAssistantMessages(session.messages, snapshotProjection.messages)
                        const restoredInteraction = preserveSubmittedInteractionAfterSnapshot(
                            session,
                            snapshotProjection,
                            incomingMessages,
                        )
                        const projectedSession = applyProjectionStateToSession(session, snapshotProjection)
                        return {
                            ...projectedSession,
                            messages: restoredInteraction.messages,
                            userInteraction: restoredInteraction.userInteraction,
                            isStreaming: keepLiveSession ? session.isStreaming : projectedSession.isStreaming,
                            currentStreamText: keepLiveSession ? session.currentStreamText : projectedSession.currentStreamText,
                            currentToolCalls: keepLiveSession ? session.currentToolCalls : projectedSession.currentToolCalls,
                            streamingBlocks: keepLiveSession ? session.streamingBlocks : projectedSession.streamingBlocks,
                            abortController: keepLiveSession ? session.abortController : (snapshotIsTerminal ? null : projectedSession.abortController),
                            runStatus: keepLiveSession ? session.runStatus : projectedSession.runStatus,
                            messagesPage: buildMessagesPageState(detail),
                            lastSequence: keepLiveSession
                                ? session.lastSequence
                                : Math.max(session.lastSequence, snapshotProjection.lastSequence),
                        }
                    }),
                conversations: newConversations,
                ...buildActiveConversationMetadataUpdates(s, detail),
            }
        })
        return detail
    } catch (err) {
        console.error('Failed to refresh harness conversation:', err)
        return null
    }
}

function applyMissingTurnCompletedProtocolError(
    conversationId: string,
    runtimeStatus: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
): void {
    handleAgentEventV2({
        type: 'protocol_error',
        transient: true,
        data: {
            reason: 'missing_turn_completed',
            runtime_status: runtimeStatus,
        },
    } as AgentEvent, set, get, conversationId)
    console.error('Harness protocol error: missing turn_completed', {
        conversationId,
        runtimeStatus,
    })
}

async function reconcileTurnStreamAfterTransportClose(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
): Promise<boolean> {
    const detail = await refreshHarnessConversationFromServer(conversationId, set)
    if (!detail) {
        return false
    }

    const resolvedSession = getConversationSession(get(), conversationId)
    if (shouldReconnectTurnStream(detail)) {
        set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
            ...session,
            abortController: null,
        })))
        if (!resolvedSession.eventStreamController) {
            subscribeToHarnessConversationEvents(conversationId, set, get)
        }
        return true
    }

    if (isTurnDoneForTransport(detail.runtime_status) && detail.runtime_status !== 'waiting_input') {
        applyMissingTurnCompletedProtocolError(conversationId, detail.runtime_status, set, get)
    }
    set((state) => stopConversationEventStream(state, conversationId))
    return false
}

async function refreshHomeHarnessWorkspaceFiles(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
): Promise<void> {
    try {
        const res = await agentApi.listWorkspaceFiles(conversationId)
        set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
            ...session,
            workspaceFiles: Array.isArray(res.data) ? res.data : [],
        })))
    } catch (err) {
        console.error('Failed to refresh home harness workspace files:', err)
    }
}

const homeHarnessWorkspaceRefreshTimers = new Map<string, ReturnType<typeof setTimeout>>()

function clearHomeHarnessWorkspaceFilesRefreshTimers(): void {
    for (const timer of homeHarnessWorkspaceRefreshTimers.values()) {
        clearTimeout(timer)
    }
    homeHarnessWorkspaceRefreshTimers.clear()
}

function scheduleHomeHarnessWorkspaceFilesRefresh(
    conversationId: number | string | null | undefined,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    delayMs = 350,
): void {
    const normalizedConversationId = String(conversationId || '').trim()
    if (!normalizedConversationId || homeHarnessWorkspaceRefreshTimers.has(normalizedConversationId)) {
        return
    }

    const timer = setTimeout(() => {
        homeHarnessWorkspaceRefreshTimers.delete(normalizedConversationId)
        void refreshHomeHarnessWorkspaceFiles(normalizedConversationId, set)
    }, delayMs)
    homeHarnessWorkspaceRefreshTimers.set(normalizedConversationId, timer)
}

function shouldRefreshWorkspaceFilesAfterEvent(event: AgentEvent): boolean {
    return [
        'artifact_publish_validated',
        'file_current_version_changed',
        'file_published',
        'file_version_created',
        'turn_completed',
        'workspace_file_upserted',
    ].includes(String(event.type || ''))
}

function shouldKeepHarnessConversationTransportAlive(
    session: Pick<ConversationSessionState, 'runStatus' | 'userInteraction' | 'runtimeState' | 'activeUserPlan' | 'outlineRuntime'>,
): boolean {
    if (isHarnessConversationActiveStatus(session.runStatus)) {
        return true
    }
    if (session.runStatus !== 'waiting_input' || session.userInteraction) {
        return false
    }

    return !isWaitingForPlanStart(session)
}

function isWaitingForPlanStart(
    session: Pick<ConversationSessionState, 'runtimeState' | 'activeUserPlan' | 'outlineRuntime'>,
): boolean {
    const runtimePhase = typeof session.runtimeState?.phase === 'string'
        ? session.runtimeState.phase
        : null
    const currentOutline = session.outlineRuntime?.current_outline ?? session.activeUserPlan ?? null
    const outlineStatus = String(
        currentOutline?.status
        || currentOutline?.projection_state?.status
        || session.outlineRuntime?.projection_state?.status
        || '',
    ).toLowerCase()

    return runtimePhase === 'planning_ready' || outlineStatus === 'planning_ready'
}

function hasApprovedPlanReadyForExecution(
    session: Pick<ConversationSessionState, 'outlineRuntime'>,
): boolean {
    const currentOutline = session.outlineRuntime?.current_outline ?? null
    const executionStatus = String(session.outlineRuntime?.execution_state?.status || '').toLowerCase()
    return Boolean(currentOutline) && executionStatus === 'planning_ready'
}

async function settleHarnessConversationStream(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
): Promise<boolean> {
    const currentSession = getConversationSession(get(), conversationId)
    if (currentSession.runStatus === 'cancelled') {
        finalizeStreamV2(set, get, conversationId, 'cancelled')
        return false
    }
    const reconciled = await reconcileTurnStreamAfterTransportClose(conversationId, set, get)
    if (reconciled) {
        return true
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

function shouldKeepHomeHarnessLiveSession(
    session: ConversationSessionState,
    projection: HomeHarnessProjectionState,
): boolean {
    if (isHarnessConversationTerminalStatus(projection.runStatus)) {
        return false
    }

    return isHarnessConversationActiveStatus(projection.runStatus) && hasHomeHarnessLocalLiveActivity(session)
}

function hasHomeHarnessLocalLiveActivity(
    session: Pick<ConversationSessionState, 'streamingBlocks' | 'abortController'>,
): boolean {
    return (
        Boolean(session.abortController)
        || session.streamingBlocks.length > 0
    )
}

function isActiveHarnessSend(
    get: () => ChatState & ChatActions,
    conversationId: number | string,
    abortController: AbortController,
): boolean {
    return getConversationSession(get(), conversationId).abortController === abortController
}

function stopConversationEventStream(
    state: ChatState,
    conversationId: number | string,
): Partial<ChatState> {
    const session = getConversationSession(state, conversationId)
    session.eventStreamController?.abort()
    return applyConversationSessionUpdate(state, conversationId, (currentSession) => ({
        ...currentSession,
        eventStreamController: null,
    }))
}

function abortAllConversationStreams(state: ChatState): void {
    state._abortController?.abort()
    for (const session of Object.values(state.conversationSessions)) {
        session.abortController?.abort()
        session.eventStreamController?.abort()
    }
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

function applyToolCallUpdatesToBlock(
    block: MessageBlock,
    callId: string,
    updates: Partial<ToolCallInfo>,
): MessageBlock {
    const nextChildren = block.children?.map((child) => applyToolCallUpdatesToBlock(child, callId, updates))
    const childrenChanged = !!nextChildren && nextChildren.some((child, index) => child !== block.children?.[index])
    const blockCallId = String(block.payload.callId || block.id)
    const incomingTaskId = updates.result?.task_id ?? updates.result?.taskId
    const blockTaskId = (
        block.payload.taskId
        ?? block.payload.result?.task_id
        ?? block.payload.result?.taskId
    )
    const taskIdMatches = incomingTaskId == null || blockTaskId == null || incomingTaskId === blockTaskId
    const isMatchingCall = blockCallId === callId && taskIdMatches

    if (!isMatchingCall) {
        return childrenChanged ? { ...block, children: nextChildren } : block
    }

    const nextPayload = { ...block.payload }
    const nextResult = updates.result
        ? { ...(nextPayload.result || {}), ...updates.result }
        : nextPayload.result

    if (nextResult) {
        nextPayload.result = nextResult
        nextPayload.progress = nextResult.progress ?? nextPayload.progress
        nextPayload.status = nextResult.status ?? nextPayload.status
        nextPayload.taskId = nextResult.task_id ?? nextResult.taskId ?? nextPayload.taskId
        nextPayload.previewUrl = nextResult.preview_url ?? nextResult.previewUrl ?? nextPayload.previewUrl
        nextPayload.resultUrl = nextResult.result_url ?? nextResult.resultUrl ?? nextPayload.resultUrl
        nextPayload.errorMessage = (
            nextResult.error_message
            ?? nextResult.errorMessage
            ?? nextResult.error
            ?? nextPayload.errorMessage
        )
    }

    if (updates.error !== undefined) {
        nextPayload.errorMessage = updates.error
    }
    if (updates.streamingText !== undefined) {
        nextPayload.streamText = updates.streamingText
    }
    if (updates.status !== undefined) {
        nextPayload.status = updates.status
    }

    return {
        ...block,
        status: updates.status ?? block.status,
        children: childrenChanged ? nextChildren : block.children,
        payload: nextPayload,
    }
}

function buildScopedReset(overrides: Partial<ChatState> = {}): Partial<ChatState> {
    return {
        conversationId: null,
        messages: [],
        activePlan: null,
        planningDraft: null,
        activeUserPlan: null,
        userProgress: null,
        userInteraction: null,
        isStreaming: false,
        runStatus: 'idle',
        currentStreamText: '',
        currentToolCalls: [],
        streamingBlocks: [],
        conversations: [],
        conversationsHasMore: false,
        conversationsPage: 1,
        _abortController: null,
        conversationSessions: {},
        ...overrides,
    }
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

            loadUiConfig: async () => {
                if (loadHarnessUiConfigRequest) {
                    return loadHarnessUiConfigRequest
                }

                loadHarnessUiConfigRequest = (async () => {
                    try {
                        const res = await agentApi.getUiConfig()
                        set({
                            uiConfig: {
                                hiddenToolCalls: normalizeHiddenToolCalls(res.data),
                            },
                        })
                    } finally {
                        loadHarnessUiConfigRequest = null
                    }
                })()

                return loadHarnessUiConfigRequest
            },

            loadConversations: async (_projectId) => {
                if (loadHarnessConversationsRequest) {
                    return loadHarnessConversationsRequest
                }

                loadHarnessConversationsRequest = (async () => {
                    try {
                        const res = await agentApi.listHarnessConversations(1, 20)
                        set({
                            conversations: res.data.items.map(buildHarnessConversationMeta),
                            conversationsPage: 1,
                            conversationsHasMore: res.data.has_more,
                            engineVersion: 'harness',
                        })
                    } finally {
                        loadHarnessConversationsRequest = null
                    }
                })()

                return loadHarnessConversationsRequest
            },

            loadConversation: async (id) => {
                const targetId = String(id)
                const requestSeq = ++loadHarnessConversationRequestSeq
                loadHarnessConversationAbortController?.abort()
                const detailAbortController = new AbortController()
                loadHarnessConversationAbortController = detailAbortController

                set((s) => {
                    const existingSession = getConversationSession(s, targetId)
                    const conversationMeta = s.conversations.find((conversation) => String(conversation.id) === targetId)
                    const selectedDesignSystemId = conversationMeta?.design_system_id ?? null
                    return {
                        conversationId: targetId,
                        ...buildActiveConversationFields(existingSession),
                        interactionProfile: conversationMeta?.interaction_profile === 'canvas_live_interaction'
                            ? 'canvas_live_interaction' as const
                            : initialState.interactionProfile,
                        mode: (conversationMeta?.mode as 'plan' | 'fast') || initialState.mode,
                        artifactMode: (conversationMeta?.artifact_mode as ChatState['artifactMode']) || initialState.artifactMode,
                        activeSkillId: conversationMeta?.skill_id ?? null,
                        skillSelectionMode: conversationMeta?.skill_selection_mode === 'manual' ? 'manual' : 'auto',
                        selectedDesignSystemId,
                        skillDecisionReason: conversationMeta?.last_skill_decision_reason ?? null,
                        skillDecisionConfidence: conversationMeta?.last_skill_decision_confidence ?? null,
                        webSearchEnabled: conversationMeta?.web_search_enabled ?? initialState.webSearchEnabled,
                        modelPreferences: conversationMeta?.model_preferences ?? { ...initialState.modelPreferences },
                        engineVersion: 'harness' as const,
                    }
                })

                let detail: HarnessConversationDetailRead | null = null
                try {
                    detail = await fetchHarnessConversationDetailSnapshot(targetId, detailAbortController.signal)
                } catch (error: any) {
                    if (error?.name === 'CanceledError' || error?.name === 'AbortError') {
                        return
                    }
                    throw error
                } finally {
                    if (loadHarnessConversationAbortController === detailAbortController) {
                        loadHarnessConversationAbortController = null
                    }
                }
                if (!detail) {
                    return
                }
                if (requestSeq !== loadHarnessConversationRequestSeq || String(get().conversationId || '') !== targetId) {
                    return
                }

                const snapshotProjection = buildSnapshotProjectionFromDetail(detail)

                set((s) => {
                    const existingIdx = s.conversations.findIndex(c => c.id === detail.id)
                    let newConversations = [...s.conversations]
                    const convMeta = buildHarnessConversationMeta(detail)

                    if (existingIdx >= 0) {
                        newConversations[existingIdx] = convMeta
                    } else {
                        newConversations = [convMeta, ...newConversations]
                    }

                    const existingSession = getConversationSession(s, detail.id)
                    const keepLiveSession = shouldKeepHomeHarnessLiveSession(existingSession, snapshotProjection)
                    const snapshotIsTerminal = isHarnessConversationTerminalStatus(snapshotProjection.runStatus)
                    const incomingMessages = keepLiveSession
                        ? existingSession.messages
                        : preserveLocalAssistantMessages(existingSession.messages, snapshotProjection.messages)
                    const restoredInteraction = preserveSubmittedInteractionAfterSnapshot(
                        existingSession,
                        snapshotProjection,
                        incomingMessages,
                    )
                    const projectedSession = applyProjectionStateToSession(existingSession, snapshotProjection)
                    const nextSession: ConversationSessionState = {
                        ...projectedSession,
                        messages: restoredInteraction.messages,
                        userInteraction: restoredInteraction.userInteraction,
                        isStreaming: keepLiveSession ? existingSession.isStreaming : projectedSession.isStreaming,
                        currentStreamText: keepLiveSession ? existingSession.currentStreamText : projectedSession.currentStreamText,
                        currentToolCalls: keepLiveSession ? existingSession.currentToolCalls : projectedSession.currentToolCalls,
                        streamingBlocks: keepLiveSession ? existingSession.streamingBlocks : projectedSession.streamingBlocks,
                        abortController: keepLiveSession ? existingSession.abortController : (snapshotIsTerminal ? null : projectedSession.abortController),
                        runStatus: keepLiveSession ? existingSession.runStatus : projectedSession.runStatus,
                        runtimeState: snapshotProjection.runtimeState,
                        messagesPage: buildMessagesPageState(detail),
                        lastSequence: keepLiveSession
                            ? existingSession.lastSequence
                            : Math.max(existingSession.lastSequence, snapshotProjection.lastSequence),
                    }
                    const conversationSessions = {
                        ...s.conversationSessions,
                        [getConversationSessionKey(detail.id)]: nextSession,
                    }
                    return {
                        conversationId: detail.id,
                        ...buildActiveConversationFields(nextSession),
                        ...buildActiveConversationMetadataUpdates(
                            {
                                ...s,
                                conversationId: detail.id,
                            },
                            detail,
                        ),
                        mode: detail.mode as 'plan' | 'fast',
                        artifactMode: (detail.artifact_mode as ChatState['artifactMode']) || 'web',
                        activeSkillId: detail.skill_id,
                        skillSelectionMode: detail.skill_selection_mode === 'manual' ? 'manual' : 'auto',
                        skillDecisionReason: detail.last_skill_decision_reason ?? null,
                        skillDecisionConfidence: detail.last_skill_decision_confidence ?? null,
                        webSearchEnabled: detail.web_search_enabled ?? initialState.webSearchEnabled,
                        modelPreferences: detail.model_preferences ?? { ...initialState.modelPreferences },
                        engineVersion: 'harness',
                        conversations: newConversations,
                        conversationSessions,
                    }
                })
                const resolvedSession = getConversationSession(get(), detail.id)
                if (
                    shouldReconnectTurnStream(detail)
                    && !resolvedSession.eventStreamController
                ) {
                    subscribeToHarnessConversationEvents(String(detail.id), set, get)
                } else if (!shouldReconnectTurnStream(detail)) {
                    set((state) => stopConversationEventStream(state, detail.id))
                }
            },

            sendMessage: async (content, attachments, options) => {
                const {
                    conversationId,
                    mode,
                    artifactMode,
                    webSearchEnabled,
                    modelPreferences,
                } = get()
                const effectiveModelPreferences = {
                    ...modelPreferences,
                    ...(options?.modelPreferences || {}),
                }

                // Auto-create conversation if none exists
                let convId = conversationId
                if (!convId) {
                    const draftState = get()
                    convId = await get().ensureHarnessConversation(draftState.activeSkillId || undefined, {
                        modelPreferences: effectiveModelPreferences,
                        artifactMode,
                    })
                }
                if (!convId) return

                const targetConversationId = convId
                const existingMessages = get().messages
                const isFirstUserMessageInConversation = existingMessages.length === 0
                const nextConversationTitle = summarizeConversationTitle(content)
                const optimisticSkillId = get().activeSkillId

                // Add user message to UI immediately
                const userMsg: ChatMessage = {
                    id: `temp-${Date.now()}`,
                    role: 'user',
                    content,
                    attachments: attachments?.map((a) => ({ type: a.type, url: a.url, name: a.name, preview_url: a.preview_url })),
                    baseFileVersions: options?.baseFileVersions || undefined,
                    skillId: optimisticSkillId,
                    createdAt: new Date().toISOString(),
                }
                const abortController = new AbortController()
                set((s) => ({
                    ...applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                        ...session,
                        messages: [...session.messages, userMsg],
                        isStreaming: true,
                        currentStreamText: '',
                        currentToolCalls: [],
                        streamingBlocks: [],
                        abortController,
                        runStatus: 'running',
                    })),
                    engineVersion: 'harness',
                    conversations: isFirstUserMessageInConversation
                        ? s.conversations.map((conversation) => (
                            conversation.id === targetConversationId && shouldReplaceConversationTitle(conversation.title)
                                ? { ...conversation, title: nextConversationTitle }
                                : conversation
                        ))
                        : s.conversations,
                }))

                const latestState = get()
                const effectiveSkillId = latestState.activeSkillId
                const effectiveSkillSelectionMode = latestState.skillSelectionMode
                const effectiveArtifactMode = latestState.artifactMode
                const selectedDesignSystemId = latestState.selectedDesignSystemId
                const effectiveSkillDecisionReason = latestState.skillDecisionReason
                const effectiveSkillDecisionConfidence = latestState.skillDecisionConfidence

                let sawTurnCompleted = false
                let sendError: any = null
                try {
                    // Strip _localFile from attachments before sending to API
                    const cleanAttachments = attachments?.map(stripTransientAttachmentFields)
                    const data: SendMessageRequest = {
                        content,
                        input_kind: options?.actionType ? 'user_ui_action' : 'user_text_message',
                        action_type: options?.actionType || null,
                        attachments: cleanAttachments,
                        references: buildHomeMediaReferences(cleanAttachments),
                        mode,
                        skill_id: effectiveSkillId,
                        skill_selection_mode: effectiveSkillSelectionMode,
                        artifact_mode: effectiveArtifactMode,
                        design_system_id: selectedDesignSystemId,
                        skill_decision_reason: effectiveSkillDecisionReason,
                        skill_decision_confidence: effectiveSkillDecisionConfidence,
                        web_search_enabled: webSearchEnabled,
                        model_preferences: effectiveModelPreferences,
                        base_file_versions: options?.baseFileVersions || null,
                    }

                    // If the user stopped a run and immediately re-submitted, the
                    // backend may still be tearing the previous run down and reject
                    // this send with a 409; recover it instead of getting stuck.
                    const stream = withHarnessActiveRunRetry(
                        targetConversationId as string,
                        abortController.signal,
                        () => streamHarnessSendMessage(
                            targetConversationId as string,
                            data,
                            abortController.signal,
                            getConversationSession(get(), targetConversationId).lastSequence,
                        ),
                        () => isActiveHarnessSend(get, targetConversationId, abortController),
                    )
                    for await (const event of stream) {
                        if (!isActiveHarnessSend(get, targetConversationId, abortController)) {
                            break
                        }
                        if (isTurnCompletedEvent(event)) {
                            sawTurnCompleted = true
                        }
                        handleAgentEventV2(event, set, get, targetConversationId)
                    }
                } catch (err: any) {
                    if (err.name !== 'AbortError' && isActiveHarnessSend(get, targetConversationId, abortController)) {
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
                    if (!isActiveHarnessSend(get, targetConversationId, abortController)) {
                        return
                    }
                    if (typeof targetConversationId === 'string') {
                        const currentSession = getConversationSession(get(), targetConversationId)
                        if (currentSession.runStatus === 'cancelled') {
                            finalizeStreamV2(set, get, targetConversationId, 'cancelled')
                            return
                        }
                        if (sawTurnCompleted) {
                            finalizeStreamV2(set, get, targetConversationId, getConversationSession(get(), targetConversationId).runStatus)
                            return
                        }
                        const resumed = await reconcileTurnStreamAfterTransportClose(targetConversationId, set, get)
                        if (resumed) {
                            return
                        }
                    }
                    if (sendError) {
                        // The send failed before a turn could start (e.g. a 409 while a
                        // prior run was still cancelling). Reset the streaming state so the
                        // UI does not stay stuck on "thinking" and the user can retry.
                        set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                            ...session,
                            runStatus: 'failed',
                            isStreaming: false,
                            streamingBlocks: [],
                            currentStreamText: '',
                            currentToolCalls: [],
                            abortController: null,
                        })))
                        return
                    }
                    set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                        ...session,
                        abortController: null,
                    })))
                }
            },

            stopStreaming: () => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = conversationId
                const session = getConversationSession(get(), targetConversationId)
                const cancelledAt = new Date().toISOString()

                session.abortController?.abort()
                session.eventStreamController?.abort()

                set((state) => ({
                    ...applyConversationSessionUpdate(state, targetConversationId, (currentSession) => (
                        applyProjectionStateToSession(
                            {
                                ...currentSession,
                                abortController: null,
                                eventStreamController: null,
                                isStreaming: false,
                                runStatus: 'cancelled',
                            },
                            finalizeHomeHarnessProjection(
                                buildProjectionStateFromSession(currentSession),
                                'cancelled',
                            ),
                        )
                    )),
                    conversations: state.conversations.map((conversation) => (
                        conversation.id === targetConversationId
                            ? buildHarnessConversationMeta({
                                ...conversation,
                                runtime_status: 'cancelled',
                                display_status: '已取消',
                                run_state: 'cancelled',
                                finished_at: conversation.finished_at ?? cancelledAt,
                            })
                            : conversation
                    )),
                }))

                if (typeof targetConversationId !== 'string') {
                    return
                }

                void agentApi.cancelHarnessConversationRun(targetConversationId)
                    .then((response) => {
                        const detail = response.data
                        if (!detail || detail.runtime_status !== 'cancelled') {
                            return
                        }
                        const snapshotProjection = buildSnapshotProjectionFromDetail(detail as HarnessConversationDetailRead)
                        set((state) => {
                            const currentSession = getConversationSession(state, targetConversationId)
                            if (currentSession.runStatus !== 'cancelled') {
                                return state
                            }
                            return {
                                ...applyConversationSessionUpdate(state, targetConversationId, (sessionToUpdate) => ({
                                    ...applyProjectionStateToSession(sessionToUpdate, snapshotProjection),
                                    messages: snapshotProjection.messages.length > 0
                                        ? snapshotProjection.messages
                                        : sessionToUpdate.messages,
                                    eventStreamController: null,
                                    abortController: null,
                                    userInteraction: snapshotProjection.userInteraction,
                                })),
                                conversations: state.conversations.map((conversation) => (
                                    conversation.id === targetConversationId
                                        ? buildHarnessConversationMeta(detail)
                                        : conversation
                                )),
                                ...buildActiveConversationMetadataUpdates(state, detail),
                            }
                        })
                    })
                    .catch((err) => {
                        console.error('Failed to cancel harness conversation:', err)
                    })
            },

            respondToAgent: async (requestId, answer, displayLabel?, approved?, answers?) => {
                let { conversationId } = get()
                if (!conversationId) {
                    conversationId = await get().ensureHarnessConversation()
                }
                if (!conversationId) return
                const targetConversationId = conversationId
                const replyLabel = displayLabel || answer
                const currentInteraction = (
                    getConversationSession(get(), targetConversationId).userInteraction
                    || get().userInteraction
                )
                const optimisticDesignSystemId = resolveDesignSystemIdFromInteractionAnswer(
                    currentInteraction?.kind,
                    answer,
                    answers,
                )

                const abortController = new AbortController()
                set((s) => {
                    const nextState = applyConversationSessionUpdate(s, targetConversationId, (session) => (
                        (() => {
                            const projected = optimisticInteractionSubmissionOps({
                                requestId,
                                answer,
                                answers: answers || session.userInteraction?.answers || null,
                                displayLabel: replyLabel,
                                approved,
                                kind: session.userInteraction?.kind || null,
                            }).reduce(
                                (current, op) => applyPresentationOpToSession(current, op),
                                session,
                            )
                            return {
                                ...projected,
                                pendingInteraction: null,
                                userInteraction: null,
                                isStreaming: true,
                                currentStreamText: '',
                                currentToolCalls: [],
                                streamingBlocks: [],
                                abortController,
                                runStatus: 'running',
                            }
                        })()
                    ))
                    if (!optimisticDesignSystemId) {
                        return nextState
                    }
                    return {
                        ...nextState,
                        selectedDesignSystemId: optimisticDesignSystemId,
                        conversations: (nextState.conversations ?? s.conversations).map((conversation) => (
                            String(conversation.id) === String(targetConversationId)
                                ? buildHarnessConversationMeta({
                                    ...conversation,
                                    design_system_id: optimisticDesignSystemId,
                                })
                                : conversation
                        )),
                    }
                })
                set({ engineVersion: 'harness' })

                let sawTurnCompleted = false
                let sendError: any = null
                try {
                    const respondStream = withHarnessActiveRunRetry(
                        targetConversationId as string,
                        abortController.signal,
                        () => streamHarnessRespondToAgent(
                            targetConversationId as string,
                            { request_id: requestId, answer, answers: answers || undefined, display_label: replyLabel, approved },
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
                    if (typeof targetConversationId === 'string') {
                        const currentSession = getConversationSession(get(), targetConversationId)
                        if (currentSession.runStatus === 'cancelled') {
                            finalizeStreamV2(set, get, targetConversationId, 'cancelled')
                            return
                        }
                        if (sawTurnCompleted) {
                            finalizeStreamV2(set, get, targetConversationId, getConversationSession(get(), targetConversationId).runStatus)
                            return
                        }
                        const resumed = await reconcileTurnStreamAfterTransportClose(targetConversationId, set, get)
                        if (resumed) {
                            return
                        }
                    }
                    if (sendError) {
                        // The action failed before a turn could start (e.g. a 409 while a
                        // prior run was still cancelling). Reset the streaming state so the
                        // UI does not stay stuck on "thinking" and the user can retry.
                        set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                            ...session,
                            runStatus: 'failed',
                            isStreaming: false,
                            streamingBlocks: [],
                            currentStreamText: '',
                            currentToolCalls: [],
                            abortController: null,
                        })))
                        return
                    }
                    set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                        ...session,
                        abortController: null,
                    })))
                }
            },

            startExecution: async () => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)
                const sessionBeforeStart = getConversationSession(get(), targetConversationId)
                if (!hasApprovedPlanReadyForExecution(sessionBeforeStart)) {
                    toast.error(i18n.t('home.planReview.startExecutionUnavailable', 'No approved plan is ready to execute.'))
                    return
                }
                const abortController = new AbortController()
                set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                    ...session,
                    isStreaming: true,
                    currentStreamText: '',
                    currentToolCalls: [],
                    streamingBlocks: [],
                    abortController,
                    runStatus: 'running',
                })))
                const executionTimestamp = new Date().toISOString()
                const currentState = get()
                const currentPlan = currentState.activeUserPlan ?? currentState.outlineRuntime?.current_outline ?? null
                const executingPlanPayload = currentPlan
                    ? {
                        ...currentPlan,
                        status: 'in_progress',
                    }
                    : null
                if (executingPlanPayload) {
                    handleAgentEventV2({
                        type: 'execution_started',
                        lane: 'user',
                        data: {
                            plan: executingPlanPayload,
                            created_at: executionTimestamp,
                        },
                    } as AgentEvent, set, get, targetConversationId)
                }
                handleAgentEventV2({
                    type: 'execution_progress_updated',
                    lane: 'user',
                    data: {
                        status: 'in_progress',
                        message: '开始执行',
                        completed_message: null,
                        created_at: executionTimestamp,
                    },
                } as AgentEvent, set, get, targetConversationId)
                let sawTurnCompleted = false
                let sendError: any = null
                try {
                    const stream = withHarnessActiveRunRetry(
                        targetConversationId,
                        abortController.signal,
                        () => streamHarnessStartExecution(
                            targetConversationId,
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
                    if (err?.name !== 'AbortError') {
                        sendError = err
                        console.error('Plan execution error:', err)
                    }
                } finally {
                    if (sawTurnCompleted) {
                        finalizeStreamV2(set, get, targetConversationId, getConversationSession(get(), targetConversationId).runStatus)
                        return
                    }
                    if (await reconcileTurnStreamAfterTransportClose(targetConversationId, set, get)) {
                        return
                    }
                    if (sendError) {
                        // The action failed before a turn could start (e.g. a 409 while a
                        // prior run was still cancelling). Reset the streaming state so the
                        // UI does not stay stuck on "thinking" and the user can retry.
                        set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                            ...session,
                            runStatus: 'failed',
                            isStreaming: false,
                            streamingBlocks: [],
                            currentStreamText: '',
                            currentToolCalls: [],
                            abortController: null,
                        })))
                        return
                    }
                    set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                        ...session,
                        abortController: null,
                    })))
                }
            },

            revisePlan: async (instruction) => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)
                const abortController = new AbortController()
                set((s) => applyConversationSessionUpdate(s, targetConversationId, (session) => ({
                    ...session,
                    isStreaming: true,
                    currentStreamText: '',
                    currentToolCalls: [],
                    streamingBlocks: [],
                    abortController,
                    runStatus: 'running',
                })))
                let sawTurnCompleted = false
                let sendError: any = null
                try {
                    const stream = withHarnessActiveRunRetry(
                        targetConversationId,
                        abortController.signal,
                        () => streamHarnessRevisePlan(
                            targetConversationId,
                            instruction,
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
                    if (err?.name !== 'AbortError') {
                        sendError = err
                        console.error('Plan revision error:', err)
                    }
                } finally {
                    if (sawTurnCompleted) {
                        finalizeStreamV2(set, get, targetConversationId, getConversationSession(get(), targetConversationId).runStatus)
                        return
                    }
                    if (await reconcileTurnStreamAfterTransportClose(targetConversationId, set, get)) {
                        return
                    }
                    if (sendError) {
                        // The action failed before a turn could start (e.g. a 409 while a
                        // prior run was still cancelling). Reset the streaming state so the
                        // UI does not stay stuck on "thinking" and the user can retry.
                        set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                            ...session,
                            runStatus: 'failed',
                            isStreaming: false,
                            streamingBlocks: [],
                            currentStreamText: '',
                            currentToolCalls: [],
                            abortController: null,
                        })))
                        return
                    }
                    set((state) => applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                        ...session,
                        abortController: null,
                    })))
                }
            },

            patchCurrentOutline: async (plan) => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)
                const response = await agentApi.patchHarnessPlan(targetConversationId, plan)
                const detail = response.data
                const projection = buildSnapshotProjectionFromDetail(detail)
                set((state) => ({
                    ...applyConversationSessionUpdate(state, targetConversationId, (session) => ({
                        ...applyProjectionStateToSession(session, projection),
                        messages: projection.messages.length > 0 ? projection.messages : session.messages,
                        userInteraction: projection.userInteraction,
                    })),
                    conversations: state.conversations.map((conversation) => (
                        conversation.id === targetConversationId
                            ? buildHarnessConversationMeta(detail)
                            : conversation
                    )),
                }))
            },

            upsertWorkspaceFile: (conversationId, file) => {
                const targetConversationId = String(conversationId)
                set((state) => applyConversationSessionUpdate(
                    state,
                    targetConversationId,
                    (session) => upsertWorkspaceFileInSession(session, file),
                ))
            },

            setMode: (mode) => set({ mode }),
            setArtifactMode: (artifactMode) => set({ artifactMode }),
            activateSkill: (skillId) => set(() => ({
                activeSkillId: skillId,
                skillSelectionMode: skillId ? 'manual' : 'auto',
                skillDecisionReason: null,
                skillDecisionConfidence: null,
            })),
            selectDesignSystem: (designSystemId) => set(() => ({
                selectedDesignSystemId: designSystemId,
            })),
            setWebSearchEnabled: (enabled) => set({ webSearchEnabled: enabled }),
            setModelPreferences: (prefs) => set((s) => ({
                modelPreferences: { ...s.modelPreferences, ...prefs }
            })),

            updateToolCall: (messageId, callId, updates) => {
                set((s) => ({
                    messages: s.messages.map((m) =>
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
                    // Also update streaming tool calls if needed
                    currentToolCalls: s.currentToolCalls.map((tc) =>
                        tc.callId === callId ? { ...tc, ...updates } : tc
                    ),
                    streamingBlocks: s.streamingBlocks.map((block) =>
                        applyToolCallUpdatesToBlock(block, String(callId), updates)
                    ),
                }))
            },

            ensureHarnessConversation: async (skillId, options) => {
                const existingConversationId = get().conversationId
                if (existingConversationId) {
                    return String(existingConversationId)
                }
                await get().createHarnessConversation(skillId, options)
                const createdConversationId = get().conversationId
                return createdConversationId == null ? null : String(createdConversationId)
            },

            createHarnessConversation: async (skillId, options) => {
                const {
                    mode,
                    artifactMode,
                    activeSkillId,
                    selectedDesignSystemId,
                    modelPreferences,
                    webSearchEnabled,
                    skillSelectionMode,
                } = get()
                const effectiveSkillId = skillId === undefined ? activeSkillId : skillId
                const effectiveArtifactMode = options?.artifactMode || artifactMode
                const effectiveDesignSystemId = options?.designSystemId === undefined
                    ? selectedDesignSystemId
                    : options.designSystemId
                const effectiveModelPreferences = {
                    ...modelPreferences,
                    ...(options?.modelPreferences || {}),
                }
                const res = await agentApi.createHarnessConversation({
                    mode,
                    skill_id: skillSelectionMode === 'manual' ? (effectiveSkillId || null) : null,
                    skill_selection_mode: skillSelectionMode,
                    artifact_mode: effectiveArtifactMode,
                    design_system_id: effectiveDesignSystemId,
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
                    planningDraft: null,
                    activeUserPlan: null,
                    outlineRuntime: null,
                    runtimeState: null,
                    userProgress: null,
                    userInteraction: null,
                    isStreaming: false,
                    currentStreamText: '',
                    currentToolCalls: [],
                    streamingBlocks: [],
                    runStatus: 'idle',
                    artifactMode: effectiveArtifactMode,
                    interactionProfile: newConv.interaction_profile === 'canvas_live_interaction'
                        ? 'canvas_live_interaction'
                        : 'home_blocking_preflight',
                    activeSkillId: newConv.skill_id ?? (skillSelectionMode === 'manual' ? effectiveSkillId || null : null),
                    skillSelectionMode: newConv.skill_selection_mode === 'manual' ? 'manual' : skillSelectionMode,
                    selectedDesignSystemId: newConv.design_system_id ?? effectiveDesignSystemId ?? null,
                    skillDecisionReason: newConv.last_skill_decision_reason ?? null,
                    skillDecisionConfidence: newConv.last_skill_decision_confidence ?? null,
                    webSearchEnabled: newConv.web_search_enabled ?? webSearchEnabled,
                    modelPreferences: effectiveModelPreferences,
                    workspaceFiles: [],
                    _abortController: null,
                    conversationSessions: {
                        ...s.conversationSessions,
                        [getConversationSessionKey(newConv.id)]: nextSession,
                    },
                    conversations: [buildHarnessConversationMeta(newConv), ...s.conversations],
                }))
            },

            loadMoreConversations: async () => {
                const { conversationsPage, conversationsHasMore } = get()
                if (!conversationsHasMore) return
                const nextPage = conversationsPage + 1
                // Optimistically bump page to prevent duplicate requests from scroll
                set({ conversationsPage: nextPage })
                try {
                    const res = await agentApi.listHarnessConversations(nextPage, 20)
                    set((s) => ({
                        conversations: [...s.conversations, ...res.data.items.map(buildHarnessConversationMeta)],
                        conversationsHasMore: res.data.has_more,
                        engineVersion: 'harness',
                    }))
                } catch (err) {
                    // Revert page on failure
                    set({ conversationsPage: nextPage - 1 })
                    console.error('Failed to load more conversations:', err)
                }
            },

            loadOlderMessages: async () => {
                const { conversationId } = get()
                if (!conversationId) return
                const targetConversationId = String(conversationId)
                const session = getConversationSession(get(), targetConversationId)
                const messagesPage = getMessagesPage(session)
                if (!messagesPage.hasMore || messagesPage.loading) {
                    return
                }
                set((state) => ({
                    ...applyConversationSessionUpdate(state, targetConversationId, (currentSession) => ({
                            ...currentSession,
                            messagesPage: {
                                ...getMessagesPage(currentSession),
                                loading: true,
                            },
                    })),
                }))
                try {
                    const response = await agentApi.listHarnessConversationMessages(
                        targetConversationId,
                        messagesPage.oldestSeq,
                        80,
                    )
                    const olderMessages = buildHarnessUiMessages(response.data.messages || [])
                    set((state) => {
                        const currentSession = getConversationSession(state, targetConversationId)
                        const existingIds = new Set(currentSession.messages.map((message) => String(message.id)))
                        const prependedMessages = olderMessages.filter((message) => !existingIds.has(String(message.id)))
                        const nextSession = {
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
                        return {
                            ...applyConversationSessionUpdate(state, targetConversationId, () => nextSession),
                            ...(String(state.conversationId || '') === targetConversationId
                                ? buildActiveConversationFields(nextSession)
                                : {}),
                        }
                    })
                } catch (error) {
                    console.error('Failed to load older harness messages:', error)
                    set((state) => ({
                        ...applyConversationSessionUpdate(state, targetConversationId, (currentSession) => ({
                            ...currentSession,
                            messagesPage: {
                                ...getMessagesPage(currentSession),
                                loading: false,
                            },
                        })),
                    }))
                }
            },

            newChat: () => {
                abortAllConversationStreams(get())
                clearHomeHarnessWorkspaceFilesRefreshTimers()
                set({
                    conversationId: null,
                    messages: [],
                    activePlan: null,
                    activeUserPlan: null,
                    outlineRuntime: null,
                    runtimeState: null,
                    userProgress: null,
                    userInteraction: null,
                    isStreaming: false,
                    currentStreamText: '',
                    currentToolCalls: [],
                    streamingBlocks: [],
                    runStatus: 'idle',
                    olderMessagesHasMore: false,
                    olderMessagesLoading: false,
                    workspaceFiles: [],
                    mode: initialState.mode,
                    artifactMode: initialState.artifactMode,
                    interactionProfile: initialState.interactionProfile,
                    engineVersion: 'harness',
                    _abortController: null,
                    activeSkillId: null,
                    skillSelectionMode: initialState.skillSelectionMode,
                    selectedDesignSystemId: null,
                    skillDecisionReason: null,
                    skillDecisionConfidence: null,
                    decisionLoading: false,
                    webSearchEnabled: initialState.webSearchEnabled,
                    modelPreferences: { ...initialState.modelPreferences },
                })
            },

            reset: () => {
                abortAllConversationStreams(get())
                clearHomeHarnessWorkspaceFilesRefreshTimers()
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

function handleAgentEventV2(
    event: AgentEvent,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    _get: () => ChatState & ChatActions,
    targetConversationId?: number | string | null,
) {
    {
        const projectionConversationId = targetConversationId ?? _get().conversationId
        const currentSession = projectionConversationId
            ? getConversationSession(_get(), projectionConversationId)
            : null
        if (isPresentationOpEvent(event as any)) {
            const conversationPatch = extractPresentationConversationPatch(event as any)
            if (!projectionConversationId) {
                set((s) => buildActiveConversationFields(
                    applyPresentationOpToSession({
                        ...createEmptyConversationSession(),
                        messages: s.messages,
                        streamingBlocks: s.streamingBlocks,
                        lastSequence: s.conversationId && currentSession ? currentSession.lastSequence : 0,
                        appliedPresentationOps: currentSession?.appliedPresentationOps ?? [],
                    }, event as any),
                ))
                return
            }
            set((s) => {
                const skillPatch = hasPresentationSkillPatch(conversationPatch) ? conversationPatch : null
                const activePatch = String(s.conversationId || '') === String(projectionConversationId) && skillPatch
                    ? {
                        activeSkillId: String(skillPatch.skill_id || skillPatch.resolved_skill_id || '') || null,
                        skillSelectionMode: skillPatch.skill_selection_mode === 'manual' ? 'manual' as const : 'auto' as const,
                        skillDecisionReason: skillPatch.last_skill_decision_reason ?? null,
                        skillDecisionConfidence: typeof skillPatch.last_skill_decision_confidence === 'number'
                            ? skillPatch.last_skill_decision_confidence
                            : null,
                    }
                    : String(s.conversationId || '') === String(projectionConversationId) && conversationPatch?.design_system_id !== undefined
                        ? {
                            selectedDesignSystemId: String(conversationPatch.design_system_id || '') || null,
                        }
                    : {}
                return {
                    ...applyConversationSessionUpdate(s, projectionConversationId, (session) => (
                        applyPresentationOpToSession(session, event as any)
                    )),
                    ...activePatch,
                    conversations: conversationPatch
                        ? s.conversations.map((conversation) => (
                            String(conversation.id) === String(projectionConversationId)
                                ? applyPresentationConversationPatchToMeta(conversation, conversationPatch)
                                : conversation
                        ))
                        : s.conversations,
                }
            })
            return
        }
        if (!projectionConversationId) {
            if (!shouldApplyRuntimeAdapterEvent(event)) {
                return
            }
            set((s) => {
                const projection = applyHomeHarnessEvent(
                    buildProjectionStateFromSession({
                        ...createEmptyConversationSession(),
                        messages: s.messages,
                        activePlan: s.activePlan,
                        activeUserPlan: s.activeUserPlan,
                        runtimeState: s.runtimeState,
                        userProgress: s.userProgress,
                        userInteraction: s.userInteraction,
                        isStreaming: s.isStreaming,
                        currentStreamText: s.currentStreamText,
                        currentToolCalls: s.currentToolCalls,
                        streamingBlocks: s.streamingBlocks,
                        workspaceFiles: s.workspaceFiles,
                    }),
                    event as HomeHarnessProjectionEvent,
                )
                return buildActiveConversationFields(
                    applyProjectionStateToSession(createEmptyConversationSession(), projection),
                )
            })
            return
        }
        const durableSequence = getDurableEventSequence(event)
        if (shouldDropAlreadyAppliedDurableEvent(event, durableSequence, currentSession)) {
            return
        }
        if (!shouldApplyRuntimeAdapterEvent(event)) {
            set((s) => applyConversationSessionUpdate(s, projectionConversationId, (session) => (
                durableSequence == null
                    ? session
                    : { ...session, lastSequence: Math.max(session.lastSequence, durableSequence) }
            )))
            if (shouldRefreshWorkspaceFilesAfterEvent(event)) {
                scheduleHomeHarnessWorkspaceFilesRefresh(projectionConversationId, set)
            }
            return
        }

        set((s) => {
            const session = getConversationSession(s, projectionConversationId)
            const projectedSession = applyProjectionStateToSession(
                session,
                applyHomeHarnessEvent(
                    buildProjectionStateFromSession(session),
                    event as HomeHarnessProjectionEvent,
                ),
            )
            const nextSession = markRuntimeEventApplied(projectedSession, event, durableSequence)
            const nextState = applyConversationSessionUpdate(s, projectionConversationId, () => nextSession)
            return {
                ...nextState,
                conversations: updateConversationMetaFromSession(
                    {
                        ...s,
                        ...nextState,
                        conversationSessions: nextState.conversationSessions ?? s.conversationSessions,
                    },
                    projectionConversationId,
                    nextSession,
                    buildConversationMetaOverridesFromEvent(
                        s.conversations.find((conversation) => String(conversation.id) === String(projectionConversationId)) ?? null,
                        nextSession,
                        event,
                    ),
                ),
            }
        })
        if (shouldRefreshWorkspaceFilesAfterEvent(event)) {
            scheduleHomeHarnessWorkspaceFilesRefresh(projectionConversationId, set)
        }

        return
    }

}

function getDurableEventSequence(event: AgentEvent): number | null {
    if ((event as any).transient === true) {
        return null
    }
    const sequence = typeof event.sequence === 'number' ? event.sequence : null
    return sequence != null && Number.isFinite(sequence) && sequence > 0 ? sequence : null
}

function shouldDropAlreadyAppliedDurableEvent(
    event: AgentEvent,
    durableSequence: number | null,
    currentSession: ConversationSessionState | null,
): boolean {
    if (durableSequence == null || !currentSession || durableSequence > currentSession.lastSequence) {
        return false
    }
    if (hasAppliedRuntimeEvent(currentSession, event, durableSequence)) {
        return true
    }
    if (isTurnCompletedEvent(event) && durableSequence === currentSession.lastSequence) {
        const nextStatus = String(event.data?.status || '').toLowerCase()
        const currentStatus = String(currentSession.runStatus || '').toLowerCase()
        if (
            nextStatus
            && nextStatus !== currentStatus
            && shouldReplaySameSequenceTurnCompleted(event, currentSession)
        ) {
            return false
        }
    }
    return !isOutOfOrderReplayableRuntimeEvent(event)
}

const OUT_OF_ORDER_REPLAYABLE_RUNTIME_EVENT_TYPES = new Set([
    'asset_added',
    'asset_registered',
    'asset_removed',
    'file_created',
    'file_current_version_changed',
    'file_published',
    'file_updated',
    'file_version_created',
    'generation_completed',
    'generation_failed',
    'generation_started',
    'item_completed',
    'item_started',
    'item_updated',
    'workspace_file_upserted',
])

function isOutOfOrderReplayableRuntimeEvent(event: AgentEvent): boolean {
    return OUT_OF_ORDER_REPLAYABLE_RUNTIME_EVENT_TYPES.has(String(event.type || ''))
}

function shouldReplaySameSequenceTurnCompleted(
    event: AgentEvent,
    currentSession: ConversationSessionState,
): boolean {
    if (!currentSession.isStreaming) {
        return false
    }
    const status = String(event.data?.status || '').toLowerCase()
    if (status !== 'failed' && status !== 'blocked') {
        return true
    }
    const summary = terminalFailureSummary(event)
    return !summary || !sessionHasVisibleMessageText(currentSession, summary)
}

function terminalFailureSummary(event: AgentEvent): string {
    const error = event.data?.error
    if (error && typeof error === 'object') {
        return String((error as Record<string, any>).summary || '').trim()
    }
    return String(event.data?.summary || event.data?.message || '').trim()
}

function sessionHasVisibleMessageText(session: ConversationSessionState, text: string): boolean {
    const needle = text.trim()
    if (!needle) {
        return false
    }
    return session.messages.some((message) => String(message.content || '').includes(needle))
}

function durableRuntimeEventKey(
    event: AgentEvent,
    durableSequence: number | null,
): string | null {
    const eventId = String((event as Record<string, any>).event_id ?? '').trim()
    if (eventId) {
        return `event:${eventId}`
    }
    const idempotencyKey = String((event as Record<string, any>).idempotency_key ?? '').trim()
    if (idempotencyKey) {
        return `idempotency:${idempotencyKey}`
    }
    if (durableSequence == null) {
        return null
    }
    return `sequence:${durableSequence}:${String(event.type || '')}:${String(event.run_id || '')}`
}

function hasAppliedRuntimeEvent(
    session: ConversationSessionState,
    event: AgentEvent,
    durableSequence: number | null,
): boolean {
    const key = durableRuntimeEventKey(event, durableSequence)
    return Boolean(key && (session.appliedRuntimeEvents || []).includes(key))
}

function markRuntimeEventApplied(
    session: ConversationSessionState,
    event: AgentEvent,
    durableSequence: number | null,
): ConversationSessionState {
    const key = durableRuntimeEventKey(event, durableSequence)
    if (!key) {
        return session
    }
    const appliedRuntimeEvents = session.appliedRuntimeEvents || []
    if (appliedRuntimeEvents.includes(key)) {
        return session
    }
    return {
        ...session,
        appliedRuntimeEvents: [...appliedRuntimeEvents.slice(-399), key],
    }
}

function finalizeStreamV2(
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
    targetConversationId: number | string | null | undefined,
    status: HomeHarnessProjectionState['runStatus'],
) {
    {
        const state = get()
        const projectionConversationId = targetConversationId ?? state.conversationId
        const terminalStatus = resolveHarnessTerminalRunStatus(status)
        if (!projectionConversationId) {
            set((s) => {
                const projection = finalizeHomeHarnessProjection(
                    buildProjectionStateFromSession({
                        ...createEmptyConversationSession(),
                        messages: s.messages,
                        activePlan: s.activePlan,
                        activeUserPlan: s.activeUserPlan,
                        runtimeState: s.runtimeState,
                        userProgress: s.userProgress,
                        userInteraction: s.userInteraction,
                        isStreaming: s.isStreaming,
                        currentStreamText: s.currentStreamText,
                        currentToolCalls: s.currentToolCalls,
                        streamingBlocks: s.streamingBlocks,
                        workspaceFiles: s.workspaceFiles,
                    }),
                    terminalStatus,
                )
                return buildActiveConversationFields(
                    applyProjectionStateToSession(createEmptyConversationSession(), projection),
                )
            })
            return
        }

        set((s) => applyConversationSessionUpdate(s, projectionConversationId, (session) => ({
            ...applyProjectionStateToSession(
                session,
                finalizeHomeHarnessProjection(buildProjectionStateFromSession(session), terminalStatus),
            ),
            abortController: null,
            eventStreamController: null,
        })))
        return
    }
}

export const __chatStoreTestUtils = {
    applyToolCallUpdatesToBlock,
    extractMessageText,
    buildHarnessUiMessages,
    dedupePlanArtifactMessages,
    filterHomepageBlocks,
}



