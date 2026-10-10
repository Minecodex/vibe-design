

const ECOMMERCE_GENERATION_OPTIONS_KIND = 'ecommerce_generation_options'
export const ECOMMERCE_INTERACTION_KINDS = new Set([
  ECOMMERCE_GENERATION_OPTIONS_KIND,
])

export function isEcommerceInteractionKind(kind?: string | null): boolean {
  return ECOMMERCE_INTERACTION_KINDS.has(String(kind || '').trim())
}
