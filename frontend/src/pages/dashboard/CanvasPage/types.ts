import type { ReactNode } from 'react'
import type { BrushPoint } from '@/api/endpoints/projects'
import type { CropRect } from './cropUtils'

export interface ToolItem {
  key: string
  label: string
  svgPath: ReactNode
}

export interface CropPanelState {
  itemId: string
  sourceWidth: number
  sourceHeight: number
  x: number
  y: number
  width: number
  height: number
  presetId: string | null
  isApplying: boolean
}

export type CropHandle = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right' | 'move'

export interface CropDragState {
  handle: CropHandle
  startClientX: number
  startClientY: number
  startRect: CropRect
}

export interface CanvasContextMenuState {
  x: number
  y: number
  type?: 'item' | 'canvas'
}

export type ActiveDropdownType = 'model' | 'res' | 'video_res' | 'duration' | 'ratio' | 'frame_start' | 'frame_end'

export interface ActiveDropdownState {
  itemId: string
  type: ActiveDropdownType
}

export interface LayerDropTarget {
  id: string
  position: 'before' | 'after' | 'inside'
}

export type MediaResizeHandle = 'nw' | 'ne' | 'sw' | 'se'

export interface MediaResizeState {
  itemId: string
  handle: MediaResizeHandle
  startRect: {
    x: number
    y: number
    width: number
    height: number
  }
}

export interface BrushResizeState {
  itemId: string
  handle: MediaResizeHandle
  startRect: {
    x: number
    y: number
    width: number
    height: number
  }
}

export type ImageEraseMode = 'brush' | 'rect'

export interface ImageEraseSnapshot {
  maskDataUrl: string | null
}

export interface ImageEraseSession {
  tool: 'erase' | 'cutout'
  itemId: string
  imageUrl: string
  displayWidth: number
  displayHeight: number
  sourceWidth: number
  sourceHeight: number
  mode: ImageEraseMode
  brushSize: number
  history: ImageEraseSnapshot[]
  future: ImageEraseSnapshot[]
  isSubmitting: boolean
  hasMask: boolean
}

export interface SpatialAngleSession {
  itemId: string
  imageUrl: string
  x: number
  y: number
  scale: 'close-up' | 'normal' | 'wide-angle'
  isSubmitting: boolean
}

export interface BrushDraftState {
  points: BrushPoint[]
  brushColor: string
  brushSize: number
}

export interface BrushToolState {
  color: string
  size: number
  activePanel: 'color' | null
}

export interface BrushToolbarState {
  activePanel: 'color' | null
}
