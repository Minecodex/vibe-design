import type { GenerationTaskRead } from '@/api/endpoints/generation'
import type { CanvasItem } from '@/api/endpoints/projects'

export const GENERATION_BINDING_RECOVERY_WINDOW_MS = 60_000

export function isGenerationTaskPendingStatus(status: CanvasItem['status'] | undefined) {
  return status === 'binding_task' || status === 'generating'
}

export function createGenerationClientRequestId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `canvas-generation-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

export function getGenerationRecoveryLookupKey(taskType: string, clientRequestId: string) {
  return `${taskType}:${clientRequestId}`
}

export function getCanvasGenerationTaskType(item: CanvasItem) {
  if (item.type === 'image_generator') {
    return 'text2image'
  }
  if (item.type !== 'video_generator') {
    return null
  }
  return (item.reference_images?.length || item.first_frame_image || item.tail_frame_image)
    ? 'image2video'
    : 'text2video'
}

export function getPendingGenerationBindingItems(items: CanvasItem[]) {
  return items
    .map((item) => {
      const taskType = getCanvasGenerationTaskType(item)
      if (
        !taskType
        || item.status !== 'binding_task'
        || item.task_id != null
        || !item.client_request_id
      ) {
        return null
      }
      return {
        itemId: item.id,
        client_request_id: item.client_request_id,
        task_type: taskType,
      }
    })
    .filter((item): item is {
      itemId: string
      client_request_id: string
      task_type: string
    } => item != null)
}

export function shouldExpireBindingTask(
  item: CanvasItem,
  now = Date.now(),
  recoveryWindowMs = GENERATION_BINDING_RECOVERY_WINDOW_MS,
) {
  const startedAt = Date.parse(String(item.binding_started_at || ''))
  if (!Number.isFinite(startedAt)) {
    return false
  }
  return now - startedAt >= recoveryWindowMs
}

export function applyRecoveredGenerationTask(item: CanvasItem, task: Partial<GenerationTaskRead>): CanvasItem {
  const resolvedResultUrl = task.result_url || task.result_urls?.[0] || item.url
  const recoveredStatus = task.status === 'completed'
    ? 'completed'
    : task.status === 'failed'
      ? 'failed'
      : 'generating'

  return {
    ...item,
    type: recoveredStatus === 'completed'
      ? (item.type === 'image_generator' ? 'image' : 'video')
      : item.type,
    status: recoveredStatus,
    task_id: task.id ?? item.task_id,
    client_request_id: task.client_request_id ?? item.client_request_id,
    url: recoveredStatus === 'completed' ? resolvedResultUrl : item.url,
    progress: recoveredStatus === 'completed' ? 100 : (task.progress ?? item.progress ?? 0),
    prompt: task.prompt ?? item.prompt,
    model_label: task.model_label ?? item.model_label,
    created_at: task.created_at ?? item.created_at,
    error_message: task.error_message ?? item.error_message,
    binding_started_at: undefined,
    asset_origin: recoveredStatus === 'completed' ? 'ai_generated' : item.asset_origin,
  }
}
