import { describe, expect, it } from 'vitest'

import { findEmptyRectPosition } from './canvasLayout'

describe('findEmptyRectPosition', () => {
  it('places a whole rectangle to the right of same-band obstacles', () => {
    const position = findEmptyRectPosition(
      { x: 0, y: 0, width: 300, height: 200 },
      [
        { id: 'existing-1', type: 'image', x: 280, y: 20, width: 160, height: 160 },
        { id: 'existing-2', type: 'image', x: 520, y: 30, width: 120, height: 140 },
      ],
      { gap: 20 },
    )

    expect(position).toEqual({ x: 660, y: 0 })
  })

  it('ignores excluded ids and group outline items', () => {
    const position = findEmptyRectPosition(
      { x: 0, y: 0, width: 300, height: 200 },
      [
        { id: 'group-1', type: 'group', x: 0, y: 0, width: 500, height: 360 },
        { id: 'member-1', type: 'image', x: 80, y: 80, width: 100, height: 100 },
      ],
      { excludeIds: ['member-1'] },
    )

    expect(position).toEqual({ x: 0, y: 0 })
  })
})
