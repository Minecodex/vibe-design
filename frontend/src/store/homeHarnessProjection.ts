import { wireRecord, wireNullableString } from './harnessWireFields'
import type {
  AgentEvent,
  HarnessRuntimeStateRead,
  OutlineRuntimeRead,
  PendingInteraction,
  PlanRead,
  PlanningDraftRead,
  UserPlanRead,
  UserProgressRead,
  WorkspaceFileRead,
} from '@/api/endpoints/agent'
import i18n from '@/i18n'
import { resolveHarnessPendingInteraction } from './harnessStreamLifecycle'
import { normalizePendingInteraction } from '@/api/agentWireNormalization'
import type { ChatMessage, MessageBlock, ToolCallInfo } from './homeHarnessStore'
import { upsertVersionedFile } from './homeHarnessFileVersions'
import {
  dedupeStreamingBlocks as sharedDedupeStreamingBlocks,
  extractMessageText as sharedExtractMessageText,
  hasEquivalentBlock as sharedHasEquivalentBlock,
  normalizeBlocks as sharedNormalizeBlocks,
  updateMessagesBlocks as sharedUpdateMessagesBlocks,
  upsertSubagentDesignJuryCard as sharedUpsertSubagentDesignJuryCard,
} from './homeHarnessProjectionBlocks'
import {
  applyHomeHarnessCritiqueEvent,
  type HomeHarnessCritiqueProjectionEvent,
  type HomeHarnessCritiqueState,
} from './homeHarnessCritiqueProjection'
import { resolveHarnessTerminalRunStatus } from './harnessTerminalEvents'
import {
  getTurnFailure,
  getTurnStatus,
  isTurnCompletedEvent,
  isTurnStartedEvent,
  type HarnessTurnStatus,
} from './harnessTurnProtocol'
import { buildGenerationProjectionUpdateFromEvent } from './generationEventProjection'
import {
  isTerminalGenerationProjectionStatus,
  normalizeGenerationProjectionStatus,
  type GenerationProjectionUpdate,
} from './generationProjection'

export type HomeHarnessProjectionEvent = AgentEvent | HomeHarnessCritiqueProjectionEvent

export interface HomeHarnessProjectionState {
  messages: ChatMessage[]
  activePlan: PlanRead | null
  planningDraft?: PlanningDraftRead | null
  activeUserPlan: UserPlanRead | null
  outlineRuntime: OutlineRuntimeRead | null
  userProgress: UserProgressRead | null
  userInteraction: PendingInteraction | null
  pendingInteraction?: PendingInteraction | null
  isStreaming: boolean
  currentStreamText: string
  currentToolCalls: ToolCallInfo[]
  streamingBlocks: MessageBlock[]
  workspaceFiles: WorkspaceFileRead[]
  runtimeState: HarnessRuntimeStateRead | null
  critique?: HomeHarnessCritiqueState | null
  lastSequence: number
  runStatus: 'idle' | 'running' | 'waiting_input' | 'completed' | 'failed' | 'blocked' | 'cancelled'
}

function resolveProjectionTerminalStatus(
  runStatus: HomeHarnessProjectionState['runStatus'],
): HomeHarnessProjectionState['runStatus'] {
  return resolveHarnessTerminalRunStatus(runStatus)
}

function terminalPhaseForStatus(
  status: HomeHarnessProjectionState['runStatus'],
): string | null {
  const terminalStatus = resolveProjectionTerminalStatus(status)
  if (terminalStatus === 'completed') {
    return 'completed'
  }
  if (terminalStatus === 'failed') {
    return 'failed'
  }
  if (terminalStatus === 'blocked') {
    return 'blocked'
  }
  if (terminalStatus === 'cancelled') {
    return 'cancelled'
  }
  return null
}

