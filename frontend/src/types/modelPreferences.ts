export interface ImageGenerationModelSettings {
  resolution?: string
  aspect_ratio?: string
}

export interface VideoGenerationModelSettings {
  resolution?: string
  aspect_ratio?: string
  duration?: number
}

export interface MediaGenerationSettings {
  image?: Record<string, ImageGenerationModelSettings>
  video?: Record<string, VideoGenerationModelSettings>
}
