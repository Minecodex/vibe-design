import { describe, expect, it } from 'vitest'

import {
  buildBrushPathSvgPath,
  createBrushPathCanvasItem,
  resizeBrushPathBoundsFromCorner,
  scaleBrushPathPoint,
} from './brushPaths'

describe('brush path canvas items', () => {
  it('creates a persisted brush_path item from sampled points', () => {
    const item = createBrushPathCanvasItem({
      id: 'brush-1',
      points: [
        { x: 100, y: 200 },
        { x: 130, y: 240 },
        { x: 160, y: 220 },
      ],
      brushColor: '#00ff00',
      brushSize: 10,
      zIndex: 7,
    })

    expect(item).toMatchObject({
      id: 'brush-1',
      type: 'brush_path',
      x: 95,
      y: 195,
      width: 70,
      height: 50,
      brushColor: '#00ff00',
      brushSize: 10,
      z_index: 7,
      pathBounds: {
        x: 95,
        y: 195,
        width: 70,
        height: 50,
      },
    })

    expect(item.points).toBeDefined()
    expect(item.points!).toHaveLength(3)
    expect(item.points!.every((point) => point.x >= 0 && point.x <= 1)).toBe(true)
    expect(item.points!.every((point) => point.y >= 0 && point.y <= 1)).toBe(true)
  })

  it('keeps a tap-sized stroke visible by enforcing a minimum brush-sized box', () => {
    const item = createBrushPathCanvasItem({
      id: 'brush-tap',
      points: [{ x: 40, y: 80 }],
      brushColor: '#111111',
      brushSize: 12,
      zIndex: 1,
    })

    expect(item.width).toBe(12)
    expect(item.height).toBe(12)
    expect(item.x).toBe(34)
    expect(item.y).toBe(74)
    expect(item.points).toEqual([{ x: 0.5, y: 0.5 }])
  })
})

describe('brush path scaling helpers', () => {
  it('scales normalized path points into the current element box', () => {
    expect(
      scaleBrushPathPoint(
        { x: 0.25, y: 0.75 },
        { width: 200, height: 80 },
      ),
    ).toEqual({ x: 50, y: 60 })
  })

  it('builds an SVG path string for a resized brush element', () => {
    expect(
      buildBrushPathSvgPath(
        [
          { x: 0, y: 0.5 },
          { x: 0.5, y: 1 },
          { x: 1, y: 0 },
        ],
        { width: 120, height: 60 },
      ),
    ).toBe('M 0 30 L 60 60 L 120 0')
  })

  it('resizes brush element bounds freely instead of keeping image-style aspect ratio', () => {
    expect(
      resizeBrushPathBoundsFromCorner({
        handle: 'nw',
        startRect: { x: 100, y: 120, width: 80, height: 40 },
        deltaX: -30,
        deltaY: -50,
      }),
    ).toEqual({
      x: 70,
      y: 70,
      width: 110,
      height: 90,
    })
  })
})