const DEFAULT_PROJECTION_TIMESTAMP = '1970-01-01T00:00:00.000Z'
export function createHomeHarnessProjectionState(): HomeHarnessProjectionState {
  return {
    messages: [],
    activePlan: null,
    planningDraft: null,
    activeUserPlan: null,
    outlineRuntime: null,
    userProgress: null,
    userInteraction: null,
    pendingInteraction: null,
    isStreaming: false,
    currentStreamText: '',
    currentToolCalls: [],
    streamingBlocks: [],
    workspaceFiles: [],
    runtimeState: null,
    critique: null,
    lastSequence: 0,
    runStatus: 'idle',
  }
}

function eventTimestamp(event: HomeHarnessProjectionEvent): string {
  const createdAt = event.data?.created_at ?? event.data?.createdAt
  if (typeof createdAt === 'string' && createdAt.trim()) {
    return createdAt
  }
  if (typeof event.sequence === 'number') {
    return new Date(event.sequence * 1000).toISOString()
  }
  return DEFAULT_PROJECTION_TIMESTAMP
}

function shouldProjectEvent(event: HomeHarnessProjectionEvent): boolean {
  return event.lane !== 'internal'
}

function mergeRuntimeState(
  runtimeState: HarnessRuntimeStateRead | null,
  patch: Record<string, unknown>,
): HarnessRuntimeStateRead | null {
  const current = runtimeState || ({
    conversation_id: String(patch.conversation_id || patch.conversationId || ''),
    phase: String(patch.phase || 'planning'),
    run_status: String(patch.run_status || patch.runStatus || 'idle'),
    item_progress: [],
    artifacts: [],
  } as HarnessRuntimeStateRead)
  return {
    ...current,
    ...patch,
    workspace_runtime_session: wireRecord(
      patch.workspace_runtime_session
      ?? patch.workspaceRuntimeSession
      ?? current.workspace_runtime_session
      ?? null
    ) ?? null,
    prepared_workspace: wireRecord(
      patch.prepared_workspace
      ?? patch.preparedWorkspace
      ?? current.prepared_workspace
      ?? null
    ) ?? null,
    runtime_contract: wireRecord(patch.runtime_contract ?? patch.runtimeContract ?? current.runtime_contract) ?? null,
  }
}

function normalizeRunId(value: unknown): string {
  const normalized = String(value ?? '').trim()
  return normalized && normalized.toLowerCase() !== 'none' && normalized.toLowerCase() !== 'null'
    ? normalized
    : ''
}

function getEventRunId(event: HomeHarnessProjectionEvent): string {
  return normalizeRunId(event.run_id ?? event.data?.run_id ?? event.data?.runId)
}

function getProjectionRunId(state: HomeHarnessProjectionState): string {
  return normalizeRunId(state.runtimeState?.run_id)
}

function isStaleRunTerminalEvent(
  state: HomeHarnessProjectionState,
  event: HomeHarnessProjectionEvent,
): boolean {
  if (event.type !== 'turn_completed') {
    return false
  }
  const currentRunId = getProjectionRunId(state)
  const eventRunId = getEventRunId(event)
  return Boolean(currentRunId && eventRunId && currentRunId !== eventRunId)
}

function normalizeBlocks(rawBlocks: unknown): MessageBlock[] {
  return sharedNormalizeBlocks(rawBlocks)
}

function extractMessageText(blocks: MessageBlock[]): string | null {
  return sharedExtractMessageText(blocks)
}

function dedupeStreamingBlocks(blocks: MessageBlock[]): MessageBlock[] {
  return sharedDedupeStreamingBlocks(blocks)
}

function hasEquivalentBlock(messages: ChatMessage[], incomingBlock: MessageBlock): boolean {
  return sharedHasEquivalentBlock(messages, incomingBlock)
}

function updateMessagesBlocks(
  messages: ChatMessage[],
  updater: (blocks: MessageBlock[]) => MessageBlock[],
): ChatMessage[] {
  return sharedUpdateMessagesBlocks(messages, updater)
}

