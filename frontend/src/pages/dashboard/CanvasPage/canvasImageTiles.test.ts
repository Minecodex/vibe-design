import { describe, expect, it } from 'vitest'

import {
  buildVisibleCanvasTileSlots,
  selectCanvasTileLevel,
} from './canvasImageTiles'

const descriptor = {
  url: '/image__tile_256_2_0_0.webp?v=1',
  status: 'ready' as const,
  tileSize: 256,
  sourceWidth: 1024,
  sourceHeight: 512,
  levelWidth: 1024,
  levelHeight: 512,
  columns: 4,
  rows: 2,
}

describe('selectCanvasTileLevel', () => {
  it('selects tile levels only for idle large on-screen images', () => {
    expect(selectCanvasTileLevel({
      displayWidth: 600,
      displayHeight: 400,
      zoom: 100,
      interactionMode: 'idle',
    })).toBeNull()

    expect(selectCanvasTileLevel({
      displayWidth: 1200,
      displayHeight: 800,
      zoom: 200,
      interactionMode: 'interactive',
    })).toBeNull()

    expect(selectCanvasTileLevel({
      displayWidth: 1200,
      displayHeight: 800,
      zoom: 200,
      interactionMode: 'idle',
    })).toBe(4)

    expect(selectCanvasTileLevel({
      displayWidth: 2048,
      displayHeight: 2048,
      zoom: 60,
      interactionMode: 'idle',
    })).toBe(3)
  })
})

describe('buildVisibleCanvasTileSlots', () => {
  it('returns only tiles intersecting the current viewport', () => {
    const slots = buildVisibleCanvasTileSlots({
      bounds: { x: -512, y: -256, width: 1024, height: 512 },
      descriptor,
      viewport: {
        width: 256,
        height: 256,
        zoom: 100,
        offset: { x: -128, y: -128 },
      },
    })

    expect(slots.map((slot) => slot.key)).toEqual(['2:1'])
    expect(slots[0]).toMatchObject({
      x: 2,
      y: 1,
      left: 512,
      top: 256,
      width: 256,
      height: 256,
    })
  })

  it('skips tile rendering when too many tiles would be visible', () => {
    const slots = buildVisibleCanvasTileSlots({
      bounds: { x: -2048, y: -2048, width: 4096, height: 4096 },
      descriptor: {
        ...descriptor,
        levelWidth: 4096,
        levelHeight: 4096,
        columns: 16,
        rows: 16,
      },
      viewport: {
        width: 4096,
        height: 4096,
        zoom: 100,
        offset: { x: 0, y: 0 },
      },
      maxVisibleTiles: 32,
    })

    expect(slots).toEqual([])
  })
})
