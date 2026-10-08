import type { AgentEvent } from '@/api/endpoints/agent'
import type { TurnCompletionOverrides, PresentationOverrides } from './harnessEventFixtures'

export function turnCompleted(
  status: 'completed' | 'failed' | 'blocked' | 'cancelled' | 'waiting_input',
  data: TurnCompletionOverrides = {},
): AgentEvent {
  const conversationId = String(data.conversation_id || 'conv-1')
  const runId = String(data.run_id || 'run-1')
  const summary = String(data.summary || data.message || data.terminal_error || '')
  return {
    type: 'turn_completed',
    sequence: data.sequence,
    run_id: runId,
    lane: 'user',
    data: {
      conversation_id: conversationId,
      run_id: runId,
      turn_id: runId,
      status,
      error: status === 'failed' || status === 'blocked'
        ? {
          error_type: data.error_type || 'Failed',
          summary,
          user_visible: data.user_visible !== false,
          failure_signature: data.failure_signature ?? null,
        }
        : null,
      runtime_snapshot: {
        runtime_status: status,
        run_state: status,
        turn_status: status,
        ...(data.runtime_snapshot || {}),
      },
      completed_at: '2026-05-01T00:00:00.000Z',
      duration_ms: null,
    },
  }
}

export function presentationDelta(
  sequence: number,
  blockKey: string,
  delta: string,
  options: PresentationOverrides = {},
): AgentEvent {
  const runId = String(options.run_id || 'run-home')
  const messageKey = String(options.message_key || `message:${runId}`)
  return {
    type: 'presentation.block.delta',
    sequence,
    run_id: runId,
    lane: 'user',
    data: {
      protocol_version: 2,
      type: 'presentation.block.delta',
      op_id: `test:${sequence}:${blockKey}:delta`,
      source_sequence: sequence,
      message_key: messageKey,
      block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      payload: { field: options.field || 'text', delta },
    },
  }
}

export function presentationComplete(
  sequence: number,
  blockKey: string,
  text: string,
  options: PresentationOverrides = {},
): AgentEvent {
  const runId = String(options.run_id || 'run-home')
  const messageKey = String(options.message_key || `message:${runId}`)
  const uiKind = String(options.ui_kind || 'text')
  const payload = { text, ...(options.payload || {}) }
  return {
    type: 'presentation.block.complete',
    sequence,
    run_id: runId,
    lane: 'user',
    data: {
      protocol_version: 2,
      type: 'presentation.block.complete',
      op_id: `test:${sequence}:${blockKey}:complete`,
      source_sequence: sequence,
      message_key: messageKey,
      block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      block: {
        id: blockKey,
        block_key: blockKey,
        kind: options.kind || (uiKind === 'text' ? 'text' : 'content'),
        order: options.order || 0,
        status: options.status || 'completed',
        visible: true,
        ui_kind: uiKind,
        uiKind,
        task_id: options.task_id,
        taskId: options.taskId ?? options.task_id,
        label: options.label,
        summary: options.summary,
        payload,
        children: options.children || [],
        revision: sequence,
        source_sequence: sequence,
      },
      payload,
    },
  }
}

export function presentationPatch(
  sequence: number,
  blockKey: string,
  patch: Record<string, unknown>,
  options: PresentationOverrides = {},
): AgentEvent {
  const runId = String(options.run_id || 'run-home')
  const messageKey = String(options.message_key || `message:${runId}`)
  const status = String(options.status || patch.status || 'running')
  return {
    type: 'presentation.block.patch',
    sequence,
    run_id: runId,
    lane: 'user',
    data: {
      protocol_version: 2,
      type: 'presentation.block.patch',
      op_id: `test:${sequence}:${blockKey}:patch`,
      source_sequence: sequence,
      message_key: messageKey,
      block_key: blockKey,
      parent_block_key: options.parent_block_key ?? null,
      status,
      payload: patch,
    },
  }
}