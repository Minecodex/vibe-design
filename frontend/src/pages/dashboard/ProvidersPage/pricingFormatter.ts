import type { ModelOption } from '@/api/endpoints/providers'
import { formatCnyFromCents } from '@/utils/money'

type PricingLabel = { label: string }

type TranslateFn = (key: string, options?: Record<string, unknown>) => string

export function formatProviderPricingItems(
  config: ModelOption['config'] | undefined,
  t: TranslateFn
): PricingLabel[] | null {
  if (!config?.pricing_cents || !config?.pricing_mode) {
    return null
  }

  const { pricing_cents, pricing_mode } = config
  const entries = Object.entries(pricing_cents)
  if (entries.length === 0 || entries.every(([, value]) => Number(value || 0) <= 0)) {
    return null
  }

  if (pricing_mode === 'flat') {
    const cost = entries[0]?.[1] ?? 0
    return [
      {
        label: t('providers.pricingFlat', {
          price: formatCnyFromCents(cost),
        }),
      },
    ]
  }

  if (pricing_mode === 'per_second') {
    return entries.map(([resolution, rate]) => ({
      label: t('providers.pricingPerSecond', {
        resolution,
        price: formatCnyFromCents(rate),
      }),
    }))
  }

  if (pricing_mode === 'per_token') {
    const input = pricing_cents.input ?? 0
    const output = pricing_cents.output ?? 0

    return [
      {
        label: t('providers.pricingInputPerMillionTokens', {
          price: formatCnyFromCents(input),
        }),
      },
      {
        label: t('providers.pricingOutputPerMillionTokens', {
          price: formatCnyFromCents(output),
        }),
      },
    ]
  }

  return entries.map(([resolution, cost]) => ({
    label: t('providers.pricingPerResolution', {
      resolution,
      price: formatCnyFromCents(cost),
    }),
  }))
}
