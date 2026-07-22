import { describe, expect, it } from 'vitest'

import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'
import { buildCanvasMentionReferences } from './canvasMessageReferences'

function imageItem(overrides: Partial<CanvasItem>): CanvasItem {
  return {
    id: 'img-1',
    type: 'image',
    url: '/api/v1/uploads/canvas/88/source.png',
    name: 'Grapes',
    x: 0,
    y: 0,
    asset_origin: 'local_upload',
    ...overrides,
  }
}

describe('buildCanvasMentionReferences', () => {
  it('builds deduped canvas item references for local upload image mentions', () => {
    const references = buildCanvasMentionReferences(
      'Use @[Grapes](canvas:img-1) and again @[Grapes duplicate](canvas:img-1).',
      [imageItem({ id: 'img-1' })],
    )

    expect(references).toEqual([
      {
        id: 'canvas:img-1',
        kind: 'canvas_item',
        media_type: 'image',
        display_name: 'Grapes',
        source: {
          type: 'canvas_item',
          item_id: 'img-1',
        },
      },
    ])
  })

  it('builds canvas item references for generated images with artifact refs', () => {
    const references = buildCanvasMentionReferences('Create a variant of @[Generated image](canvas:generated-1).', [
      imageItem({
        id: 'generated-1',
        type: 'image_generator',
        name: 'Generated image',
        asset_origin: 'ai_generated',
        url: '/api/v1/uploads/canvas/88/generated-preview.png',
        artifact_ref: 'artifact_ref:generated-image-1',
      }),
    ])

    expect(references).toEqual([
      {
        id: 'canvas:generated-1',
        kind: 'canvas_item',
        media_type: 'image',
        display_name: 'Generated image',
        source: {
          type: 'canvas_item',
          item_id: 'generated-1',
        },
      },
    ])
  })

  it('builds canvas mark references from mark chips', () => {
    const references = buildCanvasMentionReferences(
      'Retouch #[grape](canvas-mark:mark-1:image:img-1:x:0.42:y:0.61) on the image.',
      [imageItem({ id: 'img-1' })],
      [
        {
          id: 'mark-1',
          imageItemId: 'img-1',
          imageUrl: '/api/v1/uploads/canvas/88/source.png',
          relativeX: 0.42,
          relativeY: 0.61,
          number: 2,
          aiLabels: ['grape'],
          selectedLabel: 'grape',
          customLabel: null,
          isAnalyzing: false,
        } satisfies CanvasMark,
      ],
    )

    expect(references).toEqual([
      {
        id: 'canvas-mark:mark-1',
        kind: 'canvas_mark',
        media_type: 'image',
        display_name: 'grape',
        source: {
          type: 'canvas_mark',
          mark_id: 'mark-1',
          image_item_id: 'img-1',
        },
        mark: {
          id: 'mark-1',
          image_item_id: 'img-1',
          number: 2,
          label: 'grape',
          position: { x: 0.42, y: 0.61 },
        },
      },
    ])
  })

  it('omits references when a chip is removed from the final content', () => {
    const references = buildCanvasMentionReferences('Use this image after editing.', [
      imageItem({ id: 'img-1' }),
    ])

    expect(references).toBeNull()
  })

  it('ignores generated items without artifact refs, non-image, and unknown canvas item mentions', () => {
    const references = buildCanvasMentionReferences(
      '@[Generated](canvas:generated-missing-ref) @[Video](canvas:video) @[Missing](canvas:missing)',
      [
        imageItem({
          id: 'generated-missing-ref',
          asset_origin: 'ai_generated',
          url: '/api/v1/uploads/canvas/88/generated.png',
        }),
        imageItem({
          id: 'video',
          type: 'video',
          asset_origin: 'local_upload',
          url: '/api/v1/uploads/canvas/88/video.mp4',
        }),
      ],
    )

    expect(references).toBeNull()
  })
})
