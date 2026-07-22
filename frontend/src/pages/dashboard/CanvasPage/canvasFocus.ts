interface CanvasFocusItem {
  x: number
  y: number
  width?: number
  height?: number
}

export function getCenteredCanvasOffset({
  item,
  fallbackSize = { width: 0, height: 0 },
  viewport,
  zoom,
}: {
  item: CanvasFocusItem
  fallbackSize?: { width: number; height: number }
  viewport: { width: number; height: number }
  zoom: number
}) {
  const itemWidth = item.width ?? fallbackSize.width
  const itemHeight = item.height ?? fallbackSize.height
  const scale = zoom / 100
  const centerX = item.x + itemWidth / 2
  const centerY = item.y + itemHeight / 2

  return {
    x: viewport.width / 2 - centerX * scale,
    y: viewport.height / 2 - centerY * scale,
  }
}
