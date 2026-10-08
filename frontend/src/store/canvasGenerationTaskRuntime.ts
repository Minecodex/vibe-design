import { agentApi, type AgentEvent } from '@/api/endpoints/agent'
import { generationApi } from '@/api/endpoints/generation'
import type { ChatMessage, MessageBlock, ToolCallInfo } from './canvasAgentTypes'
import {
  buildGenerationProjectionUpdateFromTaskSnapshot,
  type GenerationTaskSnapshotLike,
} from './generationProjection'

const DEFAULT_POLL_INTERVAL_MS = 3000
const ERROR_RETRY_INTERVAL_MS = 5000

export type CanvasGenerationTaskSnapshot = GenerationTaskSnapshotLike & {
  conversation_id?: string | null
  params?: Record<string, any> | null
  kind?: string | null
  media_type?: string | null
  provider_code?: string | null
  model_name?: string | null
  model_label?: string | null
  resolution?: string | null
  duration?: string | number | null
  quality?: string | null
  result_urls?: string[] | null
  canvas_item?: Record<string, any> | null
  canvas_item_deleted?: boolean | null
  canvas_revision?: number | null
  suppress_standard_media_card?: boolean | null
  presentation_surface?: string | null
  presentation_scope?: Record<string, any> | null
  presentation_message_key?: string | null
  presentation_parent_block_key?: string | null
  presentation_order?: number | null
}

export type CanvasGenerationRuntimeState = {
  conversationId: string | number | null
  engineVersion?: 'harness' | string
  onCanvasUpdate?: ((action: string, item: Record<string, any>, meta?: Record<string, any>) => void) | null
}

export type CanvasGenerationRuntimeAdapter = {
  getState: () => CanvasGenerationRuntimeState
  updateToolCallByGenerationTask: (conversationId: string, snapshot: CanvasGenerationTaskSnapshot) => void
  updateCanvasItemByGenerationTask?: (conversationId: string, canvasItem: Record<string, any>) => void
  updateCanvasRevisionByAgentPatch?: (canvasRevision: number, options?: { canvasItemDeleted?: boolean }) => void
  saveCanvasItems?: (conversationId: string) => void
}

export type CanvasGenerationRuntimeStore = CanvasGenerationRuntimeState & {
  updateToolCallByGenerationTask: CanvasGenerationRuntimeAdapter['updateToolCallByGenerationTask']
  updateCanvasItemByGenerationTask: NonNullable<CanvasGenerationRuntimeAdapter['updateCanvasItemByGenerationTask']>
  updateCanvasRevisionByAgentPatch?: CanvasGenerationRuntimeAdapter['updateCanvasRevisionByAgentPatch']
}

export function createCanvasGenerationRuntimeAdapter(
  getState: () => CanvasGenerationRuntimeStore,
): CanvasGenerationRuntimeAdapter {
  return {
    getState,
    updateToolCallByGenerationTask: (conversationId, snapshot) => {
      getState().updateToolCallByGenerationTask(conversationId, snapshot)
    },
    updateCanvasItemByGenerationTask: (conversationId, canvasItem) => {
      getState().updateCanvasItemByGenerationTask(conversationId, canvasItem)
    },
    updateCanvasRevisionByAgentPatch: (canvasRevision, options) => {
      getState().updateCanvasRevisionByAgentPatch?.(canvasRevision, options)
    },
  }
}

type RuntimeTask = {
  key: string
  conversationId: string
  taskId: string
  artifactRef: string | null
  kind: string | null
  harness: boolean
  status: string
  adapter: CanvasGenerationRuntimeAdapter
  timeoutId: ReturnType<typeof setTimeout> | null
  polling: boolean
}

const tasks = new Map<string, RuntimeTask>()

export function buildGenerationTaskKey(conversationId: string | number, artifactRef?: string | number | null, taskId?: string | number | null): string {
  const item = String(artifactRef || taskId || '').trim()
  return `${String(conversationId)}:${item}`
}

