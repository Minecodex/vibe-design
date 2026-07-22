import { apiClient } from '../client'
import { ProjectRead } from './projects'
import type { AssetRead } from './assets'

export interface ShareUpdate {
    share_permission?: string | null
}

export interface ShareInfo {
    project: ProjectRead
    permission: string
    require_password: boolean
    is_member: boolean
}

export interface ShareAccess {
    password?: string
}

export interface BasicShareInfo {
    require_password: boolean
    permission: string
}

export const shareApi = {
    generateLink: async (projectId: number, permission: 'editor' | 'viewer') => {
        const res = await apiClient.post<{ code: number, message: string, data: ProjectRead }>(`/share/projects/${projectId}/generate`, { share_permission: permission })
        return res.data
    },
    accessProject: async (token: string, data: ShareAccess = {}) => {
        const res = await apiClient.post<{ code: number, message: string, data: ShareInfo }>(`/share/${token}/access`, data)
        return res.data
    },
    joinProject: async (token: string) => {
        const res = await apiClient.post<{ code: number, message: string, data: { message: string, project_id: number } }>(`/share/${token}/join`)
        return res.data
    },
    getInfo: async (token: string) => {
        const res = await apiClient.post<{ code: number, message: string, data: BasicShareInfo }>(`/share/${token}/info`)
        return res.data
    },
    listSharedAssets: async (token: string, params?: { asset_type?: string, skip?: number, limit?: number }) => {
        const res = await apiClient.get<{ code: number, message: string, data: AssetRead[] }>(`/share/${token}/assets`, { params })
        return res.data
    }
}
