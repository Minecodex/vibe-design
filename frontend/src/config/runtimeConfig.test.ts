import { afterEach, describe, expect, it, vi } from 'vitest'

declare global {
  interface Window {
    __APP_CONFIG__?: {
      APP_API_BASE_URL?: string
    }
  }
}

const clearRuntimeConfigModule = async () => {
  delete window.__APP_CONFIG__
  return import('./runtimeConfig')
}

afterEach(() => {
  delete window.__APP_CONFIG__
  vi.unstubAllEnvs()
})

describe('runtimeConfig', () => {
  it('returns defaults when runtime config is missing', async () => {
    const runtimeConfig = await clearRuntimeConfigModule()

    expect(runtimeConfig.getAppConfig()).toEqual({
      APP_API_BASE_URL: 'http://localhost:8000/api/v1',
    })
    expect(runtimeConfig.getApiBaseUrl()).toBe('http://localhost:8000/api/v1')
  })

  it('prefers runtime config values from window.__APP_CONFIG__', async () => {
    window.__APP_CONFIG__ = {
      APP_API_BASE_URL: 'https://api.example.com/api/v1',
    }

    const runtimeConfig = await import('./runtimeConfig')

    expect(runtimeConfig.getAppConfig()).toEqual({
      APP_API_BASE_URL: 'https://api.example.com/api/v1',
    })
    expect(runtimeConfig.getApiBaseUrl()).toBe('https://api.example.com/api/v1')
  })

  it('normalizes an origin-only APP_API_BASE_URL for frontend API calls and plugin service addresses', async () => {
    window.__APP_CONFIG__ = {
      APP_API_BASE_URL: 'http://localhost:8000',
    }

    const runtimeConfig = await import('./runtimeConfig')

    expect(runtimeConfig.getApiBaseUrl()).toBe('http://localhost:8000/api/v1')
    expect(runtimeConfig.getApiOrigin()).toBe('http://localhost:8000')
  })

  it('reads APP_API_BASE_URL from Vite env when runtime window config is not present', async () => {
    vi.stubEnv('APP_API_BASE_URL', 'http://localhost:8000')

    const runtimeConfig = await clearRuntimeConfigModule()

    expect(runtimeConfig.getApiBaseUrl()).toBe('http://localhost:8000/api/v1')
    expect(runtimeConfig.getApiOrigin()).toBe('http://localhost:8000')
  })
})
