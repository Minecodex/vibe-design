import type { CanvasItem } from '@/api/endpoints/projects'

import { getCenteredGeneratedResultFrame, type GeneratedImageSize } from './generatedResultSizing'
import { clampCanvasStackZIndex } from './imageActions'

const DEFAULT_GAP = 24

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

export function createImageEraseTaskItem({
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
    generation_kind: 'image_erase',
    generator_origin: 'image_action',
    url: '',
    name: `image-erase-${sourceItem.name || sourceItem.id}`,
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

export function buildImageEraseResultItem({
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
    generation_kind: 'image_erase',
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
