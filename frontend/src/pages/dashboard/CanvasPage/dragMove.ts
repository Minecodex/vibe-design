import type { CanvasItem } from '@/api/endpoints/projects'

import type { ItemBounds } from './alignmentGuides'

type ItemDimensions = {
  width: number
  height: number
}

type DragOriginalPosition = {
  x: number
  y: number
}

type ApplyDraggedCanvasItemsPreviewArgs = {
  items: CanvasItem[]
  draggedItemId: string
  deltaX: number
  deltaY: number
  originals: Record<string, DragOriginalPosition>
  selectedItems: string[]
  movingItemIds: Set<string>
  groupHitCandidates: CanvasItem[]
  getItemDims: (item: CanvasItem) => ItemDimensions
}

const GROUP_ATTACHABLE_ITEM_TYPES = new Set<CanvasItem['type']>([
  'image',
  'video',
  'image_generator',
  'video_generator',
  'text',
])

export function applyDraggedCanvasItemsPreview({
  items,
  draggedItemId,
  deltaX,
  deltaY,
  originals,
  selectedItems,
  movingItemIds,
  groupHitCandidates,
  getItemDims,
}: ApplyDraggedCanvasItemsPreviewArgs) {
  let draggedItemIndex = -1
  let combinedBounds: ItemBounds | null = null

  const nextItems = items.map((item, index) => {
    const original = originals[item.id]
    const nextItem = original
      ? { ...item, x: original.x + deltaX, y: original.y + deltaY }
      : item

    if (original) {
      const dims = getItemDims(nextItem)
      const width = nextItem.width || dims.width
      const height = nextItem.height || dims.height
      const nextBounds: ItemBounds = {
        left: nextItem.x,
        right: nextItem.x + width,
        top: nextItem.y,
        bottom: nextItem.y + height,
        centerX: nextItem.x + width / 2,
        centerY: nextItem.y + height / 2,
      }

      if (!combinedBounds) {
        combinedBounds = nextBounds
      } else {
        combinedBounds = {
          left: Math.min(combinedBounds.left, nextBounds.left),
          right: Math.max(combinedBounds.right, nextBounds.right),
          top: Math.min(combinedBounds.top, nextBounds.top),
          bottom: Math.max(combinedBounds.bottom, nextBounds.bottom),
          centerX: 0,
          centerY: 0,
        }
      }
    }

    if (nextItem.id === draggedItemId) {
      draggedItemIndex = index
    }

    return nextItem
  })

  const draggedItem = draggedItemIndex >= 0
    ? nextItems[draggedItemIndex] as CanvasItem
    : null

  if (
    !draggedItem
    || draggedItem.type === 'group'
    || selectedItems.length !== 1
    || !GROUP_ATTACHABLE_ITEM_TYPES.has(draggedItem.type)
  ) {
    return { items: nextItems, draggedBounds: finalizeCombinedBounds(combinedBounds) }
  }

  const dims = getItemDims(draggedItem)
  const centerX = draggedItem.x + (draggedItem.width || dims.width) / 2
  const centerY = draggedItem.y + (draggedItem.height || dims.height) / 2

  let containingGroupId: string | undefined
  for (const group of groupHitCandidates) {
    if (movingItemIds.has(group.id)) continue
    const groupWidth = group.width || 0
    const groupHeight = group.height || 0
    if (
      centerX >= group.x
      && centerX <= group.x + groupWidth
      && centerY >= group.y
      && centerY <= group.y + groupHeight
    ) {
      containingGroupId = group.id
      break
    }
  }

  if (draggedItem.groupId !== containingGroupId && draggedItemIndex >= 0) {
    nextItems[draggedItemIndex] = {
      ...draggedItem,
      groupId: containingGroupId,
    }
  }

  return { items: nextItems, draggedBounds: finalizeCombinedBounds(combinedBounds) }
}

function finalizeCombinedBounds(combinedBounds: ItemBounds | null) {
  if (!combinedBounds) return null

  return {
    left: combinedBounds.left,
    right: combinedBounds.right,
    top: combinedBounds.top,
    bottom: combinedBounds.bottom,
    centerX: combinedBounds.left + (combinedBounds.right - combinedBounds.left) / 2,
    centerY: combinedBounds.top + (combinedBounds.bottom - combinedBounds.top) / 2,
  }
}
