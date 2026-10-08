export type GenerationProjectionStatus = 'pending' | 'processing' | 'completed' | 'failed' | 'retrying'

export type GenerationProjectionUpdate = {
  taskId: string | number
  status?: GenerationProjectionStatus | string | null
  sourceSequence?: number | null
  progress?: number | null
  resultUrl?: string | null
  artifactId?: string | number | null
  artifactRef?: string | number | null
  errorMessage?: string | null
  source?: 'event' | 'poll' | 'local'
}

export type GenerationTaskSnapshotLike = {
  id?: string | number | null
  task_id?: string | number | null
  taskId?: string | number | null
  status?: string | null
  progress?: number | null
  result_url?: string | null
  resultUrl?: string | null
  planned_result_url?: string | null
  plannedResultUrl?: string | null
  artifact_ref?: string | number | null
  artifactRef?: string | number | null
  asset_id?: string | number | null
  assetId?: string | number | null
  artifact_id?: string | number | null
  artifactId?: string | number | null
  error_message?: string | null
  errorMessage?: string | null
  error?: string | null
  artifact?: Record<string, unknown> | null
  canvas_item?: Record<string, unknown> | null
  canvasItem?: Record<string, unknown> | null
}

export type GenerationViewModel = {
  taskId: string
  status: GenerationProjectionStatus
  source: 'event' | 'poll' | 'local'
  sourceSequence: number
  progress: number
  resultUrl: string | null
  artifactId: string | null
  errorMessage: string | null
}

export type GenerationProjectionState = {
  tasks: Record<string, GenerationViewModel>
  insertedArtifactKeys: Record<string, true>
  placeholderArtifactKeys: Record<string, true>
}

export type GenerationProjectionResult = {
  state: GenerationProjectionState
  canvasInsertion?: { taskId: string; artifactId: string; resultUrl: string }
  canvasPlaceholder?: { taskId: string; artifactId: string }
}

export function createGenerationProjectionState(): GenerationProjectionState {
  return { tasks: {}, insertedArtifactKeys: {}, placeholderArtifactKeys: {} }
}

export function buildGenerationProjectionUpdateFromTaskSnapshot(
  snapshot: GenerationTaskSnapshotLike | null | undefined,
  fallbackTaskId?: string | number | null,
): GenerationProjectionUpdate | null {
  if (!snapshot || typeof snapshot !== 'object') {
    return null
  }
  const taskId = pickFirst(
    snapshot.task_id,
    snapshot.taskId,
    snapshot.id,
    fallbackTaskId,
  )
  if (taskId == null || String(taskId).trim() === '') {
    return null
  }

  const canvasItem = isRecord(snapshot.canvas_item)
    ? snapshot.canvas_item
    : isRecord(snapshot.canvasItem)
      ? snapshot.canvasItem
      : null
  const artifact = isRecord(snapshot.artifact) ? snapshot.artifact : null
  const artifactRef = pickFirst(
    snapshot.artifact_ref,
    snapshot.artifactRef,
    canvasItem?.artifact_ref,
    canvasItem?.artifactRef,
  )

  return {
    taskId,
    status: snapshot.status,
    sourceSequence: null,
    progress: typeof snapshot.progress === 'number' ? snapshot.progress : null,
    resultUrl: stringOrNull(pickFirst(
      snapshot.result_url,
      snapshot.resultUrl,
      canvasItem?.url,
      canvasItem?.result_url,
      resolveArtifactResultUrl(artifact),
    )),
    artifactId: pickFirst(
      canvasItem?.id,
      snapshot.asset_id,
      snapshot.assetId,
      snapshot.artifact_id,
      snapshot.artifactId,
      artifact?.id,
      artifactRef,
    ),
    artifactRef,
    errorMessage: stringOrNull(pickFirst(
      snapshot.error_message,
      snapshot.errorMessage,
      snapshot.error,
    )),
    source: 'poll',
  }
}

