import { describe, expect, test } from 'vitest'
import type { CanvasItem } from '@/api/endpoints/projects'

import {
  applyGeneratorAssetsToAnchoredImageDraft,
  applyGeneratorAssetsToAnchoredVideoDraft,
  applyGeneratorAssetsToCanvasItem,
} from './generatorAssetLibrary'

describe('generatorAssetLibrary', () => {
  test('applies reference images to a canvas video item and clears frames on conflict', () => {
    const item: Partial<CanvasItem> = {
      id: 'video-1',
      type: 'video_generator',
      reference_images: ['https://example.com/existing.png'],
      first_frame_image: 'https://example.com/first.png',
      tail_frame_image: 'https://example.com/tail.png',
    }

    const result = applyGeneratorAssetsToCanvasItem({
      item,
      target: 'reference',
      assets: [
        { id: 1, url: 'https://example.com/a.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
        { id: 2, url: 'https://example.com/b.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
      ],
      maxSelection: 2,
      imageModesConflict: true,
    })

    expect(result.reference_images).toEqual([
      'https://example.com/existing.png',
      'https://example.com/a.png',
    ])
    expect(result.reference_image).toBe('https://example.com/existing.png')
    expect(result.first_frame_image).toBe('')
    expect(result.tail_frame_image).toBe('')
  })

  test('applies a frame image to a canvas video item and clears references on conflict', () => {
    const result = applyGeneratorAssetsToCanvasItem({
      item: {
        id: 'video-1',
        type: 'video_generator',
        reference_images: ['https://example.com/ref.png'],
        reference_image: 'https://example.com/ref.png',
        first_frame_image: '',
        tail_frame_image: '',
      },
      target: 'first_frame',
      assets: [
        { id: 1, url: 'https://example.com/frame.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
      ],
      maxSelection: 1,
      imageModesConflict: true,
    })

    expect(result.first_frame_image).toBe('https://example.com/frame.png')
    expect(result.reference_images).toEqual([])
    expect(result.reference_image).toBe('')
  })

  test('appends anchored image references up to the allowed limit', () => {
    const result = applyGeneratorAssetsToAnchoredImageDraft({
      draft: {
        reference_images: ['https://example.com/existing.png'],
      },
      assets: [
        { id: 1, url: 'https://example.com/a.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
        { id: 2, url: 'https://example.com/b.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
      ],
      maxSelection: 2,
    })

    expect(result.reference_images).toEqual([
      'https://example.com/existing.png',
      'https://example.com/a.png',
    ])
  })

  test('does not override the anchored source placement when targeting the same frame slot', () => {
    const originalDraft = {
      sourcePlacement: 'first_frame' as const,
      reference_images: [],
      first_frame_image: '',
      tail_frame_image: '',
    }

    const result = applyGeneratorAssetsToAnchoredVideoDraft({
      draft: originalDraft,
      target: 'first_frame',
      assets: [
        { id: 1, url: 'https://example.com/frame.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
      ],
      maxSelection: 1,
      imageModesConflict: false,
    })

    expect(result).toBe(originalDraft)
  })

  test('refuses to add a tail frame asset when tail frame is currently disallowed', () => {
    const item: Partial<CanvasItem> = {
      id: 'video-1',
      type: 'video_generator',
      reference_images: [],
      first_frame_image: '',
      tail_frame_image: '',
    }

    expect(applyGeneratorAssetsToCanvasItem({
      item,
      target: 'tail_frame',
      assets: [
        { id: 1, url: 'https://example.com/tail.png', type: 'image', origin_kind: 'local_upload', source_asset_id: null },
      ],
      maxSelection: 1,
      imageModesConflict: false,
      allowTailFrame: false,
    })).toBe(item)
  })
})