function buildErrorMessage(message: string, createdAt: string, messageId?: string): ChatMessage {
  const errorText = `Error: ${message || 'Unknown error'}`
  return {
    id: messageId || `error-${createdAt}`,
    role: 'assistant',
    content: errorText,
    blocks: normalizeBlocks([
      {
        id: `error-block-${createdAt}`,
        kind: 'text',
        order: 0,
        status: 'completed',
        visible: true,
        ui_kind: 'assistant_text',
        payload: {
          text: errorText,
        },
      },
    ]),
    createdAt,
  }
}

function appendErrorMessageOnce(
  messages: ChatMessage[],
  message: string,
  createdAt: string,
  dedupeKey?: string,
): ChatMessage[] {
  const normalized = String(message || '').trim()
  if (!normalized) {
    return messages
  }
  const resolvedKey = String(dedupeKey || `error:${normalized}`).trim()
  const alreadyVisible = messages.some((entry) => String(entry.id || '') === resolvedKey)
  return alreadyVisible ? messages : [...messages, buildErrorMessage(normalized, createdAt, resolvedKey)]
}

function withOutlineRuntimeFailure(
  outlineRuntime: OutlineRuntimeRead | null | undefined,
  message: string,
) : OutlineRuntimeRead | null {
  if (!outlineRuntime || !outlineRuntime.current_outline) {
    return outlineRuntime ?? null
  }
  return {
    ...outlineRuntime,
    last_revision: {
      ...(outlineRuntime.last_revision || {}),
      error_message: message,
    },
  }
}

function markPlanBlockTerminal(
  block: MessageBlock,
  status: 'failed' | 'blocked' | 'cancelled',
): MessageBlock {
  const terminalStepStatus = status
  const steps = Array.isArray(block.payload.steps)
    ? block.payload.steps.map((step: Record<string, unknown>) => {
      const stepStatus = String(step.status || '').toLowerCase()
      const isActive = stepStatus === 'in_progress' || stepStatus === 'running'
      if (isActive) {
        return { ...step, status: terminalStepStatus }
      }
      return step
    })
    : block.payload.steps

  return {
    ...block,
    status,
    payload: {
      ...block.payload,
      status,
      steps,
    },
    children: (block.children || []).map((child) => markPlanBlockTerminal(child, status)),
  }
}

function markPlanArtifactsTerminal(
  state: HomeHarnessProjectionState,
  status: 'failed' | 'blocked' | 'cancelled',
): HomeHarnessProjectionState {
  const updateBlocks = (blocks: MessageBlock[]): MessageBlock[] => {
    let didUpdate = false
    const nextBlocks = blocks.map((block) => {
      const nextBlock = block.uiKind === 'plan_artifact'
        ? markPlanBlockTerminal(block, status)
        : {
          ...block,
          children: updateBlocks(block.children || []),
        }
      if (nextBlock !== block) {
        didUpdate = true
      }
      return nextBlock
    })
    return didUpdate ? nextBlocks : blocks
  }

  return {
    ...state,
    streamingBlocks: updateBlocks(state.streamingBlocks),
    messages: updateMessagesBlocks(state.messages, updateBlocks),
  }
}

function markPlanArtifactsTerminalForStatus(
  state: HomeHarnessProjectionState,
  status: HomeHarnessProjectionState['runStatus'],
): HomeHarnessProjectionState {
  if (status === 'failed' || status === 'blocked' || status === 'cancelled') {
    return markPlanArtifactsTerminal(state, status)
  }
  return state
}

const TERMINAL_SUBAGENT_STATUSES = new Set([
  'completed',
  'degraded',
  'failed',
  'refused',
  'cancelled',
  'canceled',
])

function cancelRunningSubagentBlocks(blocks: MessageBlock[] | undefined): MessageBlock[] | undefined {
  if (!Array.isArray(blocks)) {
    return blocks
  }
  return blocks.map((block) => {
    const children = cancelRunningSubagentBlocks(block.children)
    if (block.uiKind !== 'subagent_card') {
      return children === block.children ? block : { ...block, children }
    }
    const status = String(block.payload?.status || block.status || '').trim().toLowerCase()
    if (TERMINAL_SUBAGENT_STATUSES.has(status)) {
      return children === block.children ? block : { ...block, children }
    }
    return {
      ...block,
      status: 'cancelled',
      children,
      payload: {
        ...block.payload,
        status: 'cancelled',
        result: {
          ...(block.payload?.result || {}),
          status: 'cancelled',
        },
      },
    }
  })
}

