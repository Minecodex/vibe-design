import { describe, expect, it } from 'vitest'

import { createCanvasSpatialIndex, rectFromBounds } from './canvasSpatialIndex'

describe('CanvasSpatialIndex', () => {
  it('queries only items intersecting a viewport rect in z-index order', () => {
    const index = createCanvasSpatialIndex([
      {
        id: 'middle',
        bounds: rectFromBounds({ x: 100, y: 100, width: 80, height: 80 }),
        value: 'middle',
        zIndex: 5,
      },
      {
        id: 'bottom',
        bounds: rectFromBounds({ x: 90, y: 90, width: 80, height: 80 }),
        value: 'bottom',
        zIndex: 1,
      },
      {
        id: 'outside',
        bounds: rectFromBounds({ x: 1000, y: 1000, width: 80, height: 80 }),
        value: 'outside',
        zIndex: 10,
      },
    ], { cellSize: 64 })

    expect(index.query({ left: 0, right: 200, top: 0, bottom: 200 })).toEqual(['bottom', 'middle'])
  })

  it('hit-tests from highest z-index to lowest and supports predicates', () => {
    const index = createCanvasSpatialIndex([
      {
        id: 'bottom',
        bounds: rectFromBounds({ x: 0, y: 0, width: 100, height: 100 }),
        value: { id: 'bottom', locked: false },
        zIndex: 1,
      },
      {
        id: 'top-locked',
        bounds: rectFromBounds({ x: 0, y: 0, width: 100, height: 100 }),
        value: { id: 'top-locked', locked: true },
        zIndex: 10,
      },
      {
        id: 'top',
        bounds: rectFromBounds({ x: 10, y: 10, width: 30, height: 30 }),
        value: { id: 'top', locked: false },
        zIndex: 20,
      },
    ], { cellSize: 32 })

    expect(index.hitTest({ x: 20, y: 20 })?.id).toBe('top')
    expect(index.hitTest({ x: 50, y: 50 }, {
      predicate: (item) => !item.locked,
    })?.id).toBe('bottom')
    expect(index.hitTest({ x: 200, y: 200 })).toBeNull()
  })

  it('keeps oversized items queryable without expanding them across every grid cell', () => {
    const index = createCanvasSpatialIndex([
      {
        id: 'large',
        bounds: rectFromBounds({ x: -10000, y: -10000, width: 20000, height: 20000 }),
        value: 'large',
        zIndex: 1,
      },
    ], { cellSize: 64, maxCellsPerItem: 4 })

    expect(index.query({ left: 10, right: 20, top: 10, bottom: 20 })).toEqual(['large'])
    expect(index.hitTest({ x: 0, y: 0 })).toBe('large')
  })
})
