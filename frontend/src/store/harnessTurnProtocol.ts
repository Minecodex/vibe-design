import type { AgentEvent } from '@/api/endpoints/agent'

export type HarnessTurnStatus = 'running' | 'completed' | 'failed' | 'blocked' | 'cancelled' | 'waiting_input'

export type HarnessTurnError = null | {
  error_type: string
  summary: string
  user_visible: boolean
  failure_signature?: string | null
}

export type HarnessRuntimeProfile = 'home' | 'canvas'

export type HarnessTurnItemType =
  | 'assistant_text'
  | 'tool_call'
  | 'generation_task'
  | 'file_change'
  | 'subagent'
  | 'interaction'

export type TurnStartedPayload = {
  conversation_id: string
  run_id: string
  turn_id: string
  status: 'running'
  runtime_profile: HarnessRuntimeProfile
  started_at: string
}

export type TurnItemPayload = {
  conversation_id: string
  run_id: string
  turn_id: string
  item_id: string
  item_type: HarnessTurnItemType
  status: 'running' | 'pending' | 'waiting_input' | 'completed' | 'failed' | 'cancelled'
  payload: Record<string, unknown>
  error?: HarnessTurnError
  completed_at?: string
}

export type TurnCompletedPayload = {
  conversation_id: string
  run_id: string
  turn_id: string
  status: HarnessTurnStatus
  error: HarnessTurnError
  runtime_snapshot: Record<string, unknown>
  completed_at: string
  duration_ms: number | null
}

export type HarnessTurnEvent = AgentEvent & {
  type: 'turn_started' | 'item_started' | 'item_updated' | 'item_completed' | 'turn_completed' | 'protocol_error'
}

export const TURN_TERMINAL_STATUSES: ReadonlySet<HarnessTurnStatus> = new Set([
  'completed',
  'failed',
  'blocked',
  'cancelled',
  'waiting_input',
])

export function isTurnStartedEvent(event: Pick<AgentEvent, 'type'> | null | undefined): event is AgentEvent & { type: 'turn_started' } {
  return event?.type === 'turn_started'
}

export function isTurnCompletedEvent(event: { type?: unknown } | null | undefined): event is AgentEvent & { type: 'turn_completed' } {
  return event?.type === 'turn_completed'
}

export function isTurnItemEvent(event: Pick<AgentEvent, 'type'> | null | undefined): event is AgentEvent & { type: 'item_started' | 'item_updated' | 'item_completed' } {
  return event?.type === 'item_started' || event?.type === 'item_updated' || event?.type === 'item_completed'
}

export function getTurnStatus(event: Pick<AgentEvent, 'data'> | null | undefined): HarnessTurnStatus | null {
  const status = String(event?.data?.status || '').toLowerCase()
  return isHarnessTurnStatus(status) ? status : null
}

export function getTurnFailure(event: Pick<AgentEvent, 'data'> | null | undefined): HarnessTurnError {
  const error = event?.data?.error
  if (!error || typeof error !== 'object') {
    return null
  }
  const source = error as Record<string, unknown>
  const summary = String(source.summary || '').trim()
  const errorType = String(source.error_type || '').trim()
  if (!summary && !errorType) {
    return null
  }
  return {
    error_type: errorType || 'HarnessTurnError',
    summary,
    user_visible: source.user_visible !== false,
    failure_signature: source.failure_signature == null ? null : String(source.failure_signature),
  }
}

export function isTurnTerminalStatus(status: string | null | undefined): status is HarnessTurnStatus {
  return isHarnessTurnStatus(status) && TURN_TERMINAL_STATUSES.has(status)
}

export function isTurnPausedStatus(status: string | null | undefined): status is 'waiting_input' {
  return status === 'waiting_input'
}

export function isTurnDoneForTransport(status: string | null | undefined): boolean {
  return isTurnTerminalStatus(status)
}

function isHarnessTurnStatus(status: string | null | undefined): status is HarnessTurnStatus {
  return status === 'running'
    || status === 'completed'
    || status === 'failed'
    || status === 'blocked'
    || status === 'cancelled'
    || status === 'waiting_input'
}
