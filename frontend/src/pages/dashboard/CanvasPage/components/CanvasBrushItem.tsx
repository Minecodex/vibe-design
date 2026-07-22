import type { CanvasItem } from '@/api/endpoints/projects'

import { buildBrushPathSvgPath } from '../brushPaths'

export function CanvasBrushItem({
  item,
}: {
  item: CanvasItem
}) {
  const width = item.width || 1
  const height = item.height || 1
  const points = item.points || []
  const path = buildBrushPathSvgPath(item.points || [], { width, height })
  const singlePoint = points.length === 1
    ? {
      x: Number((points[0].x * width).toFixed(2)),
      y: Number((points[0].y * height).toFixed(2)),
    }
    : null

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ display: 'block', overflow: 'visible' }}
      aria-label={item.name || item.id}
    >
      {singlePoint && (
        <circle
          cx={singlePoint.x}
          cy={singlePoint.y}
          r={Math.max((item.brushSize || 1) / 2, 1)}
          fill={item.brushColor || '#111111'}
        />
      )}
      <path
        d={path}
        fill="none"
        stroke={item.brushColor || '#111111'}
        strokeWidth={item.brushSize || 1}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
