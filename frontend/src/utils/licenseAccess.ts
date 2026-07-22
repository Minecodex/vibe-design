import type { LicenseEdition, LicenseStatus } from '@/api/types/auth'

export function isLicenseActive(status: LicenseStatus | null | undefined): boolean {
  return (status ?? 'active') === 'active'
}

export function canAccessHomeAgent(edition: LicenseEdition | null | undefined): boolean {
  return edition !== 'premium'
}

export function canAccessCanvasPlugins(edition: LicenseEdition | null | undefined): boolean {
  return edition === 'flagship'
}
