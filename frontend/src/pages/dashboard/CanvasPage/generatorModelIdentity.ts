export type GeneratorModelOptionIdentity = {
  model_name?: string
  provider?: string
  provider_code?: string
  value?: string
}

export function getGeneratorModelOptionName(option: GeneratorModelOptionIdentity): string {
  return option.value || option.model_name || ''
}

export function getGeneratorModelOptionProvider(option: GeneratorModelOptionIdentity): string {
  return option.provider || option.provider_code || ''
}

export function getGeneratorModelOptionKey(
  option: GeneratorModelOptionIdentity,
  fallbackIndex?: number,
): string {
  const provider = getGeneratorModelOptionProvider(option) || 'unknown'
  const modelName = getGeneratorModelOptionName(option) || `model-${fallbackIndex ?? 0}`
  return `${provider}:${modelName}`
}

export function isGeneratorModelOptionSelected(
  option: GeneratorModelOptionIdentity,
  modelName?: string,
  providerCode?: string,
): boolean {
  if (!modelName) return false
  if (getGeneratorModelOptionName(option) !== modelName) return false
  if (!providerCode) return true
  return getGeneratorModelOptionProvider(option) === providerCode
}
