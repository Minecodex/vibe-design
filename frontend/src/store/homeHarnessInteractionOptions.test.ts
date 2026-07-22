import { describe, expect, it } from 'vitest'

import {
  buildHomepageInteractionOptions,
  isCustomInteractionOption,
  normalizeInteractionOptions,
} from './homeHarnessInteractionOptions'

describe('normalizeInteractionOptions', () => {
  it('converts string options into interaction option objects', () => {
    expect(normalizeInteractionOptions(['方案一', '方案二'])).toEqual([
      { label: '方案一', value: '方案一', description: undefined, preview_url: undefined },
      { label: '方案二', value: '方案二', description: undefined, preview_url: undefined },
    ])
  })

  it('appends a fixed custom other option and ignores backend-marked custom other variants', () => {
    const options = normalizeInteractionOptions(
      ['方向一', { label: '其他（请补充说明）', value: '__server_other__', option_type: 'custom_other' }],
      { includeCustomOther: true },
    )

    expect(options.map((option) => option.label)).toEqual(['方向一', '其他'])
    expect(isCustomInteractionOption(options[1]!)).toBe(true)
  })

  it('uses regular interaction options for homepage interactions', () => {
    const options = buildHomepageInteractionOptions(['方案一'])

    expect(options.map((option) => option.label)).toEqual(['方案一', '其他'])
    expect(isCustomInteractionOption(options[1]!)).toBe(true)
    expect(options[1]?.option_type).toBe('custom_other')
  })
})
