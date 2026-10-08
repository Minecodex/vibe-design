import type { AgentEvent } from '@/api/endpoints/agent'

export interface TurnCompletionOverrides {
  conversation_id?: string
  run_id?: string
  summary?: string
  message?: string
  terminal_error?: string
  sequence?: number
  error_type?: string
  user_visible?: boolean
  failure_signature?: string | null
  runtime_snapshot?: Record<string, unknown>
}

export interface PresentationOverrides {
  run_id?: string
  message_key?: string
  parent_block_key?: string | null
  field?: string
  ui_kind?: string
  payload?: Record<string, unknown>
  kind?: string
  order?: number
  status?: string
  task_id?: string | number | null
  taskId?: string | number | null
  label?: string | null
  summary?: string | null
  children?: Record<string, unknown>[]
}

export function turnCompleted(
  status: 'completed' | 'failed' | 'blocked' | 'cancelled' | 'waiting_input',
  data: TurnCompletionOverrides = {},
): AgentEvent {
  const conversationId = String(data.conversation_id || 'conv-canvas')
  const runId = String(data.run_id || 'run-canvas')
  const summary = String(data.summary || data.message || data.terminal_error || '')
  return {
    type: 'turn_completed', sequence: data.sequence, run_id: runId, lane: 'user',
    data: {
      conversation_id: conversationId, run_id: runId, turn_id: runId, status,
      error: status === 'failed' || status === 'blocked' ? {
        error_type: data.error_type || 'Failed', summary,
        user_visible: data.user_visible !== false, failure_signature: data.failure_signature ?? null,
      } : null,
      runtime_snapshot: { runtime_status: status, run_state: status, turn_status: status, ...data.runtime_snapshot },
      completed_at: '2026-05-01T00:00:00.000Z', duration_ms: null,
    },
  }
}

export function presentationDelta(
  sequence: number, blockKey: string, delta: string, options: PresentationOverrides = {},
): AgentEvent {
  const runId = String(options.run_id || 'run-canvas')
  return {
    type: 'presentation.block.delta', sequence, run_id: runId, lane: 'user',
    data: {
      protocol_version: 2, type: 'presentation.block.delta',
      op_id: `test:${sequence}:${blockKey}:delta`, source_sequence: sequence,
      message_key: String(options.message_key || `message:${runId}`), block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null, payload: { field: options.field || 'text', delta },
    },
  }
}

export function presentationComplete(
  sequence: number, blockKey: string, text: string, options: PresentationOverrides = {},
): AgentEvent {
  const runId = String(options.run_id || 'run-canvas')
  const uiKind = String(options.ui_kind || 'text')
  const payload = { text, ...options.payload }
  return {
    type: 'presentation.block.complete', sequence, run_id: runId, lane: 'user',
    data: {
      protocol_version: 2, type: 'presentation.block.complete',
      op_id: `test:${sequence}:${blockKey}:complete`, source_sequence: sequence,
      message_key: String(options.message_key || `message:${runId}`), block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      block: {
        id: blockKey, block_key: blockKey,
        kind: options.kind || (uiKind === 'text' || uiKind === 'assistant_text' ? 'text' : 'content'),
        order: options.order || 0, status: options.status || 'completed', visible: true,
        ui_kind: uiKind, uiKind, payload, revision: sequence, source_sequence: sequence,
      },
      payload,
    },
  }
}
