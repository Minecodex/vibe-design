import type {
    HarnessConversationDetailRead,
    PendingInteraction,
} from '@/api/endpoints/agent'
import i18n from '@/i18n'
import {
    finalizeHomeHarnessProjection,
    type HomeHarnessProjectionState,
} from './homeHarnessProjection'
import { resolveHarnessSnapshotEventSequence } from './harnessEventCursor'
import { resolveHarnessPendingInteraction } from './harnessStreamLifecycle'
import {
    resolvePersistedCanvasMessageSkillId,
    shouldOmitCanvasReplayMessage,
    type ChatMessage,
    type HarnessMessageLike,
    type MessageBlock,
    type ToolCallInfo,
} from './canvasAgentTypes'
import {
    extractMessageText,
    normalizeBlocks,
} from './canvasAgentBlockNormalize'
import { shouldReplayRenderOnlyMessageStandalone } from './harnessRenderOnlyMessages'
import {
    preserveSubmittedCanvasInteractionMessages,
    shouldClearCanvasPendingInteraction,
} from './canvasInteractionBlocks'
import type { ConversationSessionState } from './canvasAgentSession'

export function normalizePendingInteraction(
    raw: Record<string, any> | PendingInteraction | null | undefined,
): PendingInteraction | null {
    if (!raw || typeof raw !== 'object') {
        return null
    }

    const source = raw as Record<string, any>

    const kind = source.kind ? String(source.kind) : undefined
    const question = String(
        source.question
        || (
            kind === 'plan_approval'
                ? i18n.t(
                    'canvas.chat.plan.awaiting_approval_hint',
                    'Reply to approve the plan or describe what should change before execution continues.',
                )
                : ''
        ),
    )

    return {
        ...source,
        request_id: String(source.request_id ?? source.tool_call_id ?? ''),
        question,
        content: typeof source.content === 'string' ? source.content : null,
        kind,
        schema: source.schema && typeof source.schema === 'object'
            ? source.schema as PendingInteraction['schema']
            : {
                title: question || 'Interaction',
                fields: [{
                    id: 'response',
                    label: question || 'Response',
                    type: source.input_type === 'cards' ? 'cards' : (
                        source.input_type === 'buttons' ? 'radio' : 'text'
                    ),
                    options: Array.isArray(source.options) ? source.options : [],
                }],
            },
        answers: source.answers && typeof source.answers === 'object'
            ? source.answers as Record<string, any>
            : null,
        status: String(source.status || 'pending') === 'submitted' ? 'submitted' : 'pending',
    }
}

export function buildHarnessUiMessages(rawMessages: HarnessMessageLike[]): ChatMessage[] {
    return buildHarnessUiMessagesForConversation(rawMessages, null)
}