function cancelRunningSubagentCards(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((message) => {
    const nextBlocks = cancelRunningSubagentBlocks(message.blocks)
    return nextBlocks === message.blocks ? message : { ...message, blocks: nextBlocks }
  })
}

function withStreamingSnapshot(
  state: HomeHarnessProjectionState,
  updates: Partial<HomeHarnessProjectionState>,
): HomeHarnessProjectionState {
  const nextStreamingBlocks = updates.streamingBlocks ?? state.streamingBlocks
  return {
    ...state,
    ...updates,
    streamingBlocks: nextStreamingBlocks,
    currentStreamText: extractMessageText(nextStreamingBlocks) || '',
  }
}

export function finalizeHomeHarnessProjection(
  state: HomeHarnessProjectionState,
  status: HomeHarnessProjectionState['runStatus'],
  createdAt = DEFAULT_PROJECTION_TIMESTAMP,
): HomeHarnessProjectionState {
  const dedupedStreamingBlocks = dedupeStreamingBlocks(state.streamingBlocks).filter(
    (block) => !hasEquivalentBlock(state.messages, block),
  )
  const assistantMessage: ChatMessage = {
    id: `assistant-${createdAt}`,
    role: 'assistant',
    content: extractMessageText(dedupedStreamingBlocks),
    blocks: dedupedStreamingBlocks,
    createdAt,
  }
  const nextMessages: ChatMessage[] = dedupedStreamingBlocks.length > 0
    ? [...state.messages, assistantMessage]
    : state.messages

  return {
    ...state,
    messages: nextMessages,
    streamingBlocks: [],
    currentStreamText: '',
    currentToolCalls: [],
    isStreaming: false,
    runtimeState: state.runtimeState
      ? {
        ...state.runtimeState,
        run_status: resolveProjectionTerminalStatus(status),
        runtime_status: resolveProjectionTerminalStatus(status),
        run_state: resolveProjectionTerminalStatus(status),
        phase: terminalPhaseForStatus(status) ?? state.runtimeState.phase,
        activity: terminalPhaseForStatus(status) ?? state.runtimeState.activity,
      }
      : null,
    runStatus: status,
  }
}

function shouldClearUserInteractionForEvent(event: HomeHarnessProjectionEvent): boolean {
  switch (event.type) {
    case 'design_system_selected':
    case 'run_preparing':
    case 'file_created':
    case 'file_updated':
    case 'file_published':
    case 'asset_added':
    case 'asset_registered':
    case 'asset_removed':
    case 'file_version_created':
    case 'file_current_version_changed':
    case 'workspace_file_upserted':
      return true
    default:
      return false
  }
}

function applyGenerationEventToHomeState(
  state: HomeHarnessProjectionState,
  event: HomeHarnessProjectionEvent,
): HomeHarnessProjectionState {
  const update = buildGenerationProjectionUpdateFromEvent(event)
  if (!update) {
    return state
  }

  const messages = sharedUpdateMessagesBlocks(
    state.messages,
    (blocks) => updateGenerationBlocks(blocks, update),
  )
  const streamingBlocks = updateGenerationBlocks(state.streamingBlocks, update)
  if (messages === state.messages && streamingBlocks === state.streamingBlocks) {
    return state
  }

  return {
    ...state,
    messages,
    streamingBlocks,
  }
}

function updateGenerationBlocks(
  blocks: MessageBlock[],
  update: GenerationProjectionUpdate,
): MessageBlock[] {
  let didUpdate = false
  const nextBlocks = blocks.map((block) => {
    const nextChildren = block.children?.length
      ? updateGenerationBlocks(block.children, update)
      : block.children
    const childrenChanged = nextChildren !== block.children
    const nextBlock = updateGenerationBlock(block, update)
    if (childrenChanged || nextBlock !== block) {
      didUpdate = true
      return {
        ...nextBlock,
        children: nextChildren,
      }
    }
    return block
  })

  return didUpdate ? nextBlocks : blocks
}

