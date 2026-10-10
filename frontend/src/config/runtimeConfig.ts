export interface AppRuntimeConfig {
  APP_API_BASE_URL: string
}

const DEFAULT_APP_CONFIG: AppRuntimeConfig = {
  APP_API_BASE_URL: 'http://localhost:8000/api/v1',
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

export function normalizeApiBaseUrl(value: string): string {
  const trimmed = trimTrailingSlash(value.trim())
  if (!trimmed) {
    return DEFAULT_APP_CONFIG.APP_API_BASE_URL
  }

  return /\/api\/v1$/i.test(trimmed) ? trimmed : `${trimmed}/api/v1`
}

export function normalizeApiOrigin(value: string): string {
  return normalizeApiBaseUrl(value).replace(/\/api\/v1$/i, '')
}

function getRuntimeConfigSource(): Partial<AppRuntimeConfig> | undefined {
  const envConfig: Partial<AppRuntimeConfig> = {
    APP_API_BASE_URL: import.meta.env.APP_API_BASE_URL,
  }

  if (typeof window === 'undefined') {
    return envConfig
  }

  return { ...envConfig, ...window.__APP_CONFIG__ }
}

export function getAppConfig(): AppRuntimeConfig {
  const runtimeConfig = getRuntimeConfigSource()

  return {
    APP_API_BASE_URL: normalizeApiBaseUrl(runtimeConfig?.APP_API_BASE_URL || DEFAULT_APP_CONFIG.APP_API_BASE_URL),
  }
}

export function getApiBaseUrl(): string {
  return getAppConfig().APP_API_BASE_URL
}

export function getApiOrigin(): string {
  return normalizeApiOrigin(getApiBaseUrl())
}

declare global {
  interface Window {
    __APP_CONFIG__?: Partial<AppRuntimeConfig>
  }
}
