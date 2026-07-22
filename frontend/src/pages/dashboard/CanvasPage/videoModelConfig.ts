import {
  getAllowedVideoDurations,
  getVideoGeneratorCapability,
  type GeneratorCanvasItemLike,
  type VideoGeneratorCapability,
} from './generatorCapabilities'

export type VideoModelRegistryConfig = {
  allowed_aspect_ratios?: string[]
  allowed_sizes?: string[]
  dimension_table?: Record<string, Record<string, { width?: number | null; height?: number | null }>>
  dimension_policy?: string
  dimension_source?: string
  allowed_durations?: string[]
  allowed_durations_by_mode?: Partial<Record<'text' | 'reference' | 'frames', string[]>>
  min_duration?: number
  max_duration?: number
  supports_first_frame?: boolean
  supports_tail_frame?: boolean
  supports_audio?: boolean
  audio_allowed_sizes?: string[]
  tail_frame_allowed_sizes?: string[]
  requires_first_frame_for_tail_frame?: boolean
  audio_tail_frame_mutually_exclusive?: boolean
  max_image_inputs?: number
  disallow_reference_mode?: boolean
  image_modes_conflict?: boolean
  disallow_manual_aspect_ratio_with_images?: boolean
}

export type VideoModelOptionLike = {
  value?: string
  model_name?: string
  provider?: string
  provider_code?: string
  config?: VideoModelRegistryConfig
}

const DEFAULT_VIDEO_RATIOS = ['16:9', '9:16', '1:1']
const DEFAULT_VIDEO_RESOLUTIONS = ['720p']

export function findVideoModelOption(
  models: VideoModelOptionLike[],
  modelName?: string,
  providerCode?: string,
): VideoModelOptionLike | undefined {
  if (!modelName) return undefined
  return models.find((model) => {
    const candidateModelName = model.value || model.model_name
    const candidateProvider = model.provider || model.provider_code
    if (candidateModelName !== modelName) return false
    if (!providerCode) return true
    return candidateProvider === providerCode
  })
}

export function getVideoCapabilityFromConfig(
  config?: VideoModelRegistryConfig,
  fallbackModelName?: string,
): VideoGeneratorCapability {
  const fallback = getVideoGeneratorCapability(fallbackModelName)
  if (!config) return fallback
  const disallowReferenceMode = Boolean(config.disallow_reference_mode)

  return {
    ...fallback,
    supportsReferenceImages: !disallowReferenceMode && typeof config.max_image_inputs === 'number'
      ? config.max_image_inputs > 0
      : fallback.supportsReferenceImages,
    maxReferenceImages: disallowReferenceMode
      ? 0
      : typeof config.max_image_inputs === 'number'
      ? Math.max(0, config.max_image_inputs)
      : fallback.maxReferenceImages,
    supportsFirstFrame: config.supports_first_frame ?? fallback.supportsFirstFrame,
    supportsTailFrame: config.supports_tail_frame ?? fallback.supportsTailFrame,
    supportsAudio: config.supports_audio ?? fallback.supportsAudio,
    audioAllowedResolutions: config.audio_allowed_sizes?.length
      ? config.audio_allowed_sizes
      : fallback.audioAllowedResolutions,
    tailFrameAllowedResolutions: config.tail_frame_allowed_sizes?.length
      ? config.tail_frame_allowed_sizes
      : fallback.tailFrameAllowedResolutions,
    requiresFirstFrameForTailFrame: config.requires_first_frame_for_tail_frame ?? fallback.requiresFirstFrameForTailFrame,
    audioTailFrameMutuallyExclusive: config.audio_tail_frame_mutually_exclusive ?? fallback.audioTailFrameMutuallyExclusive,
    imageModesConflict: config.image_modes_conflict ?? fallback.imageModesConflict,
    disableAspectRatioWhenImages: config.disallow_manual_aspect_ratio_with_images ?? fallback.disableAspectRatioWhenImages,
    allowedDurations: config.allowed_durations?.length ? config.allowed_durations : fallback.allowedDurations,
    allowedDurationsByMode: config.allowed_durations_by_mode ?? fallback.allowedDurationsByMode,
    minDuration: typeof config.min_duration === 'number' ? config.min_duration : fallback.minDuration,
    maxDuration: typeof config.max_duration === 'number' ? config.max_duration : fallback.maxDuration,
  }
}

export function getResolvedVideoModelCapability(
  models: VideoModelOptionLike[],
  modelName?: string,
  providerCode?: string,
): VideoGeneratorCapability {
  const matchedModel = findVideoModelOption(models, modelName, providerCode)
  return getVideoCapabilityFromConfig(matchedModel?.config, modelName)
}

export function getAllowedVideoRatios(
  config?: VideoModelRegistryConfig,
  fallback = DEFAULT_VIDEO_RATIOS,
): string[] {
  return config?.allowed_aspect_ratios?.length ? config.allowed_aspect_ratios : fallback
}

export function getAllowedVideoResolutions(
  config?: VideoModelRegistryConfig,
  fallback = DEFAULT_VIDEO_RESOLUTIONS,
): string[] {
  return config?.allowed_sizes?.length ? config.allowed_sizes : fallback
}

export function getResolvedVideoDurationsFromConfig(
  models: VideoModelOptionLike[],
  item: GeneratorCanvasItemLike,
  modelName?: string,
  providerCode?: string,
  fallbackDurations?: string[],
): string[] {
  const capability = getResolvedVideoModelCapability(models, modelName, providerCode)
  return getAllowedVideoDurations(capability, item, fallbackDurations)
}
