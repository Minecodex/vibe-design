import type { AgentEvent } from '@/api/endpoints/agent'
import { EMPTY_MESSAGE_BLOCKS, type ChatMessage, type MessageBlock } from './canvasAgentTypes'
import type { ChatActions, ChatState } from './canvasAgentStore'
import {
    applyConversationSessionUpdate,
    type ConversationSessionState,
} from './canvasAgentSession'
import {
    appendBlockDeltaWithPlaceholder,
    extractMessageText,
    hasEquivalentBlock,
} from './canvasAgentBlockNormalize'
import { hasRenderableMessageBlock } from './canvasMessageVisibility'

export type PendingStreamBlockDelta = {
    blockId: string
    field: string
    delta: string
    sequence: number | null
    messageId?: string | null
}

const STREAM_BLOCK_DELTA_BATCH_DELAY_MS = 32
const ROOT_STREAM_BLOCK_DELTA_BATCH_KEY = '__root__'
const pendingStreamBlockDeltas = new Map<string, PendingStreamBlockDelta[]>()
const pendingStreamBlockDeltaTimers = new Map<string, ReturnType<typeof setTimeout>>()

export function getStreamBlockDeltaBatchKey(conversationId: number | string | null | undefined): string {
    return conversationId == null ? ROOT_STREAM_BLOCK_DELTA_BATCH_KEY : String(conversationId)
}

export function clearPendingStreamBlockDeltas(conversationId?: number | string | null): void {
    if (conversationId == null) {
        for (const timer of pendingStreamBlockDeltaTimers.values()) {
            clearTimeout(timer)
        }
        pendingStreamBlockDeltaTimers.clear()
        pendingStreamBlockDeltas.clear()
        return
    }

    const batchKey = getStreamBlockDeltaBatchKey(conversationId)
    const timer = pendingStreamBlockDeltaTimers.get(batchKey)
    if (timer) {
        clearTimeout(timer)
        pendingStreamBlockDeltaTimers.delete(batchKey)
    }
    pendingStreamBlockDeltas.delete(batchKey)
}

export function applyQueuedStreamBlockDeltas(blocks: MessageBlock[], deltas: PendingStreamBlockDelta[]): MessageBlock[] {
    return deltas.reduce(
        (nextBlocks, delta) => appendBlockDeltaWithPlaceholder(
            nextBlocks,
            delta.blockId,
            delta.field,
            delta.delta,
            delta.messageId,
        ),
        blocks,
    )
}

export function flushPendingStreamBlockDeltas(
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    _get: () => ChatState & ChatActions,
    conversationId?: number | string | null,
): boolean {
    const batchKey = getStreamBlockDeltaBatchKey(conversationId)
    const pendingDeltas = pendingStreamBlockDeltas.get(batchKey)
    if (!pendingDeltas || pendingDeltas.length === 0) {
        return false
    }

    const timer = pendingStreamBlockDeltaTimers.get(batchKey)
    if (timer) {
        clearTimeout(timer)
        pendingStreamBlockDeltaTimers.delete(batchKey)
    }
    pendingStreamBlockDeltas.delete(batchKey)

    const maxSequence = pendingDeltas.reduce<number | null>((acc, delta) => (
        delta.sequence == null
            ? acc
            : Math.max(acc ?? 0, delta.sequence)
    ), null)

    const nextBlocks = (blocks: MessageBlock[]): MessageBlock[] => applyQueuedStreamBlockDeltas(blocks, pendingDeltas)

    if (conversationId == null) {
        set((state) => ({
            streamingBlocks: nextBlocks(state.streamingBlocks),
        }))
        return true
    }

    set((state) => applyConversationSessionUpdate(state, conversationId, (session) => ({
        ...session,
        ...(maxSequence == null
            ? {}
            : {
                lastSequence: Math.max(session.lastSequence, maxSequence),
            }),
        streamingBlocks: nextBlocks(session.streamingBlocks),
    })))
    return true
}

