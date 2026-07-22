import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { buildCutoutResultItem, getOpaqueBoundsFromAlphaChannel } from './cutout'

describe('cutout', () => {
  const sourceItem: CanvasItem = {
    id: 'image-1',
    type: 'image',
    url: 'https://example.com/source.png',
    x: 120,
    y: 64,
    width: 320,
    height: 180,
    z_index: 8,
    asset_origin: 'local_upload',
  }

  it('creates a nearby cutout result item using the cropped cutout size', () => {
    const resultItem = buildCutoutResultItem({
      sourceItem,
      canvasItems: [sourceItem],
      resultUrl: 'https://example.com/cutout.png',
      resultWidth: 140,
      resultHeight: 96,
    })

    expect(resultItem).toMatchObject({
      type: 'image',
      url: 'https://example.com/cutout.png',
      width: 140,
      height: 96,
      asset_origin: 'local_upload',
    })
    expect(resultItem.x).toBe(464)
    expect(resultItem.y).toBe(64)
    expect((resultItem.z_index || 0)).toBeGreaterThan(sourceItem.z_index || 0)
  })

  it('finds the minimal opaque bounds from the alpha channel', () => {
    const width = 5
    const height = 4
    const alpha = new Uint8ClampedArray(width * height * 4)
    const setAlpha = (x: number, y: number, value: number) => {
      alpha[(y * width + x) * 4 + 3] = value
    }

    setAlpha(1, 1, 255)
    setAlpha(3, 2, 128)

    expect(getOpaqueBoundsFromAlphaChannel(alpha, width, height)).toEqual({
      left: 1,
      top: 1,
      width: 3,
      height: 2,
    })
  })

  it('returns null when the cutout is fully transparent', () => {
    const alpha = new Uint8ClampedArray(4 * 4 * 4)

    expect(getOpaqueBoundsFromAlphaChannel(alpha, 4, 4)).toBeNull()
  })
})
