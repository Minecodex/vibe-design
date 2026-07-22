import { describe, expect, it } from 'vitest'

import { runAgentHistoryPerfHarness } from './agentHistoryPerfHarness'

describe('agentHistoryPerfHarness', () => {
  it('models 300 rich-media messages as virtualized and bounded by mounted rows', () => {
    const result = runAgentHistoryPerfHarness(300)

    expect(result.shouldVirtualize).toBe(true)
    expect(result.estimatedImageNodesWithoutOptimization).toBeGreaterThan(80)
    expect(result.estimatedMountedRowsWithVirtualization).toBeLessThan(30)
  })

  it('models 1000 rich-media messages without mounting all rows', () => {
    const result = runAgentHistoryPerfHarness(1000)

    expect(result.shouldVirtualize).toBe(true)
    expect(result.renderWeight).toBeGreaterThan(1000)
    expect(result.estimatedMountedRowsWithVirtualization).toBe(18)
  })
})