export function queuePendingStreamBlockDelta(
    event: AgentEvent,
    set: (partial: Partial<ChatState> | ((state: ChatState & ChatActions) => Partial<ChatState>)) => void,
    get: () => ChatState & ChatActions,
    conversationId?: number | string | null,
): void {
    const batchKey = getStreamBlockDeltaBatchKey(conversationId)
    const pendingDeltas = pendingStreamBlockDeltas.get(batchKey) || []
    pendingDeltas.push({
        blockId: String(event.data.block_id),
        field: String(event.data.field),
        delta: String(event.data.delta || ''),
        sequence: typeof event.sequence === 'number' ? event.sequence : null,
        messageId: event.data.message_id ? String(event.data.message_id) : null,
    })
    pendingStreamBlockDeltas.set(batchKey, pendingDeltas)

    if (pendingStreamBlockDeltaTimers.has(batchKey)) {
        return
    }

    const timer = setTimeout(() => {
        pendingStreamBlockDeltaTimers.delete(batchKey)
        flushPendingStreamBlockDeltas(set, get, conversationId)
    }, STREAM_BLOCK_DELTA_BATCH_DELAY_MS)
    pendingStreamBlockDeltaTimers.set(batchKey, timer)
}

export function getBlockMessageId(block: MessageBlock | undefined): string {
    if (!block) {
        return ''
    }
    return String(
        block.messageId
        ?? block.payload.message_id
        ?? block.payload.messageId
        ?? '',
    ).trim()
}

export function getStreamingBlocksMessageId(blocks: MessageBlock[]): string | null {
    const messageIds = Array.from(new Set(
        blocks
            .map((block) => getBlockMessageId(block))
            .filter(Boolean),
    ))
    if (messageIds.length === 0) {
        return null
    }
    if (messageIds.length > 1) {
        return '__multiple__'
    }
    return messageIds[0]
}

export function appendStreamingBlocksAsAssistantMessage(
    messages: ChatMessage[],
    streamingBlocks: MessageBlock[],
    createdAt: string,
): ChatMessage[] {
    const dedupedStreamingBlocks = streamingBlocks.filter(
        (block) => !hasEquivalentBlock(messages, block),
    )
    const renderableStreamingBlocks = dedupedStreamingBlocks.filter(hasRenderableMessageBlock)
    if (renderableStreamingBlocks.length === 0) {
        return messages
    }

    return [
        ...messages,
        {
            id: `assistant-${createdAt}`,
            role: 'assistant',
            content: extractMessageText(renderableStreamingBlocks),
            blocks: renderableStreamingBlocks,
            createdAt,
        },
    ]
}

export function finalizeSessionStreamingBlocks(
    session: ConversationSessionState,
    createdAt: string,
    options?: {
        isStreaming?: boolean
        abortController?: AbortController | null
    },
): ConversationSessionState {
    if (session.streamingBlocks.length === 0) {
        return {
            ...session,
            currentStreamText: '',
            ...(options?.isStreaming === undefined ? {} : { isStreaming: options.isStreaming }),
            ...(options?.abortController === undefined ? {} : { abortController: options.abortController }),
        }
    }

    return {
        ...session,
        messages: appendStreamingBlocksAsAssistantMessage(session.messages, session.streamingBlocks, createdAt),
        streamingBlocks: EMPTY_MESSAGE_BLOCKS,
        currentStreamText: '',
        ...(options?.isStreaming === undefined ? {} : { isStreaming: options.isStreaming }),
        ...(options?.abortController === undefined ? {} : { abortController: options.abortController }),
    }
}

export function finalizeSessionStreamingBlocksForIncomingMessage(
    session: ConversationSessionState,
    incomingMessageId: string | null | undefined,
    createdAt: string,
): ConversationSessionState {
    const normalizedIncomingMessageId = String(incomingMessageId || '').trim()
    if (!normalizedIncomingMessageId || session.streamingBlocks.length === 0) {
        return session
    }

    const activeMessageId = getStreamingBlocksMessageId(session.streamingBlocks)
    if (!activeMessageId || activeMessageId === normalizedIncomingMessageId) {
        return session
    }

    return finalizeSessionStreamingBlocks(session, createdAt, { isStreaming: true })
}
