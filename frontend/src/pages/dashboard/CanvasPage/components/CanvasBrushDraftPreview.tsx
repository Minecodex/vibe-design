import type { BrushPoint } from '@/api/endpoints/projects'

import { CanvasBrushItem } from './CanvasBrushItem'
import {
  getBrushPathBounds,
  normalizeBrushPoints,
} from '../brushPaths'

export function CanvasBrushDraftPreview({
  points,
  brushColor,
  brushSize,
}: {
  points: BrushPoint[]
  brushColor: string
  brushSize: number
}) {
  const bounds = getBrushPathBounds(points, brushSize)
  const normalizedPoints = normalizeBrushPoints(points, bounds)

  return (
    <div
      data-testid="brush-draft-preview-box"
      style={{
        position: 'absolute',
        left: bounds.x,
        top: bounds.y,
        width: bounds.width,
        height: bounds.height,
      }}
    >
      <CanvasBrushItem
        item={{
          id: 'brush-draft-preview',
          type: 'brush_path',
          url: '',
          x: bounds.x,
          y: bounds.y,
          width: bounds.width,
          height: bounds.height,
          brushColor,
          brushSize,
          points: normalizedPoints,
        }}
      />
    </div>
  )
}