function updateGenerationBlock(
  block: MessageBlock,
  update: GenerationProjectionUpdate,
): MessageBlock {
  const taskId = String(update.taskId || '').trim()
  if (!taskId || !isGenerationTaskBlock(block, taskId)) {
    return block
  }

  const incomingStatus = normalizeGenerationProjectionStatus(update.status)
  const existingStatus = normalizeGenerationProjectionStatus(block.payload.status ?? block.status)
  const incomingSequence = numberOrNull(update.sourceSequence)
  const existingSequence = numberOrNull(
    block.payload.generationSourceSequence
    ?? block.payload.generation_source_sequence
    ?? block.payload.sourceSequence
    ?? block.payload.source_sequence,
  )
  if (incomingSequence != null && existingSequence != null && incomingSequence < existingSequence) {
    return block
  }
  if (
    existingStatus
    && incomingStatus
    && isTerminalGenerationProjectionStatus(existingStatus)
    && !isTerminalGenerationProjectionStatus(incomingStatus)
    && (incomingSequence == null || existingSequence == null || incomingSequence <= existingSequence)
  ) {
    return block
  }

  const payload = { ...block.payload }
  const result = isRecord(payload.result) ? { ...payload.result } : null
  const nextStatus = incomingStatus ?? existingStatus ?? String(block.status || payload.status || 'processing')
  payload.status = nextStatus
  if (result) {
    result.status = nextStatus
  }
  if (typeof update.progress === 'number') {
    payload.progress = update.progress
    if (result) {
      result.progress = update.progress
    }
  }
  if (update.resultUrl) {
    payload.resultUrl = update.resultUrl
    payload.result_url = update.resultUrl
    if (result) {
      result.resultUrl = update.resultUrl
      result.result_url = update.resultUrl
    }
  }
  const artifactRef = update.artifactRef ?? update.artifactId
  if (update.artifactId != null) {
    payload.artifactId = String(update.artifactId)
    if (result) {
      result.artifactId = String(update.artifactId)
    }
  }
  if (artifactRef != null) {
    payload.artifactRef = String(artifactRef)
    if (result) {
      result.artifactRef = String(artifactRef)
    }
  }
  if (update.errorMessage) {
    payload.errorMessage = update.errorMessage
    if (result) {
      result.errorMessage = update.errorMessage
    }
  }
  if (incomingSequence != null) {
    payload.generationSourceSequence = Math.max(existingSequence ?? 0, incomingSequence)
  }
  if (result) {
    payload.result = result
  }

  return {
    ...block,
    status: nextStatus,
    payload,
  }
}

