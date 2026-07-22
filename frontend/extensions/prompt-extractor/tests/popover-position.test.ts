import { describe, expect, it } from 'vitest'

import { resolvePopoverPosition } from '../src/PromptResultView'

describe('prompt extractor popover positioning', () => {
  it('flips to the left and upward when the click point is near the bottom-right edge', () => {
    const placement = resolvePopoverPosition(
      { x: 1180, y: 760 },
      { width: 1280, height: 800 },
      { width: 440, height: 360 },
    )

    expect(placement.left).toBeLessThan(1180)
    expect(placement.top).toBeLessThan(760)
  })

  it('stays to the right and below when there is enough space', () => {
    const placement = resolvePopoverPosition(
      { x: 240, y: 180 },
      { width: 1280, height: 800 },
      { width: 440, height: 360 },
    )

    expect(placement.left).toBeGreaterThan(240)
    expect(placement.top).toBeGreaterThan(180)
  })
})
