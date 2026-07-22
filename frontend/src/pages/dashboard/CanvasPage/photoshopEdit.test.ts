import { describe, expect, it } from 'vitest'

import { buildPhotoshopEditPayload, canPhotoshopEditSelection } from './photoshopEdit'

describe('photoshopEdit helpers', () => {
  it('allows photoshop edit for a single selected image', () => {
    expect(canPhotoshopEditSelection(['image-1'], 'image')).toBe(true)
  })

  it('rejects photoshop edit for multi-selection or non-image types', () => {
    expect(canPhotoshopEditSelection(['image-1', 'image-2'], 'image')).toBe(false)
    expect(canPhotoshopEditSelection(['video-1'], 'video')).toBe(false)
  })

  it('builds the create-job payload from the selected canvas item', () => {
    expect(buildPhotoshopEditPayload({ id: 'image-1', url: '/api/v1/uploads/canvas/1/source.svg' })).toEqual({
      source_canvas_item_id: 'image-1',
      svg_url: '/api/v1/uploads/canvas/1/source.svg',
    })
  })
})
