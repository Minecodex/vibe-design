import type {
    AgentEvent,
    WorkspaceFileRead,
} from '@/api/endpoints/agent'
import i18n from '@/i18n'
import { applyCanvasGenerationEvent } from './canvasGenerationProjection'
import {
    createCanvasGenerationRuntimeAdapter,
    recoverGenerationTasksFromSession,
    upsertGenerationTaskFromItemEvent,
} from './canvasGenerationTaskRuntime'
import type { ChatActions, ChatState } from './canvasAgentStore'
import { EMPTY_MESSAGE_BLOCKS } from './canvasAgentTypes'
import {
    applyConversationSessionUpdate,
    getConversationSession,
    mergeChatStatePatches,
    type ConversationSessionState,
} from './canvasAgentSession'
import {
    appendErrorMessageIfMissing,
    buildErrorMessage,
    extractCanvasRevisionMetaFromEvent,
    extractMessageText,
    normalizeCanvasUpdateDispatch,
} from './canvasAgentBlockNormalize'
import {
    appendStreamingBlocksAsAssistantMessage,
    finalizeSessionStreamingBlocks,
    flushPendingStreamBlockDeltas,
} from './canvasAgentStreamBatching'
import {
    applyCanvasTurnCompletedEvent,
    resolveCanvasEventTimestamp,
    updateCanvasConversationMetaForRunStarted,
} from './canvasHarnessLifecycle'
import { isTurnCompletedEvent } from './harnessTurnProtocol'
import { isPresentationOpEvent } from './harnessMessageProjection/cursor'
import {
    applyPresentationConversationPatchToMeta,
    extractPresentationConversationPatch,
    hasPresentationSkillPatch,
} from './harnessMessageProjection/conversationPatch'
import { shouldApplyRuntimeAdapterEvent } from './harnessMessageProjection/protocol'
import { applyPresentationOpToSession } from './harnessMessageProjection/reducer'
import { normalizeCanvasResolvedSkillId } from './canvasAgentTypes'

function isActiveCanvasConversation(
    state: ChatState,
    conversationId: number | string | null | undefined,
): boolean {
    return (
        state.conversationId != null
        && conversationId != null
        && String(state.conversationId) === String(conversationId)
    )
}

function dispatchCanvasUpdateForActiveConversation(
    get: () => ChatState & ChatActions,
    conversationId: number | string | null | undefined,
    canvasUpdate: { action: string; item: Record<string, any>; meta?: Record<string, any> },
): void {
    const state = get()
    if (!isActiveCanvasConversation(state, conversationId)) {
        return
    }
    if (canvasUpdate.meta === undefined) {
        state.onCanvasUpdate?.(canvasUpdate.action, canvasUpdate.item)
        return
    }
    state.onCanvasUpdate?.(canvasUpdate.action, canvasUpdate.item, canvasUpdate.meta)
}

function syncCanvasRevisionForActiveConversation(
    get: () => ChatState & ChatActions,
    conversationId: number | string | null | undefined,
    event: AgentEvent,
): void {
    const state = get()
    if (!isActiveCanvasConversation(state, conversationId)) {
        return
    }
    const meta = extractCanvasRevisionMetaFromEvent(event)
    if (!meta) {
        return
    }
    state.onCanvasUpdate?.('sync_canvas_revision', {}, meta)
}

export function getDurableCanvasEventSequence(event: AgentEvent): number | null {
    if ((event as any).transient === true) {
        return null
    }
    const sequence = typeof event.sequence === 'number' ? event.sequence : null
    return sequence != null && Number.isFinite(sequence) && sequence > 0 ? sequence : null
}

