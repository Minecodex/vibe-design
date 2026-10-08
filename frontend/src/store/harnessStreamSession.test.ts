import { describe, expect, it, vi } from 'vitest'

import { startHarnessStreamSession } from './harnessStreamSession'

describe('harnessStreamSession', () => {
  it('resumes from last sequence and settles after stream closes', async () => {
    const events: string[] = []
    const closed: AbortController[] = []
    const stream = vi.fn(async function* (_conversationId: string, afterSequence?: number | AbortSignal) {
      expect(afterSequence).toBe(7)
      yield 'event-8'
    })

    startHarnessStreamSession({
      conversationId: 'conv-1',
      lastSequence: 7,
      stream,
      onEvent: (event) => events.push(event),
      onClose: (controller) => {
        closed.push(controller)
      },
    })

    await vi.waitFor(() => {
      expect(events).toEqual(['event-8'])
      expect(closed).toHaveLength(1)
    })
    expect(stream).toHaveBeenCalledTimes(1)
  })

  it('does not surface abort as a stream error', async () => {
    const errors: unknown[] = []
    const stream = vi.fn(async function* () {

      const error = new Error('aborted')
      error.name = 'AbortError'
      yield* [] // This fixture intentionally emits no events.
      throw error
    })

    startHarnessStreamSession({
      conversationId: 'conv-1',
      stream,
      onEvent: () => undefined,
      onError: (error) => errors.push(error),
    })

    await vi.waitFor(() => expect(stream).toHaveBeenCalledTimes(1))
    expect(errors).toEqual([])
  })

  it('reconnects from the latest emitted sequence and skips duplicate replayed events', async () => {
    vi.useFakeTimers()
    const events: Array<{ sequence: number; value: string }> = []
    const stream = vi.fn(async function* (_conversationId: string, afterSequence?: number | AbortSignal) {
      if (stream.mock.calls.length === 1) {
        expect(afterSequence).toBeInstanceOf(AbortSignal)
        yield { sequence: 1, value: 'first' }
        throw new Error('network closed')
      }
      expect(afterSequence).toBe(1)
      yield { sequence: 1, value: 'duplicate-first' }
      yield { sequence: 2, value: 'second' }
    })

    const session = startHarnessStreamSession({
      conversationId: 'conv-1',
      stream,
      reconnectDelayMs: 25,
      shouldReconnect: () => stream.mock.calls.length < 2,
      onEvent: (event: { sequence: number; value: string }) => events.push(event),
    })

    try {
      await vi.waitFor(() => expect(stream).toHaveBeenCalledTimes(1))
      await vi.waitFor(() => expect(events.map((event) => event.value)).toEqual(['first']))

      await vi.advanceTimersByTimeAsync(25)

      await vi.waitFor(() => {
        expect(stream).toHaveBeenCalledTimes(2)
        expect(events.map((event) => event.value)).toEqual(['first', 'second'])
      })
    } finally {
      session.abort()
      vi.useRealTimers()
    }
  })

  it('can surface lower-sequence events for stores that do their own idempotency', async () => {
    const events: Array<{ sequence: number; value: string }> = []
    const stream = vi.fn(async function* () {
      yield { sequence: 10, value: 'presentation' }
      yield { sequence: 9, value: 'workspace-file' }
    })

    startHarnessStreamSession({
      conversationId: 'conv-1',
      stream,
      skipDuplicateSequences: false,
      onEvent: (event: { sequence: number; value: string }) => events.push(event),
    })

    await vi.waitFor(() => {
      expect(events.map((event) => event.value)).toEqual(['presentation', 'workspace-file'])
    })
  })

  it('stops reconnecting after a turn_completed event', async () => {
    const stream = vi.fn(async function* () {
      yield { type: 'turn_completed', sequence: 1 }
    })
    const reconcile = vi.fn(() => true)

    startHarnessStreamSession({
      conversationId: 'conv-1',
      stream,
      onEvent: () => undefined,
      onTransportClosedWithoutTerminal: reconcile,
    })

    await vi.waitFor(() => expect(stream).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reconcile).not.toHaveBeenCalled()
    expect(stream).toHaveBeenCalledTimes(1)
  })

  it('stops reconnecting after a protocol_error event', async () => {
    const stream = vi.fn(async function* () {
      yield { type: 'protocol_error', sequence: 1, data: { reason: 'missing_turn_completed' } }
    })
    const reconcile = vi.fn(() => false)

    startHarnessStreamSession({
      conversationId: 'conv-1',
      stream,
      onEvent: () => undefined,
      onTransportClosedWithoutTerminal: reconcile,
    })

    await vi.waitFor(() => expect(stream).toHaveBeenCalledTimes(1))
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(reconcile).not.toHaveBeenCalled()
    expect(stream).toHaveBeenCalledTimes(1)
  })

  it('calls reconcile callback when transport closes without terminal event', async () => {
    const stream = vi.fn(async function* () {
      yield { type: 'message_done', sequence: 1 }
    })
    const reconcile = vi.fn(() => false)

    startHarnessStreamSession({
      conversationId: 'conv-1',
      stream,
      onEvent: () => undefined,
      onTransportClosedWithoutTerminal: reconcile,
    })

    await vi.waitFor(() => expect(reconcile).toHaveBeenCalledTimes(1))
    expect(stream).toHaveBeenCalledTimes(1)
  })
})
