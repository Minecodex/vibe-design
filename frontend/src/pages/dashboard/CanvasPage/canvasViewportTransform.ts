type CanvasOffset = {
  x: number
  y: number
}

export function getCanvasViewportTransform(offset: CanvasOffset, zoom: number) {
  return `translate(-50%, -50%) translate(${offset.x}px, ${offset.y}px) scale(${zoom / 100})`
}

export function applyCanvasViewportTransform(
  element: HTMLElement | null | undefined,
  offset: CanvasOffset,
  zoom: number,
) {
  if (!element) return
  element.style.transform = getCanvasViewportTransform(offset, zoom)
}
