import { beforeEach, describe, expect, it, vi } from 'vitest'

const authMocks = vi.hoisted(() => ({
  getHealth: vi.fn(),
  getBalance: vi.fn(),
}))

vi.mock('@/api/endpoints/auth', () => ({
  authApi: {
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshToken: vi.fn(),
    getMe: vi.fn(),
    getHealth: authMocks.getHealth,
  },
}))

vi.mock('@/api/endpoints/billing', () => ({
  billingApi: {
    getBalance: authMocks.getBalance,
  },
}))

vi.mock('@/utils/storage', () => ({
  storage: {
    setToken: vi.fn(),
    setRefreshToken: vi.fn(),
    clearTokens: vi.fn(),
    getToken: vi.fn(),
  },
}))

import { useAuthStore } from './authStore'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('authStore', () => {
  beforeEach(() => {
    authMocks.getHealth.mockReset()
    authMocks.getBalance.mockReset()
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
      deployType: 'saas',
      licenseStatus: 'active',
      licenseEdition: null,
      licenseExpired: false,
      licenseExpiresAt: null,
    })
  })

  it('dedupes concurrent deploy type requests', async () => {
    const healthDeferred = deferred<{
      data: {
        deploy_type: 'private'
        license_status: 'active'
        license_edition: 'premium'
        license_expired: boolean
        license_expires_at: string | null
      }
    }>()
    authMocks.getHealth.mockReturnValue(healthDeferred.promise)

    const firstRequest = useAuthStore.getState().fetchDeployType()
    const secondRequest = useAuthStore.getState().fetchDeployType()

    expect(authMocks.getHealth).toHaveBeenCalledTimes(1)

    healthDeferred.resolve({
      data: {
        deploy_type: 'private',
        license_status: 'active',
        license_edition: 'premium',
        license_expired: false,
        license_expires_at: null,
      },
    })

    await Promise.all([firstRequest, secondRequest])

    expect(useAuthStore.getState().deployType).toBe('private')
    expect(useAuthStore.getState().licenseStatus).toBe('active')
    expect(useAuthStore.getState().licenseEdition).toBe('premium')
    expect(useAuthStore.getState().licenseExpired).toBe(false)
  })
})
