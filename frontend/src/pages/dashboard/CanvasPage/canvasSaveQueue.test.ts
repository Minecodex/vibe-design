import { describe, expect, it, vi } from 'vitest'

import { createCoalescingRunner } from './canvasSaveQueue'

const tick = () => new Promise<void>((resolve) => setTimeout(resolve, 0))

describe('createCoalescingRunner', () => {
  it('runs a single scheduled value immediately', async () => {
    const calls: number[] = []
    const schedule = createCoalescingRunner<number>(async (value) => {
      calls.push(value)
    })

    await schedule(1)

    expect(calls).toEqual([1])
  })

  it('never overlaps runs', async () => {
    let active = 0
    let maxActive = 0
    const schedule = createCoalescingRunner<number>(async () => {
      active += 1
      maxActive = Math.max(maxActive, active)
      await tick()
      active -= 1
    })

    await Promise.all([schedule(1), schedule(2), schedule(3)])

    expect(maxActive).toBe(1)
  })

  it('coalesces bursts to the latest value and drops superseded ones', async () => {
    const started: number[] = []
    const release: { current?: () => void } = {}
    const schedule = createCoalescingRunner<number>(async (value) => {
      started.push(value)
      await new Promise<void>((resolve) => {
        release.current = resolve
      })
    })

    // First snapshot starts running and blocks.
    const first = schedule(1)
    // Two more arrive while the first is in flight; the second (3) supersedes 2.
    schedule(2)
    schedule(3)
    expect(started).toEqual([1])

    // Finishing the first run flushes only the latest pending snapshot (3), not 2.
    release.current?.()
    await tick()
    expect(started).toEqual([1, 3])

    release.current?.()
    await first
    expect(started).toEqual([1, 3])
  })

  it('keeps draining after a failing run and reports the error', async () => {
    const onError = vi.fn()
    const calls: number[] = []
    const schedule = createCoalescingRunner<number>(async (value) => {
      calls.push(value)
      if (value === 1) throw new Error('save failed')
    }, onError)

    const first = schedule(1)
    schedule(2)
    await first
    await tick()

    expect(calls).toEqual([1, 2])
    expect(onError).toHaveBeenCalledTimes(1)
    expect(onError).toHaveBeenCalledWith(expect.any(Error), 1)
  })
})
