import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { applyDraggedCanvasItemsPreview } from './dragMove'

function createItem(overrides: Partial<CanvasItem> = {}): CanvasItem {
  return {
    id: overrides.id || 'item-1',
    type: overrides.type || 'image',
    url: overrides.url || '',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 100,
    height: overrides.height ?? 80,
    z_index: overrides.z_index ?? 0,
    ...overrides,
  }
}

describe('applyDraggedCanvasItemsPreview', () => {
  it('moves dragged items from their original coordinates and updates dragged item group membership without remapping the whole list again', () => {
    const items = [
      createItem({ id: 'dragged', type: 'image', x: 10, y: 20, width: 120, height: 90 }),
      createItem({ id: 'group-a', type: 'group', x: 200, y: 200, width: 300, height: 240 }),
      createItem({ id: 'untouched', type: 'text', x: 700, y: 700, width: 160, height: 60 }),
    ]

    const result = applyDraggedCanvasItemsPreview({
      items,
      draggedItemId: 'dragged',
      deltaX: 250,
      deltaY: 240,
      originals: {
        dragged: { x: 10, y: 20 },
      },
      selectedItems: ['dragged'],
      movingItemIds: new Set(['dragged']),
      groupHitCandidates: [items[1]],
      getItemDims: (item) => ({
        width: item.width || 1,
        height: item.height || 1,
      }),
    })

    expect(result.items[0]).toMatchObject({
      id: 'dragged',
      x: 260,
      y: 260,
      groupId: 'group-a',
    })
    expect(result.draggedBounds).toEqual({
      left: 260,
      right: 380,
      top: 260,
      bottom: 350,
      centerX: 320,
      centerY: 305,
    })
    expect(result.items[1]).toBe(items[1])
    expect(result.items[2]).toBe(items[2])
  })

  it('clears an existing group assignment when the dragged item no longer overlaps any stationary group', () => {
    const items = [
      createItem({ id: 'dragged', type: 'image', x: 220, y: 220, width: 120, height: 90, groupId: 'group-a' }),
      createItem({ id: 'group-a', type: 'group', x: 200, y: 200, width: 300, height: 240 }),
    ]

    const result = applyDraggedCanvasItemsPreview({
      items,
      draggedItemId: 'dragged',
      deltaX: 400,
      deltaY: 0,
      originals: {
        dragged: { x: 220, y: 220 },
      },
      selectedItems: ['dragged'],
      movingItemIds: new Set(['dragged']),
      groupHitCandidates: [items[1]],
      getItemDims: (item) => ({
        width: item.width || 1,
        height: item.height || 1,
      }),
    })

    expect(result.items[0]).toMatchObject({
      id: 'dragged',
      x: 620,
      y: 220,
      groupId: undefined,
    })
  })

  it('tracks a combined dragged bounds box while multiple selected items move together', () => {
    const items = [
      createItem({ id: 'dragged', type: 'image', x: 10, y: 20, width: 100, height: 80 }),
      createItem({ id: 'child', type: 'text', x: 220, y: 170, width: 140, height: 60 }),
      createItem({ id: 'group-a', type: 'group', x: 600, y: 600, width: 300, height: 200 }),
    ]

    const result = applyDraggedCanvasItemsPreview({
      items,
      draggedItemId: 'dragged',
      deltaX: 40,
      deltaY: 30,
      originals: {
        dragged: { x: 10, y: 20 },
        child: { x: 220, y: 170 },
      },
      selectedItems: ['dragged', 'child'],
      movingItemIds: new Set(['dragged', 'child']),
      groupHitCandidates: [items[2]],
      getItemDims: (item) => ({
        width: item.width || 1,
        height: item.height || 1,
      }),
    })

    expect(result.draggedBounds).toEqual({
      left: 50,
      right: 400,
      top: 50,
      bottom: 260,
      centerX: 225,
      centerY: 155,
    })
  })
})
