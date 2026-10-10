import { describe, expect, it } from 'vitest'
import type { AgentEvent } from '@/api/endpoints/agent'
import {
  getTurnFailure,
  getTurnStatus,
  isTurnCompletedEvent,
  isTurnDoneForTransport,
  isTurnPausedStatus,
  isTurnTerminalStatus,
} from './harnessTurnProtocol'

function event(type: AgentEvent['type'], data: Record<string, unknown>): AgentEvent {
  return { type, data }
}

describe('harnessTurnProtocol', () => {
  it('resolves failed terminal status and failure', () => {
    const terminal = event('turn_completed', {
      status: 'failed',
      error: {
        error_type: 'ToolExecutionFailed',
        summary: 'tool failed',
        user_visible: true,
        failure_signature: 'sig-1',
      },
    })

    expect(isTurnCompletedEvent(terminal)).toBe(true)
    expect(getTurnStatus(terminal)).toBe('failed')
    expect(getTurnFailure(terminal)).toEqual({
      error_type: 'ToolExecutionFailed',
      summary: 'tool failed',
      user_visible: true,
      failure_signature: 'sig-1',
    })
    expect(isTurnTerminalStatus('failed')).toBe(true)
  })

  it('treats waiting input as done for transport but paused', () => {
    expect(isTurnDoneForTransport('waiting_input')).toBe(true)
    expect(isTurnPausedStatus('waiting_input')).toBe(true)
    expect(isTurnTerminalStatus('waiting_input')).toBe(true)
  })

  it('does not treat protocol error as terminal success', () => {
    const protocolError = event('protocol_error', { reason: 'missing_turn_completed' })

    expect(isTurnCompletedEvent(protocolError)).toBe(false)
    expect(getTurnStatus(protocolError)).toBe(null)
    expect(isTurnDoneForTransport(getTurnStatus(protocolError))).toBe(false)
  })
})
