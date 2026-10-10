import {
    agentApi,
    type AgentEvent,
    type HarnessConversationRead,
} from '@/api/endpoints/agent'
import i18n from '@/i18n'
import {
    isHarnessConversationActiveStatus,
    isHarnessConversationTerminalStatus,
} from './harnessTerminalEvents'
import { shouldReconnectTurnStream } from './harnessStreamLifecycle'
import { getTurnFailure, getTurnStatus, isTurnCompletedEvent, isTurnDoneForTransport } from './harnessTurnProtocol'
import type { ChatActions, ChatState } from './canvasAgentStore'
import { EMPTY_MESSAGE_BLOCKS, type ConversationRunStatus } from './canvasAgentTypes'
import {
    applyConversationSessionUpdate,
    getConversationSession,
    isSameConversationId,
    mergeChatStatePatches,
    type ConversationSessionState,
} from './canvasAgentSession'
import { appendErrorMessageIfMissing } from './canvasAgentBlockNormalize'
import {
    appendStreamingBlocksAsAssistantMessage,
    clearPendingStreamBlockDeltas,
    finalizeSessionStreamingBlocks,
    flushPendingStreamBlockDeltas,
} from './canvasAgentStreamBatching'
import type { HomeHarnessProjectionState } from './homeHarnessProjection'
import {
    buildCanvasHarnessProjectionFromSnapshot,
    projectionToCanvasSession,
    type HarnessConversationSnapshotDetail,
} from './canvasHarnessProjection'
import {
    createCanvasGenerationRuntimeAdapter,
    disposeConversationGenerationTasks,
    recoverGenerationTasksFromSession,
} from './canvasGenerationTaskRuntime'

export async function fetchHarnessConversationSnapshot(
    conversationId: string,
): Promise<HarnessConversationSnapshotDetail | null> {
    const res = await agentApi.getHarnessConversation(conversationId)
    return res?.data
        ? (res.data as HarnessConversationSnapshotDetail)
        : null
}

export function shouldKeepCanvasLiveSession(
    session: ConversationSessionState,
    projection: HomeHarnessProjectionState,
): boolean {
    if (isHarnessConversationTerminalStatus(projection.runStatus)) {
        return false
    }

    if (session.runStatus === 'cancelled') {
        return !isHarnessConversationTerminalStatus(projection.runStatus)
    }

    const hasLocalLiveActivity = (
        Boolean(session.abortController)
        || session.streamingBlocks.length > 0
    )

    if (!hasLocalLiveActivity) {
        return false
    }

    return isHarnessConversationActiveStatus(projection.runStatus)
}

export async function refreshHarnessConversationFromServer(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
): Promise<HarnessConversationRead | null> {
    try {
        const detail = await fetchHarnessConversationSnapshot(conversationId)
        if (!detail) {
            return null
        }
        const snapshotProjection = buildCanvasHarnessProjectionFromSnapshot(detail)
        set((s) => {
            const currentSession = getConversationSession(s, conversationId)
            const preserveLocalCancellation = (
                currentSession.runStatus === 'cancelled'
                && !isHarnessConversationTerminalStatus(snapshotProjection.runStatus)
            )
            const existingIdx = s.conversations.findIndex(c => c.id === detail.id)
            let newConversations = [...s.conversations]
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
            if (existingIdx >= 0 && !preserveLocalCancellation) {
                newConversations[existingIdx] = convMeta
            } else if (existingIdx < 0) {
                newConversations = [convMeta, ...newConversations]
            }

            const sessionPatch = applyConversationSessionUpdate(s, conversationId, (session) => {
                    const keepLiveSession = shouldKeepCanvasLiveSession(session, snapshotProjection)
                    if (keepLiveSession) {
                        return {
                            ...session,
                            lastSequence: session.lastSequence,
                        }
                    }
                    const nextSession = projectionToCanvasSession(snapshotProjection, session, detail)
                    const reconciledSession = snapshotProjection.messages.length > 0
                        ? nextSession
                        : { ...nextSession, messages: session.messages }
                    if (!isHarnessConversationTerminalStatus(snapshotProjection.runStatus)) {
                        return reconciledSession
                    }
                    return {
                        ...reconciledSession,
                        isStreaming: false,
                        streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                        currentStreamText: '',
                        currentToolCalls: [],
                        abortController: null,
                    }
            })
            return mergeChatStatePatches(
                s,
                sessionPatch,
                { conversations: newConversations },
            )
        })
        return detail
    } catch (err) {
        console.error('Failed to refresh harness conversation:', err)
        return null
    }
}

