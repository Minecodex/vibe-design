import type { CSSProperties, MouseEvent, MutableRefObject } from 'react'
import type { CanvasItem } from '@/api/endpoints/projects'
import type { getCanvasSelectionBorder, getCanvasSelectionHandleAppearance } from '../selectionStyles'

export type CanvasResizeStart = {
  x: number
  y: number
  w: number
  h: number
  top: number
  left: number
}

export interface CanvasSelectionProps {
  canvasItems: CanvasItem[]
  selectedItems: string[]
  activeTool: string
  isDark: boolean
  zoom: number
  offset: { x: number; y: number }
  handleItemMouseDown: (event: MouseEvent<HTMLDivElement>, itemId: string) => void
  setContextMenu: (menu: { x: number; y: number; type: 'item' }) => void
  setActiveContextMenuItem: (id: string | null) => void
  getCanvasSelectionBorder: typeof getCanvasSelectionBorder
  getCanvasSelectionHandleAppearance: (options: Parameters<typeof getCanvasSelectionHandleAppearance>[0]) => CSSProperties
}

export interface CanvasResizeProps {
  beginTransaction: () => void
  setActiveGuides: (guides: []) => void
  movingItemIdsRef: MutableRefObject<Set<string>>
  resizingHandle: MutableRefObject<string | null>
  dragItemStart: MutableRefObject<{ x: number; y: number } | null>
  resizingStart: MutableRefObject<CanvasResizeStart | null>
  interactionPreview?: { begin: (items: CanvasItem[]) => void }
}
