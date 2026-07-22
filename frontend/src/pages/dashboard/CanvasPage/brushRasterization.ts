import type { CanvasItem } from '@/api/endpoints/projects'

import { scaleBrushPathPoint } from './brushPaths'

export function rasterizeBrushPathToCanvas(
  ctx: CanvasRenderingContext2D,
  item: Pick<CanvasItem, 'points' | 'brushColor' | 'brushSize' | 'width' | 'height'>,
) {
  const points = item.points || []
  if (points.length === 0) return

  ctx.save()
  ctx.beginPath()

  const firstPoint = scaleBrushPathPoint(points[0], {
    width: item.width || 1,
    height: item.height || 1,
  })
  ctx.moveTo(firstPoint.x, firstPoint.y)

  if (points.length === 1) {
    ctx.lineTo(firstPoint.x, firstPoint.y)
  } else {
    points.slice(1).forEach((point) => {
      const scaledPoint = scaleBrushPathPoint(point, {
        width: item.width || 1,
        height: item.height || 1,
      })
      ctx.lineTo(scaledPoint.x, scaledPoint.y)
    })
  }

  ctx.strokeStyle = item.brushColor || '#111111'
  ctx.lineWidth = item.brushSize || 1
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.stroke()
  ctx.restore()
}
