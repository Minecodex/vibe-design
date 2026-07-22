import { apiClient } from '../client'
import type { HealthResponse, LoginRequest, LoginResponse, RegisterRequest, User } from '../types/auth'
import type { ApiResponse } from '../types/common'

export const authApi = {
  register: (data: RegisterRequest) =>
    apiClient.post<ApiResponse<User>>('/auth/register', data),

  login: (data: LoginRequest) =>
    apiClient.post<LoginResponse>('/auth/login', data),

  logout: () =>
    apiClient.post('/auth/logout'),

  refreshToken: (refreshToken: string) =>
    apiClient.post<LoginResponse>('/auth/refresh', { refresh_token: refreshToken }),

  getMe: () =>
    apiClient.get<ApiResponse<User>>('/auth/me'),

  getHealth: () =>
    apiClient.get<HealthResponse>('/health'),
}
