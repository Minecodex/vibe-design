import type { CanvasItem } from '@/api/endpoints/projects'

export type CanvasGenerationFailureKind = 'task_failed' | 'internal_failed'
export type CanvasGenerationPollingStatus = 'generating' | 'completed' | 'failed'

type FailureLike = Pick<CanvasItem, 'type' | 'status' | 'task_id' | 'generation_kind'> & {
  taskId?: string | number | null
  failure_kind?: CanvasGenerationFailureKind
}

export function getGenerationFailureKind(item: {
  status?: string | null
  task_id?: string | number | null
  taskId?: string | number | null
} | null | undefined): CanvasGenerationFailureKind | undefined {
  if (!item || item.status !== 'failed') {
    return undefined
  }

  return item.task_id != null || item.taskId != null ? 'task_failed' : 'internal_failed'
}

function finiteRetryNumber(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

export function getGenerationPollingStatus(task: {
  status?: string | null
  auto_retry_count?: number | string | null
  auto_retry_max?: number | string | null
} | null | undefined): CanvasGenerationPollingStatus {
  const rawStatus = String(task?.status || '').toLowerCase()
  if (rawStatus === 'completed' || rawStatus === 'succeeded') {
    return 'completed'
  }

  if (rawStatus === 'failed' || rawStatus === 'error' || rawStatus === 'cancelled' || rawStatus === 'canceled') {
    const autoRetryCount = finiteRetryNumber(task?.auto_retry_count)
    const autoRetryMax = finiteRetryNumber(task?.auto_retry_max)
    if (autoRetryCount != null && autoRetryMax != null && autoRetryCount < autoRetryMax) {
      return 'generating'
    }
    return 'failed'
  }

  return 'generating'
}

export function isRetryableFailedGenerationItem(item: FailureLike | null | undefined) {
  if (!item) return false
  const isGenerator = item.type === 'image_generator' || item.type === 'video_generator'
  if (!isGenerator || item.status !== 'failed') {
    return false
  }
  return (item.failure_kind || getGenerationFailureKind(item)) === 'task_failed'
}

export function isInternalFailedGenerationItem(item: FailureLike | null | undefined) {
  if (!item) return false
  const isGenerator = item.type === 'image_generator' || item.type === 'video_generator'
  if (!isGenerator || item.status !== 'failed') {
    return false
  }

  return (item.failure_kind || getGenerationFailureKind(item)) === 'internal_failed'
}
