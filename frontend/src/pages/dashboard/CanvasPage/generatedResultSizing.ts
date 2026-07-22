import type { CanvasItem } from '@/api/endpoints/projects'

export interface GeneratedImageSize {
  width: number
  height: number
}

export function getCenteredGeneratedResultFrame(
  taskItem: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>,
  resultSize?: GeneratedImageSize | null,
) {
  const placeholderWidth = taskItem.width ?? resultSize?.width ?? 0
  const placeholderHeight = taskItem.height ?? resultSize?.height ?? 0
  const width = resultSize?.width ?? taskItem.width
  const height = resultSize?.height ?? taskItem.height

  const centerX = taskItem.x + placeholderWidth / 2
  const centerY = taskItem.y + placeholderHeight / 2

  return {
    x: centerX - (width || 0) / 2,
    y: centerY - (height || 0) / 2,
    width,
    height,
  }
}