export function shouldKeepHarnessConversationTransportAlive(
    session: Pick<ConversationSessionState, 'runStatus' | 'pendingInteraction'>,
): boolean {
    return isHarnessConversationActiveStatus(session.runStatus) || (
        session.runStatus === 'waiting_input'
        && !session.pendingInteraction
    )
}

export function isHarnessConversationTerminal(
    runStatus: ConversationSessionState['runStatus'],
): boolean {
    return isHarnessConversationTerminalStatus(runStatus)
}

export function applyCanvasMissingTurnCompletedProtocolError(
    conversationId: string,
    runtimeStatus: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
): void {
    const summary = i18n.t('homeHarness.protocol.missingTurnCompleted')
    const timestamp = new Date().toISOString()
    set((state) => {
        const sessionPatch = applyConversationSessionUpdate(state, conversationId, (session) => {
            session.eventStreamController?.abort()
            return {
                ...session,
                messages: appendErrorMessageIfMissing(session.messages, summary),
                runStatus: 'failed',
                isStreaming: false,
                abortController: null,
                eventStreamController: null,
            }
        })
        return mergeChatStatePatches(
            state,
            sessionPatch,
            {
                conversations: updateCanvasConversationMetaFromTerminalEvent(
                    state.conversations,
                    conversationId,
                    { status: 'failed', failureSummary: summary },
                    timestamp,
                ),
            },
        )
    })
    console.error('Harness protocol error: missing turn_completed', {
        conversationId,
        runtimeStatus,
    })
}

export async function reconcileCanvasTurnStreamAfterTransportClose(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
): Promise<boolean> {
    const detail = await refreshHarnessConversationFromServer(conversationId, set)
    if (!detail) {
        return false
    }

    if (shouldReconnectTurnStream(detail)) {
        set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
            ...session,
            abortController: null,
        })))
        return true
    }

    if (isTurnDoneForTransport(detail.runtime_status) && detail.runtime_status !== 'waiting_input') {
        applyCanvasMissingTurnCompletedProtocolError(conversationId, detail.runtime_status, set)
    }
    set((state) => stopConversationEventStream(state, conversationId))
    return false
}

export async function refreshHarnessWorkspaceFiles(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
) {
    try {
        const res = await agentApi.listWorkspaceFiles(conversationId)
        set((s) => applyConversationSessionUpdate(s, conversationId, (session) => ({
            ...session,
            workspaceFiles: res.data,
        })))
    } catch (err) {
        console.error('Failed to refresh harness workspace files:', err)
    }
}

const harnessWorkspaceRefreshTimers = new Map<string, ReturnType<typeof setTimeout>>()

export function scheduleHarnessWorkspaceFilesRefresh(
    conversationId: string,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    delayMs = 350,
) {
    if (harnessWorkspaceRefreshTimers.has(conversationId)) {
        return
    }

    const timer = setTimeout(() => {
        harnessWorkspaceRefreshTimers.delete(conversationId)
        void refreshHarnessWorkspaceFiles(conversationId, set)
    }, delayMs)

    harnessWorkspaceRefreshTimers.set(conversationId, timer)
}

