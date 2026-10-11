import { describe, expect, it } from 'vitest'
import {
  createTextCanvasItem,
  DEFAULT_TEXT_FONT_FAMILY,
  getFontVariantCss,
  getVariantForFontFamily,
  normalizeTextCanvasItem,
} from './textTypography'

describe('persisted canvas text typography', () => {
  it.each([undefined, null, ''])('normalizes omitted variant %s to a renderable regular style', variant => {
    expect(getVariantForFontFamily(DEFAULT_TEXT_FONT_FAMILY, variant)).toBe('Regular')
    expect(getFontVariantCss(DEFAULT_TEXT_FONT_FAMILY, variant)).toEqual({ fontWeight: 400, fontStyle: 'normal' })
  })

  it('renders a minimal persisted text item and a newly created item without optional font fields', () => {
    const item = normalizeTextCanvasItem({ id: 'text', type: 'text', url: '', x: 0, y: 0, text: 'persisted' })
    expect(item.fontVariant).toBe('Regular')
    expect(createTextCanvasItem({ id: 'new', x: 0, y: 0 }).fontVariant).toBe('Regular')
  })

  it('keeps supported variants and rejects unsupported family/variant combinations', () => {
    expect(getVariantForFontFamily(DEFAULT_TEXT_FONT_FAMILY, 'Bold')).toBe('Bold')
    expect(getVariantForFontFamily(DEFAULT_TEXT_FONT_FAMILY, 'invalid')).toBe('Regular')
  })
})
