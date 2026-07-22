import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  buildAnchoredVideoInputs,
  findNearbyVideoTaskPosition,
  isHoverOnlyFailedVideoTask,
} from './imageAnchoredVideo'

describe('imageAnchoredVideo', () => {
  it('includes the locked source image in effective references by default', () => {
    const result = buildAnchoredVideoInputs({
      sourceImageUrl: 'https://example.com/source.png',
      sourcePlacement: 'reference',
      referenceImages: ['https://example.com/other.png'],
      firstFrameImage: '',
      tailFrameImage: '',
    })

    expect(result.referenceImages).toEqual([
      'https://example.com/source.png',
      'https://example.com/other.png',
    ])
    expect(result.firstFrameImage).toBe('')
    expect(result.tailFrameImage).toBe('')
  })

  it('moves the locked source image into first frame mode', () => {
    const result = buildAnchoredVideoInputs({
      sourceImageUrl: 'https://example.com/source.png',
      sourcePlacement: 'first_frame',
      referenceImages: ['https://example.com/other.png'],
      firstFrameImage: '',
      tailFrameImage: '',
    })

    expect(result.referenceImages).toEqual(['https://example.com/other.png'])
    expect(result.firstFrameImage).toBe('https://example.com/source.png')
    expect(result.tailFrameImage).toBe('')
  })

  it('moves the locked source image into tail frame mode', () => {
    const result = buildAnchoredVideoInputs({
      sourceImageUrl: 'https://example.com/source.png',
      sourcePlacement: 'tail_frame',
      referenceImages: ['https://example.com/other.png'],
      firstFrameImage: '',
      tailFrameImage: '',
    })

    expect(result.referenceImages).toEqual(['https://example.com/other.png'])
    expect(result.firstFrameImage).toBe('')
    expect(result.tailFrameImage).toBe('https://example.com/source.png')
  })

  it('finds the first non-overlapping nearby slot in priority order', () => {
    const sourceItem: CanvasItem = {
      id: 'image-1',
      type: 'image',
      url: 'https://example.com/source.png',
      x: 100,
      y: 100,
      width: 400,
      height: 300,
    }

    const items: CanvasItem[] = [
      sourceItem,
      {
        id: 'block-right',
        type: 'video',
        url: 'https://example.com/right.mp4',
        x: 524,
        y: 90,
        width: 500,
        height: 320,
      },
    ]

    const result = findNearbyVideoTaskPosition({
      sourceItem,
      canvasItems: items,
      taskSize: { width: 480, height: 270 },
      gap: 24,
    })

    expect(result).toEqual({ x: 60, y: 424 })
  })

  it('marks only failed image-action video generators as hover-only failures', () => {
    expect(isHoverOnlyFailedVideoTask({
      type: 'video_generator',
      status: 'failed',
      generator_origin: 'image_action',
    })).toBe(true)

    expect(isHoverOnlyFailedVideoTask({
      type: 'video_generator',
      status: 'generating',
      generator_origin: 'image_action',
    })).toBe(false)

    expect(isHoverOnlyFailedVideoTask({
      type: 'video_generator',
      status: 'failed',
      generator_origin: 'standalone',
    })).toBe(false)
  })
})