export function stopConversationEventStream(
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

export function resolveCanvasEventTimestamp(event: AgentEvent): string {
    const candidates = [
        event.data?.created_at,
        event.data?.updated_at,
        event.data?.finished_at,
        event.data?.started_at,
    ]
    const resolved = candidates.find((value) => typeof value === 'string' && value.trim().length > 0)
    return resolved ? String(resolved) : new Date().toISOString()
}

export function normalizeRunId(value: unknown): string {
    const normalized = String(value ?? '').trim()
    return normalized && normalized.toLowerCase() !== 'none' && normalized.toLowerCase() !== 'null'
        ? normalized
        : ''
}

export function getCanvasEventRunId(event: AgentEvent): string {
    return normalizeRunId((event).run_id ?? event.data?.run_id ?? event.data?.runId)
}

export function getCanvasConversationRunId(
    conversations: HarnessConversationRead[],
    conversationId: number | string,
): string {
    const conversation = conversations.find((entry) => isSameConversationId(entry.id, conversationId))
    const runtimeState = conversation?.runtime_state
    const runtimeStateRunId = runtimeState && typeof runtimeState === 'object' && !Array.isArray(runtimeState)
        ? (runtimeState).run_id
        : null
    return normalizeRunId(conversation?.run_id ?? runtimeStateRunId)
}

export function updateCanvasConversationMetaForRunStarted(
    conversations: HarnessConversationRead[],
    conversationId: number | string,
    event: AgentEvent,
    timestamp: string,
    options: { markRunning?: boolean } = {},
): HarnessConversationRead[] {
    const eventRunId = getCanvasEventRunId(event)
    const markRunning = options.markRunning !== false
    let didChange = false
    const nextConversations = conversations.map((conversation) => {
        if (!isSameConversationId(conversation.id, conversationId)) {
            return conversation
        }
        if (!markRunning) {
            const runtimeState = (
                conversation.runtime_state
                && typeof conversation.runtime_state === 'object'
                && !Array.isArray(conversation.runtime_state)
            ) ? conversation.runtime_state : null
            const nextRunId = eventRunId || conversation.run_id
            const nextRuntimeStateRunId = eventRunId || runtimeState?.run_id
            const nextRuntimeState = runtimeState && nextRuntimeStateRunId !== runtimeState.run_id
                ? { ...runtimeState, run_id: nextRuntimeStateRunId }
                : conversation.runtime_state
            const baseChanged = nextRunId !== conversation.run_id
                || nextRuntimeState !== conversation.runtime_state
            const nextConversation = {
                ...conversation,
                run_id: nextRunId,
                updated_at: baseChanged ? timestamp : conversation.updated_at,
                runtime_state: nextRuntimeState,
            } as HarnessConversationRead
            const conversationChanged = nextConversation.run_id !== conversation.run_id
                || nextConversation.updated_at !== conversation.updated_at
                || nextConversation.runtime_state !== conversation.runtime_state
            didChange ||= conversationChanged
            return conversationChanged ? nextConversation : conversation
        }
        const runtimeState = (
            conversation.runtime_state
            && typeof conversation.runtime_state === 'object'
            && !Array.isArray(conversation.runtime_state)
        ) ? conversation.runtime_state : null
        const nextRuntimeStateRunId = eventRunId || runtimeState?.run_id
        const runtimeStateChanged = Boolean(runtimeState) && (
            nextRuntimeStateRunId !== runtimeState?.run_id
            || runtimeState?.runtime_status !== 'running'
            || runtimeState?.run_status !== 'running'
            || runtimeState?.run_state !== 'running'
        )
        const nextRuntimeState = runtimeState && runtimeStateChanged
            ? {
                ...runtimeState,
                run_id: nextRuntimeStateRunId,
                runtime_status: 'running',
                run_status: 'running',
                run_state: 'running',
            }
            : conversation.runtime_state
        const baseChanged = (eventRunId || conversation.run_id) !== conversation.run_id
            || conversation.runtime_status !== 'running'
            || conversation.run_state !== 'running'
            || conversation.finished_at !== null
            || nextRuntimeState !== conversation.runtime_state
        const nextConversation = {
            ...conversation,
            run_id: eventRunId || conversation.run_id,
            runtime_status: 'running',
            run_state: 'running',
            updated_at: baseChanged ? timestamp : conversation.updated_at,
            finished_at: null,
            runtime_state: nextRuntimeState,
        } as HarnessConversationRead
        const conversationChanged = nextConversation.run_id !== conversation.run_id
            || nextConversation.runtime_status !== conversation.runtime_status
            || nextConversation.run_state !== conversation.run_state
            || nextConversation.updated_at !== conversation.updated_at
            || nextConversation.finished_at !== conversation.finished_at
            || nextConversation.runtime_state !== conversation.runtime_state
        didChange ||= conversationChanged
        return conversationChanged ? nextConversation : conversation
    })
    return didChange ? nextConversations : conversations
}

export function updateCanvasConversationMetaFromTerminalEvent(
    conversations: HarnessConversationRead[],
    conversationId: number | string,
    terminal: {
        status: ConversationRunStatus
        failureSummary: string | null
    },
    timestamp: string,
): HarnessConversationRead[] {
    let didChange = false
    const nextConversations = conversations.map((conversation) => {
        if (!isSameConversationId(conversation.id, conversationId)) {
            return conversation
        }
        const runtimeState = (
            conversation.runtime_state
            && typeof conversation.runtime_state === 'object'
            && !Array.isArray(conversation.runtime_state)
        ) ? conversation.runtime_state : null
        const runtimeStateChanged = Boolean(runtimeState) && (
            runtimeState?.runtime_status !== terminal.status
            || runtimeState?.run_state !== terminal.status
        )
        const nextRuntimeState = runtimeState && runtimeStateChanged
            ? {
                ...runtimeState,
                runtime_status: terminal.status,
                run_state: terminal.status,
            }
            : conversation.runtime_state
        const nextConversation = {
            ...conversation,
            runtime_status: terminal.status as HarnessConversationRead['runtime_status'],
            run_state: terminal.status,
            updated_at: timestamp,
            finished_at: terminal.status === 'running' || terminal.status === 'waiting_input'
                ? conversation.finished_at
                : conversation.finished_at ?? timestamp,
            last_error_summary: terminal.failureSummary ?? conversation.last_error_summary,
            runtime_state: nextRuntimeState,
        } as HarnessConversationRead
        const conversationChanged = nextConversation.runtime_status !== conversation.runtime_status
            || nextConversation.run_state !== conversation.run_state
            || nextConversation.updated_at !== conversation.updated_at
            || nextConversation.finished_at !== conversation.finished_at
            || nextConversation.last_error_summary !== conversation.last_error_summary
            || nextConversation.runtime_state !== conversation.runtime_state
        didChange ||= conversationChanged
        return conversationChanged ? nextConversation : conversation
    })
    return didChange ? nextConversations : conversations
}

export function applyCanvasTurnCompletedEvent(
    event: AgentEvent,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
    scopedConversationId?: number | string | null,
): boolean {
    const currentState = get()
    const conversationId = scopedConversationId ?? currentState.conversationId
    if (!isTurnCompletedEvent(event)) {
        return false
    }
    const status = (getTurnStatus(event) ?? 'completed') as ConversationRunStatus
    const failure = getTurnFailure(event)
    const terminal = {
        status,
        failureSummary: failure?.summary || null,
        failureVisible: failure?.user_visible !== false,
        clearInteraction: status !== 'waiting_input',
    }

    const timestamp = resolveCanvasEventTimestamp(event)
    const currentRunId = conversationId != null
        ? getCanvasConversationRunId(currentState.conversations, conversationId)
        : ''
    const eventRunId = getCanvasEventRunId(event)
    if (conversationId != null && currentRunId && eventRunId && currentRunId !== eventRunId) {
        set((state) => applyConversationSessionUpdate(state, conversationId, (session) => (
            event.sequence == null
                ? session
                : { ...session, lastSequence: Math.max(session.lastSequence, event.sequence) }
        )))
        return true
    }
    flushPendingStreamBlockDeltas(set, get, conversationId)

    if (!conversationId) {
        set((state) => {
            const finalizedMessages = appendStreamingBlocksAsAssistantMessage(
                state.messages,
                state.streamingBlocks,
                timestamp,
            )
            return {
                messages: finalizedMessages,
                pendingInteraction: terminal.clearInteraction ? null : state.pendingInteraction,
                streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                currentStreamText: '',
                isStreaming: false,
                _abortController: null,
            }
        })
        return true
    }

    set((state) => {
        const sessionPatch = applyConversationSessionUpdate(state, conversationId, (session) => {
            const finalizedSession = finalizeSessionStreamingBlocks(session, timestamp, {
                isStreaming: false,
                abortController: null,
            })
            return {
                ...finalizedSession,
                messages: terminal.failureVisible && terminal.failureSummary
                    ? appendErrorMessageIfMissing(finalizedSession.messages, terminal.failureSummary)
                    : finalizedSession.messages,
                pendingInteraction: terminal.clearInteraction ? null : finalizedSession.pendingInteraction,
                runStatus: terminal.status as ConversationRunStatus,
                eventStreamController: null,
                lastSequence: typeof event.sequence === 'number'
                    ? Math.max(finalizedSession.lastSequence, event.sequence)
                    : finalizedSession.lastSequence,
            }
        })
        return mergeChatStatePatches(
            state,
            sessionPatch,
            {
                conversations: updateCanvasConversationMetaFromTerminalEvent(
                    state.conversations,
                    conversationId,
                    terminal,
                    timestamp,
                ),
            },
        )
    })
    const finalizedSession = getConversationSession(get(), conversationId)
    recoverGenerationTasksFromSession(
        String(conversationId),
        finalizedSession,
        createCanvasGenerationRuntimeAdapter(get),
    )

    return true
}

export function abortAllConversationStreams(state: ChatState): void {
    state._abortController?.abort()
    for (const [conversationId, session] of Object.entries(state.conversationSessions)) {
        session.abortController?.abort()
        session.eventStreamController?.abort()
        disposeConversationGenerationTasks(conversationId)
    }
    clearPendingStreamBlockDeltas()
}
