import type { AgentEvent } from '@/api/endpoints/agent'
import type { ChatMessage, MessageBlock } from './canvasAgentTypes'

export function toSnakeKey(key: string): string {
    return key
        .replace(/([a-z0-9])([A-Z])/g, '$1_$2')
        .replace(/-/g, '_')
        .toLowerCase()
}

export function normalizeHarnessPayload(value: unknown): unknown {
    if (Array.isArray(value)) {
        return value.map(item => normalizeHarnessPayload(item))
    }
    if (!value || typeof value !== 'object') {
        return value
    }

    const source = value as Record<string, unknown>
    const next: Record<string, unknown> = {}
    for (const [key, entry] of Object.entries(source)) {
        const normalizedKey = toSnakeKey(key)
        next[normalizedKey] = normalizeHarnessPayload(entry)
    }
    return next
}

export function normalizeCanvasUpdateDispatch(
    event: AgentEvent,
    scopedConversationId: number | string | null | undefined,
): { action: string; item: Record<string, any>; meta?: Record<string, any> } | null {
    const data = (
        normalizeHarnessPayload(event.data || {}) as Record<string, any>
    ) || {}
    const result = data.result && typeof data.result === 'object' ? data.result : {}
    const payload = data.payload && typeof data.payload === 'object' ? data.payload : {}
    const rawItem = (
        data.item && typeof data.item === 'object'
            ? data.item
            : data.canvas_item && typeof data.canvas_item === 'object'
                ? data.canvas_item
                : data.media && typeof data.media === 'object'
                    ? data.media
                    : payload.item && typeof payload.item === 'object'
                        ? payload.item
                        : payload.canvas_item && typeof payload.canvas_item === 'object'
                            ? payload.canvas_item
                            : result.canvas_item && typeof result.canvas_item === 'object'
                                ? result.canvas_item
                                : data
    ) as Record<string, any>
    const action = String(data.action || data.canvas_action || payload.action || payload.canvas_action || '').trim()
        || (rawItem.url || data.url || data.result_url || payload.url || payload.result_url || result.url || result.result_url ? 'add_generated_media' : '')

    if (action !== 'add_generated_media' && action !== 'add') {
        return null
    }

    const item = { ...rawItem }
    if (!item.url && (data.result_url || payload.result_url || result.result_url)) {
        item.url = data.result_url || payload.result_url || result.result_url
    }
    if (!item.url && (data.url || payload.url || result.url)) {
        item.url = data.url || payload.url || result.url
    }
    if (item.artifact_ref == null && (data.artifact_ref != null || payload.artifact_ref != null || result.artifact_ref != null)) {
        item.artifact_ref = data.artifact_ref ?? payload.artifact_ref ?? result.artifact_ref
    }
    if (item.messageId == null) {
        item.messageId = data.message_id ?? data.messageId ?? payload.message_id ?? payload.messageId ?? null
    }
    if (item.agentMediaKey == null) {
        item.agentMediaKey = data.agent_media_key ?? data.agentMediaKey ?? payload.agent_media_key ?? payload.agentMediaKey ?? result.agent_media_key ?? result.agentMediaKey ?? item.id ?? null
    }
    if (item.conversationId == null && scopedConversationId != null) {
        item.conversationId = scopedConversationId
    }
    const meta = buildCanvasRevisionMeta(data, payload, result, rawItem, item)
    if (meta.canvasRevision != null && item.canvas_revision == null && item.canvasRevision == null) {
        item.canvas_revision = meta.canvasRevision
    }
    if (meta.canvasItemDeleted === true && item.canvas_item_deleted == null && item.canvasItemDeleted == null) {
        item.canvas_item_deleted = true
    }

    return {
        action,
        item,
        meta: meta.canvasRevision != null || meta.canvasItemDeleted === true ? meta : undefined,
    }
}

