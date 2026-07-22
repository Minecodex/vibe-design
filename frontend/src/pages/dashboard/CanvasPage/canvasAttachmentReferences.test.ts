import { describe, expect, it } from 'vitest'

import {
  buildCanvasAssetAttachmentReference,
  buildCanvasAttachmentReferences,
  mergeCanvasMessageReferences,
} from './canvasAttachmentReferences'

describe('canvasAttachmentReferences', () => {
  it('builds upload references for harness input images', () => {
    expect(buildCanvasAttachmentReferences([
      {
        type: 'image',
        url: 'references/inputs/upload_001/source.jpeg',
        name: 'source.jpeg',
      },
    ])).toEqual([
      {
        id: 'upload:references/inputs/upload_001/source.jpeg',
        kind: 'upload_attachment',
        media_type: 'image',
        display_name: 'source.jpeg',
        source: {
          type: 'harness_input',
          path: 'references/inputs/upload_001/source.jpeg',
        },
      },
    ])
  })

  it('uses explicit references only when they match the attachment url', () => {
    expect(buildCanvasAttachmentReferences([
      {
        type: 'image',
        url: 'references/generated/generated_image_001/original.png',
        name: 'fallback.png',
        reference: {
          id: 'workspace-file:references/generated/generated_image_001/original.png',
          kind: 'workspace_file',
          media_type: 'image',
          display_name: 'explicit.png',
          source: {
            type: 'workspace_file',
            path: 'references/generated/generated_image_001/original.png',
          },
        },
      },
    ])).toEqual([
      {
        id: 'workspace-file:references/generated/generated_image_001/original.png',
        kind: 'workspace_file',
        media_type: 'image',
        display_name: 'explicit.png',
        source: {
          type: 'workspace_file',
          path: 'references/generated/generated_image_001/original.png',
        },
      },
    ])
  })

  it('builds asset-library references for canvas upload urls', () => {
    expect(buildCanvasAssetAttachmentReference({
      url: '/api/v1/uploads/canvas/3/shirt.jpeg',
      name: 'shirt.jpeg',
    })).toEqual({
      id: 'home-asset:/api/v1/uploads/canvas/3/shirt.jpeg',
      kind: 'home_asset',
      media_type: 'image',
      display_name: 'shirt.jpeg',
      source: {
        type: 'home_asset',
        url: '/api/v1/uploads/canvas/3/shirt.jpeg',
      },
    })
  })

  it('merges reference groups by id', () => {
    const first = {
      id: 'upload:references/inputs/upload_001/source.jpeg',
      kind: 'upload_attachment' as const,
      media_type: 'image' as const,
      display_name: 'source.jpeg',
      source: {
        type: 'harness_input' as const,
        path: 'references/inputs/upload_001/source.jpeg',
      },
    }
    const second = {
      id: 'home-asset:/api/v1/uploads/canvas/3/shirt.jpeg',
      kind: 'home_asset' as const,
      media_type: 'image' as const,
      display_name: 'shirt.jpeg',
      source: {
        type: 'home_asset' as const,
        url: '/api/v1/uploads/canvas/3/shirt.jpeg',
      },
    }

    expect(mergeCanvasMessageReferences([first], [first, second])).toEqual([first, second])
  })
})
