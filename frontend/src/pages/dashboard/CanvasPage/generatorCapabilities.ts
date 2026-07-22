export interface GeneratorCanvasItemLike {
  reference_image?: string
  reference_images?: string[]
  first_frame_image?: string
  tail_frame_image?: string
  resolution?: string
}

export interface ImageGeneratorCapability {
  supportsReferenceImages: boolean
  maxReferenceImages: number
}

export type VideoGeneratorInputMode = 'text' | 'reference' | 'frames'

export interface VideoGeneratorCapability {
  modelName?: string
  supportsReferenceImages: boolean
  maxReferenceImages: number
  supportsFirstFrame: boolean
  supportsTailFrame: boolean
  supportsAudio?: boolean
  audioAllowedResolutions?: string[]
  tailFrameAllowedResolutions?: string[]
  requiresFirstFrameForTailFrame?: boolean
  audioTailFrameMutuallyExclusive?: boolean
  disableAspectRatioWhenImages: boolean
  imageModesConflict: boolean
  allowedDurations?: string[]
  allowedDurationsByMode?: Partial<Record<VideoGeneratorInputMode, string[]>>
  minDuration?: number
  maxDuration?: number
}

export type TailFrameConstraintReason =
  | 'unsupported'
  | 'requires_first_frame'
  | 'requires_pro_resolution'
  | 'audio_conflict'
  | null

const DEFAULT_IMAGE_CAPABILITY: ImageGeneratorCapability = {
  supportsReferenceImages: false,
  maxReferenceImages: 0,
}

const DEFAULT_VIDEO_CAPABILITY: VideoGeneratorCapability = {
  supportsReferenceImages: false,
  maxReferenceImages: 0,
  supportsFirstFrame: false,
  supportsTailFrame: false,
  disableAspectRatioWhenImages: false,
  imageModesConflict: false,
}

const IMAGE_CAPABILITIES: Record<string, ImageGeneratorCapability> = {
  'gemini-3.1-flash-image-preview-official': {
    supportsReferenceImages: true,
    maxReferenceImages: 14,
  },
  'nano-banana-2': {
    supportsReferenceImages: true,
    maxReferenceImages: 14,
  },
  'gemini-3-pro-image-preview-official': {
    supportsReferenceImages: true,
    maxReferenceImages: 14,
  },
  'nano-banana-pro': {
    supportsReferenceImages: true,
    maxReferenceImages: 14,
  },
  'gemini-3-pro-image-preview': {
    supportsReferenceImages: true,
    maxReferenceImages: 14,
  },
  'gpt-image-2': {
    supportsReferenceImages: true,
    maxReferenceImages: 16,
  },
  'doubao-seedream-4-5': {
    supportsReferenceImages: true,
    maxReferenceImages: 10,
  },
  'doubao-seedance-4-5': {
    supportsReferenceImages: true,
    maxReferenceImages: 10,
  },
  'doubao-seedream-5-0-lite': {
    supportsReferenceImages: true,
    maxReferenceImages: 10,
  },
}

const VIDEO_CAPABILITIES: Record<string, VideoGeneratorCapability> = {
  'kling-v2-6': {
    modelName: 'kling-v2-6',
    supportsReferenceImages: true,
    maxReferenceImages: 2,
    supportsFirstFrame: true,
    supportsTailFrame: true,
    supportsAudio: true,
    audioAllowedResolutions: ['1080p_audio'],
    tailFrameAllowedResolutions: ['1080p'],
    requiresFirstFrameForTailFrame: true,
    audioTailFrameMutuallyExclusive: true,
    disableAspectRatioWhenImages: false,
    imageModesConflict: true,
    allowedDurations: ['5s', '10s'],
  },
  'kling-v3': {
    modelName: 'kling-v3',
    supportsReferenceImages: true,
    maxReferenceImages: 2,
    supportsFirstFrame: true,
    supportsTailFrame: true,
    supportsAudio: true,
    requiresFirstFrameForTailFrame: true,
    disableAspectRatioWhenImages: false,
    imageModesConflict: true,
    minDuration: 3,
    maxDuration: 15,
  },
  'doubao-seedance-1-5-pro': {
    modelName: 'doubao-seedance-1-5-pro',
    supportsReferenceImages: false,
    maxReferenceImages: 0,
    supportsFirstFrame: true,
    supportsTailFrame: true,
    disableAspectRatioWhenImages: false,
    imageModesConflict: false,
    minDuration: 4,
    maxDuration: 12,
  },
  'doubao-seedance-2.0': {
    modelName: 'doubao-seedance-2.0',
    supportsReferenceImages: true,
    maxReferenceImages: 9,
    supportsFirstFrame: true,
    supportsTailFrame: true,
    disableAspectRatioWhenImages: false,
    imageModesConflict: true,
    minDuration: 5,
    maxDuration: 15,
  },
}

