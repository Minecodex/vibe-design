import type { TFunction } from 'i18next'
import type { HomeHarnessCritiqueState } from '@/store/homeHarnessCritiqueProjection'

const TERMINAL_STATUSES = new Set(['shipped', 'below_threshold', 'degraded', 'failed', 'completed'])

// The backend "arms" the critique at the very start of a turn (rendering_context),
// emitting critique.started with status="running", round 0 and no scores — before
// any artifact exists. Only treat the critique as worth showing once a real round
// has been evaluated (round >= 1 or scores present) or it has reached a terminal
// state. This keeps the empty "armed" placeholder hidden until quality check
// actually begins.
export function isCritiqueVisible(critique: HomeHarnessCritiqueState | null): critique is HomeHarnessCritiqueState {
  if (!critique) return false
  if (TERMINAL_STATUSES.has(critique.status)) return true
  return critique.round >= 1 || Object.keys(critique.scores).length > 0
}
const DIMENSION_KEY_ALIASES: Record<string, string> = {
  'clarity-of-value-proposition': 'value-proposition-clarity',
}

export function normalizeDesignJuryDimensionKey(name: string): string {
  return String(name || '')
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
}

export function resolveDesignJuryDimensionLabel(name: string, t: TFunction): string {
  const rawName = String(name || '').trim()
  const slug = normalizeDesignJuryDimensionKey(rawName)
  const alias = slug ? t(`home.chat.design_jury.dimension_aliases.${slug}`, '') : ''
  const canonicalKey = String(alias || DIMENSION_KEY_ALIASES[slug] || slug || rawName).trim()
  const canonicalLabel = canonicalKey
    ? t(`home.chat.design_jury.dimensions.${canonicalKey}`, '')
    : ''
  if (canonicalLabel) {
    return canonicalLabel
  }
  const rawLabel = rawName ? t(`home.chat.design_jury.dimensions.${rawName}`, '') : ''
  return rawLabel || rawName
}

