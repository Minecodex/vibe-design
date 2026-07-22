import type { TFunction } from 'i18next'

const SUBAGENT_PURPOSE_LABELS: Record<string, {
  key: string
  defaultValue: string
}> = {
  qualityReview: {
    key: 'subagent.purposeLabels.qualityReview',
    defaultValue: 'Quality review',
  },
}

function translateLabel(t: TFunction, key: string, defaultValue: string): string {
  const translated = t(key, { defaultValue })
  return typeof translated === 'string' ? translated : defaultValue
}

function normalizeLabel(value: string): string {
  return value.trim().replace(/\s+/g, ' ').toLowerCase()
}

export function getLocalizedSubagentPurpose(
  t: TFunction,
  purpose: string,
  subagentType?: unknown,
): string {
  const normalizedPurpose = purpose.trim()
  const normalizedType = String(subagentType || '').trim().toLowerCase()
  const label = normalizedType === 'qualityreview' || normalizeLabel(normalizedPurpose) === 'quality review'
    ? SUBAGENT_PURPOSE_LABELS.qualityReview
    : undefined

  if (label) {
    return translateLabel(t, label.key, label.defaultValue)
  }

  return normalizedPurpose
}