export function getImageGeneratorCapability(modelName?: string): ImageGeneratorCapability {
  if (!modelName) return DEFAULT_IMAGE_CAPABILITY
  return IMAGE_CAPABILITIES[modelName] || DEFAULT_IMAGE_CAPABILITY
}

export function getVideoGeneratorCapability(modelName?: string): VideoGeneratorCapability {
  if (!modelName) return DEFAULT_VIDEO_CAPABILITY
  return VIDEO_CAPABILITIES[modelName] || DEFAULT_VIDEO_CAPABILITY
}

export function normalizeReferenceImages(item: GeneratorCanvasItemLike): string[] {
  if (Array.isArray(item.reference_images) && item.reference_images.length > 0) {
    return item.reference_images.filter(Boolean)
  }
  return item.reference_image ? [item.reference_image] : []
}

export function getVideoImageInputMode(
  capability: VideoGeneratorCapability,
  item: GeneratorCanvasItemLike,
): VideoGeneratorInputMode {
  const referenceImages = normalizeReferenceImages(item)
  if (capability.supportsReferenceImages && referenceImages.length > 0) {
    return 'reference'
  }
  if (item.first_frame_image || item.tail_frame_image) {
    return 'frames'
  }
  return 'text'
}

export function getAllowedVideoDurations(
  capability: VideoGeneratorCapability,
  item: GeneratorCanvasItemLike,
  fallbackDurations?: string[],
): string[] {
  const mode = getVideoImageInputMode(capability, item)
  const modeDurations = capability.allowedDurationsByMode?.[mode]
  if (modeDurations && modeDurations.length > 0) {
    return modeDurations
  }
  if (capability.allowedDurations && capability.allowedDurations.length > 0) {
    return capability.allowedDurations
  }
  if (
    typeof capability.minDuration === 'number' &&
    typeof capability.maxDuration === 'number' &&
    capability.minDuration <= capability.maxDuration
  ) {
    const minDuration = capability.minDuration
    const maxDuration = capability.maxDuration
    return Array.from(
      { length: maxDuration - minDuration + 1 },
      (_, index) => `${minDuration + index}s`,
    )
  }
  if (fallbackDurations && fallbackDurations.length > 0) {
    return fallbackDurations
  }
  return ['5s', '10s', '15s']
}

export function normalizeVideoResolution(value?: string, fallback = '720p'): string {
  const raw = String(value || fallback).trim().toLowerCase()
  return raw || fallback
}

export function isAudioResolution(value?: string): boolean {
  return normalizeVideoResolution(value).endsWith('_audio')
}

export function getTailFrameConstraintState(
  capability: VideoGeneratorCapability | null | undefined,
  item: GeneratorCanvasItemLike,
  resolution?: string,
): { enabled: boolean; reason: TailFrameConstraintReason } {
  if (!capability) {
    return { enabled: false, reason: 'unsupported' }
  }
  if (!capability.supportsTailFrame) {
    return { enabled: false, reason: 'unsupported' }
  }

  if (capability.requiresFirstFrameForTailFrame && !item.first_frame_image) {
    return { enabled: false, reason: 'requires_first_frame' }
  }

  if (capability.audioTailFrameMutuallyExclusive && isAudioResolution(resolution)) {
    return { enabled: false, reason: 'audio_conflict' }
  }

  const allowedResolutions = capability.tailFrameAllowedResolutions?.map((value) =>
    normalizeVideoResolution(value),
  )
  if (
    allowedResolutions?.length &&
    !allowedResolutions.includes(normalizeVideoResolution(resolution))
  ) {
    return { enabled: false, reason: 'requires_pro_resolution' }
  }

  return { enabled: true, reason: null }
}

export function getAvailableVideoResolutions(
  capability: VideoGeneratorCapability | null | undefined,
  item: GeneratorCanvasItemLike,
  allowedResolutions: string[],
): string[] {
  if (!capability) {
    return allowedResolutions
  }
  if (!item.tail_frame_image) {
    return allowedResolutions
  }

  const normalizedTailFrameResolutions = capability.tailFrameAllowedResolutions?.map((value) =>
    normalizeVideoResolution(value),
  )

  return allowedResolutions.filter((resolution) => {
    const normalizedResolution = normalizeVideoResolution(resolution)
    if (
      normalizedTailFrameResolutions?.length &&
      !normalizedTailFrameResolutions.includes(normalizedResolution)
    ) {
      return false
    }
    if (capability.audioTailFrameMutuallyExclusive && isAudioResolution(normalizedResolution)) {
      return false
    }
    return true
  })
}

export function getGeneratorOptionsDropdownType(_isImageGroup: boolean): 'res' {
  return 'res'
}

export function shouldDisableVideoAspectRatio(
  capability: VideoGeneratorCapability,
  item: GeneratorCanvasItemLike,
): boolean {
  return capability.disableAspectRatioWhenImages && getVideoImageInputMode(capability, item) !== 'text'
}
