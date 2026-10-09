import { wireRecord } from '@/store/harnessWireFields'
import type { GenerationTaskRead } from '@/api/endpoints/generation'

export type CanvasGenerationTaskSnapshot = Partial<GenerationTaskRead> & {
  task_id?: string | number
  artifact_ref?: string | null
  provider_code?: string | null
  resolution?: string | null
  duration?: string | number | null
  quality?: string | null
  canvas_item?: Record<string, unknown> | null
  canvas_revision?: number | null
  canvas_item_deleted?: boolean | null
  artifact?: Record<string, unknown> | null
}

export const mergeGenerationTaskSnapshot = (
  currentResult: Record<string, unknown> | undefined,
  taskData: CanvasGenerationTaskSnapshot,
) => {
  const nextCanvasItemSource = wireRecord(currentResult?.canvas_item) ?? taskData.canvas_item
  const nextCanvasItem: Record<string, unknown> | undefined = nextCanvasItemSource
    ? { ...nextCanvasItemSource }
    : undefined
  const nextParams = taskData.params || wireRecord(currentResult?.params) || null
  const nextResolution = nextParams?.resolution || currentResult?.resolution || nextCanvasItem?.resolution
  const nextAspectRatio = nextParams?.aspect_ratio || currentResult?.aspect_ratio || nextCanvasItem?.aspect_ratio
  const nextDuration = nextParams?.duration || currentResult?.duration || nextCanvasItem?.duration

  if (nextCanvasItem) {
    nextCanvasItem.task_id = taskData.task_id ?? taskData.id
    nextCanvasItem.provider_code = taskData.provider_code || nextCanvasItem.provider_code
    nextCanvasItem.model_name = taskData.model_name || nextCanvasItem.model_name
    nextCanvasItem.model_label = taskData.model_label || nextCanvasItem.model_label
    nextCanvasItem.status = taskData.status === 'completed'
      ? 'completed'
      : taskData.status === 'failed'
        ? 'failed'
        : nextCanvasItem.status
    nextCanvasItem.failure_kind = taskData.status === 'failed' ? 'task_failed' : undefined
    if (nextResolution) nextCanvasItem.resolution = nextResolution
    if (nextAspectRatio) nextCanvasItem.aspect_ratio = nextAspectRatio
    if (nextDuration) nextCanvasItem.duration = String(nextDuration)
    if (taskData.result_url) nextCanvasItem.url = taskData.result_url
  }

  return {
    ...currentResult,
    task_snapshot_loaded: true,
    id: taskData.id ?? taskData.task_id,
    task_id: taskData.task_id ?? taskData.id,
    artifact_ref: taskData.artifact_ref ?? currentResult?.artifact_ref,
    status: taskData.status,
    progress: taskData.progress,
    result_url: taskData.result_url || currentResult?.result_url,
    result_urls: taskData.result_urls || currentResult?.result_urls,
    error_message: taskData.error_message || currentResult?.error_message,
    canvas_revision: taskData.canvas_revision ?? currentResult?.canvas_revision,
    canvas_item_deleted: taskData.canvas_item_deleted ?? currentResult?.canvas_item_deleted,
    provider_code: taskData.provider_code || currentResult?.provider_code,
    model_name: taskData.model_name || currentResult?.model_name,
    model_label: taskData.model_label || currentResult?.model_label,
    resolution: taskData.resolution || currentResult?.resolution,
    duration: taskData.duration || currentResult?.duration,
    quality: taskData.quality || currentResult?.quality,
    params: nextParams,
    canvas_item: nextCanvasItem,
    artifact: taskData.artifact || currentResult?.artifact,
  }
}