export function applyGenerationProjectionUpdate(
  state: GenerationProjectionState,
  update: GenerationProjectionUpdate,
): GenerationProjectionResult {
  const taskId = String(update.taskId || '').trim()
  if (!taskId) {
    return { state }
  }
  const existing = state.tasks[taskId]
  const incomingSequence = Number(update.sourceSequence ?? existing?.sourceSequence ?? 0)
  if (existing && incomingSequence < existing.sourceSequence) {
    return { state }
  }

  const incomingStatus = normalizeGenerationProjectionStatus(update.status) ?? existing?.status ?? 'pending'
  if (
    existing
    && existing.status === 'completed'
    && !isTerminalGenerationProjectionStatus(incomingStatus)
    && incomingSequence === existing.sourceSequence
  ) {
    return { state }
  }
  if (
    existing
    && existing.status === 'failed'
    && existing.source === 'event'
    && !isTerminalGenerationProjectionStatus(incomingStatus)
    && incomingSequence === existing.sourceSequence
  ) {
    return { state }
  }

  const nextTask: GenerationViewModel = {
    taskId,
    status: incomingStatus,
    source: update.source ?? existing?.source ?? 'local',
    sourceSequence: Math.max(existing?.sourceSequence ?? 0, incomingSequence),
    progress: normalizeProgress(update.progress, existing?.progress ?? 0, incomingStatus),
    resultUrl: update.resultUrl ?? existing?.resultUrl ?? null,
    artifactId: update.artifactId == null ? existing?.artifactId ?? null : String(update.artifactId),
    errorMessage: update.errorMessage ?? existing?.errorMessage ?? null,
  }

  const nextState: GenerationProjectionState = {
    tasks: { ...state.tasks, [taskId]: nextTask },
    insertedArtifactKeys: { ...state.insertedArtifactKeys },
    placeholderArtifactKeys: { ...(state.placeholderArtifactKeys || {}) },
  }

  const artifactId = nextTask.artifactId
  const artifactKey = artifactId ? `${taskId}:${artifactId}` : null
  if (
    nextTask.status === 'completed'
    && nextTask.resultUrl
    && artifactId
    && artifactKey
    && !nextState.insertedArtifactKeys[artifactKey]
  ) {
    nextState.insertedArtifactKeys[artifactKey] = true
    return {
      state: nextState,
      canvasInsertion: {
        taskId,
        artifactId,
        resultUrl: nextTask.resultUrl,
      },
    }
  }

  if (
    !isTerminalGenerationProjectionStatus(nextTask.status)
    && artifactId
    && artifactKey
    && !nextState.placeholderArtifactKeys[artifactKey]
  ) {
    nextState.placeholderArtifactKeys[artifactKey] = true
    return {
      state: nextState,
      canvasPlaceholder: {
        taskId,
        artifactId,
      },
    }
  }

  return { state: nextState }
}

export function normalizeGenerationProjectionStatus(status: GenerationProjectionUpdate['status']): GenerationProjectionStatus | null {
  const normalized = String(status || '').trim().toLowerCase()
  if (normalized === 'queued' || normalized === 'running') return 'processing'
  if (normalized === 'pending' || normalized === 'processing' || normalized === 'completed' || normalized === 'failed' || normalized === 'retrying') {
    return normalized
  }
  return null
}

function normalizeProgress(progress: number | null | undefined, fallback: number, status: GenerationProjectionStatus): number {
  if (status === 'completed') return 100
  if (typeof progress === 'number' && Number.isFinite(progress)) {
    return Math.min(Math.max(Math.round(progress), 0), 100)
  }
  return fallback
}

export function isTerminalGenerationProjectionStatus(status: GenerationProjectionStatus): boolean {
  return status === 'completed' || status === 'failed'
}

function pickFirst(...values: unknown[]): any {
  return values.find((value) => value != null && value !== '')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function stringOrNull(value: unknown): string | null {
  if (value == null) return null
  const normalized = String(value).trim()
  return normalized || null
}

function resolveArtifactResultUrl(artifact: Record<string, unknown> | null): string | null {
  if (!artifact) return null
  const baseDir = String(artifact.base_dir || artifact.baseDir || '').trim()
  const relativePath = String(artifact.relative_path || artifact.relativePath || '').trim()
  if (relativePath && (!baseDir || baseDir === 'FILES_DIR')) {
    return relativePath
  }
  return stringOrNull(artifact.absolute_path || artifact.absolutePath)
}
