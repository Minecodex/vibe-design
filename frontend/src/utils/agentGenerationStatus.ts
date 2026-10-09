import { wireRecord } from '@/store/harnessWireFields'
export type AgentToolStatus = 'pending' | 'running' | 'completed' | 'failed'

type GenerationRecord = Record<string, unknown> | undefined

type ResolveAsyncGenerationToolStatusInput = {
    currentStatus: AgentToolStatus
    result?: GenerationRecord
    error?: unknown
    args?: GenerationRecord
}

export function isAsyncGenerationTool(toolName: string) {
    return toolName === 'generate_image' || toolName === 'generate_video'
}

export function getGenerationTaskId(
    result?: GenerationRecord,
    args?: GenerationRecord,
): string | number | null {
    const rawTaskId = result?.task_id ?? result?.id ?? args?.task_id
    if (typeof rawTaskId === 'number' && Number.isFinite(rawTaskId)) {
        return rawTaskId
    }
    if (typeof rawTaskId === 'string') {
        const trimmed = rawTaskId.trim()
        if (trimmed.length > 0) {
            return trimmed
        }
    }
    return null
}

export function resolveAsyncGenerationToolStatus({
    currentStatus,
    result,
    error,
    args,
}: ResolveAsyncGenerationToolStatusInput): AgentToolStatus {
    const taskId = getGenerationTaskId(result, args)
    const hasTaskId = taskId != null
    const resStatus = result?.status
    const canvasItemStatus = wireRecord(result?.canvas_item)?.status
    const hasResultUrl = !!(result?.result_url || (Array.isArray(result?.result_urls) && result.result_urls.length))
    const hasError = !!(error || result?.error || result?.error_message)
    const hasFailedStatus = resStatus === 'failed' || canvasItemStatus === 'failed' || currentStatus === 'failed'

    if (hasTaskId) {
        if (hasFailedStatus) return 'failed'
        if (resStatus === 'completed' || hasResultUrl) return 'completed'
        return 'running'
    }

    if (hasFailedStatus) return 'failed'
    if (resStatus === 'completed' || hasResultUrl) return 'completed'
    if (hasError) return 'failed'
    return currentStatus
}