export function handleAgentEventV2(
    event: AgentEvent,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    _get: () => ChatState & ChatActions,
    targetConversationId?: number | string | null,
) {
    const eventType: AgentEvent['type'] = event.type
    const scopedConversationId = targetConversationId ?? _get().conversationId
    const durableEventSequence = getDurableCanvasEventSequence(event)
    const currentScopedSession = scopedConversationId
        ? getConversationSession(_get(), scopedConversationId)
        : null
    syncCanvasRevisionForActiveConversation(_get, scopedConversationId, event)
    if (isPresentationOpEvent(event as any)) {
        const conversationPatch = extractPresentationConversationPatch(event as any)
        if (!scopedConversationId) {
            set((s) => {
                const nextSession = applyPresentationOpToSession({
                    messages: s.messages,
                    streamingBlocks: s.streamingBlocks,
                    lastSequence: 0,
                    appliedPresentationOps: [],
                }, event as any)
                return {
                    messages: nextSession.messages,
                    streamingBlocks: nextSession.streamingBlocks,
                }
            })
            return
        }
        set((s) => {
            const skillPatch = hasPresentationSkillPatch(conversationPatch) ? conversationPatch : null
            const activePatch = String(s.conversationId || '') === String(scopedConversationId) && skillPatch
                ? {
                    activeSkillId: normalizeCanvasResolvedSkillId(
                        String(skillPatch.skill_id || skillPatch.resolved_skill_id || '') || null,
                        s.uiConfig,
                    ),
                }
                : {}
            const sessionPatch = applyConversationSessionUpdate(s, scopedConversationId, (session) => (
                    applyPresentationOpToSession(session, event as any)
            ))
            const conversationsPatch = conversationPatch
                ? {
                    conversations: s.conversations.map((conversation) => (
                        String(conversation.id) === String(scopedConversationId)
                            ? applyPresentationConversationPatchToMeta(conversation, conversationPatch)
                            : conversation
                    )),
                }
                : {}
            return mergeChatStatePatches(
                s,
                sessionPatch,
                activePatch,
                conversationsPatch,
            )
        })
        recoverGenerationTasksAfterSessionProjection(scopedConversationId, event, _get)
        return
    }
    const applyEventSequence = (session: ConversationSessionState): ConversationSessionState => (
        durableEventSequence == null
            ? session
            : {
                ...session,
                lastSequence: Math.max(session.lastSequence, durableEventSequence),
            }
    )
    if (!shouldApplyRuntimeAdapterEvent(event)) {
        if (scopedConversationId) {
            set((s) => applyConversationSessionUpdate(s, scopedConversationId, applyEventSequence))
        }
        return
    }
    flushPendingStreamBlockDeltas(set, _get, scopedConversationId)

    if (
        durableEventSequence != null
        && currentScopedSession
        && durableEventSequence <= currentScopedSession.lastSequence
    ) {
        if (
            !(
                isTurnCompletedEvent(event)
                && durableEventSequence === currentScopedSession.lastSequence
                && shouldReplaySameSequenceTurnCompleted(event, currentScopedSession)
            )
        ) {
            return
        }
    }

    if (eventType === 'protocol_error') {
        const summary = i18n.t('homeHarness.protocol.missingTurnCompleted')
        if (!scopedConversationId) {
            set((s) => ({
                messages: appendErrorMessageIfMissing(s.messages, summary),
                isStreaming: false,
                _abortController: null,
            }))
            return
        }
        set((s) => applyConversationSessionUpdate(s, scopedConversationId, (session) => ({
            ...applyEventSequence(session),
            messages: appendErrorMessageIfMissing(session.messages, summary),
            runStatus: 'failed',
            isStreaming: false,
            abortController: null,
            eventStreamController: null,
        })))
        return
    }

    if (eventType === 'turn_started') {
        const timestamp = resolveCanvasEventTimestamp(event)
        if (!scopedConversationId) {
            set((state) => ({
                isStreaming: true,
                conversations: state.conversations,
            }))
            return
        }
        set((state) => {
            const sessionPatch = applyConversationSessionUpdate(state, scopedConversationId, (session) => ({
                ...applyEventSequence(session),
                runStatus: 'running',
                isStreaming: true,
            }))
            return mergeChatStatePatches(
                state,
                sessionPatch,
                {
                    conversations: updateCanvasConversationMetaForRunStarted(
                        state.conversations,
                        scopedConversationId,
                        event,
                        timestamp,
                    ),
                },
            )
        })
        return
    }

    if (eventType === 'run_started') {
        const timestamp = resolveCanvasEventTimestamp(event)
        if (!scopedConversationId) {
            return
        }
        set((state) => mergeChatStatePatches(
            state,
            applyConversationSessionUpdate(state, scopedConversationId, (session) => applyEventSequence(session)),
            {
                conversations: updateCanvasConversationMetaForRunStarted(
                    state.conversations,
                    scopedConversationId,
                    event,
                    timestamp,
                    { markRunning: false },
                ),
            },
        ))
        return
    }

    if (event.type === 'message_error') {
        if (!scopedConversationId) {
            set((s) => ({
                messages: [
                    ...s.messages,
                    ...(s.streamingBlocks.length > 0
                        ? [{
                            id: `assistant-${Date.now()}`,
                            role: 'assistant' as const,
                            content: extractMessageText(s.streamingBlocks),
                            blocks: s.streamingBlocks,
                            createdAt: new Date().toISOString(),
                        }]
                        : []),
                    buildErrorMessage(String(event.data.message || 'Unknown error')),
                ],
                streamingBlocks: EMPTY_MESSAGE_BLOCKS,
            }))
            return
        }
        set((s) => applyConversationSessionUpdate(s, scopedConversationId, (session) => ({
            ...applyEventSequence(session),
            messages: [
                ...session.messages,
                ...(session.streamingBlocks.length > 0
                    ? [{
                        id: `assistant-${Date.now()}`,
                        role: 'assistant' as const,
                        content: extractMessageText(session.streamingBlocks),
                        blocks: session.streamingBlocks,
                        createdAt: new Date().toISOString(),
                    }]
                    : []),
                buildErrorMessage(String(event.data.message || 'Unknown error')),
            ],
            streamingBlocks: EMPTY_MESSAGE_BLOCKS,
            isStreaming: false,
            abortController: null,
        })))
        return
    }

    if (applyCanvasTurnCompletedEvent(event, set, _get, scopedConversationId)) {
        return
    }

    if (
        event.type === 'item_started'
        || event.type === 'item_updated'
        || event.type === 'item_completed'
    ) {
        if (scopedConversationId) {
            set((s) => applyConversationSessionUpdate(s, scopedConversationId, applyEventSequence))
        }
        upsertGenerationTaskFromItemEvent(event, createCanvasGenerationRuntimeAdapter(_get))
        return
    }

    if (event.type === 'canvas_update') {
        const canvasUpdate = normalizeCanvasUpdateDispatch(event, scopedConversationId)
        if (canvasUpdate) {
            const conversationId = scopedConversationId != null ? String(scopedConversationId) : null
            if (conversationId) {
                set((s) => applyConversationSessionUpdate(s, conversationId, (session) => (
                    applyEventSequence(session)
                )))
            }
            dispatchCanvasUpdateForActiveConversation(_get, conversationId, canvasUpdate)
        }
        return
    }

    if (
        event.type === 'generation_started'
        || event.type === 'generation_completed'
        || event.type === 'generation_failed'
    ) {
        let canvasUpdate: { action: string; item: Record<string, any>; meta?: Record<string, any> } | undefined
        if (scopedConversationId) {
            set((s) => applyConversationSessionUpdate(s, scopedConversationId, (session) => {
                const projected = applyCanvasGenerationEvent(
                    applyEventSequence(session),
                    event,
                    scopedConversationId,
                )
                canvasUpdate = projected.canvasUpdate
                return projected.session
            }))
        }
        if (canvasUpdate) {
            dispatchCanvasUpdateForActiveConversation(_get, scopedConversationId, canvasUpdate)
        }
        return
    }

    switch (eventType) {
        case 'file_created':
        case 'file_updated':
            if (!scopedConversationId) {
                set((s) => {
                    const file: WorkspaceFileRead = {
                        name: event.data.file_path?.split('/').pop() || '',
                        path: event.data.file_path || '',
                        type: event.data.type || 'other',
                        size: event.data.size || 0,
                        created_at: new Date().toISOString(),
                    }
                    const existing = s.workspaceFiles.findIndex(f => f.path === file.path)
                    const files = [...s.workspaceFiles]
                    if (existing >= 0) {
                        files[existing] = file
                    } else {
                        files.push(file)
                    }
                    return { workspaceFiles: files }
                })
                break
            }
            set((s) => applyConversationSessionUpdate(s, scopedConversationId, (session) => {
                const file: WorkspaceFileRead = {
                    name: event.data.file_path?.split('/').pop() || '',
                    path: event.data.file_path || '',
                    type: event.data.type || 'other',
                    size: event.data.size || 0,
                    created_at: new Date().toISOString(),
                }
                const existing = session.workspaceFiles.findIndex(f => f.path === file.path)
                const files = [...session.workspaceFiles]
                if (existing >= 0) {
                    files[existing] = file
                } else {
                    files.push(file)
                }
                return {
                    ...applyEventSequence(session),
                    workspaceFiles: files,
                }
            }))
            break

    }
}