export function upsertGenerationTaskFromItemEvent(
  event: AgentEvent,
  adapter: CanvasGenerationRuntimeAdapter,
): string | null {
  if (!isGenerationTaskItemEvent(event)) {
    return null
  }
  const state = adapter.getState()
  const payload = event.data?.payload
  const nestedConversationId = payload && typeof payload === 'object'
    ? (payload as Record<string, unknown>).conversation_id
    : undefined
  const conversationId = String(
    event.data?.conversation_id
    || nestedConversationId
    || state.conversationId
    || '',
  ).trim()
  if (!conversationId) {
    return null
  }

  const source = normalizeItemPayload(event)
  const taskId = String(source.task_id ?? source.id ?? '').trim()
  const artifactRef = String(source.artifact_ref ?? event.data.item_id ?? '').trim() || null
  if (!taskId && !artifactRef) {
    return null
  }

  const key = buildGenerationTaskKey(conversationId, artifactRef, taskId)
  const snapshot = normalizeGenerationSnapshot({
    ...source,
    task_id: taskId || source.task_id,
    artifact_ref: artifactRef || source.artifact_ref,
    status: normalizeRuntimeStatus(event.data.status || source.status || event.type),
  })
  const runtimeTask = upsertRuntimeTask(key, {
    conversationId,
    taskId: taskId || String(source.task_id || ''),
    artifactRef,
    kind: String(source.kind || '').trim() || null,
    harness: state.engineVersion === 'harness' || Boolean(event.data.conversation_id || source.conversation_id),
    status: String(snapshot.status || 'processing'),
    adapter,
  })

  if (!shouldSuppressStandardMediaCard(snapshot)) {
    adapter.updateToolCallByGenerationTask(conversationId, snapshot)
  }
  notifyCanvasRevision(adapter, snapshot)
  const canvasItem = shouldSkipCanvasProjection(snapshot)
    ? null
    : normalizeCanvasItem(snapshot) || buildCanvasPlaceholderFromSnapshot(snapshot, conversationId)
  if (canvasItem) {
    adapter.updateCanvasItemByGenerationTask?.(conversationId, canvasItem)
    publishCanvasPlaceholderUpdate(adapter, conversationId, snapshot, canvasItem)
    if (isTerminalStatus(snapshot.status)) {
      publishCanvasTerminalUpdate(adapter, conversationId, snapshot, canvasItem)
    }
  }

  if (isTerminalStatus(snapshot.status)) {
    disposeGenerationTask(key)
  } else {
    startGenerationTaskPolling(runtimeTask.key)
  }

  return key
}

// A task that reached a terminal status will never poll again, so drop it from the
// module-level registry. Leaving terminal tasks in place leaks an entry per generation
// for the lifetime of the page (the map was only ever cleared on conversation switch).
function disposeGenerationTask(taskKey: string): void {
  stopGenerationTaskPolling(taskKey)
  tasks.delete(taskKey)
}

export function recoverGenerationTasksFromSession(
  conversationId: string | number,
  session: { messages?: ChatMessage[]; streamingBlocks?: MessageBlock[]; currentToolCalls?: ToolCallInfo[] },
  adapter: CanvasGenerationRuntimeAdapter,
): number {
  const snapshots = collectPendingGenerationSnapshots(session)
  let recovered = 0
  for (const snapshot of snapshots) {
    const taskId = String(snapshot.task_id ?? snapshot.id ?? '').trim()
    const artifactRef = String(snapshot.artifact_ref ?? '').trim() || null
    const key = buildGenerationTaskKey(conversationId, artifactRef, taskId)
    upsertRuntimeTask(key, {
      conversationId: String(conversationId),
      taskId,
      artifactRef,
      kind: inferKind(snapshot),
      harness: adapter.getState().engineVersion === 'harness',
      status: String(snapshot.status || 'processing'),
      adapter,
    })
    startGenerationTaskPolling(key)
    recovered += 1
  }
  return recovered
}

export function startGenerationTaskPolling(taskKey: string): boolean {
  const task = tasks.get(taskKey)
  if (!task || task.polling || isTerminalStatus(task.status)) {
    return false
  }
  task.polling = true
  schedulePoll(task, 0)
  return true
}

export function stopGenerationTaskPolling(taskKey: string): boolean {
  const task = tasks.get(taskKey)
  if (!task) {
    return false
  }
  if (task.timeoutId) {
    clearTimeout(task.timeoutId)
  }
  task.timeoutId = null
  task.polling = false
  return true
}

