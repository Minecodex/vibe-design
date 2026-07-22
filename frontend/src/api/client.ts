import axios, { type AxiosInstance } from 'axios'
import { setupInterceptors } from './interceptors'
import { getApiBaseUrl } from '@/config/runtimeConfig'

const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: getApiBaseUrl(),
    timeout: 15000,
    headers: {
      'Content-Type': 'application/json',
    },
  })

  setupInterceptors(client)
  return client
}

export const apiClient = createApiClient()
