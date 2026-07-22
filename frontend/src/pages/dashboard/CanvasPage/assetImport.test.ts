import { describe, expect, it, vi } from 'vitest'

import { planImportedCanvasItems } from './assetImport'

describe('assetImport', () => {
  it('lays out imported assets using the current canvas center and existing items', () => {
    const findPosition = vi
      .fn()
      .mockReturnValueOnce({ x: 120, y: 240 })
      .mockReturnValueOnce({ x: 360, y: 480 })

    const result = planImportedCanvasItems({
      assets: [
        {
          id: 1,
          url: 'https://example.com/first.png',
          type: 'image',
          origin_kind: 'ai_generated',
        },
        {
          id: 2,
          url: 'https://example.com/second.mp4',
          type: 'video',
          origin_kind: 'local_upload',
        },
      ],
      mediaSizes: [
        { width: 640, height: 480 },
        { width: 1920, height: 1080 },
      ],
      viewportCenter: { x: 50, y: 60 },
      existingItems: [{ id: 'existing', type: 'image', url: '', x: 0, y: 0, width: 100, height: 100 }],
      createId: () => 'generated-id',
      findPosition,
    })

    expect(findPosition).toHaveBeenNthCalledWith(
      1,
      50,
      60,
      640,
      480,
      [{ id: 'existing', type: 'image', url: '', x: 0, y: 0, width: 100, height: 100 }],
    )
    expect(findPosition).toHaveBeenNthCalledWith(
      2,
      50,
      60,
      1920,
      1080,
      expect.arrayContaining([
        { id: 'existing', type: 'image', url: '', x: 0, y: 0, width: 100, height: 100 },
        expect.objectContaining({
          id: 'generated-id',
          x: 120,
          y: 240,
          width: 640,
          height: 480,
        }),
      ]),
    )
    expect(result).toHaveLength(2)
    expect(result[0]).toMatchObject({
      id: 'generated-id',
      type: 'image',
      x: 120,
      y: 240,
      width: 640,
      height: 480,
      z_index: 1,
      asset_origin: 'ai_generated',
      source_asset_id: 1,
    })
    expect(result[1]).toMatchObject({
      id: 'generated-id',
      type: 'video',
      x: 360,
      y: 480,
      width: 1920,
      height: 1080,
      z_index: 2,
      asset_origin: 'local_upload',
      source_asset_id: 2,
    })
  })
})