export function applyGenerationTaskSnapshot(
  taskKey: string,
  snapshot: CanvasGenerationTaskSnapshot,
  adapterOverride?: CanvasGenerationRuntimeAdapter,
): void {
  const task = tasks.get(taskKey)
  const adapter = adapterOverride || task?.adapter
  const conversationId = task?.conversationId || String(snapshot.conversation_id || adapter?.getState().conversationId || '').trim()
  if (!adapter || !conversationId) {
    return
  }
  const normalized = normalizeGenerationSnapshot(snapshot)
  if (task) {
    task.status = String(normalized.status || task.status || 'processing')
  }
  if (!shouldSuppressStandardMediaCard(normalized)) {
    adapter.updateToolCallByGenerationTask(conversationId, normalized)
  }
  notifyCanvasRevision(adapter, normalized)
  const canvasItem = shouldSkipCanvasProjection(normalized)
    ? null
    : normalizeCanvasItem(normalized) || buildCanvasPlaceholderFromSnapshot(normalized, conversationId)
  if (canvasItem) {
    adapter.updateCanvasItemByGenerationTask?.(conversationId, canvasItem)
    publishCanvasPlaceholderUpdate(adapter, conversationId, normalized, canvasItem)
    if (isTerminalStatus(normalized.status)) {
      publishCanvasTerminalUpdate(adapter, conversationId, normalized, canvasItem)
    }
  }
  if (isTerminalStatus(normalized.status)) {
    disposeGenerationTask(taskKey)
  }
}

export function disposeConversationGenerationTasks(conversationId: string | number): void {
  const prefix = `${String(conversationId)}:`
  for (const [key] of tasks) {
    if (!key.startsWith(prefix)) {
      continue
    }
    stopGenerationTaskPolling(key)
    tasks.delete(key)
  }
}

export function updateToolCallsByGenerationTask(
  messages: ChatMessage[],
  snapshot: CanvasGenerationTaskSnapshot,
): ChatMessage[] {
  let didChange = false
  const nextMessages = messages.map((message) => {
    let nextMessage = message
    if (message.toolCalls?.length) {
      // Only rebuild this message when one of ITS tool calls actually matched the
      // snapshot. `Array.map` always allocates a new array, so without this guard every
      // message that merely has tool calls would get a fresh reference on each poll and
      // defeat the memoized MessageBubble (sibling messages would re-render needlessly).
      let toolCallsChanged = false
      const nextToolCalls = message.toolCalls.map((toolCall) => {
        if (!isMatchingGenerationToolCall(toolCall, snapshot)) {
          return toolCall
        }
        toolCallsChanged = true
        return mergeToolCallSnapshot(toolCall, snapshot)
      })
      if (toolCallsChanged) {
        didChange = true
        nextMessage = { ...nextMessage, toolCalls: nextToolCalls }
      }
    }
    if (nextMessage.blocks?.length) {
      const nextBlocks = updateBlocksByGenerationTask(nextMessage.blocks, snapshot)
      if (nextBlocks !== nextMessage.blocks) {
        didChange = true
        nextMessage = { ...nextMessage, blocks: nextBlocks }
      }
    }
    return nextMessage
  })
  return didChange ? nextMessages : messages
}

export function updateBlocksByGenerationTask(
  blocks: MessageBlock[],
  snapshot: CanvasGenerationTaskSnapshot,
): MessageBlock[] {
  let didChange = false
  const nextBlocks = blocks.map((block) => {
    const payload = block.payload || {}
    const result = payload.result && typeof payload.result === 'object' ? payload.result : payload
    const matches = idsMatch(result.task_id, snapshot.task_id)
      || idsMatch(result.id, snapshot.task_id)
      || idsMatch(result.artifact_ref, snapshot.artifact_ref)
      || idsMatch(payload.artifact_ref, snapshot.artifact_ref)
    const children = block.children?.length ? updateBlocksByGenerationTask(block.children, snapshot) : block.children
    if (!matches && children === block.children) {
      return block
    }
    didChange = true
    const merged = mergeResultSnapshot(result, snapshot)
    return {
      ...block,
      status: blockStatusFromSnapshot(snapshot, block.status),
      payload: matches
        ? {
          ...payload,
          ...merged,
          result: payload.result && typeof payload.result === 'object'
            ? { ...payload.result, ...merged }
            : payload.result,
        }
        : payload,
      children,
    }
  })
  return didChange ? nextBlocks : blocks
}

