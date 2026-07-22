export interface BrandConfig {
  appName: string
  appNameEn: string
}

export function getLocalizedAppName(language: string, brand: BrandConfig): string {
  return language.startsWith('zh') ? brand.appName : brand.appNameEn
}

export function resolveLocalizedProviderName(
  language: string,
  brand: BrandConfig,
  providerCode: string,
  providerName: string,
): string {
  if (providerCode === 'builtin') {
    return getLocalizedAppName(language, brand)
  }

  return providerName
}
