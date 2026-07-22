import type { AxiosInstance, InternalAxiosRequestConfig, AxiosError } from 'axios'
import { toastBillingErrorIfNeeded } from './errorHandling'
import { storage } from '@/utils/storage'
import i18n from '@/i18n'

const clearAuthState = async () => {
  const authModule = await import('@/store/authStore')
  authModule.useAuthStore.setState({ user: null, isAuthenticated: false, error: null })
}

export const setupInterceptors = (client: AxiosInstance): void => {
  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = storage.getToken()
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      config.headers['Accept-Language'] = i18n.language
      return config
    },
    (error) => Promise.reject(error)
  )

  client.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
      const originalRequest = error.config as InternalAxiosRequestConfig & {
        _retry?: boolean
      }

      if (
        error.response?.status === 401 &&
        !originalRequest._retry &&
        !originalRequest.url?.includes('/auth/refresh') &&
        !originalRequest.url?.includes('/auth/login') &&
        !originalRequest.url?.includes('/auth/register')
      ) {
        originalRequest._retry = true
        try {
          const refreshToken = storage.getRefreshToken()
          if (!refreshToken) throw new Error('No refresh token')

          const { data } = await client.post('/auth/refresh', {
            refresh_token: refreshToken,
          })
          storage.setToken(data.access_token)
          storage.setRefreshToken(data.refresh_token)
          originalRequest.headers.Authorization = `Bearer ${data.access_token}`
          return client(originalRequest)
        } catch (refreshError) {
          storage.clearTokens()
          await clearAuthState()
          window.location.href = '/?login=true'
          return Promise.reject(refreshError)
        }
      }

      toastBillingErrorIfNeeded(error)
      return Promise.reject(error)
    }
  )
}
