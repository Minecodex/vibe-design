type ClampArgs = {
  value: number
  min: number
  max: number
}

function clamp({ value, min, max }: ClampArgs) {
  if (max < min) return min
  return Math.min(Math.max(value, min), max)
}

type ViewportMenuPositionArgs = {
  anchorX: number
  anchorY: number
  panelWidth: number
  panelHeight: number
  viewportWidth: number
  viewportHeight: number
  margin?: number
}

export function getViewportMenuPosition({
  anchorX,
  anchorY,
  panelWidth,
  panelHeight,
  viewportWidth,
  viewportHeight,
  margin = 12,
}: ViewportMenuPositionArgs) {
  return {
    left: clamp({
      value: anchorX,
      min: margin,
      max: viewportWidth - panelWidth - margin,
    }),
    top: clamp({
      value: anchorY,
      min: margin,
      max: viewportHeight - panelHeight - margin,
    }),
  }
}

type ViewportSidePanelPositionArgs = {
  anchorLeft: number
  anchorTop: number
  anchorWidth: number
  panelWidth: number
  panelHeight: number
  viewportWidth: number
  viewportHeight: number
  gap?: number
  margin?: number
}

export function getViewportSidePanelPosition({
  anchorLeft,
  anchorTop,
  anchorWidth,
  panelWidth,
  panelHeight,
  viewportWidth,
  viewportHeight,
  gap = 20,
  margin = 16,
}: ViewportSidePanelPositionArgs) {
  const rightLeft = anchorLeft + anchorWidth + gap
  const leftLeft = anchorLeft - panelWidth - gap
  const fitsRight = rightLeft + panelWidth <= viewportWidth - margin
  const fitsLeft = leftLeft >= margin

  let left = rightLeft
  let side: 'right' | 'left' = 'right'

  if (!fitsRight && fitsLeft) {
    left = leftLeft
    side = 'left'
  }

  left = clamp({
    value: left,
    min: margin,
    max: viewportWidth - panelWidth - margin,
  })

  const top = clamp({
    value: anchorTop,
    min: margin,
    max: viewportHeight - panelHeight - margin,
  })

  return { left, top, side }
}
