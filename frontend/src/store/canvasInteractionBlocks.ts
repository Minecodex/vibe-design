import type { PendingInteraction } from '@/api/endpoints/agent'
import type { ChatMessage, MessageBlock } from './canvasAgentTypes'
import {
    extractMessageText,
    normalizeBlock,
    normalizeBlocks,
} from './canvasAgentBlockNormalize'

export function upsertRenderMessage(
    messages: ChatMessage[],
    payload: Record<string, any>,
): ChatMessage[] {
    const renderKey = String(payload.render_key || payload.renderKey || '').trim()
    const messageId = String(payload.message_id || payload.messageId || '').trim()
    const normalizedBlocks = normalizeBlocks(payload.blocks)
    const createdAt = new Date().toISOString()

    if (!renderKey && !messageId) {
        return messages
    }

    const existingIndex = messages.findIndex((message) => (
        (messageId && String(message.id) === messageId)
        || (renderKey && (message.blocks || []).some((block) => (
            String(block.renderKey || block.payload?.renderKey || block.payload?.render_key || '').trim() === renderKey
        )))
    ))

    const existingMessage = existingIndex >= 0 ? messages[existingIndex] : null
    const blocks = existingMessage
        ? preserveSubmittedCanvasInteractionBlocks(existingMessage.blocks || [], normalizedBlocks)
        : normalizedBlocks
    const content = payload.content ?? extractMessageText(blocks)

    const nextMessage: ChatMessage = {
        id: messageId || `render-only-${renderKey || Date.now()}`,
        role: 'assistant',
        content,
        blocks,
        createdAt,
    }

    if (existingIndex < 0) {
        return [...messages, nextMessage]
    }

    const nextMessages = [...messages]
    nextMessages[existingIndex] = {
        ...nextMessages[existingIndex],
        ...nextMessage,
    }
    return nextMessages
}

export function canvasInteractionRequestIdFromBlock(block: MessageBlock): string {
    return String(block.payload?.requestId || block.payload?.request_id || '').trim()
}

export function isSubmittedCanvasInteractionBlock(block: MessageBlock, requestId?: string): boolean {
    const blockRequestId = canvasInteractionRequestIdFromBlock(block)
    return block.uiKind === 'interaction_form'
        && String(block.payload?.status || '').trim() === 'submitted'
        && Boolean(blockRequestId)
        && (!requestId || blockRequestId === requestId)
}

export function findSubmittedCanvasInteractionBlock(messages: ChatMessage[], requestId: string): MessageBlock | null {
    for (const message of messages) {
        for (const block of message.blocks || []) {
            if (isSubmittedCanvasInteractionBlock(block, requestId)) {
                return block
            }
        }
    }
    return null
}