export function extractCanvasRevisionMetaFromEvent(event: AgentEvent): { canvasRevision: number; canvasItemDeleted: boolean } | null {
    const data = (
        normalizeHarnessPayload(event.data || {}) as Record<string, any>
    ) || {}
    const topLevelPayload = (
        normalizeHarnessPayload((event as any).payload || {}) as Record<string, any>
    ) || {}
    const sources = [
        ...collectCanvasRevisionSources(data),
        ...collectCanvasRevisionSources(topLevelPayload),
    ]
    const meta = buildCanvasRevisionMeta(...sources)
    return meta.canvasRevision != null
        ? {
            canvasRevision: meta.canvasRevision,
            canvasItemDeleted: meta.canvasItemDeleted === true,
        }
        : null
}

function buildCanvasRevisionMeta(...sources: Record<string, any>[]): Record<string, any> {
    const revision = firstValidCanvasRevision(...sources.flatMap((source) => [
        source.canvas_revision,
        source.canvasRevision,
    ]))
    const canvasItemDeleted = sources.some((source) => (
        source.canvas_item_deleted === true || source.canvasItemDeleted === true
    ))
    return {
        ...(revision != null
            ? { canvasRevision: revision }
            : {}),
        canvasItemDeleted,
    }
}

function collectCanvasRevisionSources(source: unknown, seen = new Set<unknown>()): Record<string, any>[] {
    if (!source || typeof source !== 'object' || Array.isArray(source) || seen.has(source)) {
        return []
    }
    seen.add(source)
    const record = source as Record<string, any>
    const nestedKeys = [
        'payload',
        'result',
        'block',
        'canvas_item',
        'canvasItem',
        'item',
        'media',
        'artifact',
    ]
    return [
        record,
        ...nestedKeys.flatMap((key) => collectCanvasRevisionSources(record[key], seen)),
    ]
}

function firstValidCanvasRevision(...values: unknown[]): number | null {
    for (const value of values) {
        if (value == null || value === '') {
            continue
        }
        const parsed = Number(value)
        if (Number.isFinite(parsed) && parsed >= 0) {
            return Math.trunc(parsed)
        }
    }
    return null
}

export function normalizeBlock(raw: Record<string, any>): MessageBlock {
    const payload = (normalizeHarnessPayload(raw.payload || {}) as Record<string, any>) || {}
    return {
        id: String(raw.id),
        kind: raw.kind,
        order: Number(raw.order ?? 0),
        status: String(raw.status ?? 'completed'),
        visible: raw.visible !== false,
        uiKind: String(raw.uiKind ?? raw.ui_kind ?? raw.kind ?? 'text'),
        payload,
        renderKey: raw.renderKey ?? raw.render_key ?? payload.renderKey ?? payload.render_key,
        messageId: raw.message_id ?? raw.messageId,
        taskId: raw.taskId ?? raw.task_id ?? payload.taskId ?? payload.task_id,
        label: raw.label ?? payload.label ?? payload.result?.label,
        summary: raw.summary ?? payload.summary,
        expanded: typeof raw.expanded === 'boolean' ? raw.expanded : undefined,
        children: normalizeBlocks(raw.children),
        revision: normalizePositiveNumber(raw.revision ?? payload.revision),
        sourceSequence: normalizePositiveNumber(
            raw.sourceSequence
            ?? raw.source_sequence
            ?? payload.sourceSequence
            ?? payload.source_sequence,
        ),
    }
}

function normalizePositiveNumber(value: unknown): number | undefined {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined
}

export function normalizeBlocks(rawBlocks: unknown): MessageBlock[] {
    if (!Array.isArray(rawBlocks)) return []
    return rawBlocks
        .filter((block): block is Record<string, any> => !!block && typeof block === 'object')
        .map(normalizeBlock)
        .sort((a, b) => a.order - b.order)
}

export function appendBlockDelta(blocks: MessageBlock[], blockId: string, field: string, delta: string): MessageBlock[] {
    const normalizedField = toSnakeKey(field)
    return blocks.map((block) => {
        if (block.id !== blockId) return block
        const previous = typeof block.payload[normalizedField] === 'string' ? block.payload[normalizedField] : ''
        return {
            ...block,
            payload: {
                ...block.payload,
                [normalizedField]: `${previous}${delta}`,
            },
        }
    })
}

