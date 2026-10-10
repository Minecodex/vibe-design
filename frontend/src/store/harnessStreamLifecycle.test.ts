import { describe, expect, it } from 'vitest'

import {
  hasHarnessPendingInteraction,
  resolveHarnessPendingInteraction,
  shouldReconnectTurnStream,
} from './harnessStreamLifecycle'

describe('harnessStreamLifecycle', () => {
  it('resumes event stream while runtime is running', () => {
    expect(shouldReconnectTurnStream({ runtime_status: 'running' })).toBe(true)
  })

  it('does not resume waiting_input when the projection cursor is caught up', () => {
    expect(shouldReconnectTurnStream({
      runtime_status: 'waiting_input',
      runtime_state: {},
      projection: { event_last_sequence: 7 },
      event_stream: { last_sequence: 7 },
    })).toBe(false)
  })

  it('resumes waiting_input only to catch up a durable projection gap', () => {
    expect(shouldReconnectTurnStream({
      runtime_status: 'waiting_input',
      runtime_state: {},
      projection: { event_last_sequence: 6 },
      event_stream: { last_sequence: 7 },
    })).toBe(true)
  })

  it('does not resume a planning-ready conversation that is waiting for the user to start execution', () => {
    expect(shouldReconnectTurnStream({
      phase: 'planning_ready',
      runtime_status: 'waiting_input',
      runtime_state: {},
    })).toBe(false)
  })

  it('does not treat empty or non-object interaction values as pending', () => {
    expect(hasHarnessPendingInteraction({ runtime_state: { user_interaction: null } })).toBe(false)
    expect(hasHarnessPendingInteraction({ runtime_state: { user_interaction: [] } })).toBe(false)
  })

  it('recognizes a pending interaction stored at the conversation top level', () => {
    // quick_brief / design_system_id / ask_user persist the form at detail.user_interaction,
    // not inside runtime_state. Both must be detected.
    expect(hasHarnessPendingInteraction({
      user_interaction: { request_id: 'req-1', question: 'Confirm?' },
      runtime_state: {},
    })).toBe(true)
  })

  it('does not resume a waiting_input conversation whose form is only at the top level', () => {
    expect(shouldReconnectTurnStream({
      runtime_status: 'waiting_input',
      user_interaction: { request_id: 'req-1', question: 'Pick a slide count' },
      runtime_state: {},
    })).toBe(false)
  })

  it('keeps quick brief, design-system, and ask-user cards paused when restored from the top level', () => {
    for (const kind of ['quick_brief', 'design_system_picker', 'ask_user'] as const) {
      const detail = {
        runtime_status: 'waiting_input',
        user_interaction: {
          kind,
          request_id: `${kind}:req-1`,
          question: 'Confirm?',
          status: 'pending',
        },
        runtime_state: {},
      }
      expect(resolveHarnessPendingInteraction(detail)?.kind).toBe(kind)
      expect(shouldReconnectTurnStream(detail)).toBe(false)
    }
  })

  it('does not resume terminal runtime statuses', () => {
    for (const runtimeStatus of ['completed', 'failed', 'blocked', 'cancelled'] as const) {
      expect(shouldReconnectTurnStream({ runtime_status: runtimeStatus })).toBe(false)
    }
  })

  it('does not reconnect after terminal was observed in the stream', () => {
    expect(shouldReconnectTurnStream({ runtime_status: 'running' }, { sawTerminal: true })).toBe(false)
  })
})
