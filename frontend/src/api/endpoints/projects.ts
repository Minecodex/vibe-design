import { apiClient } from '../client'
import type { ApiResponse, PaginatedResponse } from '../types/common'

export interface CanvasItem {
    id: string
    type: 'image' | 'video' | 'image_generator' | 'video_generator' | 'group' | 'text' | 'brush_path'
    generator_origin?: 'image_action' | 'standalone'
    generation_kind?: 'text_redraw' | 'image_erase' | 'image_hd_upscale'
    url: string
    name?: string
    groupId?: string
    background_color?: string
    x: number
    y: number
    z_index?: number
    is_hidden?: boolean
    is_locked?: boolean
    status?: 'binding_task' | 'generating' | 'completed' | 'failed'
    task_id?: string | number
    client_request_id?: string
    binding_started_at?: string
    artifact_ref?: string
    progress?: number
    error_message?: string | null
    failure_kind?: 'task_failed' | 'internal_failed' | 'task_binding_failed'
    width?: number
    height?: number
    media_display_size_source?: 'placeholder' | 'intrinsic' | 'user'
    text?: string
    fontFamily?: string
    fontVariant?: string
    fontSize?: number
    fillColor?: string
    strokeColor?: string
    strokeWidth?: number
    textAlign?: 'left' | 'center' | 'right'
    lineHeight?: number
    letterSpacing?: number
    underline?: boolean
    strikeThrough?: boolean
    listStyle?: 'none' | 'ordered' | 'unordered'
    textTransform?: 'none' | 'uppercase' | 'lowercase' | 'capitalize'
    writingMode?: 'horizontal' | 'vertical'
    points?: BrushPoint[]
    brushColor?: string
    brushSize?: number
    pathBounds?: BrushPathBounds
    prompt?: string
    model_name?: string
    model_label?: string
    provider_code?: string
    aspect_ratio?: string
    resolution?: string
    duration?: string
    created_at?: string
    creator_name?: string
    creator_avatar?: string
    reference_image?: string
    reference_images?: string[]
    first_frame_image?: string
    tail_frame_image?: string
    asset_origin?: 'ai_generated' | 'local_upload' | 'legacy' | 'asset_library'
    source_asset_id?: number
    agent_message_id?: string | number | null
    agent_conversation_id?: string | number | null
    agent_media_key?: string | null
    agent_group_key?: string | null
    agent_group_order?: number | null
    group_layout_mode?: 'manual' | 'agent_grid'
    suppressCompletionToast?: boolean
}

export interface BrushPoint {
    x: number
    y: number
}

export interface BrushPathBounds {
    x: number
    y: number
    width: number
    height: number
}

export interface CanvasMark {
    id: string
    imageItemId: string
    imageUrl: string
    relativeX: number
    relativeY: number
    number: number
    aiLabels: string[]
    selectedLabel: string | null
    customLabel: string | null
    isAnalyzing: boolean
}

export interface ProjectPreviewItem {
    asset_type: 'image' | 'video'
    url: string
    list_preview_url?: string | null
    list_preview_status?: 'ready' | 'pending' | 'missing' | null
}

export interface ProjectUserRead {
    id: number
    nickname: string | null
    username: string
    avatar_url: string | null
    role: string
}

export interface ProjectListItemRead {
    id: number
    user_id: number
    title: string
    thumbnail_url: string | null
    project_preview_items?: ProjectPreviewItem[] | null
    status: string
    share_token: string | null
    share_permission: string | null
    share_password: string | null
    share_expiration: number | null
    created_at: string
    updated_at: string
    users?: ProjectUserRead[]
}

export interface ProjectRead extends ProjectListItemRead {
    canvas_data?: CanvasDataRecord[] | null
    canvas_revision?: number
}

export interface ProjectCreate {
    title?: string
    status?: string
}

export interface ProjectUpdate {
    title?: string
    canvas_data?: Array<CanvasItem | Record<string, unknown>> | null
    canvas_base_revision?: number
    status?: string
}

export interface CanvasMetadataRecord {
    id: 'global_state'
    type?: 'meta'
    [field: string]: unknown
}
export type CanvasDataRecord = CanvasItem | CanvasMetadataRecord

export function isCanvasItemRecord(record: CanvasDataRecord): record is CanvasItem {
    return record.id !== 'global_state' && record.type !== 'meta'
}

export const projectsApi = {
    list: async (params: { page?: number, page_size?: number } = {}) => {
        const res = await apiClient.get<ApiResponse<PaginatedResponse<ProjectListItemRead>>>('/projects', { params })
        return res.data
    },
    get: (id: number) => apiClient.get<ProjectRead>(`/projects/${id}`),
    create: (data: ProjectCreate = {}) => apiClient.post<ProjectRead>('/projects', data),
    update: (id: number, data: ProjectUpdate) => apiClient.put<ProjectRead>(`/projects/${id}`, data),
    delete: (id: number) => apiClient.delete<{ message: string }>(`/projects/${id}`),
}
