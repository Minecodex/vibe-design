import { describe, expect, it } from 'vitest'

import {
  DEFAULT_TEXT_FONT_FAMILY,
  DEFAULT_TEXT_FONT_SIZE,
  createTextCanvasItem,
  getSupportedFontVariants,
  getVariantForFontFamily,
  textFontRegistry,
} from './textTypography'

describe('canvas text item defaults', () => {
  it('creates a text canvas item with the expected default styling', () => {
    const item = createTextCanvasItem({
      id: 'text-1',
      x: 120,
      y: 240,
    })

    expect(item).toMatchObject({
      id: 'text-1',
      type: 'text',
      x: 120,
      y: 240,
      text: '输入文字',
      fontFamily: DEFAULT_TEXT_FONT_FAMILY,
      fontVariant: 'Regular',
      fontSize: DEFAULT_TEXT_FONT_SIZE,
      fillColor: '#111111',
      strokeColor: 'transparent',
      strokeWidth: 0,
      textAlign: 'left',
      lineHeight: 1.2,
      letterSpacing: 0,
      underline: false,
      strikeThrough: false,
      listStyle: 'none',
      textTransform: 'none',
      writingMode: 'horizontal',
    })

    expect(item.width).toBeGreaterThan(0)
    expect(item.height).toBeGreaterThan(0)
  })
})

describe('text font registry', () => {
  it('exposes locally hosted open-source font families with declared variants', () => {
    expect(textFontRegistry.length).toBeGreaterThanOrEqual(7)
    expect(textFontRegistry.every((font) => font.sources.length > 0)).toBe(true)
    expect(textFontRegistry.every((font) => font.variants.length > 0)).toBe(true)
  })

  it('returns only the variants supported by the selected font family', () => {
    expect(getSupportedFontVariants('Instrument Sans')).toEqual([
      'Regular',
      'Medium',
      'SemiBold',
      'Bold',
      'Italic',
    ])
    expect(getSupportedFontVariants('Cormorant Garamond')).toEqual([
      'Regular',
      'Medium',
      'SemiBold',
      'Bold',
      'Italic',
    ])
  })

  it('falls back to Regular when a selected variant is not supported by the next font', () => {
    expect(getVariantForFontFamily('Cormorant Garamond', 'SemiBold')).toBe('SemiBold')
    expect(getVariantForFontFamily('Space Grotesk', 'Italic')).toBe('Regular')
    expect(getVariantForFontFamily('Nonexistent Font', 'Bold')).toBe('Regular')
  })
})
