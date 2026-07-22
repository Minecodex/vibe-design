import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { loadSession, saveSession } from '../src/lib/storage'
import { loginWithPassword } from '../src/lib/auth'

const storageState = new Map<string, unknown>()

beforeEach(() => {
  storageState.clear()
  vi.stubGlobal('chrome', {
    storage: {
      local: {
        async get(key?: string | string[]) {
          if (!key) {
            return Object.fromEntries(storageState.entries())
          }
          if (Array.isArray(key)) {
            return Object.fromEntries(key.map((item) => [item, storageState.get(item)]))
          }
          return { [key]: storageState.get(key) }
        },
        async set(values: Record<string, unknown>) {
          Object.entries(values).forEach(([key, value]) => storageState.set(key, value))
        },
        async remove(key: string | string[]) {
          const keys = Array.isArray(key) ? key : [key]
          keys.forEach((item) => storageState.delete(item))
        },
      },
    },
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('prompt extractor auth helpers', () => {
  it('persists tokens and server base URL together', async () => {
    await saveSession({
      serverBaseUrl: 'https://demo.example.com',
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    })

    await expect(loadSession()).resolves.toEqual({
      serverBaseUrl: 'https://demo.example.com',
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    })
  })

  it('posts account and password to the auth login endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: 'access-token',
        refresh_token: 'refresh-token',
      }),
    })
    vi.stubGlobal('fetch', fetchMock)

    const result = await loginWithPassword({
      serverBaseUrl: 'https://demo.example.com',
      account: 'demo',
      password: 'secret',
    })

    expect(fetchMock).toHaveBeenCalledWith(
      'https://demo.example.com/api/v1/auth/login',
      expect.objectContaining({
        method: 'POST',
      }),
    )
    expect(result).toEqual({
      accessToken: 'access-token',
      refreshToken: 'refresh-token',
    })
  })
})
