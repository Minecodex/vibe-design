import { apiClient } from '../client'

export interface AssetRead {
    id: number
    project_id: number
    user_id: number
    asset_type: 'image' | 'video'
    url: string
    created_at: string
    updated_at: string
    adder_avatar?: string | null
    adder_nickname?: string | null
    is_favorite: boolean
    project_name?: string | null
    canvas_item_id?: string | null
    canvas_group_id?: string | null
    canvas_group_name?: string | null
    origin_kind: 'ai_generated' | 'local_upload' | 'legacy'
    source_asset_id?: number | null
    list_preview_url?: string | null
    list_preview_status?: 'ready' | 'pending' | 'missing' | null
    analysis_content?: string | null
}

export function getAssetListMediaUrl(asset: AssetRead): string {
    if (asset.asset_type !== 'image') {
        return asset.url
    }
    return asset.list_preview_url ?? asset.url
}

export interface AssetProjectSummaryRead {
    project_id: number
    project_name?: string | null
    asset_count: number
    image_count: number
    video_count: number
    latest_asset_updated_at?: string | null
}

export interface AssetGroupSummaryRead {
    group_id?: string | null
    group_name?: string | null
    asset_count: number
    image_count: number
    video_count: number
    is_ungrouped: boolean
}

export interface AssetCreate {
    asset_type: 'image' | 'video'
    url: string
    origin_kind: 'ai_generated' | 'local_upload'
}

export interface AssetBatchRequest {
    asset_ids: number[]
    action: 'delete' | 'favorite' | 'unfavorite'
}

export interface AssetBatchResponse {
    success: boolean
    message: string
}

export interface CanvasAssetPreviewRead {
    url?: string | null
    status?: 'ready' | 'pending' | 'missing' | null
}

export interface CanvasAssetTileRead {
    url?: string | null
    status?: 'ready' | 'pending' | 'missing' | null
    tile_size: number
    source_width?: number | null
    source_height?: number | null
    level_width?: number | null
    level_height?: number | null
    columns?: number | null
    rows?: number | null
}

export const assetsApi = {
    // Add an asset from the canvas
    create: (projectId: number, data: AssetCreate) =>
        apiClient.post<AssetRead>(`/projects/${projectId}/assets`, data),

    // List all assets for a project
    list: (projectId: number, params?: { asset_type?: string, origin_kind?: string, favorite_only?: boolean, user_id?: number, canvas_group_id?: string, ungrouped_only?: boolean, skip?: number, limit?: number }) =>
        apiClient.get<AssetRead[]>(`/projects/${projectId}/assets`, { params }),

    listGroups: (projectId: number, params?: { asset_type?: string, origin_kind?: string, favorite_only?: boolean }) =>
        apiClient.get<AssetGroupSummaryRead[]>(`/projects/${projectId}/assets/groups`, { params }),

    // Perform batch operations for a specific project
    batch: (projectId: number, data: AssetBatchRequest) =>
        apiClient.post<AssetBatchResponse>(`/projects/${projectId}/assets/batch`, data),

    // List all assets for the current user across all projects
    listAll: (params?: { asset_type?: string, origin_kind?: string, favorite_only?: boolean, skip?: number, limit?: number }) =>
        apiClient.get<AssetRead[]>(`/assets`, { params }),

    // List accessible projects aggregated for the asset library folder view
    listProjectSummaries: (params?: { asset_type?: string, origin_kind?: string, favorite_only?: boolean, skip?: number, limit?: number }) =>
        apiClient.get<AssetProjectSummaryRead[]>(`/assets/projects`, { params }),

    getCanvasPreview: (projectId: number, params: { url: string, width: 256 | 512 | 1024 | 2048 }) =>
        apiClient.get<CanvasAssetPreviewRead>(`/projects/${projectId}/assets/canvas-preview`, { params }),

    getCanvasTile: (projectId: number, params: { url: string, z: number, x: number, y: number }) =>
        apiClient.get<CanvasAssetTileRead>(`/projects/${projectId}/assets/canvas-tile`, { params }),

    // Perform batch operations globally
    globalBatch: (data: AssetBatchRequest) =>
        apiClient.post<AssetBatchResponse>(`/assets/batch`, data),
}
