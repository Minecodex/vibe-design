export const CANVAS_SELECTION_STROKE_COLOR = 'var(--app-primary)'
export const CANVAS_SELECTION_HANDLE_FILL = 'var(--app-primary-foreground)'

export function getCanvasSelectionBorder(borderWidth: number) {
  return `${borderWidth}px solid ${CANVAS_SELECTION_STROKE_COLOR}`
}

export function getCanvasSelectionHandleAppearance(args: {
  borderWidth: number
  isDark: boolean
  fillColor?: string
}) {
  const { borderWidth, fillColor } = args

  return {
    backgroundColor: fillColor ?? CANVAS_SELECTION_HANDLE_FILL,
    borderColor: CANVAS_SELECTION_STROKE_COLOR,
    border: getCanvasSelectionBorder(borderWidth),
  }
}

export function getCanvasSelectionContainerOverflow(hasExternalHandles: boolean) {
  return hasExternalHandles ? 'visible' : 'hidden'
}
