import { describe, expect, it } from 'vitest'

import {
  applyCanvasViewportTransform,
  getCanvasViewportTransform,
} from './canvasViewportTransform'

describe('canvasViewportTransform', () => {
  it('formats the shared canvas content transform from offset and zoom', () => {
    expect(getCanvasViewportTransform({ x: 48, y: -32 }, 125)).toBe(
      'translate(-50%, -50%) translate(48px, -32px) scale(1.25)',
    )
  })

  it('writes the shared transform to a canvas content element', () => {
    const element = document.createElement('div')

    applyCanvasViewportTransform(element, { x: -16, y: 24 }, 80)

    expect(element.style.transform).toBe(
      'translate(-50%, -50%) translate(-16px, 24px) scale(0.8)',
    )
  })
})
