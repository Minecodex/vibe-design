import type { CanvasItem } from '@/api/endpoints/projects'

import { clampCanvasStackZIndex } from './imageActions'

const DEFAULT_GAP = 24

export function getOpaqueBoundsFromAlphaChannel(
  rgba: Uint8ClampedArray,
  width: number,
  height: number,
): { left: number, top: number, width: number, height: number } | null {
  let minX = width
  let minY = height
  let maxX = -1
  let maxY = -1

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = rgba[(y * width + x) * 4 + 3]
      if (alpha <= 0) continue

      minX = Math.min(minX, x)
      minY = Math.min(minY, y)
      maxX = Math.max(maxX, x)
      maxY = Math.max(maxY, y)
    }
  }

  if (maxX < minX || maxY < minY) {
    return null
  }

  return {
    left: minX,
    top: minY,
    width: maxX - minX + 1,
    height: maxY - minY + 1,
  }
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
  resultSize: { width: number, height: number },
  canvasItems: CanvasItem[],
  gap: number,
) {
  const sourceWidth = sourceItem.width || 0
  const sourceHeight = sourceItem.height || 0
  const resultWidth = resultSize.width || 0
  const resultHeight = resultSize.height || 0

  const candidates = [
    { x: sourceItem.x + sourceWidth + gap, y: sourceItem.y },
    { x: sourceItem.x, y: sourceItem.y + sourceHeight + gap },
    { x: sourceItem.x - resultWidth - gap, y: sourceItem.y },
    { x: sourceItem.x, y: sourceItem.y - resultHeight - gap },
  ]

  return candidates.find((candidate) => (
    !canvasItems.some((item) => overlaps(candidate.x, candidate.y, resultWidth, resultHeight, item))
  )) || candidates[0]
}

export function buildCutoutResultItem({
  sourceItem,
  canvasItems,
  resultUrl,
  resultWidth,
  resultHeight,
  gap = DEFAULT_GAP,
}: {
  sourceItem: CanvasItem
  canvasItems: CanvasItem[]
  resultUrl: string
  resultWidth?: number
  resultHeight?: number
  gap?: number
}): CanvasItem {
  const finalWidth = Math.max(1, Math.round(resultWidth || sourceItem.width || 1))
  const finalHeight = Math.max(1, Math.round(resultHeight || sourceItem.height || 1))
  const placement = findNearbyPlacement(sourceItem, { width: finalWidth, height: finalHeight }, canvasItems, gap)

  return {
    id: `cutout-${sourceItem.id}-${Date.now()}`,
    type: 'image',
    url: resultUrl,
    name: `cutout-${sourceItem.name || sourceItem.id}`,
    x: placement.x,
    y: placement.y,
    width: finalWidth,
    height: finalHeight,
    z_index: clampCanvasStackZIndex((sourceItem.z_index || 0) + 1),
    status: 'completed',
    asset_origin: 'local_upload',
  }
}