export function resetCanvasGenerationTaskRuntimeForTests(): void {
  for (const key of Array.from(tasks.keys())) {
    stopGenerationTaskPolling(key)
  }
  tasks.clear()
}

function upsertRuntimeTask(key: string, patch: Omit<RuntimeTask, 'key' | 'timeoutId' | 'polling'>): RuntimeTask {
  const existing = tasks.get(key)
  if (existing) {
    Object.assign(existing, patch)
    return existing
  }
  const created: RuntimeTask = {
    key,
    timeoutId: null,
    polling: false,
    ...patch,
  }
  tasks.set(key, created)
  return created
}

function schedulePoll(task: RuntimeTask, delayMs: number): void {
  if (task.timeoutId) {
    clearTimeout(task.timeoutId)
  }
  task.timeoutId = setTimeout(() => {
    void pollOnce(task)
  }, delayMs)
}

async function pollOnce(task: RuntimeTask): Promise<void> {
  if (!task.polling || isTerminalStatus(task.status)) {
    return
  }
  try {
    const response = task.harness
      ? task.artifactRef
        ? await agentApi.getHarnessGenerationArtifactTask(task.conversationId, task.artifactRef)
        : await agentApi.getHarnessGenerationTask(task.conversationId, task.taskId)
      : await generationApi.queryTask(Number(task.taskId))
    applyGenerationTaskSnapshot(task.key, response.data as CanvasGenerationTaskSnapshot)
    if (!task.polling || isTerminalStatus(task.status)) {
      return
    }
    schedulePoll(task, DEFAULT_POLL_INTERVAL_MS)
  } catch (error) {
    console.error('Failed to poll canvas generation task:', error)
    if (task.polling) {
      schedulePoll(task, ERROR_RETRY_INTERVAL_MS)
    }
  }
}

function isGenerationTaskItemEvent(event: AgentEvent): boolean {
  return (
    (event.type === 'item_started' || event.type === 'item_updated' || event.type === 'item_completed')
    && String(event.data?.item_type || '').trim() === 'generation_task'
  )
}

function normalizeItemPayload(event: AgentEvent): Record<string, any> {
  const payload = event.data?.payload
  return payload && typeof payload === 'object' ? payload : {}
}

function normalizeGenerationSnapshot(snapshot: Record<string, any>): CanvasGenerationTaskSnapshot {
  const status = normalizeSnapshotStatus(snapshot.status)
  const messageId = presentationMessageIdFromSnapshot(snapshot)
  const canvasItem = snapshot.canvas_item && typeof snapshot.canvas_item === 'object'
    ? { ...snapshot.canvas_item }
    : undefined
  if (canvasItem) {
    canvasItem.status = status === 'completed'
      ? 'completed'
      : status === 'failed'
        ? 'failed'
        : canvasItem.status || 'processing'
    if (snapshot.result_url) {
      canvasItem.url = snapshot.result_url
    }
    if (status === 'failed') {
      canvasItem.error_message = snapshot.error_message || snapshot.error || canvasItem.error_message
      canvasItem.failure_kind = canvasItem.failure_kind || 'task_failed'
    }
    if (canvasItem.messageId == null && messageId) {
      canvasItem.messageId = messageId
    }
    if (canvasItem.agent_message_id == null && messageId) {
      canvasItem.agent_message_id = messageId
    }
    if (canvasItem.agentMediaKey == null && canvasItem.agent_media_key == null) {
      const artifactRef = String(snapshot.artifact_ref ?? canvasItem.artifact_ref ?? '').trim()
      canvasItem.agentMediaKey = buildGeneratedCanvasPlaceholderId(artifactRef || String(snapshot.task_id ?? snapshot.id ?? canvasItem.task_id ?? ''))
    }
    const groupKey = agentGroupKeyFromSnapshot(snapshot)
    if (canvasItem.agent_group_key == null && groupKey) {
      canvasItem.agent_group_key = groupKey
    }
  }
  return {
    ...snapshot,
    task_id: snapshot.task_id ?? snapshot.id,
    artifact_ref: snapshot.artifact_ref ?? canvasItem?.artifact_ref,
    status,
    progress: typeof snapshot.progress === 'number' ? snapshot.progress : status === 'completed' ? 100 : snapshot.progress,
    result_url: snapshot.result_url ?? canvasItem?.url,
    error_message: snapshot.error_message ?? snapshot.error,
    canvas_item_deleted: snapshot.canvas_item_deleted === true || snapshot.canvasItemDeleted === true,
    canvas_revision: normalizeCanvasRevision(snapshot.canvas_revision ?? snapshot.canvasRevision),
    canvas_item: canvasItem,
  }
}

