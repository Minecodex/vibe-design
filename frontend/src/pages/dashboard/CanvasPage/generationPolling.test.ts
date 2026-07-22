import { describe, expect, it, vi } from 'vitest'

import { startSerialPolling } from './generationPolling'

describe('startSerialPolling', () => {
  it('runs the first poll immediately on start', () => {
    const poll = vi.fn(async () => null)

    startSerialPolling(poll)

    expect(poll).toHaveBeenCalledTimes(1)
  })

  it('waits for the previous poll promise to resolve before scheduling the next one', async () => {
    vi.useFakeTimers()

    let resolveFirstPoll: ((delay: number | null) => void) | null = null
    const poll = vi
      .fn<() => Promise<number | null>>()
      .mockImplementationOnce(
        () =>
          new Promise<number | null>((resolve) => {
            resolveFirstPoll = resolve
          })
      )
      .mockResolvedValueOnce(null)

    startSerialPolling(poll)

    expect(poll).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)
    expect(poll).toHaveBeenCalledTimes(1)

    expect(resolveFirstPoll).not.toBeNull()
    resolveFirstPoll!(500)
    await Promise.resolve()
    await vi.advanceTimersByTimeAsync(499)
    expect(poll).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1)
    expect(poll).toHaveBeenCalledTimes(2)

    vi.useRealTimers()
  })
})
