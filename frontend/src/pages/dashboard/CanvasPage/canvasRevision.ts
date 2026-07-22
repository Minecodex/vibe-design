export const CANVAS_REVISION_BROADCAST_CHANNEL = 'canvas-revision'

export interface CanvasRevisionBroadcastMessage {
  projectId: number
  canvasRevision: number
}

export function normalizeCanvasRevision(value: unknown): number {
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric >= 0 ? Math.trunc(numeric) : 0
}

export function isCanvasRevisionConflictError(error: unknown): boolean {
  const response = (error as { response?: { status?: number } } | null)?.response
  return response?.status === 409
}

export function isSameCanvasRevision(left: unknown, right: unknown): boolean {
  const normalizedLeft = normalizeCanvasRevision(left)
  const normalizedRight = normalizeCanvasRevision(right)
  return normalizedLeft > 0 && normalizedLeft === normalizedRight
}

export interface CanvasRevisionSyncState {
  currentRevision: number
  isStale: boolean
  staleRevision?: number | null
}

export interface CanvasRevisionSyncOptions {
  resolveStale?: boolean
}

export interface CanvasRevisionSyncResult {
  currentRevision: number
  isStale: boolean
  staleRevision: number | null
  revisionChanged: boolean
  staleCleared: boolean
}

export function applyAgentPatchCanvasRevisionSync(
  state: CanvasRevisionSyncState,
  revision: unknown,
  options: CanvasRevisionSyncOptions = {},
): CanvasRevisionSyncResult {
  const normalizedRevision = normalizeCanvasRevision(revision)
  const currentRevision = normalizeCanvasRevision(state.currentRevision)
  const mayResolveStale = options.resolveStale !== false
  const staleCleared =
    normalizedRevision > 0
    && mayResolveStale
    && state.isStale
    && isSameCanvasRevision(state.staleRevision, normalizedRevision)

  return {
    currentRevision: Math.max(currentRevision, normalizedRevision),
    isStale: state.isStale && !staleCleared,
    staleRevision: staleCleared ? null : state.staleRevision ?? null,
    revisionChanged: normalizedRevision > currentRevision,
    staleCleared,
  }
}

export function broadcastCanvasRevision(projectId: number, canvasRevision: number) {
  if (typeof BroadcastChannel === 'undefined') return
  const channel = new BroadcastChannel(CANVAS_REVISION_BROADCAST_CHANNEL)
  channel.postMessage({ projectId, canvasRevision })
  channel.close()
}
