import { describe, expect, it } from 'vitest'

import {
  CANVAS_WHEEL_ZOOM_SENSITIVITY,
  MAX_CANVAS_ZOOM,
  MIN_CANVAS_ZOOM,
  clampCanvasZoom,
  getCanvasWheelZoomUpdate,
} from './canvasZoom'

describe('canvasZoom', () => {
  it('uses the increased wheel zoom sensitivity', () => {
    expect(CANVAS_WHEEL_ZOOM_SENSITIVITY).toBe(6)
  })

  it('uses 2 percent as the minimum canvas zoom', () => {
    expect(MIN_CANVAS_ZOOM).toBe(2)
  })

  it('clamps zoom values to the shared canvas bounds', () => {
    expect(clampCanvasZoom(1)).toBe(2)
    expect(clampCanvasZoom(55)).toBe(55)
    expect(clampCanvasZoom(999)).toBe(MAX_CANVAS_ZOOM)
  })

  it('allows fit-view style values below 10 percent to settle at 2 percent', () => {
    expect(clampCanvasZoom(7)).toBe(7)
    expect(clampCanvasZoom(1.5)).toBe(2)
  })

  it('computes a cursor-anchored zoom update for ctrl + wheel', () => {
    expect(getCanvasWheelZoomUpdate({
      oldZoom: 100,
      oldOffset: { x: 0, y: 0 },
      client: { x: 250, y: 150 },
      viewportRect: { left: 100, top: 50, width: 400, height: 200 },
      deltaY: -100,
      deltaMode: 0,
    })).toEqual({
      newZoom: 106,
      newOffset: { x: 3, y: 0 },
    })
  })

  it('returns null when the zoom level would not change', () => {
    expect(getCanvasWheelZoomUpdate({
      oldZoom: MAX_CANVAS_ZOOM,
      oldOffset: { x: 12, y: 8 },
      client: { x: 120, y: 90 },
      viewportRect: { left: 20, top: 30, width: 300, height: 200 },
      deltaY: -100,
      deltaMode: 0,
    })).toBeNull()
  })
})
