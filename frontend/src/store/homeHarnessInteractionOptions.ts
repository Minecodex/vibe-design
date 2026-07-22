import type { InteractionOption } from '@/api/endpoints/agent'

export interface NormalizedInteractionOption extends InteractionOption {
  isCustom?: boolean
}

const CUSTOM_OTHER_VALUE = '__custom_other__'

function normalizeOptionLabel(value: unknown): string {
  return String(value || '').trim()
}

export function normalizeInteractionOptions(
  options: unknown,
  { includeCustomOther = false }: { includeCustomOther?: boolean } = {},
): NormalizedInteractionOption[] {
  if (!Array.isArray(options)) {
    return includeCustomOther
      ? [{ label: '其他', value: CUSTOM_OTHER_VALUE, isCustom: true }]
      : []
  }

  const normalized: NormalizedInteractionOption[] = []
  const seen = new Set<string>()

  for (const option of options) {
    const label = normalizeOptionLabel(
      typeof option === 'string' ? option : option?.label ?? option?.value,
    )
    const value = normalizeOptionLabel(
      typeof option === 'string' ? option : option?.value ?? option?.label,
    )
    const optionType = typeof option === 'object' && option
      ? normalizeOptionLabel((option as Record<string, unknown>).option_type ?? (option as Record<string, unknown>).optionType)
      : ''
    const isCustomOther = typeof option === 'object' && option
      ? (option as Record<string, unknown>).is_custom_other === true || (option as Record<string, unknown>).isCustomOther === true
      : false

    if (!label || !value) {
      continue
    }
    if (isCustomOther || optionType === 'custom_other') {
      continue
    }

    const key = `${label}::${value}`
    if (seen.has(key)) {
      continue
    }
    seen.add(key)

    normalized.push({
      label,
      value,
      description: typeof option === 'object' && option && 'description' in option
        ? normalizeOptionLabel((option as Record<string, unknown>).description)
        : undefined,
      preview_url: typeof option === 'object' && option && 'preview_url' in option
        ? normalizeOptionLabel((option as Record<string, unknown>).preview_url)
        : undefined,
      option_type: optionType || undefined,
      is_custom_other: isCustomOther || undefined,
    })
  }

  if (includeCustomOther) {
    normalized.push({
      label: '其他',
      value: CUSTOM_OTHER_VALUE,
      isCustom: true,
      option_type: 'custom_other',
      is_custom_other: true,
    })
  }

  return normalized
}

export function isCustomInteractionOption(option: Pick<NormalizedInteractionOption, 'isCustom' | 'value'>): boolean {
  return option.isCustom === true || String(option.value || '') === CUSTOM_OTHER_VALUE
}

export function buildHomepageInteractionOptions(options: unknown): NormalizedInteractionOption[] {
  return normalizeInteractionOptions(options, { includeCustomOther: true })
}