export function appendBlockDeltaWithPlaceholder(
    blocks: MessageBlock[],
    blockId: string,
    field: string,
    delta: string,
    messageId?: string | null,
): MessageBlock[] {
    const updated = appendBlockDelta(blocks, blockId, field, delta)
    if (updated.some((block) => block.id === blockId)) {
        return updated
    }

    const normalizedField = toSnakeKey(field)
    const nextOrder = blocks.length > 0
        ? Math.max(...blocks.map((block) => Number(block.order ?? 0))) + 1
        : 0
    return [
        ...blocks,
        {
            id: blockId,
            kind: 'text',
            order: nextOrder,
            status: 'running',
            visible: true,
            uiKind: 'text',
            messageId: messageId ? String(messageId) : undefined,
            payload: {
                [normalizedField]: delta,
            },
        },
    ]
}

export function upsertBlockStart(blocks: MessageBlock[], raw: Record<string, any>): MessageBlock[] {
    const normalized = normalizeBlock(raw)
    const existing = blocks.find((block) => block.id === normalized.id)
    if (!existing) {
        return [...blocks, normalized].sort((a, b) => a.order - b.order)
    }

    return blocks
        .map((block) => {
            if (block.id !== normalized.id) {
                return block
            }
            return {
                ...normalized,
                payload: {
                    ...normalized.payload,
                    ...block.payload,
                },
                children: normalized.children?.length ? normalized.children : block.children,
            }
        })
        .sort((a, b) => a.order - b.order)
}

export function mergeBlockPatch(blocks: MessageBlock[], blockId: string, patch: Record<string, any>): MessageBlock[] {
    const merge = (target: Record<string, any>, nextPatch: Record<string, any>): Record<string, any> => {
        const result = { ...target }
        for (const [key, value] of Object.entries(nextPatch)) {
            if (key === 'children' && Array.isArray(value)) {
                result[key] = normalizeBlocks(value)
                continue
            }
            if (
                value &&
                typeof value === 'object' &&
                !Array.isArray(value) &&
                result[key] &&
                typeof result[key] === 'object' &&
                !Array.isArray(result[key])
            ) {
                result[key] = merge(result[key] as Record<string, any>, value as Record<string, any>)
            } else {
                result[key] = value
            }
        }
        return result
    }

    return blocks.map((block) => {
        if (block.id !== blockId) return block
        return merge(block as unknown as Record<string, any>, patch) as unknown as MessageBlock
    })
}

export function extractMessageText(blocks: MessageBlock[]): string | null {
    const text = blocks
        .filter(
            block => block.kind === 'text'
                || (block.kind === 'content' && (block.uiKind === 'assistant_text' || block.uiKind === 'assistant_final_answer')),
        )
        .map(block => String(block.payload.text || '').trim())
        .filter(Boolean)
        .join('\n')
    return text || null
}

export function getBlockIdentityKeys(block: MessageBlock): string[] {
    const keys = new Set<string>()
    const taskId = block.taskId
        ?? block.payload.task_id
        ?? block.payload.result?.task_id
    const callId = block.payload.call_id
        ?? block.payload.result?.call_id
    const artifactRef = block.payload.artifact_ref
        ?? block.payload.result?.artifact_ref
    const renderKey = block.renderKey
        ?? block.payload.render_key
        ?? block.payload.renderKey

    if (taskId != null && String(taskId)) {
        keys.add(`task:${String(taskId)}`)
    }
    if (callId != null && String(callId)) {
        keys.add(`call:${String(callId)}`)
    }
    if (artifactRef != null && String(artifactRef)) {
        keys.add(`artifact:${String(artifactRef)}`)
    }
    if (renderKey != null && String(renderKey)) {
        keys.add(`render:${String(renderKey)}`)
    }

    // Only blocks with stable tool/task identities should be deduped across
    // messages. Plain text block ids like "text-0" repeat every turn.
    if (keys.size > 0 && block.id) {
        keys.add(`block:${block.id}`)
    }

    return Array.from(keys)
}

