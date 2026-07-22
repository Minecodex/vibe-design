import { describe, expect, it } from 'vitest'

import {
  getMediaDisplayInitializationUpdate,
  getMediaSelectionOverlayMetrics,
  resizeMediaSelectionFromCorner,
} from './mediaSelectionResize'

describe('mediaSelectionResize', () => {
  it('keeps selection border and handles visually fixed across zoom levels', () => {
    const lowZoom = getMediaSelectionOverlayMetrics(50)
    const highZoom = getMediaSelectionOverlayMetrics(200)

    expect(lowZoom.handleSize * 0.5).toBe(highZoom.handleSize * 2)
    expect(lowZoom.borderWidth * 0.5).toBe(highZoom.borderWidth * 2)
    expect(lowZoom.handleSize * 0.5).toBe(12)
    expect(lowZoom.borderWidth * 0.5).toBe(2)
  })

  it('keeps saved image display dimensions when intrinsic dimensions differ', () => {
    const next = getMediaDisplayInitializationUpdate({
      item: { type: 'image', x: 100, y: 80, width: 520, height: 260 },
      intrinsicWidth: 400,
      intrinsicHeight: 200,
    })

    expect(next).toBeNull()
  })

  it('keeps saved video display dimensions when intrinsic dimensions differ', () => {
    const next = getMediaDisplayInitializationUpdate({
      item: { type: 'video', x: 100, y: 80, width: 400, height: 200 },
      intrinsicWidth: 1920,
      intrinsicHeight: 1080,
    })

    expect(next).toBeNull()
  })

  it('initializes media display size from intrinsic dimensions only when saved dimensions are missing', () => {
    const next = getMediaDisplayInitializationUpdate({
      item: { type: 'image', x: 100, y: 80, width: undefined, height: undefined },
      intrinsicWidth: 400,
      intrinsicHeight: 200,
    })

    expect(next).toEqual({
      width: 400,
      height: 200,
      x: 100,
      y: 80,
      media_display_size_source: 'intrinsic',
    })
  })

  it('replaces untouched agent placeholder display size with intrinsic dimensions', () => {
    const next = getMediaDisplayInitializationUpdate({
      item: {
        type: 'image_generator',
        x: 100,
        y: 80,
        width: 1024,
        height: 1024,
        url: '',
        asset_origin: 'ai_generated',
        media_display_size_source: 'placeholder',
      },
      intrinsicWidth: 2048,
      intrinsicHeight: 1536,
    })

    expect(next).toEqual({
      width: 2048,
      height: 1536,
      x: 100,
      y: 80,
      media_display_size_source: 'intrinsic',
    })
  })

  it('keeps user-resized agent placeholder dimensions when intrinsic dimensions load', () => {
    const next = getMediaDisplayInitializationUpdate({
      item: {
        type: 'image_generator',
        x: 100,
        y: 80,
        width: 520,
        height: 260,
        url: '',
        asset_origin: 'ai_generated',
        media_display_size_source: 'user',
      },
      intrinsicWidth: 2048,
      intrinsicHeight: 1536,
    })

    expect(next).toBeNull()
  })

  it('resizes from the bottom-right corner proportionally while keeping the opposite corner fixed', () => {
    const next = resizeMediaSelectionFromCorner({
      handle: 'se',
      startRect: { x: 100, y: 80, width: 400, height: 200 },
      deltaX: 120,
      deltaY: 10,
    })

    expect(next).toEqual({
      x: 100,
      y: 80,
      width: 520,
      height: 260,
    })
  })

  it('resizes from the top-left corner proportionally while keeping the bottom-right corner fixed', () => {
    const next = resizeMediaSelectionFromCorner({
      handle: 'nw',
      startRect: { x: 100, y: 80, width: 400, height: 200 },
      deltaX: 120,
      deltaY: 10,
    })

    expect(next).toEqual({
      x: 220,
      y: 140,
      width: 280,
      height: 140,
    })
  })

  it('uses the stronger drag axis to determine proportional resize', () => {
    const next = resizeMediaSelectionFromCorner({
      handle: 'ne',
      startRect: { x: 100, y: 80, width: 400, height: 200 },
      deltaX: 10,
      deltaY: -80,
    })

    expect(next).toEqual({
      x: 100,
      y: 0,
      width: 560,
      height: 280,
    })
  })

  it('does not shrink below the minimum proportional display size', () => {
    const next = resizeMediaSelectionFromCorner({
      handle: 'sw',
      startRect: { x: 100, y: 80, width: 400, height: 200 },
      deltaX: 390,
      deltaY: -10,
      minSize: 80,
    })

    expect(next).toEqual({
      x: 340,
      y: 80,
      width: 160,
      height: 80,
    })
  })
})
