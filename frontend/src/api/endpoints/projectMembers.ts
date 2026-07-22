import { apiClient } from '../client'
import { User } from './users'

export interface ProjectMemberRead {
    id: number
    project_id: number
    user_id: number
    role: string
    created_at: string
    updated_at: string
    user?: User
}

export interface ProjectMemberCreate {
    user_id: number
    role?: string
}

export const projectMembersApi = {
    list: async (projectId: number) => {
        const res = await apiClient.get<{ code: number, message: string, data: ProjectMemberRead[] }>(`/projects/${projectId}/members`)
        return res.data
    },
    add: async (projectId: number, data: ProjectMemberCreate) => {
        const res = await apiClient.post<{ code: number, message: string, data: ProjectMemberRead }>(`/projects/${projectId}/members`, data)
        return res.data
    },
    remove: async (projectId: number, userId: number) => {
        const res = await apiClient.delete<{ code: number, message: string }>(`/projects/${projectId}/members/${userId}`)
        return res.data
    }
}
