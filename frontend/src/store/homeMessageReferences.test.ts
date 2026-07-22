import { describe, expect, it } from 'vitest'

import { buildHomeMediaReferences } from './homeMessageReferences'

describe('buildHomeMediaReferences', () => {
  it('builds upload references for homepage input image attachments', () => {
    expect(buildHomeMediaReferences([
      {
        type: 'image',
        url: 'references/inputs/upload_001/source.png',
        name: 'source.png',
      },
    ])).toEqual([
      {
        id: 'upload:references/inputs/upload_001/source.png',
        kind: 'upload_attachment',
        media_type: 'image',
        display_name: 'source.png',
        source: {
          type: 'harness_input',
          path: 'references/inputs/upload_001/source.png',
        },
      },
    ])
  })

  it('builds home asset references for selected library images', () => {
    expect(buildHomeMediaReferences([
      {
        type: 'image',
        url: 'https://cdn.example.com/assets/library-image.png',
        name: 'library-image.png',
      },
    ])).toEqual([
      {
        id: 'home-asset:https://cdn.example.com/assets/library-image.png',
        kind: 'home_asset',
        media_type: 'image',
        display_name: 'library-image.png',
        source: {
          type: 'home_asset',
          url: 'https://cdn.example.com/assets/library-image.png',
        },
      },
    ])
  })

  it('uses explicit attachment references when they match the attachment source', () => {
    expect(buildHomeMediaReferences([
      {
        type: 'image',
        url: '/api/v1/uploads/canvas/7/source.png',
        name: 'fallback-name.png',
        reference: {
          id: 'home-asset:/api/v1/uploads/canvas/7/source.png',
          kind: 'home_asset',
          media_type: 'image',
          display_name: 'explicit-canvas-source.png',
          source: {
            type: 'home_asset',
            url: '/api/v1/uploads/canvas/7/source.png',
          },
        },
      },
    ])).toEqual([
      {
        id: 'home-asset:/api/v1/uploads/canvas/7/source.png',
        kind: 'home_asset',
        media_type: 'image',
        display_name: 'explicit-canvas-source.png',
        source: {
          type: 'home_asset',
          url: '/api/v1/uploads/canvas/7/source.png',
        },
      },
    ])
  })

  it('ignores explicit attachment references when they do not match the attachment source', () => {
    expect(buildHomeMediaReferences([
      {
        type: 'image',
        url: '/api/v1/uploads/canvas/7/source.png',
        name: 'canvas-source.png',
        reference: {
          id: 'home-asset:/api/v1/uploads/canvas/8/source.png',
          kind: 'home_asset',
          media_type: 'image',
          display_name: 'wrong-source.png',
          source: {
            type: 'home_asset',
            url: '/api/v1/uploads/canvas/8/source.png',
          },
        },
      },
    ])).toEqual([
      {
        id: 'home-asset:/api/v1/uploads/canvas/7/source.png',
        kind: 'home_asset',
        media_type: 'image',
        display_name: 'canvas-source.png',
        source: {
          type: 'home_asset',
          url: '/api/v1/uploads/canvas/7/source.png',
        },
      },
    ])
  })

  it('builds workspace file references for generated and preview image paths', () => {
    expect(buildHomeMediaReferences([
      {
        type: 'image',
        url: 'references/generated/generated_image_001/original.png',
        name: 'generated.png',
      },
      {
        type: 'image',
        url: 'project/assets/preview.png',
        name: 'preview.png',
      },
    ])).toEqual([
      {
        id: 'workspace-file:references/generated/generated_image_001/original.png',
        kind: 'workspace_file',
        media_type: 'image',
        display_name: 'generated.png',
        source: {
          type: 'workspace_file',
          path: 'references/generated/generated_image_001/original.png',
        },
      },
      {
        id: 'workspace-file:project/assets/preview.png',
        kind: 'workspace_file',
        media_type: 'image',
        display_name: 'preview.png',
        source: {
          type: 'workspace_file',
          path: 'project/assets/preview.png',
        },
      },
    ])
  })

  it('rejects non-image attachments and unsafe workspace paths', () => {
    expect(buildHomeMediaReferences([
      {
        type: 'file',
        url: 'references/inputs/upload_001/brief.pdf',
        name: 'brief.pdf',
      },
      {
        type: 'image',
        url: 'references/generated/../secret.png',
        name: 'secret.png',
      },
    ])).toBeNull()
  })
})
