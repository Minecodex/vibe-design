import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  applyBrushResizePreview,
  applyDragPreview,
  applyGroupResizePreview,
  applyMediaResizePreview,
} from './canvasInteractionTransforms'

function item(overrides: Partial<CanvasItem>): CanvasItem {
  return {
    id: overrides.id || 'item',
    type: overrides.type || 'image',
    url: overrides.url ?? '/image.png',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 100,
    height: overrides.height ?? 80,
    z_index: overrides.z_index ?? 0,
    ...overrides,
  }
}

describe('canvas interaction transforms', () => {
  it('computes drag previews without mutating the original item array', () => {
    const source = [
      item({ id: 'a', x: 10, y: 20 }),
      item({ id: 'b', x: 200, y: 200 }),
    ]

    const result = applyDragPreview({
      items: source,
      draggedItemId: 'a',
      deltaX: 15,
      deltaY: -5,
      originals: { a: { x: 10, y: 20 } },
      selectedItems: ['a'],
      movingItemIds: new Set(['a']),
      groupHitCandidates: [],
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(result.items.find((nextItem) => nextItem.id === 'a')).toMatchObject({ x: 25, y: 15 })
    expect(source.find((sourceItem) => sourceItem.id === 'a')).toMatchObject({ x: 10, y: 20 })
  })

  it('computes media, brush, and group resize previews through the shared helpers', () => {
    const source = [
      item({ id: 'media', width: 100, height: 50 }),
      item({
        id: 'brush',
        type: 'brush_path',
        width: 80,
        height: 40,
        pathBounds: { x: 0, y: 0, width: 80, height: 40 },
      }),
      item({ id: 'group', type: 'group', width: 200, height: 100 }),
    ]

    const media = applyMediaResizePreview({
      items: source,
      itemId: 'media',
      handle: 'se',
      startRect: { x: 0, y: 0, width: 100, height: 50 },
      deltaX: 50,
      deltaY: 0,
    }).find((nextItem) => nextItem.id === 'media')
    expect(media).toMatchObject({ width: 150, height: 75, media_display_size_source: 'user' })

    const brush = applyBrushResizePreview({
      items: source,
      itemId: 'brush',
      handle: 'se',
      startRect: { x: 0, y: 0, width: 80, height: 40 },
      deltaX: 20,
      deltaY: 10,
    }).find((nextItem) => nextItem.id === 'brush')
    expect(brush).toMatchObject({ width: 100, height: 50, pathBounds: { width: 100, height: 50 } })

    const group = applyGroupResizePreview({
      items: source,
      groupId: 'group',
      handle: 'se',
      start: { w: 200, h: 100, top: 0, left: 0 },
      deltaX: 30,
      deltaY: 40,
    }).find((nextItem) => nextItem.id === 'group')
    expect(group).toMatchObject({ width: 230, height: 140 })
  })
})