function shouldSkipCanvasProjection(snapshot: CanvasGenerationTaskSnapshot): boolean {
  return snapshot.canvas_item_deleted === true
}

function notifyCanvasRevision(
  adapter: CanvasGenerationRuntimeAdapter,
  snapshot: CanvasGenerationTaskSnapshot,
): void {
  if (typeof snapshot.canvas_revision !== 'number' || snapshot.canvas_revision < 0) {
    return
  }
  adapter.updateCanvasRevisionByAgentPatch?.(snapshot.canvas_revision, {
    canvasItemDeleted: snapshot.canvas_item_deleted === true,
  })
}

function normalizeCanvasRevision(value: unknown): number | null {
  const numeric = Number(value)
  return Number.isFinite(numeric) && numeric >= 0 ? Math.trunc(numeric) : null
}

function presentationMessageIdFromSnapshot(snapshot: Record<string, any>): string | null {
  const scope = snapshot.presentation_scope && typeof snapshot.presentation_scope === 'object'
    ? snapshot.presentation_scope as Record<string, any>
    : null
  const value = snapshot.presentation_message_key
    ?? snapshot.presentationMessageKey
    ?? scope?.message_key
    ?? scope?.messageKey
  const text = String(value ?? '').trim()
  return text || null
}

function agentGroupKeyFromSnapshot(snapshot: Record<string, any>): string | null {
  void snapshot
  return null
}

function normalizeSnapshotStatus(status: unknown): string {
  const raw = String(status || '').trim().toLowerCase()
  if (raw === 'running') return 'processing'
  if (raw === 'item_started' || raw === 'item_updated') return 'processing'
  if (raw === 'item_completed') return 'completed'
  return raw || 'processing'
}

function normalizeRuntimeStatus(status: unknown): string {
  const raw = String(status || '').trim().toLowerCase()
  if (raw === 'running' || raw === 'pending') return 'processing'
  return raw || 'processing'
}

function shouldSuppressStandardMediaCard(snapshot: CanvasGenerationTaskSnapshot): boolean {
  if ((snapshot as Record<string, any>).suppress_standard_media_card === true) {
    return true
  }
  const params = (snapshot as Record<string, any>).params
  return !!(params && typeof params === 'object' && params.suppress_standard_media_card === true)
}

function isTerminalStatus(status: unknown): boolean {
  const raw = String(status || '').trim().toLowerCase()
  return raw === 'completed' || raw === 'failed' || raw === 'cancelled'
}

function normalizeCanvasItem(snapshot: CanvasGenerationTaskSnapshot): Record<string, any> | null {
  const item = snapshot.canvas_item
  return item && typeof item === 'object' ? item : null
}

function buildCanvasPlaceholderFromSnapshot(
  snapshot: CanvasGenerationTaskSnapshot,
  conversationId: string | number,
): Record<string, any> | null {
  const taskId = String(snapshot.task_id ?? snapshot.id ?? '').trim()
  const artifactRef = String(snapshot.artifact_ref ?? '').trim()
  if (!taskId && !artifactRef) {
    return null
  }
  const stableId = buildGeneratedCanvasPlaceholderId(artifactRef || taskId)
  const status = normalizeSnapshotStatus(snapshot.status)
  return {
    id: stableId,
    type: inferKind(snapshot) === 'video' ? 'video_generator' : 'image_generator',
    url: snapshot.result_url || '',
    task_id: taskId || snapshot.task_id,
    artifact_ref: artifactRef || null,
    status: status === 'completed' ? 'completed' : status === 'failed' ? 'failed' : 'generating',
    progress: typeof snapshot.progress === 'number' ? snapshot.progress : status === 'completed' ? 100 : 0,
    error_message: snapshot.error_message ?? snapshot.error,
    failure_kind: status === 'failed' ? 'task_failed' : undefined,
    conversationId,
    messageId: presentationMessageIdFromSnapshot(snapshot),
    agent_message_id: presentationMessageIdFromSnapshot(snapshot),
    agent_group_key: agentGroupKeyFromSnapshot(snapshot),
    agentMediaKey: stableId,
    agent_media_key: stableId,
    suppressCompletionToast: true,
  }
}

