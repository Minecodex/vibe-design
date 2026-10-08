import type { AgentEvent } from '@/api/endpoints/agent'
import type { MessageBlock, ToolCallInfo } from './canvasAgentTypes'
import { normalizeHarnessPayload } from './canvasAgentBlockNormalize'

export function applyToolCallUpdatesToBlock(
    block: MessageBlock,
    callId: string,
    updates: Partial<ToolCallInfo>,
): MessageBlock {
    const nextChildren = block.children?.map((child) => applyToolCallUpdatesToBlock(child, callId, updates))
    const childrenChanged = !!nextChildren && nextChildren.some((child, index) => child !== block.children?.[index])
    const blockCallId = String(block.payload.call_id || block.id)
    const incomingTaskId = updates.result?.task_id
    const blockTaskId = (
        block.payload.task_id
        ?? block.payload.result?.task_id
    )
    const taskIdMatches = (
        incomingTaskId == null
        || blockTaskId == null
        || String(incomingTaskId) === String(blockTaskId)
    )
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
        nextPayload.task_id = nextResult.task_id ?? nextPayload.task_id
        nextPayload.preview_url = nextResult.preview_url ?? nextPayload.preview_url
        nextPayload.result_url = nextResult.result_url ?? nextPayload.result_url
        nextPayload.error_message = (
            nextResult.error_message
            ?? nextResult.error
            ?? nextPayload.error_message
        )
    }

    if (updates.error !== undefined) {
        nextPayload.error_message = updates.error
    }
    if (updates.streamingText !== undefined) {
        nextPayload.stream_text = updates.streamingText
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

export function normalizeToolResultStatus(result: Record<string, unknown>, fallbackStatus?: unknown): ToolCallInfo['status'] {
    const rawStatus = String(result.status ?? fallbackStatus ?? '').toLowerCase()
    if (
        rawStatus === 'failed'
        || rawStatus === 'error'
        || rawStatus === 'cancelled'
    ) {
        return 'failed'
    }
    if (
        rawStatus === 'completed'
        || rawStatus === 'succeeded'
        || !!result.result_url
    ) {
        return 'completed'
    }
    if (extractToolResultStreamText(result)) {
        return 'completed'
    }
    return 'running'
}

export function extractToolResultStreamText(result: Record<string, unknown>): string | undefined {
    const text = result.stream_text
        ?? result.output
        ?? result.analysis
        ?? result.description
        ?? result.message
        ?? result.content

    return typeof text === 'string' && text.trim().length > 0 ? text : undefined
}

export function getToolUiKind(toolName: string, result?: Record<string, unknown>): string {
    if (toolName === 'generate_image' || toolName === 'generate_video') {
        return 'generation_task'
    }
    if (toolName === 'web_search' || toolName === 'search_web') {
        return 'web_search_card'
    }
    if (result && extractToolResultStreamText(result)) {
        return 'stream_panel'
    }
    return 'compact_tool'
}

export function buildToolPayloadMeta(toolName: string): Record<string, unknown> | undefined {
    if (toolName === 'generate_image') {
        return { media_type: 'image' }
    }
    if (toolName === 'generate_video') {
        return { media_type: 'video' }
    }
    return undefined
}

export function extractToolElapsedMs(event: AgentEvent, result: Record<string, unknown>): number | undefined {
    const eventResult = event.data.result
    const nestedElapsed = eventResult && typeof eventResult === 'object'
        ? (eventResult as Record<string, unknown>).elapsed_ms
        : undefined
    const rawElapsed = (
        result.elapsed_ms
        ?? event.data.elapsed_ms
        ?? nestedElapsed
    )

    const elapsedMs = Number(rawElapsed)
    return Number.isFinite(elapsedMs) && elapsedMs >= 0 ? elapsedMs : undefined
}

export function upsertStreamingToolResultBlock(blocks: MessageBlock[], event: AgentEvent): MessageBlock[] {
    const toolName = String(event.data.tool || '')
    const callId = String(event.data.call_id || '')
    if (!toolName || !callId) {
        return blocks
    }

    const normalizedResult = (
        normalizeHarnessPayload(event.data.result || {}) as Record<string, unknown>
    ) || {}
    const status = normalizeToolResultStatus(normalizedResult, event.data.status)
    const errorMessage = String(
        normalizedResult.error_message
        ?? event.data.error
        ?? '',
    ) || undefined
    const streamText = extractToolResultStreamText(normalizedResult)
    const elapsedMs = extractToolElapsedMs(event, normalizedResult)
    const existingBlock = blocks.find((block) => String(block.payload.call_id || block.id) === callId)

    const nextPayload = {
        tool_name: toolName,
        call_id: callId,
        status: normalizedResult.status ?? status,
        progress: normalizedResult.progress,
        task_id: normalizedResult.task_id,
        preview_url: normalizedResult.preview_url,
        result_url: normalizedResult.result_url,
        error_message: errorMessage,
        elapsed_ms: elapsedMs,
        meta: buildToolPayloadMeta(toolName),
        result: normalizedResult,
        stream_text: streamText,
    }

    if (existingBlock) {
        return blocks.map((block) => (
            String(block.payload.call_id || block.id) === callId
                ? {
                    ...block,
                    status,
                    uiKind: getToolUiKind(toolName, normalizedResult),
                    payload: {
                        ...block.payload,
                        ...nextPayload,
                    },
                }
                : block
        ))
    }

    const nextOrder = blocks.length > 0
        ? Math.max(...blocks.map((block) => Number(block.order ?? 0))) + 1
        : 0

    return [
        ...blocks,
        {
            id: `tool-${callId}`,
            kind: 'tool' as const,
            order: nextOrder,
            status,
            visible: true,
            uiKind: getToolUiKind(toolName, normalizedResult),
            payload: nextPayload,
        },
    ].sort((a, b) => a.order - b.order)
}
