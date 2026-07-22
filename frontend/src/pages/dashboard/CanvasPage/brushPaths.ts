import type { BrushPathBounds, BrushPoint, CanvasItem } from '@/api/endpoints/projects'

type BrushPathSize = {
  width: number
  height: number
}

type BrushResizeHandle = 'nw' | 'ne' | 'sw' | 'se'

type CreateBrushPathCanvasItemArgs = {
  id: string
  points: BrushPoint[]
  brushColor: string
  brushSize: number
  zIndex: number
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function distanceBetween(a: BrushPoint, b: BrushPoint) {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

export function smoothBrushPoints(points: BrushPoint[]) {
  if (points.length <= 2) return points

  const deduped = points.filter((point, index) => {
    if (index === 0) return true
    return distanceBetween(point, points[index - 1]) >= 1.5
  })

  return deduped
}

export function getBrushPathBounds(points: BrushPoint[], brushSize: number): BrushPathBounds {
  const safeBrushSize = Math.max(1, brushSize)
  const halfBrush = safeBrushSize / 2
  const xs = points.map((point) => point.x)
  const ys = points.map((point) => point.y)
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const maxX = Math.max(...xs)
  const maxY = Math.max(...ys)

  return {
    x: Math.round(minX - halfBrush),
    y: Math.round(minY - halfBrush),
    width: Math.max(safeBrushSize, Math.round(maxX - minX + safeBrushSize)),
    height: Math.max(safeBrushSize, Math.round(maxY - minY + safeBrushSize)),
  }
}

export function normalizeBrushPoints(points: BrushPoint[], bounds: BrushPathBounds): BrushPoint[] {
  return points.map((point) => ({
    x: bounds.width <= 0 ? 0.5 : clamp((point.x - bounds.x) / bounds.width, 0, 1),
    y: bounds.height <= 0 ? 0.5 : clamp((point.y - bounds.y) / bounds.height, 0, 1),
  }))
}

export function scaleBrushPathPoint(point: BrushPoint, size: BrushPathSize): BrushPoint {
  return {
    x: Number((point.x * size.width).toFixed(2)),
    y: Number((point.y * size.height).toFixed(2)),
  }
}

export function resizeBrushPathBoundsFromCorner(args: {
  handle: BrushResizeHandle
  startRect: { x: number; y: number; width: number; height: number }
  deltaX: number
  deltaY: number
  minSize?: number
}) {
  const { handle, startRect, deltaX, deltaY } = args
  const minSize = Math.max(args.minSize ?? 12, 1)

  let nextX = startRect.x
  let nextY = startRect.y
  let nextWidth = startRect.width
  let nextHeight = startRect.height

  if (handle.includes('w')) {
    nextX = startRect.x + deltaX
    nextWidth = startRect.width - deltaX
    if (nextWidth < minSize) {
      nextX = startRect.x + (startRect.width - minSize)
      nextWidth = minSize
    }
  } else {
    nextWidth = Math.max(minSize, startRect.width + deltaX)
  }

  if (handle.includes('n')) {
    nextY = startRect.y + deltaY
    nextHeight = startRect.height - deltaY
    if (nextHeight < minSize) {
      nextY = startRect.y + (startRect.height - minSize)
      nextHeight = minSize
    }
  } else {
    nextHeight = Math.max(minSize, startRect.height + deltaY)
  }

  return {
    x: Math.round(nextX),
    y: Math.round(nextY),
    width: Math.round(nextWidth),
    height: Math.round(nextHeight),
  }
}

export function buildBrushPathSvgPath(points: BrushPoint[], size: BrushPathSize) {
  if (points.length === 0) return ''

  const scaledPoints = points.map((point) => scaleBrushPathPoint(point, size))
  if (scaledPoints.length === 1) {
    const point = scaledPoints[0]
    return `M ${point.x} ${point.y} L ${point.x} ${point.y}`
  }

  return scaledPoints
    .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x} ${point.y}`)
    .join(' ')
}

export function createBrushPathCanvasItem({
  id,
  points,
  brushColor,
  brushSize,
  zIndex,
}: CreateBrushPathCanvasItemArgs): CanvasItem {
  const sampledPoints = smoothBrushPoints(points)
  const bounds = getBrushPathBounds(sampledPoints, brushSize)

  return {
    id,
    type: 'brush_path',
    url: '',
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    z_index: zIndex,
    brushColor,
    brushSize,
    pathBounds: bounds,
    points: normalizeBrushPoints(sampledPoints, bounds),
  }
}
