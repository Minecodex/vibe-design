import { describe, expect, it } from 'vitest'

import {
  CANVAS_SELECTION_STROKE_COLOR,
  getCanvasSelectionBorder,
  getCanvasSelectionContainerOverflow,
  getCanvasSelectionHandleAppearance,
} from './selectionStyles'

describe('selectionStyles', () => {
  it('uses the same stroke source for the selection box and corner handles', () => {
    const outlineBorder = getCanvasSelectionBorder(1.5)
    const handleAppearance = getCanvasSelectionHandleAppearance({
      borderWidth: 1.5,
      isDark: false,
    })

    expect(outlineBorder).toBe(`1.5px solid ${CANVAS_SELECTION_STROKE_COLOR}`)
    expect(handleAppearance.border).toBe(outlineBorder)
    expect(handleAppearance.borderColor).toBe(CANVAS_SELECTION_STROKE_COLOR)
  })

  it('uses the app token for handle fills', () => {
    expect(
      getCanvasSelectionHandleAppearance({ borderWidth: 2, isDark: false }).backgroundColor,
    ).toBe('var(--app-primary-foreground)')
    expect(
      getCanvasSelectionHandleAppearance({ borderWidth: 2, isDark: true }).backgroundColor,
    ).toBe('var(--app-primary-foreground)')
  })

  it('does not clip selection handles that extend outside the media frame', () => {
    expect(getCanvasSelectionContainerOverflow(true)).toBe('visible')
    expect(getCanvasSelectionContainerOverflow(false)).toBe('hidden')
  })
})