export function applySubmittedInteractionMetadataToMessages(
    messages: ChatMessage[],
    metadata: Record<string, any>,
): ChatMessage[] {
    const requestId = String(metadata.request_id || metadata.requestId || '').trim()
    if (!requestId) {
        return messages
    }

    const submittedLabel = String(metadata.display_label || metadata.displayLabel || metadata.answer || '').trim()
    const submittedAnswer = String(metadata.answer || '').trim()
    const answers = metadata.answers && typeof metadata.answers === 'object' && !Array.isArray(metadata.answers)
        ? metadata.answers as Record<string, any>
        : null

    return messages.map((message) => {
        if (!message.blocks?.length) {
            return message
        }

        let didUpdate = false
        const nextBlocks = message.blocks.map((block) => {
            if (
                block.kind !== 'interaction'
                || block.uiKind !== 'interaction_form'
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

        if (!didUpdate) {
            return message
        }

        return {
            ...message,
            blocks: nextBlocks,
            content: message.content ?? extractMessageText(nextBlocks),
        }
    })
}

export function buildHarnessUiMessagesForConversation(
    rawMessages: HarnessMessageLike[],
    _conversationId: string | number | null,
): ChatMessage[] {
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
        if (shouldOmitCanvasReplayMessage(message)) {
            return
        }

        const metadata = (message.metadata || {}) as Record<string, any>
        const renderBlocks = normalizeBlocks((message as Record<string, any>).blocks)
        const isRenderOnly = Boolean(metadata.render_only)
        const createdAt = message.created_at || new Date().toISOString()
        const messageId = message.id || `msg-${index}`
        const presentationMessageKey = String(metadata.render_kind || '') === 'presentation_v2'
            && typeof metadata.message_key === 'string'
            && metadata.message_key.trim()
            ? String(metadata.message_key)
            : ''
        const stableMessageId = presentationMessageKey || messageId

        if (message.role === 'assistant' && isRenderOnly) {
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

        if (message.role === 'tool') {
            return
        }

        flushPendingRenderBlocks()
        const nextMessages = message.role === 'user'
            ? applySubmittedInteractionMetadataToMessages(messages, metadata)
            : messages
        if (nextMessages !== messages) {
            messages.splice(0, messages.length, ...nextMessages)
        }
        messages.push({
            id: stableMessageId,
            role: message.role as 'user' | 'assistant' | 'tool',
            content: message.content || null,
            attachments: message.attachments || undefined,
            skillId: message.role === 'user' ? resolvePersistedCanvasMessageSkillId(metadata) : null,
            createdAt,
            isHistoryLoaded: true,
        })
    })

    flushPendingRenderBlocks()
    return messages
}

export type HarnessConversationSnapshotDetail = HarnessConversationDetailRead

export function resolveHarnessRuntimeInteraction(detail: HarnessConversationSnapshotDetail): PendingInteraction | null {
    return normalizePendingInteraction(resolveHarnessPendingInteraction(detail) as Record<string, any> | null)
}

export function buildCanvasHarnessProjectionFromSnapshot(
    detail: HarnessConversationSnapshotDetail,
): HomeHarnessProjectionState {
    const runtimeUserInteraction = resolveHarnessRuntimeInteraction(detail)
    const replayedMessages = buildHarnessUiMessagesForConversation(Array.isArray(detail.messages) ? detail.messages : [], detail.id)
    const replayed = {
        messages: replayedMessages,
        activePlan: null,
        activeUserPlan: null,
        outlineRuntime: null,
        userProgress: null,
        userInteraction: runtimeUserInteraction,
        isStreaming: false,
        currentStreamText: '',
        currentToolCalls: [],
        streamingBlocks: [],
        workspaceFiles: Array.isArray(detail.workspace_files) ? detail.workspace_files : [],
        runtimeState: detail.runtime_state ?? null,
        lastSequence: resolveHarnessSnapshotEventSequence(detail),
        runStatus: 'idle',
    } satisfies HomeHarnessProjectionState
    const rawRuntimeStatus = String(detail.runtime_status || detail.status || '').toLowerCase()
    if (rawRuntimeStatus === 'running') {
        return {
            ...replayed,
            isStreaming: true,
            runStatus: 'running',
        }
    }
    if (replayed.streamingBlocks.length === 0) {
        return {
            ...replayed,
            isStreaming: false,
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
                                : replayed.runStatus,
        }
    }
    const terminalStatus = rawRuntimeStatus === 'failed'
        ? 'failed'
        : rawRuntimeStatus === 'blocked'
            ? 'blocked'
            : rawRuntimeStatus === 'waiting_input'
                ? 'waiting_input'
                : rawRuntimeStatus === 'cancelled'
                    ? 'cancelled'
                    : 'completed'
    const terminalTimestamp = detail.finished_at || detail.updated_at || detail.started_at || new Date().toISOString()
    return finalizeHomeHarnessProjection(replayed, terminalStatus, terminalTimestamp)
}

export function buildCanvasMessagesPageState(
    detail: HarnessConversationSnapshotDetail,
): NonNullable<ConversationSessionState['messagesPage']> {
    return {
        hasMore: Boolean(detail.messages_page?.has_more),
        oldestSeq: typeof detail.messages_page?.oldest_seq === 'number' ? detail.messages_page.oldest_seq : null,
        loading: false,
    }
}

export function projectionToCanvasSession(
    projection: HomeHarnessProjectionState,
    existingSession: ConversationSessionState,
    detail: HarnessConversationSnapshotDetail,
): ConversationSessionState {
    const messages = preserveSubmittedCanvasInteractionMessages(
        existingSession.messages,
        projection.messages as unknown as ChatMessage[],
    )
    const pendingInteraction = projection.pendingInteraction ?? resolveHarnessRuntimeInteraction(detail)
    return {
        ...existingSession,
        messages,
        activePlan: projection.activePlan,
        pendingInteraction: shouldClearCanvasPendingInteraction(messages, pendingInteraction)
            ? null
            : pendingInteraction,
        runStatus: projection.runStatus,
        isStreaming: projection.isStreaming,
        currentStreamText: projection.currentStreamText,
        currentToolCalls: projection.currentToolCalls as unknown as ToolCallInfo[],
        streamingBlocks: projection.streamingBlocks as unknown as MessageBlock[],
        workspaceFiles: projection.workspaceFiles,
        lastSequence: Math.max(existingSession.lastSequence, projection.lastSequence),
        messagesPage: buildCanvasMessagesPageState(detail),
    }
}