export function preserveSubmittedCanvasInteractionBlocks(
    existingBlocks: MessageBlock[],
    incomingBlocks: MessageBlock[],
): MessageBlock[] {
    const submittedByRequestId = new Map<string, MessageBlock>()
    for (const block of existingBlocks) {
        if (isSubmittedCanvasInteractionBlock(block)) {
            submittedByRequestId.set(canvasInteractionRequestIdFromBlock(block), block)
        }
    }
    if (submittedByRequestId.size === 0) {
        return incomingBlocks
    }
    return incomingBlocks.map((block) => {
        if (block.uiKind !== 'interaction_form') {
            return block
        }
        const requestId = canvasInteractionRequestIdFromBlock(block)
        const submittedBlock = submittedByRequestId.get(requestId)
        if (!submittedBlock || String(block.payload?.status || '').trim() === 'submitted') {
            return block
        }
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
}

export function preserveSubmittedCanvasInteractionMessages(
    existingMessages: ChatMessage[],
    incomingMessages: ChatMessage[],
): ChatMessage[] {
    const submittedByRequestId = new Map<string, MessageBlock>()
    for (const message of existingMessages) {
        for (const block of message.blocks || []) {
            if (isSubmittedCanvasInteractionBlock(block)) {
                submittedByRequestId.set(canvasInteractionRequestIdFromBlock(block), block)
            }
        }
    }
    if (submittedByRequestId.size === 0) {
        return incomingMessages
    }

    let didUpdate = false
    const nextMessages = incomingMessages.map((message) => {
        if (!message.blocks?.length) {
            return message
        }
        let messageUpdated = false
        const nextBlocks = message.blocks.map((block) => {
            if (block.uiKind !== 'interaction_form') {
                return block
            }
            const requestId = canvasInteractionRequestIdFromBlock(block)
            const submittedBlock = submittedByRequestId.get(requestId)
            if (!submittedBlock || String(block.payload?.status || '').trim() === 'submitted') {
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
    return didUpdate ? nextMessages : incomingMessages
}

export function shouldClearCanvasPendingInteraction(
    messages: ChatMessage[],
    pendingInteraction: PendingInteraction | null,
): boolean {
    const requestId = String(
        pendingInteraction?.request_id
        || (pendingInteraction as any)?.requestId
        || '',
    ).trim()
    return Boolean(requestId && findSubmittedCanvasInteractionBlock(messages, requestId))
}

export function buildCanvasInteractionFormBlock(payload: Record<string, any>): MessageBlock | null {
    const requestId = String(payload.request_id || payload.tool_call_id || '').trim()
    if (!requestId) {
        return null
    }

    const question = String(payload.question || '').trim()
    const interactionStatus = String(payload.status || 'pending') === 'submitted'
        ? 'submitted'
        : 'pending'

    return normalizeBlock({
        id: `interaction-form:${requestId}`,
        kind: 'interaction',
        order: 0,
        status: 'completed',
        visible: true,
        ui_kind: 'interaction_form',
        payload: {
            ...payload,
            request_id: requestId,
            requestId,
            tool_call_id: requestId,
            toolCallId: requestId,
            question,
            content: typeof payload.content === 'string' ? payload.content.trim() || null : null,
            kind: payload.kind ? String(payload.kind) : undefined,
            schema: payload.schema && typeof payload.schema === 'object' ? payload.schema : null,
            answers: payload.answers && typeof payload.answers === 'object' ? payload.answers : null,
            status: interactionStatus,
            render_key: `interaction:${requestId}`,
            renderKey: `interaction:${requestId}`,
        },
    })
}

export function findCanvasInteractionMessageIndex(messages: ChatMessage[], requestId: string): number {
    return messages.findIndex((message) => (
        (message.blocks || []).some((block) => (
            block.uiKind === 'interaction_form'
            && String(block.payload?.requestId || block.payload?.request_id || '').trim() === requestId
        ))
    ))
}

export function upsertCanvasInteractionCardMessage(
    messages: ChatMessage[],
    payload: Record<string, any>,
): ChatMessage[] {
    const requestId = String(payload.request_id || payload.tool_call_id || '').trim()
    const interactionBlock = buildCanvasInteractionFormBlock(payload)
    if (!requestId || !interactionBlock) {
        return messages
    }

    const existingIndex = findCanvasInteractionMessageIndex(messages, requestId)
    const content = String(payload.content || payload.question || payload.schema?.title || '').trim() || null

    if (
        interactionBlock.payload.status !== 'submitted'
        && existingIndex >= 0
        && (messages[existingIndex]?.blocks || []).some((block) => isSubmittedCanvasInteractionBlock(block, requestId))
    ) {
        return messages
    }

    if (existingIndex < 0) {
        return [...messages, {
            id: `interaction:${requestId}`,
            role: 'assistant',
            content,
            blocks: [interactionBlock],
            createdAt: new Date().toISOString(),
        }]
    }

    const nextMessages = [...messages]
    const existingMessage = nextMessages[existingIndex]
    const nextBlocks = (existingMessage.blocks || [])
        .filter((block) => !(
            block.uiKind === 'interaction_form'
            && String(block.payload?.requestId || block.payload?.request_id || '').trim() === requestId
        ))
        .concat(interactionBlock)
        .sort((left, right) => left.order - right.order)

    nextMessages[existingIndex] = {
        ...existingMessage,
        content,
        blocks: nextBlocks,
    }
    return nextMessages
}
