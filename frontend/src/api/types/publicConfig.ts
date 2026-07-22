export interface UploadLimits {
  avatar_max_bytes: number
  canvas_image_max_bytes: number
  canvas_video_max_bytes: number
  harness_attachment_max_bytes: number
}

export interface PublicConfigResponse {
  app_name: string
  app_name_en: string
  upload_limits?: UploadLimits
}