function recoverGenerationTasksAfterSessionProjection(
    conversationId: number | string,
    event: AgentEvent,
    get: () => ChatState & ChatActions,
): void {
    if (!shouldRecoverGenerationTasksAfterPresentationOp(event)) {
        return
    }
    const session = getConversationSession(get(), conversationId)
    recoverGenerationTasksFromSession(
        String(conversationId),
        session,
        createCanvasGenerationRuntimeAdapter(get),
    )
}

function shouldRecoverGenerationTasksAfterPresentationOp(event: AgentEvent): boolean {
    return (
        event.type === 'presentation.block.upsert'
        || event.type === 'presentation.block.complete'
        || event.type === 'presentation.block.patch'
    )
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

export function finalizeStreamV2(
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
    targetConversationId?: number | string | null,
) {
    const state = get()
    const scopedConversationId = targetConversationId ?? state.conversationId
    flushPendingStreamBlockDeltas(set, get, scopedConversationId)
    const refreshedState = get()
    const refreshedScopedConversationId = targetConversationId ?? refreshedState.conversationId
    if (!refreshedScopedConversationId) {
        set((s) => {
            const finalizedMessages = appendStreamingBlocksAsAssistantMessage(
                s.messages,
                refreshedState.streamingBlocks,
                new Date().toISOString(),
            )
            return {
                messages: finalizedMessages,
                streamingBlocks: EMPTY_MESSAGE_BLOCKS,
                currentStreamText: '',
                isStreaming: false,
                _abortController: null,
            }
        })
        return
    }

    set((s) => applyConversationSessionUpdate(s, refreshedScopedConversationId, (currentSession) => (
        finalizeSessionStreamingBlocks(currentSession, new Date().toISOString(), {
            isStreaming: false,
            abortController: null,
        })
    )))
}
