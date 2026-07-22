import type { CanvasItem } from '@/api/endpoints/projects'
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
  taskWidth: number,
  taskHeight: number,
  gap: number,
) {
  const sourceWidth = sourceItem.width || 0
  const sourceHeight = sourceItem.height || 0

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

export function createHDUpscaleTaskItem({
  sourceItem,
  canvasItems,
  taskId,
  width,
  height,
  gap = DEFAULT_GAP,
}: {
  sourceItem: CanvasItem
  canvasItems: CanvasItem[]
  taskId: string
  width: number
  height: number
  gap?: number
}): CanvasItem {
  const placement = findNearbyPlacement(sourceItem, canvasItems, width, height, gap)

  return {
    id: taskId,
    type: 'image_generator',
    generation_kind: 'image_hd_upscale',
    generator_origin: 'image_action',
    url: '',
    name: `hd-upscale-${sourceItem.name || sourceItem.id}`,
    x: placement.x,
    y: placement.y,
    width: width,
    height: height,
    z_index: clampCanvasStackZIndex((sourceItem.z_index || 0) + 1),
    status: 'generating',
    prompt: '',
    asset_origin: 'ai_generated',
  }
}
