import { describe, expect, it } from 'vitest'

import { extractCanvasRevisionMetaFromEvent } from './canvasAgentBlockNormalize'

describe('canvasAgentBlockNormalize canvas revision meta', () => {
  it('extracts canvas revision metadata from nested presentation media blocks', () => {
    const meta = extractCanvasRevisionMetaFromEvent({
      type: 'presentation.block.complete',
      sequence: 11,
      data: {
        block: {
          payload: {
            status: 'failed',
            result: {
              canvas_revision: 54,
              canvas_item_deleted: true,
            },
          },
        },
      },
    })

    expect(meta).toEqual({ canvasRevision: 54, canvasItemDeleted: true })
  })

  it('ignores invalid canvas revision metadata', () => {
    const meta = extractCanvasRevisionMetaFromEvent({
      type: 'generation_failed',
      data: {
        result: {
          canvas_revision: -1,
          canvas_item_deleted: true,
        },
      },
    })

    expect(meta).toBeNull()
  })

  it('falls through invalid earlier revisions and extracts top-level payload revisions', () => {
    const meta = extractCanvasRevisionMetaFromEvent({
      type: 'presentation.block.patch',
      data: {
        canvas_revision: -1,
      },
      payload: {
        block: {
          payload: {
            canvas_revision: 55,
            canvas_item_deleted: false,
          },
        },
      },
    })

    expect(meta).toEqual({ canvasRevision: 55, canvasItemDeleted: false })
  })
})