function publishCanvasPlaceholderUpdate(
  adapter: CanvasGenerationRuntimeAdapter,
  conversationId: string,
  snapshot: CanvasGenerationTaskSnapshot,
  canvasItem: Record<string, any>,
): void {
  if (isTerminalStatus(snapshot.status)) {
    return
  }
  const state = adapter.getState()
  if (state.conversationId == null || String(state.conversationId) !== String(conversationId)) {
    return
  }
  state.onCanvasUpdate?.('add', {
    ...canvasItem,
    status: canvasItem.status || 'generating',
    conversationId: canvasItem.conversationId ?? conversationId,
    canvas_revision: snapshot.canvas_revision,
    canvas_item_deleted: snapshot.canvas_item_deleted,
  })
}

function publishCanvasTerminalUpdate(
  adapter: CanvasGenerationRuntimeAdapter,
  conversationId: string,
  snapshot: CanvasGenerationTaskSnapshot,
  canvasItem: Record<string, any>,
): void {
  const state = adapter.getState()
  if (state.conversationId == null || String(state.conversationId) !== String(conversationId)) {
    return
  }
  if (snapshot.status === 'completed' && snapshot.result_url) {
    state.onCanvasUpdate?.('add_generated_media', {
      ...canvasItem,
      url: snapshot.result_url,
      status: 'completed',
      type: inferKind(snapshot) === 'video' ? 'video' : 'image',
      artifact_ref: snapshot.artifact_ref,
      conversationId: canvasItem.conversationId ?? conversationId,
      canvas_revision: snapshot.canvas_revision,
      canvas_item_deleted: snapshot.canvas_item_deleted,
    })
  } else if (snapshot.status === 'failed') {
    state.onCanvasUpdate?.('update', {
      ...canvasItem,
      status: 'failed',
      error_message: snapshot.error_message,
      failure_kind: canvasItem.failure_kind || 'task_failed',
      conversationId: canvasItem.conversationId ?? conversationId,
      canvas_revision: snapshot.canvas_revision,
      canvas_item_deleted: snapshot.canvas_item_deleted,
    })
  }
}

