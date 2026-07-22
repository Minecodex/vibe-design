import { apiClient } from '../client'

export interface User {
    id: number
    username: string
    email: string
    role: string
    is_active: boolean
    avatar_url: string | null
    nickname?: string | null
    bio?: string | null
}

export interface UserUpdate {
    username?: string
    nickname?: string
    bio?: string
    avatar_url?: string | null
    is_active?: boolean
    email?: string
    role?: string
    password?: string
}

export interface ApimartKeyStatus {
    configured: boolean
    status?: string | null
    key_hint?: string | null
    updated_at?: string | null
}

export interface UserCreate {
    email: string
    username: string
    password?: string
    role?: string
    nickname?: string
}

export interface PaginatedData<T> {
    items: T[]
    total: number
    page: number
    page_size: number
    total_pages: number
}

export interface ChangePasswordRequest {
    old_password: string
    new_password: string
}

export const usersApi = {
    getMe: () => apiClient.get<User>('/users/me'),
    getUser: (id: number) => apiClient.get<User>(`/users/${id}`),
    getUsers: async (params: { page?: number, page_size?: number, search?: string }) => {
        const res = await apiClient.get<{ code: number, message: string, data: PaginatedData<User> }>('/users/', { params })
        return res.data
    },
    createUser: async (data: UserCreate) => {
        const res = await apiClient.post<{ code: number, message: string, data: User }>('/users/', data)
        return res.data
    },
    search: async (query: string) => {
        const res = await apiClient.get<{ code: number, message: string, data: User[] }>('/users/search', { params: { query } })
        return res.data
    },
    updateUser: (id: number, data: UserUpdate) =>
        apiClient.patch<User>(`/users/${id}`, data),
    getMyApimartKeyStatus: () =>
        apiClient.get<ApimartKeyStatus>('/users/me/apimart-key/status'),
    getApimartKeyStatus: (id: number) =>
        apiClient.get<ApimartKeyStatus>(`/users/${id}/apimart-key/status`),
    setApimartKey: (id: number, api_key: string) =>
        apiClient.put<ApimartKeyStatus>(`/users/${id}/apimart-key`, { api_key }),
    revokeApimartKey: (id: number) =>
        apiClient.delete<ApimartKeyStatus>(`/users/${id}/apimart-key`),
    uploadAvatar: (id: number, file: File) => {
        const formData = new FormData()
        formData.append('file', file)
        return apiClient.post<User>(`/users/${id}/avatar`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data',
            },
        })
    },
    changePassword: (id: number, data: ChangePasswordRequest) =>
        apiClient.put<{ message: string }>(`/users/${id}/password`, data),
}
