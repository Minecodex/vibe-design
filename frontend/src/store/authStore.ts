import { create } from 'zustand'
import { devtools, persist } from 'zustand/middleware'
import { authApi } from '@/api/endpoints/auth'
import { billingApi } from '@/api/endpoints/billing'
import { storage } from '@/utils/storage'
import type { User, LoginRequest, RegisterRequest, LicenseEdition, LicenseStatus } from '@/api/types/auth'

let refreshBalanceRequest: Promise<void> | null = null
let fetchDeployTypeRequest: Promise<void> | null = null

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isLoading: boolean
  error: string | null
  deployType: 'saas' | 'private'
  licenseStatus: LicenseStatus
  licenseEdition: LicenseEdition | null
  licenseExpired: boolean
  licenseExpiresAt: string | null
  providerBalanceSyncEnabled: boolean
}

interface AuthActions {
  login: (credentials: LoginRequest) => Promise<void>
  register: (data: RegisterRequest) => Promise<void>
  logout: () => Promise<void>
  clearError: () => void
  updateUser: (user: User) => void
  refreshBalance: () => Promise<void>
  fetchDeployType: () => Promise<void>
}

type AuthStore = AuthState & AuthActions

export const useAuthStore = create<AuthStore>()(
  devtools(
    persist(
      (set, get) => ({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: null,
        deployType: 'saas',
        licenseStatus: 'active',
        licenseEdition: null,
        licenseExpired: false,
        licenseExpiresAt: null,
        providerBalanceSyncEnabled: false,

        login: async (credentials) => {
          set({ isLoading: true, error: null })
          try {
            const { data } = await authApi.login(credentials)
            storage.setToken(data.access_token)
            storage.setRefreshToken(data.refresh_token)
            set({
              user: data.user,
              isAuthenticated: true,
              isLoading: false,
            })
            // Fetch deploy type after login
            await get().fetchDeployType()
          } catch (err: unknown) {
            const detail =
              (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
            let message: string
            if (typeof detail === 'string') {
              message = detail
            } else if (Array.isArray(detail)) {
              message = detail.map((d: { msg?: string }) => d.msg || '').filter(Boolean).join('; ') || '登录失败，请重试'
            } else {
              message = '登录失败，请重试'
            }
            set({ error: message, isLoading: false })
            throw err
          }
        },

        register: async (data) => {
          set({ isLoading: true, error: null })
          try {
            await authApi.register(data)
            set({ isLoading: false })
          } catch (err: unknown) {
            const detail =
              (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
            let message: string
            if (typeof detail === 'string') {
              message = detail
            } else if (Array.isArray(detail)) {
              message = detail.map((d: { msg?: string }) => d.msg || '').filter(Boolean).join('; ') || '注册失败，请重试'
            } else {
              message = '注册失败，请重试'
            }
            set({ error: message, isLoading: false })
            throw err
          }
        },

        logout: async () => {
          try {
            await authApi.logout()
          } catch {
            // ignore logout errors
          } finally {
            storage.clearTokens()
            set({ user: null, isAuthenticated: false, error: null })
          }
        },

        clearError: () => set({ error: null }),

        updateUser: (user) => set({ user }),

        refreshBalance: async () => {
          if (refreshBalanceRequest) {
            return refreshBalanceRequest
          }

          refreshBalanceRequest = (async () => {
            try {
              const { data } = await billingApi.getBalance()
              set((state) => ({
                user: state.user ? { ...state.user, balance_cents: data.balance_cents } : null,
              }))
            } catch {
              // ignore balance refresh errors
            } finally {
              refreshBalanceRequest = null
            }
          })()

          return refreshBalanceRequest
        },

        fetchDeployType: async () => {
          if (fetchDeployTypeRequest) {
            return fetchDeployTypeRequest
          }

          fetchDeployTypeRequest = (async () => {
            try {
              const { data } = await authApi.getHealth()
              console.log('Fetched deploy type:', data.deploy_type)
              set({
                deployType: data.deploy_type || 'saas',
                licenseStatus: data.license_status ?? 'active',
                licenseEdition: data.license_edition ?? null,
                licenseExpired: data.license_expired ?? false,
                licenseExpiresAt: data.license_expires_at ?? null,
                providerBalanceSyncEnabled: data.provider_balance_sync_enabled ?? false,
              })
            } catch (err) {
              console.error('Failed to fetch deploy type:', err)
            } finally {
              fetchDeployTypeRequest = null
            }
          })()

          return fetchDeployTypeRequest
        },
      }),
      {
        name: 'auth-storage-v2',
        partialize: (state) => ({
          user: state.user,
          isAuthenticated: state.isAuthenticated,
          deployType: state.deployType,
          licenseStatus: state.licenseStatus,
          licenseEdition: state.licenseEdition,
          licenseExpired: state.licenseExpired,
          licenseExpiresAt: state.licenseExpiresAt,
          providerBalanceSyncEnabled: state.providerBalanceSyncEnabled,
        }),
      }
    ),
    { name: 'AuthStore' }
  )
)
