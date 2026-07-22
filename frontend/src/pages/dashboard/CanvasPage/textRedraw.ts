import type { TextRedrawSegment } from '@/api/endpoints/generation'
import type { CanvasItem } from '@/api/endpoints/projects'

import { getCenteredGeneratedResultFrame, type GeneratedImageSize } from './generatedResultSizing'
import { clampCanvasStackZIndex } from './imageActions'
import { TEXT_REDRAW_PANEL_TOKENS } from './textRedrawUi'

const DEFAULT_GAP = 24

export interface EditableTextRedrawSegment extends TextRedrawSegment {
  originalText: string
}

function overlaps(
  left: number,
  top: number,
  width: number,
  height: number,
  item: CanvasItem,
) {
  const itemWidth = item.width || 0
  const itemHeight = item.height || 0

  return !(
    left + width <= item.x ||
    item.x + itemWidth <= left ||
    top + height <= item.y ||
    item.y + itemHeight <= top
  )
}

function findNearbyPlacement(
  sourceItem: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>,
  canvasItems: CanvasItem[],
  gap: number,
) {
  const sourceWidth = sourceItem.width || 0
  const sourceHeight = sourceItem.height || 0
  const taskWidth = sourceWidth
  const taskHeight = sourceHeight

  const candidates = [
    { x: sourceItem.x + sourceWidth + gap, y: sourceItem.y },
    { x: sourceItem.x, y: sourceItem.y + sourceHeight + gap },
    { x: sourceItem.x - taskWidth - gap, y: sourceItem.y },
    { x: sourceItem.x, y: sourceItem.y - taskHeight - gap },
  ]

  return candidates.find((candidate) => (
    !canvasItems.some((item) => overlaps(candidate.x, candidate.y, taskWidth, taskHeight, item))
  )) || candidates[0]
}

export function createEditableTextRedrawSegments(segments: TextRedrawSegment[]): EditableTextRedrawSegment[] {
  return [...segments]
    .sort((a, b) => a.order - b.order)
    .map((segment) => ({
      ...segment,
      originalText: segment.text,
    }))
}

export function createTextRedrawTaskItem({
  sourceItem,
  canvasItems,
  taskId,
  gap = DEFAULT_GAP,
}: {
  sourceItem: CanvasItem
  canvasItems: CanvasItem[]
  taskId: string
  gap?: number
}): CanvasItem {
  const placement = findNearbyPlacement(sourceItem, canvasItems, gap)

  return {
    id: taskId,
    type: 'image_generator',
    generation_kind: 'text_redraw',
    generator_origin: 'image_action',
    url: '',
    name: `text-redraw-${sourceItem.name || sourceItem.id}`,
    x: placement.x,
    y: placement.y,
    width: sourceItem.width,
    height: sourceItem.height,
    z_index: clampCanvasStackZIndex((sourceItem.z_index || 0) + 1),
    status: 'generating',
    prompt: '',
    asset_origin: 'ai_generated',
  }
}

export function buildTextRedrawResultItem({
  taskItem,
  resultUrl,
  resultSize,
}: {
  taskItem: CanvasItem
  resultUrl: string
  resultSize?: GeneratedImageSize | null
}): CanvasItem {
  const frame = getCenteredGeneratedResultFrame(taskItem, resultSize)

  return {
    ...taskItem,
    type: 'image',
    status: 'completed',
    url: resultUrl,
    x: frame.x,
    y: frame.y,
    width: frame.width,
    height: frame.height,
    progress: 100,
    error_message: null,
    asset_origin: 'ai_generated',
  }
}

export function getTextRedrawPanelPosition({
  item,
  zoom,
  offset,
  viewport,
}: {
  item: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>
  zoom: number
  offset: { x: number; y: number }
  viewport: { width: number; height: number }
}) {
  const scaledWidth = (item.width || 0) * zoom / 100
  const scaledX = offset.x + item.x * zoom / 100
  const scaledY = offset.y + item.y * zoom / 100

  const unclampedLeft = scaledX + scaledWidth + TEXT_REDRAW_PANEL_TOKENS.panelGap
  const maxLeft = viewport.width - TEXT_REDRAW_PANEL_TOKENS.panelWidth - TEXT_REDRAW_PANEL_TOKENS.panelMargin
  const maxTop = viewport.height - TEXT_REDRAW_PANEL_TOKENS.panelHeight - TEXT_REDRAW_PANEL_TOKENS.panelMargin

  return {
    left: Math.max(TEXT_REDRAW_PANEL_TOKENS.panelMargin, Math.min(unclampedLeft, maxLeft)),
    top: Math.max(TEXT_REDRAW_PANEL_TOKENS.panelMargin, Math.min(scaledY, maxTop)),
    width: TEXT_REDRAW_PANEL_TOKENS.panelWidth,
    height: TEXT_REDRAW_PANEL_TOKENS.panelHeight,
  }
}
