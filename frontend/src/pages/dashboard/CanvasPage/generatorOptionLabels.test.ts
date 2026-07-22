import { describe, expect, it } from 'vitest'

import {
  formatAspectRatioOptionLabel,
  formatAspectRatioOptionLabelWithDimensions,
  formatDimensionLabel,
  formatResolutionOptionLabel,
} from './generatorOptionLabels'

describe('generatorOptionLabels', () => {
  const zhLabels = {
    square: '方形',
    landscape: '横向',
    portrait: '竖向',
  }

  it('formats media dimensions with a readable multiply sign', () => {
    expect(formatDimensionLabel(1920, 1080)).toBe('1920 × 1080')
  })

  it('adds the standard suffix to the 1K image resolution option', () => {
    expect(formatResolutionOptionLabel('1K', '标准')).toBe('1K（标准）')
    expect(formatResolutionOptionLabel('2K', '标准')).toBe('2K')
  })

  it('adds localized hints for common aspect ratios', () => {
    expect(formatAspectRatioOptionLabel('1:1', zhLabels)).toBe('1:1（方形）')
    expect(formatAspectRatioOptionLabel('16:9', zhLabels)).toBe('16:9（横向）')
    expect(formatAspectRatioOptionLabel('9:16', zhLabels)).toBe('9:16（竖向）')
  })

  it('leaves unsupported aspect ratios unchanged', () => {
    expect(formatAspectRatioOptionLabel('4:3', zhLabels)).toBe('4:3')
  })

  it('appends dimensions to aspect ratio option labels', () => {
    expect(
      formatAspectRatioOptionLabelWithDimensions('21:9', zhLabels, { width: 1568, height: 672 })
    ).toBe('21:9（横向） 1568 × 672')
  })
})
