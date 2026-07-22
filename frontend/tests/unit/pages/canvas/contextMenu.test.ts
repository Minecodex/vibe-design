import { describe, expect, it } from 'vitest'

import { buildCanvasSelectionMenuItems } from '@/pages/dashboard/CanvasPage/contextMenu'

describe('buildCanvasSelectionMenuItems', () => {
  it('does not include save-to-asset-library in the canvas selection menu', () => {
    const items = buildCanvasSelectionMenuItems({
      firstSelectedItemType: 'image',
      selectedItemIds: ['item-1'],
      allSelectedItemsAreMediaWithUrl: true,
      selectionCanMerge: false,
      currentSelectionHasImage: true,
    })

    expect(items.some((item) => item.key === 'save_to_asset_library')).toBe(false)
  })

  it('inserts restore below paste for a single media asset with a source url', () => {
    const items = buildCanvasSelectionMenuItems({
      firstSelectedItemType: 'image',
      selectedItemIds: ['item-1'],
      allSelectedItemsAreMediaWithUrl: true,
      selectionCanMerge: false,
      currentSelectionHasImage: true,
    })

    const keys = items.map((item) => item.key ?? item.type)
    expect(keys.slice(0, 4)).toEqual(['copy', 'paste', 'restore', 'divider'])
  })

  it('does not include restore for multi-selection', () => {
    const items = buildCanvasSelectionMenuItems({
      firstSelectedItemType: 'image',
      selectedItemIds: ['item-1', 'item-2'],
      allSelectedItemsAreMediaWithUrl: true,
      selectionCanMerge: true,
      currentSelectionHasImage: true,
    })

    expect(items.some((item) => item.key === 'restore')).toBe(false)
  })
})
