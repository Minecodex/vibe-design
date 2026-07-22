import { describe, expect, test } from 'vitest'

import type { ModelOption } from '@/api/endpoints/providers'

import { formatProviderPricingItems } from './pricingFormatter'

const translations: Record<string, string> = {
  'providers.pricingFlat': '{{price}} / call',
  'providers.pricingPerSecond': '{{resolution}}: {{price}} / sec',
  'providers.pricingPerResolution': '{{resolution}}: {{price}} / call',
  'providers.pricingInputPerMillionTokens': 'Input: {{price}} / 1M tokens',
  'providers.pricingOutputPerMillionTokens': 'Output: {{price}} / 1M tokens',
}

const t = (key: string, options?: Record<string, unknown>) => {
  const template = translations[key] ?? key
  if (!options) {
    return template
  }
  return Object.entries(options).reduce(
    (result, [name, value]) => result.replace(`{{${name}}}`, String(value)),
    template
  )
}

describe('formatProviderPricingItems', () => {
  test('formats per-resolution image pricing as per-call pricing by resolution', () => {
    const config: ModelOption['config'] = {
      pricing_mode: 'per_resolution',
      pricing_cents: {
        '1K': 5,
        '2K': 9,
      },
    }

    expect(formatProviderPricingItems(config, t)).toEqual([
      { label: '1K: ¥0.05 / call' },
      { label: '2K: ¥0.09 / call' },
    ])
  })

  test('formats flat pricing as per-call pricing', () => {
    const config: ModelOption['config'] = {
      pricing_mode: 'flat',
      pricing_cents: {
        flat: 28,
      },
    }

    expect(formatProviderPricingItems(config, t)).toEqual([{ label: '¥0.28 / call' }])
  })

  test('formats per-second pricing with the resolution label', () => {
    const config: ModelOption['config'] = {
      pricing_mode: 'per_second',
      pricing_cents: {
        '720p': 26,
      },
    }

    expect(formatProviderPricingItems(config, t)).toEqual([{ label: '720p: ¥0.26 / sec' }])
  })

  test('hides zero pricing so post-paid provider models do not show a pricing plan', () => {
    const config: ModelOption['config'] = {
      pricing_mode: 'per_token',
      pricing_cents: {
        input: 0,
        output: 0,
      },
    }

    expect(formatProviderPricingItems(config, t)).toBeNull()
  })
})