export function hasEquivalentBlock(messages: ChatMessage[], incomingBlock: MessageBlock): boolean {
    const identityKeys = getBlockIdentityKeys(incomingBlock)
    if (identityKeys.length === 0) {
        return false
    }

    const stack: MessageBlock[] = messages.flatMap((message) => message.blocks || [])
    while (stack.length > 0) {
        const block = stack.pop()!
        const blockKeys = getBlockIdentityKeys(block)
        if (blockKeys.some((key) => identityKeys.includes(key))) {
            return true
        }
        if (block.children?.length) {
            stack.push(...block.children)
        }
    }

    return false
}

export function blocksShareIdentity(left: MessageBlock, right: MessageBlock): boolean {
    const leftKeys = getBlockIdentityKeys(left)
    if (leftKeys.length === 0) {
        return false
    }
    const rightKeys = getBlockIdentityKeys(right)
    return rightKeys.some((key) => leftKeys.includes(key))
}

export function replaceEquivalentBlockInBlocks(
    blocks: MessageBlock[],
    incomingBlock: MessageBlock,
): { blocks: MessageBlock[]; updated: boolean } {
    let didUpdate = false

    const nextBlocks = blocks.map((block) => {
        if (block.id === incomingBlock.id || blocksShareIdentity(block, incomingBlock)) {
            didUpdate = true
            return incomingBlock
        }

        if (block.children?.length) {
            const childUpdate = replaceEquivalentBlockInBlocks(block.children, incomingBlock)
            if (childUpdate.updated) {
                didUpdate = true
                return {
                    ...block,
                    children: childUpdate.blocks,
                }
            }
        }

        return block
    })

    return {
        blocks: didUpdate ? nextBlocks.sort((a, b) => a.order - b.order) : blocks,
        updated: didUpdate,
    }
}

export function replaceEquivalentBlockInMessages(
    messages: ChatMessage[],
    incomingBlock: MessageBlock,
): { messages: ChatMessage[]; updated: boolean } {
    let didUpdate = false

    const nextMessages = messages.map((message) => {
        if (!message.blocks?.length) {
            return message
        }

        const blockUpdate = replaceEquivalentBlockInBlocks(message.blocks, incomingBlock)
        if (!blockUpdate.updated) {
            return message
        }

        didUpdate = true
        return {
            ...message,
            blocks: blockUpdate.blocks,
            content: extractMessageText(blockUpdate.blocks),
        }
    })

    return {
        messages: didUpdate ? nextMessages : messages,
        updated: didUpdate,
    }
}

export function removeEquivalentBlockFromBlocks(blocks: MessageBlock[], incomingBlock: MessageBlock): MessageBlock[] {
    return blocks.flatMap((block) => {
        if (block.id === incomingBlock.id || blocksShareIdentity(block, incomingBlock)) {
            return []
        }
        if (block.children?.length) {
            return [{
                ...block,
                children: removeEquivalentBlockFromBlocks(block.children, incomingBlock),
            }]
        }
        return [block]
    })
}

export function buildErrorMessage(message: string): ChatMessage {
    const errorText = `⚠ ${message || 'Unknown error'}`
    return {
        id: `error-${Date.now()}`,
        role: 'assistant',
        content: errorText,
        blocks: normalizeBlocks([
            {
                id: `error-block-${Date.now()}`,
                kind: 'text',
                order: 0,
                status: 'completed',
                visible: true,
                ui_kind: 'text',
                payload: {
                    text: errorText,
                },
            },
        ]),
        createdAt: new Date().toISOString(),
    }
}

export function appendErrorMessageIfMissing(messages: ChatMessage[], message: string): ChatMessage[] {
    const normalized = String(message || '').trim()
    if (!normalized) {
        return messages
    }
    const errorText = `⚠ ${normalized}`
    const alreadyVisible = messages.some((item) => String(item.content || '').trim() === errorText)
    return alreadyVisible ? messages : [...messages, buildErrorMessage(normalized)]
}