function buildGeneratedCanvasPlaceholderId(seed: string): string {
  const stable = String(seed || 'pending')
    .trim()
    .replace(/[^a-zA-Z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    || 'pending'
  return `agent-generated-${stable}`
}

function collectPendingGenerationSnapshots(
  session: { messages?: ChatMessage[]; streamingBlocks?: MessageBlock[]; currentToolCalls?: ToolCallInfo[] },
): CanvasGenerationTaskSnapshot[] {
  const snapshots: CanvasGenerationTaskSnapshot[] = []
  for (const toolCall of session.currentToolCalls || []) {
    pushToolCallSnapshot(snapshots, toolCall)
  }
  for (const block of session.streamingBlocks || []) {
    pushBlockSnapshot(snapshots, block)
  }
  for (const message of session.messages || []) {
    for (const toolCall of message.toolCalls || []) {
      pushToolCallSnapshot(snapshots, toolCall)
    }
    for (const block of message.blocks || []) {
      pushBlockSnapshot(snapshots, block)
    }
  }
  return dedupePendingSnapshots(snapshots)
}

function pushToolCallSnapshot(target: CanvasGenerationTaskSnapshot[], toolCall: ToolCallInfo): void {
  if (!isGenerationToolName(toolCall.name) || !toolCall.result) {
    return
  }
  if (isTerminalStatus(toolCall.result.status) || isTerminalStatus(toolCall.status)) {
    return
  }
  const update = buildGenerationProjectionUpdateFromTaskSnapshot(toolCall.result)
  if (update) {
    target.push(toolCall.result as CanvasGenerationTaskSnapshot)
  }
}

function pushBlockSnapshot(target: CanvasGenerationTaskSnapshot[], block: MessageBlock): void {
  const payload = block.payload || {}
  const result = payload.result && typeof payload.result === 'object' ? payload.result : payload
  const update = buildGenerationProjectionUpdateFromTaskSnapshot(result)
  if (update && !isTerminalStatus(result.status || block.status)) {
    target.push(result as CanvasGenerationTaskSnapshot)
  }
  for (const child of block.children || []) {
    pushBlockSnapshot(target, child)
  }
}

function dedupePendingSnapshots(snapshots: CanvasGenerationTaskSnapshot[]): CanvasGenerationTaskSnapshot[] {
  const seen = new Set<string>()
  return snapshots.filter((snapshot) => {
    const key = `${snapshot.artifact_ref || ''}:${snapshot.task_id || snapshot.id || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function isGenerationToolName(name: string): boolean {
  return name === 'generate_image' || name === 'generate_video'
}

function isMatchingGenerationToolCall(toolCall: ToolCallInfo, snapshot: CanvasGenerationTaskSnapshot): boolean {
  if (!isGenerationToolName(toolCall.name)) {
    return false
  }
  const result = toolCall.result || {}
  return idsMatch(result.task_id, snapshot.task_id)
    || idsMatch(result.id, snapshot.task_id)
    || idsMatch(result.artifact_ref, snapshot.artifact_ref)
    || idsMatch(toolCall.args?.artifact_ref, snapshot.artifact_ref)
}

function mergeToolCallSnapshot(toolCall: ToolCallInfo, snapshot: CanvasGenerationTaskSnapshot): ToolCallInfo {
  return {
    ...toolCall,
    status: snapshot.status === 'completed' ? 'completed' : snapshot.status === 'failed' ? 'failed' : 'running',
    result: mergeResultSnapshot(toolCall.result || {}, snapshot),
    error: snapshot.status === 'failed' ? snapshot.error_message || toolCall.error : toolCall.error,
  }
}

function mergeResultSnapshot(result: Record<string, any>, snapshot: CanvasGenerationTaskSnapshot): Record<string, any> {
  const canvasItem = snapshot.canvas_item
    ? {
      ...(result.canvas_item || {}),
      ...snapshot.canvas_item,
    }
    : result.canvas_item
  return {
    ...result,
    task_snapshot_loaded: true,
    task_id: snapshot.task_id ?? result.task_id,
    artifact_ref: snapshot.artifact_ref ?? result.artifact_ref,
    status: snapshot.status ?? result.status,
    progress: snapshot.progress ?? result.progress,
    result_url: snapshot.result_url ?? result.result_url,
    result_urls: snapshot.result_urls ?? result.result_urls,
    error_message: snapshot.error_message ?? result.error_message,
    canvas_revision: snapshot.canvas_revision ?? result.canvas_revision,
    canvas_item_deleted: snapshot.canvas_item_deleted ?? result.canvas_item_deleted,
    provider_code: snapshot.provider_code ?? result.provider_code,
    model_name: snapshot.model_name ?? result.model_name,
    model_label: snapshot.model_label ?? result.model_label,
    resolution: snapshot.resolution ?? result.resolution,
    duration: snapshot.duration ?? result.duration,
    quality: snapshot.quality ?? result.quality,
    params: snapshot.params ?? result.params,
    canvas_item: canvasItem,
    artifact: snapshot.artifact ?? result.artifact,
  }
}

function blockStatusFromSnapshot(snapshot: CanvasGenerationTaskSnapshot, fallback: string): string {
  if (snapshot.status === 'completed') return 'completed'
  if (snapshot.status === 'failed') return 'failed'
  return fallback === 'failed' ? 'failed' : 'running'
}

function idsMatch(left: unknown, right: unknown): boolean {
  const a = String(left ?? '').trim()
  const b = String(right ?? '').trim()
  return Boolean(a && b && a === b)
}

function inferKind(snapshot: Record<string, any>): string | null {
  const kind = String(snapshot.kind || snapshot.media_type || '').trim().toLowerCase()
  if (kind === 'image' || kind === 'video') return kind
  const canvasType = String(snapshot.canvas_item?.type || '').trim().toLowerCase()
  if (canvasType.includes('video')) return 'video'
  if (canvasType.includes('image')) return 'image'
  return null
}
