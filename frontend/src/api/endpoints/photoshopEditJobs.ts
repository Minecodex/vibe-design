import { apiClient } from '../client'

export interface PhotoshopEditJobRead {
  id: number
  project_id: number
  request_user_id: number
  source_canvas_item_id: string
  source_asset_id?: number | null
  svg_url: string
  status: 'pending' | 'claimed' | 'saved' | 'failed' | 'cancelled'
  claimed_by_user_id?: number | null
  result_asset_id?: number | null
  result_canvas_item_id?: string | null
  created_at: string
  updated_at: string
}

export interface PhotoshopEditJobCreate {
  source_canvas_item_id: string
  svg_url: string
}

export interface PhotoshopEditJobSaveRequest {
  result_url: string
  width: number
  height: number
  name?: string
  target_project_id?: number
}

export const photoshopEditJobsApi = {
  create: (projectId: number, data: PhotoshopEditJobCreate) =>
    apiClient.post<PhotoshopEditJobRead>(`/projects/${projectId}/photoshop-edit-jobs`, data),
  listPending: () =>
    apiClient.get<PhotoshopEditJobRead[]>('/photoshop-edit-jobs/pending'),
  claim: (jobId: number) =>
    apiClient.post<PhotoshopEditJobRead>(`/photoshop-edit-jobs/${jobId}/claim`),
  save: (jobId: number, data: PhotoshopEditJobSaveRequest) =>
    apiClient.post<PhotoshopEditJobRead>(`/photoshop-edit-jobs/${jobId}/save`, data),
}
