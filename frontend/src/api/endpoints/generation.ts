import { apiClient } from '../client'

const GENERATION_REQUEST_TIMEOUT_MS = 700000

export interface GenerateImageRequest {
    prompt: string
    model_name: string
    provider_code: string
    aspect_ratio?: string
    resolution?: string
    image_url?: string
    image_urls?: string[]
    client_request_id?: string
}

export interface GenerateVideoRequest {
    prompt: string
    model_name: string
    provider_code: string
    aspect_ratio?: string
    duration?: number
    quality?: string
    resolution?: string
    audio?: boolean
    image_url?: string
    image_tail_url?: string
    first_frame_image?: string
    tail_frame_image?: string
    image_urls?: string[]
    client_request_id?: string
}

export interface RecoverGenerationTaskItem {
    client_request_id: string
    task_type: string
}

export interface RecoverGenerationTasksRequest {
    items: RecoverGenerationTaskItem[]
}

export interface GenerateImageEraseRequest {
    source_image_url: string
    source_width: number
    source_height: number
}

export interface GenerateSpatialAngleRequest {
    source_image_url: string
    source_width: number
    source_height: number
    x: number
    y: number
    scale: string
}

export interface GenerateHDUpscaleRequest {
    source_image_url: string
    source_width: number
    source_height: number
}

export interface GenerateHDUpscaleResponse {
    task: GenerationTaskRead
    calculated_width: number
    calculated_height: number
}

export interface TextRedrawSegment {
    id: string
    text: string
    order: number
}

export interface ExtractTextRedrawRequest {
    image_url: string
}

export interface ExtractTextRedrawResponse {
    segments: TextRedrawSegment[]
}

export interface GenerateTextRedrawRequest {
    source_image_url: string
    original_segments: TextRedrawSegment[]
    edited_segments: TextRedrawSegment[]
    source_width?: number
    source_height?: number
}

export interface GenerationTaskRead {
    id: number
    project_id: number
    task_type: string
    provider_code: string
    model_name: string
    model_label?: string | null
    prompt: string
    status: 'pending' | 'processing' | 'completed' | 'failed'
    progress: number
    client_request_id?: string | null
    external_task_id: string | null
    result_url: string | null
    result_urls?: string[] | null
    error_message: string | null
    params?: Record<string, unknown> | null
    created_at: string
    updated_at: string
}

export interface RecoverGenerationTasksResponse {
    tasks: Record<string, GenerationTaskRead>
}

export const generationApi = {
    generateImage: (projectId: number, data: GenerateImageRequest) =>
        apiClient.post<GenerationTaskRead>(`/projects/${projectId}/generate/image`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    generateVideo: (projectId: number, data: GenerateVideoRequest) =>
        apiClient.post<GenerationTaskRead>(`/projects/${projectId}/generate/video`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    recoverTasks: (projectId: number, data: RecoverGenerationTasksRequest) =>
        apiClient.post<RecoverGenerationTasksResponse>(`/projects/${projectId}/generation-tasks/recover`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    extractTextRedraw: (projectId: number, data: ExtractTextRedrawRequest) =>
        apiClient.post<ExtractTextRedrawResponse>(`/projects/${projectId}/text-redraw/extract`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    generateTextRedraw: (projectId: number, data: GenerateTextRedrawRequest) =>
        apiClient.post<GenerationTaskRead>(`/projects/${projectId}/generate/text-redraw`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    generateImageErase: (projectId: number, data: GenerateImageEraseRequest) =>
        apiClient.post<GenerationTaskRead>(`/projects/${projectId}/generate/erase`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    generateHDUpscale: (projectId: number, data: GenerateHDUpscaleRequest) =>
        apiClient.post<GenerateHDUpscaleResponse>(`/projects/${projectId}/generate/hd`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    generateSpatialAngle: (projectId: number, data: GenerateSpatialAngleRequest) =>
        apiClient.post<GenerationTaskRead>(`/projects/${projectId}/generate/spatial-angle`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),

    queryTask: (taskId: number) =>
        apiClient.get<GenerationTaskRead>(`/generation-tasks/${taskId}/status`),

    retryTask: (taskId: number, data: Partial<GenerateImageRequest & GenerateVideoRequest>) =>
        apiClient.post<GenerationTaskRead>(`/generation-tasks/${taskId}/retry`, data, { timeout: GENERATION_REQUEST_TIMEOUT_MS }),
}