function isGenerationTaskBlock(block: MessageBlock, taskId: string): boolean {
  const payload = block.payload || {}
  const result = isRecord(payload.result) ? payload.result : {}
  const blockTaskId = block.taskId
    ?? payload.taskId
    ?? payload.task_id
    ?? result.taskId
    ?? result.task_id
  return String(blockTaskId ?? '').trim() === taskId
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function numberOrNull(value: unknown): number | null {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function normalizeCritiqueProjectionEventData(
  eventType: string,
  data: Record<string, unknown>,
): Record<string, unknown> {
  if (eventType !== 'critique.round_completed') {
    return data
  }
  return {
    ...data,
    status: 'completed',
    display_status: data.display_status ?? data.displayStatus ?? 'round_completed',
    displayStatus: data.displayStatus ?? data.display_status ?? 'round_completed',
  }
}

function inferWorkspaceFileType(data: Record<string, unknown>): string {
  const explicit = String(data.type ?? data.file_type ?? data.fileType ?? '').trim()
  if (explicit) {
    return explicit
  }
  const mimeType = String(data.mime_type ?? data.mimeType ?? '').trim().toLowerCase()
  if (mimeType.startsWith('image/')) {
    return 'image'
  }
  if (mimeType.startsWith('video/')) {
    return 'video'
  }
  const name = String(data.name ?? data.original_name ?? data.filename ?? data.path ?? data.file_path ?? '').toLowerCase()
  const extension = name.split('.').pop() || ''
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(extension)) {
    return 'image'
  }
  if (['mp4', 'webm', 'mov', 'm4v', 'avi'].includes(extension)) {
    return 'video'
  }
  if (['html', 'htm', 'zip'].includes(extension)) {
    return 'web'
  }
  return 'other'
}

function normalizeWorkspaceFileSource(data: Record<string, unknown>): WorkspaceFileRead['source'] {
  const explicit = String(data.source ?? '').trim()
  if (explicit === 'versioned_file' || explicit === 'input_asset' || explicit === 'reference_asset' || explicit === 'plan_asset') {
    return explicit
  }
  const kind = String(data.kind ?? '').trim().toLowerCase()
  if (kind === 'input') {
    return 'input_asset'
  }
  if (kind === 'reference') {
    return 'reference_asset'
  }
  return explicit || 'versioned_file'
}

function workspaceFileFromEventData(
  data: Record<string, unknown>,
  timestamp: string,
): WorkspaceFileRead | null {
  const path = String(data.path ?? data.file_path ?? data.filePath ?? data.url ?? '').trim()
  const fileId = String(data.file_id ?? data.fileId ?? data.asset_id ?? data.assetId ?? path).trim()
  const name = String(
    data.name
    ?? data.original_name
    ?? data.originalName
    ?? data.filename
    ?? data.file_name
    ?? data.fileName
    ?? path.split('/').pop()
    ?? fileId
    ?? '',
  ).trim()
  if (!path && !fileId && !name) {
    return null
  }
  return {
    file_id: fileId || path || name,
    name: name || path.split('/').pop() || fileId || 'file',
    path,
    type: inferWorkspaceFileType(data),
    size: Number(data.size ?? 0),
    created_at: String(data.created_at ?? data.createdAt ?? timestamp),
    updated_at: wireNullableString(data.updated_at ?? data.updatedAt ?? null),
    current_version_id: String(data.current_version_id ?? data.currentVersionId ?? ''),
    current_version_path: wireNullableString(data.current_version_path ?? data.currentVersionPath ?? null),
    artifact_kind: wireNullableString(data.artifact_kind ?? data.artifactKind ?? null),
    artifact_metadata: wireRecord(data.artifact_metadata ?? data.artifactMetadata) ?? null,
    versions: Array.isArray(data.versions) ? data.versions : [],
    source: normalizeWorkspaceFileSource(data),
  }
}

function upsertWorkspaceFile(
  files: WorkspaceFileRead[],
  file: WorkspaceFileRead,
): WorkspaceFileRead[] {
  const normalizedPath = String(file.path || '').trim()
  const normalizedFileId = String(file.file_id || normalizedPath || file.name || '').trim()
  const existing = files.findIndex((entry) => (
    (normalizedPath && String(entry.path || '') === normalizedPath)
    || (normalizedFileId && String(entry.file_id || '') === normalizedFileId)
  ))
  const workspaceFiles = [...files]
  if (existing >= 0) {
    workspaceFiles[existing] = file
  } else {
    workspaceFiles.push(file)
  }
  return workspaceFiles
}

export function applyHomeHarnessEvent(
  state: HomeHarnessProjectionState,
  event: HomeHarnessProjectionEvent,
): HomeHarnessProjectionState {
  if (!shouldProjectEvent(event)) {
    return state
  }
  const nextSequence = typeof event.sequence === 'number'
    ? Math.max(state.lastSequence, event.sequence)
    : state.lastSequence
  const withSequence = (nextState: HomeHarnessProjectionState): HomeHarnessProjectionState => ({
    ...nextState,
    pendingInteraction: nextState.userInteraction ?? nextState.pendingInteraction ?? null,
    lastSequence: nextSequence,
  })
  const withUpdates = (updates: Partial<HomeHarnessProjectionState>): HomeHarnessProjectionState => (
    withSequence({
      ...state,
      ...updates,
    })
  )
  const timestamp = eventTimestamp(event)
  if (isStaleRunTerminalEvent(state, event)) {
    return withSequence(state)
  }
  if (state.userInteraction && shouldClearUserInteractionForEvent(event)) {
    state = {
      ...state,
      userInteraction: null,
    }
  }

  switch (event.type) {
    case 'critique.started':
    case 'critique.round_completed':
    case 'critique.protocol_rejected':
    case 'critique.shipped':
    case 'critique.below_threshold':
    case 'critique.degraded':
    case 'critique.failed':
      {
        const critiqueData = normalizeCritiqueProjectionEventData(event.type, event.data || {})
        const critique = applyHomeHarnessCritiqueEvent(state.critique ?? null, {
          ...event,
          data: critiqueData,
        })
        const subagentTaskId = String(critiqueData.subagent_task_id ?? critiqueData.subagentTaskId ?? '').trim()
        if (!subagentTaskId) {
          return withUpdates({ critique })
        }
        const upsertDesignJuryCard = (blocks: MessageBlock[]) => (
          sharedUpsertSubagentDesignJuryCard(blocks, subagentTaskId, critiqueData)
        )
        return withStreamingSnapshot(state, withUpdates({
          critique,
          streamingBlocks: upsertDesignJuryCard(state.streamingBlocks),
          messages: sharedUpdateMessagesBlocks(state.messages, upsertDesignJuryCard),
        }))
      }

    case 'turn_started':
      if (!isTurnStartedEvent(event)) {
        return withSequence(state)
      }
      return withUpdates({
        runtimeState: mergeRuntimeState(state.runtimeState, {
          ...event.data,
          run_id: event.run_id ?? event.data.run_id ?? state.runtimeState?.run_id ?? null,
          turn_id: event.data.turn_id ?? event.data.run_id ?? state.runtimeState?.run_id ?? null,
          run_status: 'running',
          runtime_status: 'running',
          run_state: 'running',
        }),
        isStreaming: true,
        runStatus: 'running',
        // A new turn starts a fresh critique lifecycle. Drop any leftover
        // panel state from the previous turn so a terminal (shipped/failed)
        // or empty "armed" card does not bleed into the next turn's UI; the
        // fresh critique.started for this turn arrives during rendering_context.
        critique: null,
      })

    case 'run_started':
      return withUpdates({
        runtimeState: mergeRuntimeState(state.runtimeState, {
          ...event.data,
          run_id: event.run_id ?? event.data.run_id ?? event.data.runId ?? state.runtimeState?.run_id ?? null,
        }),
      })

    case 'run_preparing':
      // Transient connection handshake — server emits this as the first
      // SSE frame on every subscription, including reconnects against
      // already-completed conversations. It must NOT flip runStatus or
      // splice runtime_status='running' into runtimeState, or a stale GET
      // /stream subscription will resurrect a finished run on the client
      // and trigger an infinite reconnect loop. runStatus and isStreaming
      // are owned by the durable turn-lifecycle events (turn_started /
      // turn_completed).
      return withUpdates({
        runtimeState: mergeRuntimeState(state.runtimeState, {
          run_id: event.run_id ?? event.data.run_id ?? event.data.runId ?? state.runtimeState?.run_id ?? null,
        }),
      })

    case 'file_created':
    case 'file_updated':
    case 'file_published':
    case 'asset_added':
    case 'asset_registered':
    case 'workspace_file_upserted':
      {
        const file = workspaceFileFromEventData(event.data || {}, timestamp)
        if (!file) {
          return withSequence(state)
        }
        const workspaceFiles = upsertWorkspaceFile(state.workspaceFiles, file)
        return withStreamingSnapshot(state, withUpdates({ workspaceFiles }))
      }

    case 'asset_removed':
      {
        const path = String(event.data.path || event.data.file_path || '')
        const fileId = String(event.data.file_id || '')
        if (!path && !fileId) {
          return withSequence(state)
        }
        return withStreamingSnapshot(state, withUpdates({
          workspaceFiles: state.workspaceFiles.filter((entry) => (
            (!path || entry.path !== path)
            && (!fileId || String(entry.file_id || '') !== fileId)
          )),
        }))
      }

    case 'file_version_created':
    case 'file_current_version_changed':
      return withStreamingSnapshot(
        state,
        withUpdates({ workspaceFiles: upsertVersionedFile(state.workspaceFiles, { ...event.data, created_at: timestamp }) }),
      )

    case 'protocol_error':
      {
        const summary = i18n.t('homeHarness.protocol.missingTurnCompleted')
        const finalized = finalizeHomeHarnessProjection(
          markPlanArtifactsTerminalForStatus(state, 'failed'),
          'failed',
          timestamp,
        )
        return withSequence({
          ...finalized,
          messages: appendErrorMessageOnce(
            finalized.messages,
            summary,
            timestamp,
            `protocol:${String(event.data.reason || 'unknown')}:${String(event.data.runtime_status || '')}`,
          ),
        })
      }

    case 'turn_completed':
      {
        if (!isTurnCompletedEvent(event)) {
          return withSequence(state)
        }
        const status = getTurnStatus(event) ?? 'completed'
        const turnFailure = getTurnFailure(event)
        const runtimeSnapshot = (
          event.data.runtime_snapshot && typeof event.data.runtime_snapshot === 'object'
            ? event.data.runtime_snapshot as Record<string, unknown>
            : {}
        )
        const stateForTerminal = status === 'cancelled'
          ? {
            ...state,
            streamingBlocks: cancelRunningSubagentBlocks(state.streamingBlocks) || [],
            messages: cancelRunningSubagentCards(state.messages),
          }
          : state
        const finalized = finalizeHomeHarnessProjection(
          status === 'failed' || status === 'blocked'
            ? markPlanArtifactsTerminalForStatus(stateForTerminal, status)
            : stateForTerminal,
          status as Exclude<HarnessTurnStatus, 'running'>,
          timestamp,
        )
        const mergedRuntimeState = mergeRuntimeState(finalized.runtimeState, {
          ...runtimeSnapshot,
          run_id: event.run_id ?? event.data.run_id ?? runtimeSnapshot.run_id ?? finalized.runtimeState?.run_id ?? null,
          turn_id: event.data.turn_id ?? runtimeSnapshot.turn_id ?? event.data.run_id ?? finalized.runtimeState?.run_id ?? null,
          run_status: status,
          runtime_status: status,
          run_state: status,
        })
        const summary = String(turnFailure?.summary || '').trim()
        const visible = turnFailure?.user_visible !== false
        const dedupeKey = turnFailure?.failure_signature
          ? `failure:${turnFailure.failure_signature}`
          : `turn:${event.data.turn_id || event.data.run_id || event.sequence || status}`
        return withSequence({
          ...finalized,
          runtimeState: mergedRuntimeState,
          messages: visible && summary && (status === 'failed' || status === 'blocked')
            ? appendErrorMessageOnce(finalized.messages, summary, timestamp, dedupeKey)
            : finalized.messages,
          outlineRuntime: summary && status === 'failed'
            ? withOutlineRuntimeFailure(finalized.outlineRuntime, summary)
            : finalized.outlineRuntime,
          userInteraction: status === 'waiting_input'
            ? normalizePendingInteraction(resolveHarnessPendingInteraction({ user_interaction: runtimeSnapshot.user_interaction })) || finalized.userInteraction || state.userInteraction
            : null,
        })
      }

    case 'canvas_update':
    case 'tool_started':
    case 'tool_completed':
      return withSequence(state)

    case 'generation_started':
    case 'generation_completed':
    case 'generation_failed':
    case 'item_started':
    case 'item_updated':
    case 'item_completed':
      return withSequence(applyGenerationEventToHomeState(state, event))

    default:
      return withSequence(state)
  }
}
