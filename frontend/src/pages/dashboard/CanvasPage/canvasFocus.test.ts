import { describe, expect, it } from 'vitest'

import { getCenteredCanvasOffset } from './canvasFocus'

describe('getCenteredCanvasOffset', () => {
  it('centers an item in the viewport using the current zoom', () => {
    expect(getCenteredCanvasOffset({
      item: { x: 100, y: 50, width: 200, height: 100 },
      viewport: { width: 1000, height: 800 },
      zoom: 150,
    })).toEqual({
      x: 200,
      y: 250,
    })
  })

  it('uses fallback dimensions when width or height is missing', () => {
    expect(getCenteredCanvasOffset({
      item: { x: 10, y: 20 },
      fallbackSize: { width: 80, height: 40 },
      viewport: { width: 400, height: 300 },
      zoom: 100,
    })).toEqual({
      x: 150,
      y: 110,
    })
  })
})
