import type { GenerationProjectionUpdate } from './generationProjection'

type GenerationEventLike = {
  type: string
  sequence?: number | null
  data?: Record<string, any> | null
}

const GENERATION_EVENT_TYPES = new Set(['generation_started', 'generation_completed', 'generation_failed'])
const GENERATION_ITEM_EVENT_TYPES = new Set(['item_started', 'item_updated', 'item_completed'])

export function isGenerationProjectionEvent(event: GenerationEventLike): boolean {
  return GENERATION_EVENT_TYPES.has(String(event.type || '')) || isGenerationTaskItemEvent(event)
}

export function buildGenerationProjectionUpdateFromEvent(
  event: GenerationEventLike,
): GenerationProjectionUpdate | null {
  if (!isGenerationProjectionEvent(event)) {
    return null
  }

  if (isGenerationTaskItemEvent(event)) {
    return buildGenerationProjectionUpdateFromItemEvent(event)
  }

  const data = isRecord(event.data) ? event.data : {}
  const result = isRecord(data.result) ? data.result : {}
  const taskId = pickFirst(
    result.task_id,
    result.taskId,
    data.task_id,
    data.taskId,
  )
  if (taskId == null || String(taskId).trim() === '') {
    return null
  }

  return {
    taskId,
    status: pickFirst(result.status, data.status, statusFromEventType(event.type)),
    sourceSequence: typeof event.sequence === 'number' ? event.sequence : numberOrNull(data.sequence),
    progress: numberOrNull(pickFirst(result.progress, data.progress)),
    resultUrl: stringOrNull(pickFirst(result.result_url, result.resultUrl, data.result_url, data.resultUrl, data.url)),
    artifactId: pickFirst(
      result.asset_id,
      result.assetId,
      result.artifact_id,
      result.artifactId,
      data.asset_id,
      data.assetId,
      data.artifact_id,
      data.artifactId,
      result.artifact_ref,
      result.artifactRef,
      data.artifact_ref,
      data.artifactRef,
    ),
    artifactRef: pickFirst(
      result.artifact_ref,
      result.artifactRef,
      data.artifact_ref,
      data.artifactRef,
      data.agent_media_key,
      data.agentMediaKey,
    ),
    errorMessage: stringOrNull(pickFirst(
      result.error_message,
      result.errorMessage,
      result.error,
      data.error_message,
      data.errorMessage,
      data.error,
    )),
    source: 'event',
  }
}

function buildGenerationProjectionUpdateFromItemEvent(
  event: GenerationEventLike,
): GenerationProjectionUpdate | null {
  const data = isRecord(event.data) ? event.data : {}
  const payload = isRecord(data.payload) ? data.payload : {}
  const error = isRecord(data.error) ? data.error : null
  const taskId = pickFirst(
    payload.task_id,
    payload.taskId,
    data.task_id,
    data.taskId,
    data.item_id,
    data.itemId,
  )
  if (taskId == null || String(taskId).trim() === '') {
    return null
  }

  return {
    taskId,
    status: pickFirst(data.status, payload.status, statusFromItemEventType(event.type)),
    sourceSequence: typeof event.sequence === 'number' ? event.sequence : numberOrNull(data.sequence),
    progress: numberOrNull(pickFirst(payload.progress, data.progress)),
    resultUrl: stringOrNull(pickFirst(
      payload.result_url,
      payload.resultUrl,
      payload.url,
      payload.canvas_item?.url,
      payload.canvasItem?.url,
      data.result_url,
      data.resultUrl,
    )),
    artifactId: pickFirst(
      payload.asset_id,
      payload.assetId,
      payload.artifact_id,
      payload.artifactId,
      payload.artifact_ref,
      payload.artifactRef,
      data.item_id,
      data.itemId,
    ),
    artifactRef: pickFirst(
      payload.artifact_ref,
      payload.artifactRef,
      data.item_id,
      data.itemId,
    ),
    errorMessage: stringOrNull(pickFirst(
      error?.summary,
      payload.error_message,
      payload.errorMessage,
      payload.error,
      data.error_message,
      data.errorMessage,
    )),
    source: 'event',
  }
}

function isGenerationTaskItemEvent(event: GenerationEventLike): boolean {
  if (!GENERATION_ITEM_EVENT_TYPES.has(String(event.type || ''))) {
    return false
  }
  const data = isRecord(event.data) ? event.data : {}
  return String(data.item_type || data.itemType || '').trim() === 'generation_task'
}

export function buildCanvasItemFromGenerationEvent(
  event: GenerationEventLike,
  insertion: { taskId: string; artifactId: string; resultUrl: string },
  conversationId?: number | string | null,
): Record<string, any> {
  const data = isRecord(event.data) ? event.data : {}
  const result = isRecord(data.result) ? data.result : {}
  const payload = isRecord(data.payload) ? data.payload : {}
  const rawItem = isRecord(data.canvas_item)
    ? data.canvas_item
    : isRecord(result.canvas_item)
      ? result.canvas_item
      : isRecord(payload.canvas_item)
        ? payload.canvas_item
        : isRecord(data.item)
          ? data.item
          : {}
  const item = { ...rawItem }
  item.id = item.id ?? insertion.artifactId
  item.type = item.type ?? inferCanvasCompletedType(data, result, payload)
  item.url = item.url ?? insertion.resultUrl
  item.task_id = item.task_id ?? insertion.taskId
  item.result_url = item.result_url ?? insertion.resultUrl
  item.artifact_ref = item.artifact_ref ?? result.artifact_ref ?? data.artifact_ref ?? null
  item.agentMediaKey = item.agentMediaKey ?? data.agent_media_key ?? data.agentMediaKey ?? insertion.artifactId
  applyCanvasRevisionMetaToItem(item, buildCanvasRevisionMeta(data, result, payload, item))
  if (conversationId != null && item.conversationId == null) {
    item.conversationId = conversationId
  }
  return item
}

