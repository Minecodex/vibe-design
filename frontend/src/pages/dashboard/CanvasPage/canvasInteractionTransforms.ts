import type { CanvasItem } from '@/api/endpoints/projects'

import type { ItemBounds } from './alignmentGuides'
import { resizeBrushPathBoundsFromCorner } from './brushPaths'
import { applyDraggedCanvasItemsPreview } from './dragMove'
import { resizeMediaSelectionFromCorner } from './mediaSelectionResize'

type ItemDimensions = {
  width: number
  height: number
}

type GroupResizeHandle = string | null | undefined

export function applyBrushResizePreview(args: {
  items: CanvasItem[]
  itemId: string
  handle: 'nw' | 'ne' | 'sw' | 'se'
  startRect: { x: number; y: number; width: number; height: number }
  deltaX: number
  deltaY: number
}) {
  return args.items.map((item) => {
    if (item.id !== args.itemId) return item
    const nextRect = resizeBrushPathBoundsFromCorner({
      handle: args.handle,
      startRect: args.startRect,
      deltaX: args.deltaX,
      deltaY: args.deltaY,
    })
    return {
      ...item,
      ...nextRect,
      pathBounds: item.pathBounds
        ? {
          ...item.pathBounds,
          ...nextRect,
        }
        : item.pathBounds,
    }
  })
}

export function applyMediaResizePreview(args: {
  items: CanvasItem[]
  itemId: string
  handle: 'nw' | 'ne' | 'sw' | 'se'
  startRect: { x: number; y: number; width: number; height: number }
  deltaX: number
  deltaY: number
}) {
  return args.items.map((item) => {
    if (item.id !== args.itemId) return item
    return {
      ...item,
      ...resizeMediaSelectionFromCorner({
        handle: args.handle,
        startRect: args.startRect,
        deltaX: args.deltaX,
        deltaY: args.deltaY,
      }),
      media_display_size_source: 'user' as const,
    }
  })
}

export function applyGroupResizePreview(args: {
  items: CanvasItem[]
  groupId: string
  handle: GroupResizeHandle
  start: { w: number; h: number; top: number; left: number }
  deltaX: number
  deltaY: number
}) {
  return args.items.map((item) => {
    if (item.id !== args.groupId) return item
    const next = { ...item }
    if (args.handle?.includes('e')) next.width = Math.max(50, args.start.w + args.deltaX)
    if (args.handle?.includes('w')) {
      const newW = Math.max(50, args.start.w - args.deltaX)
      if (newW > 50) {
        next.x = args.start.left + args.deltaX
        next.width = newW
      }
    }
    if (args.handle?.includes('s')) next.height = Math.max(50, args.start.h + args.deltaY)
    if (args.handle?.includes('n')) {
      const newH = Math.max(50, args.start.h - args.deltaY)
      if (newH > 50) {
        next.y = args.start.top + args.deltaY
        next.height = newH
      }
    }
    return next
  })
}

export function applyDragPreview(args: {
  items: CanvasItem[]
  draggedItemId: string
  deltaX: number
  deltaY: number
  originals: Record<string, { x: number; y: number }>
  selectedItems: string[]
  movingItemIds: Set<string>
  groupHitCandidates: CanvasItem[]
  getItemDims: (item: CanvasItem) => ItemDimensions
}): {
  items: CanvasItem[]
  draggedBounds: ItemBounds | null
} {
  return applyDraggedCanvasItemsPreview(args)
}
