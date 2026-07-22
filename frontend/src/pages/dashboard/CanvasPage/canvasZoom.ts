export const MIN_CANVAS_ZOOM = 2
export const MAX_CANVAS_ZOOM = 500
export const CANVAS_WHEEL_ZOOM_SENSITIVITY = 6

export function clampCanvasZoom(zoom: number) {
  return Math.min(Math.max(zoom, MIN_CANVAS_ZOOM), MAX_CANVAS_ZOOM)
}

export function getCanvasWheelZoomUpdate(args: {
  oldZoom: number
  oldOffset: { x: number; y: number }
  client: { x: number; y: number }
  viewportRect: { left: number; top: number; width: number; height: number }
  deltaY: number
  deltaMode: number
}) {
  const { oldZoom, oldOffset, client, viewportRect, deltaY, deltaMode } = args
  const step = deltaMode === 1 ? deltaY : deltaY / 100
  const newZoom = clampCanvasZoom(oldZoom - step * CANVAS_WHEEL_ZOOM_SENSITIVITY)

  if (newZoom === oldZoom) {
    return null
  }

  const mx = client.x - (viewportRect.left + viewportRect.width / 2)
  const my = client.y - (viewportRect.top + viewportRect.height / 2)
  const ratio = newZoom / oldZoom

  return {
    newZoom,
    newOffset: {
      x: mx - (mx - oldOffset.x) * ratio,
      y: my - (my - oldOffset.y) * ratio,
    },
  }
}