export function buildCanvasPlaceholderFromGenerationEvent(
  event: GenerationEventLike,
  placeholder: { taskId: string; artifactId: string },
  conversationId?: number | string | null,
): Record<string, any> {
  const data = isRecord(event.data) ? event.data : {}
  const result = isRecord(data.result) ? data.result : {}
  const payload = isRecord(data.payload) ? data.payload : {}
  const rawItem = isRecord(data.canvas_item)
    ? data.canvas_item
    : isRecord(result.canvas_item)
      ? result.canvas_item
      : isRecord(payload.canvas_item)
        ? payload.canvas_item
        : {}
  const item = { ...rawItem }
  const artifactRef = pickFirst(
    item.artifact_ref,
    item.artifactRef,
    result.artifact_ref,
    result.artifactRef,
    data.artifact_ref,
    data.artifactRef,
    payload.artifact_ref,
    payload.artifactRef,
    placeholder.artifactId,
  )
  item.id = item.id ?? buildGeneratedCanvasPlaceholderId(placeholder.artifactId, placeholder.taskId)
  item.type = item.type ?? inferCanvasPlaceholderType(data, result, payload)
  item.url = item.url ?? ''
  item.task_id = item.task_id ?? placeholder.taskId
  item.artifact_ref = item.artifact_ref ?? artifactRef ?? null
  item.status = item.status ?? 'generating'
  item.progress = item.progress ?? result.progress ?? data.progress ?? payload.progress ?? 0
  item.agentMediaKey = item.agentMediaKey ?? item.agent_media_key ?? item.id
  applyCanvasRevisionMetaToItem(item, buildCanvasRevisionMeta(data, result, payload, item))
  if (conversationId != null && item.conversationId == null) {
    item.conversationId = conversationId
  }
  return item
}

export function buildCanvasRevisionMetaFromGenerationEvent(event: GenerationEventLike): Record<string, any> | undefined {
  const data = isRecord(event.data) ? event.data : {}
  const result = isRecord(data.result) ? data.result : {}
  const payload = isRecord(data.payload) ? data.payload : {}
  const item = isRecord(data.canvas_item)
    ? data.canvas_item
    : isRecord(result.canvas_item)
      ? result.canvas_item
      : isRecord(payload.canvas_item)
        ? payload.canvas_item
        : isRecord(data.item)
          ? data.item
          : {}
  const meta = buildCanvasRevisionMeta(data, result, payload, item)
  return meta.canvasRevision != null || meta.canvasItemDeleted === true ? meta : undefined
}

function buildCanvasRevisionMeta(...sources: Record<string, any>[]): Record<string, any> {
  const revision = pickFirst(...sources.flatMap((source) => [
    source.canvas_revision,
    source.canvasRevision,
  ]))
  const normalizedRevision = numberOrNull(revision)
  const canvasItemDeleted = sources.some((source) => (
    source.canvas_item_deleted === true || source.canvasItemDeleted === true
  ))
  return {
    ...(normalizedRevision != null ? { canvasRevision: Math.trunc(normalizedRevision) } : {}),
    canvasItemDeleted,
  }
}

function applyCanvasRevisionMetaToItem(item: Record<string, any>, meta: Record<string, any>): void {
  if (meta.canvasRevision != null && item.canvas_revision == null && item.canvasRevision == null) {
    item.canvas_revision = meta.canvasRevision
  }
  if (meta.canvasItemDeleted === true && item.canvas_item_deleted == null && item.canvasItemDeleted == null) {
    item.canvas_item_deleted = true
  }
}

function statusFromEventType(type: string): string | null {
  if (type === 'generation_completed') return 'completed'
  if (type === 'generation_failed') return 'failed'
  if (type === 'generation_started') return 'processing'
  return null
}

function statusFromItemEventType(type: string): string | null {
  if (type === 'item_started') return 'processing'
  if (type === 'item_updated') return 'processing'
  if (type === 'item_completed') return 'completed'
  return null
}

function pickFirst(...values: any[]): any {
  return values.find((value) => value != null && value !== '')
}

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function numberOrNull(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function stringOrNull(value: unknown): string | null {
  if (value == null) return null
  const normalized = String(value).trim()
  return normalized || null
}

function inferCanvasPlaceholderType(
  data: Record<string, any>,
  result: Record<string, any>,
  payload: Record<string, any>,
): 'image_generator' | 'video_generator' {
  const type = String(
    data.media_type
    || data.mediaType
    || result.media_type
    || result.mediaType
    || payload.media_type
    || payload.mediaType
    || data.kind
    || result.kind
    || payload.kind
    || data.tool_name
    || result.tool_name
    || payload.tool_name
    || '',
  ).toLowerCase()
  return type.includes('video') ? 'video_generator' : 'image_generator'
}

function inferCanvasCompletedType(
  data: Record<string, any>,
  result: Record<string, any>,
  payload: Record<string, any>,
): 'image' | 'video' {
  return inferCanvasPlaceholderType(data, result, payload) === 'video_generator' ? 'video' : 'image'
}

function buildGeneratedCanvasPlaceholderId(artifactId: string, taskId: string): string {
  const stable = String(artifactId || taskId || 'pending')
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'pending'
  return `agent-generated-${stable}`
}
