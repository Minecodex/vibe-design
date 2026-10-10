import type { HarnessConversationRead } from '@/api/endpoints/agent'

type HarnessInteractionSnapshot = {
  runtime_state?: unknown
  user_interaction?: unknown
}

type HarnessStreamCursorDetail = Partial<Pick<
  HarnessConversationRead,
  'phase' | 'runtime_status'
>> & HarnessInteractionSnapshot & {
  projection?: Record<string, unknown> | null
  event_stream?: Record<string, unknown> | null
  eventStream?: Record<string, unknown> | null
}

function isPendingInteractionObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

export function hasHarnessPendingInteraction(
  detail: HarnessInteractionSnapshot | null | undefined,
): boolean {
  return !!resolveHarnessPendingInteraction(detail)
}

export function resolveHarnessPendingInteraction(
  detail: HarnessInteractionSnapshot | null | undefined,
): Record<string, unknown> | null {
  if (!detail) {
    return null
  }

  // The workflow persists the pending form at the conversation top level
  // (quick_brief / design_system / ask_user all do this); the nested
  // runtime_state copy is frequently absent. Check both so a waiting-on-user
  // conversation is recognized and we don't needlessly resubscribe its stream.
  if (isPendingInteractionObject(detail.user_interaction)) {
    return detail.user_interaction
  }

  const runtimeState = detail.runtime_state
  if (!runtimeState || typeof runtimeState !== 'object' || Array.isArray(runtimeState)) {
    return null
  }

  const runtimeInteraction = (runtimeState as Record<string, unknown>).user_interaction
  return isPendingInteractionObject(runtimeInteraction)
    ? runtimeInteraction as Record<string, unknown>
    : null
}

export type TurnStreamSessionState = {
  sawTerminal?: boolean
  sawWaitingInputTerminal?: boolean
}

export function hasHarnessProjectionGap(
  detail: Pick<HarnessStreamCursorDetail, 'projection' | 'event_stream' | 'eventStream'> | null | undefined,
): boolean {
  if (!detail) {
    return false
  }
  const projection = isRecord(detail.projection) ? detail.projection : {}
  const eventStream = isRecord(detail.event_stream)
    ? detail.event_stream
    : isRecord(detail.eventStream)
      ? detail.eventStream
      : {}
  const appliedSequence = normalizeSequence(
    projection.event_last_sequence
    ?? projection.applied_event_sequence
    ?? projection.appliedEventSequence
    ?? projection.last_event_sequence
    ?? projection.latest_event_sequence,
  )
  const latestSequence = normalizeSequence(
    eventStream.last_sequence
    ?? eventStream.lastSequence
    ?? eventStream.latest_sequence
    ?? eventStream.latestSequence,
  )
  return latestSequence > appliedSequence
}

export function shouldReconnectTurnStream(
  detail: HarnessStreamCursorDetail | null | undefined,
  session: TurnStreamSessionState = {},
): boolean {
  if (!detail || session.sawTerminal) {
    return false
  }
  if (detail.runtime_status === 'running') {
    return true
  }

  const runtimeState = isRecord(detail.runtime_state) ? detail.runtime_state : null
  const runtimePhase = typeof runtimeState?.phase === 'string'
    ? runtimeState.phase
    : null
  const isWaitingForPlanStart = detail.phase === 'planning_ready' || runtimePhase === 'planning_ready'
  if (detail.runtime_status === 'waiting_input') {
    return (
      !isWaitingForPlanStart
      && !session.sawWaitingInputTerminal
      && hasHarnessProjectionGap(detail)
    )
  }

  return false
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function normalizeSequence(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 0
}
