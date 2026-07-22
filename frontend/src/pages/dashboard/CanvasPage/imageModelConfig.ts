import { getImageGeneratorCapability, type ImageGeneratorCapability } from './generatorCapabilities'
import { isGeneratorModelOptionSelected } from './generatorModelIdentity'

export type ImageModelRegistryConfig = {
  allowed_aspect_ratios?: string[]
  allowed_aspect_ratios_by_size?: Record<string, string[]>
  allowed_sizes?: string[]
  dimension_table?: Record<string, Record<string, { width?: number | null; height?: number | null }>>
  dimension_policy?: string
  dimension_source?: string
  max_reference_images?: number
}

export type ImageModelOptionLike = {
  value?: string
  model_name?: string
  provider?: string
  provider_code?: string
  config?: ImageModelRegistryConfig
}

const DEFAULT_IMAGE_RESOLUTIONS = ['1K']
const DEFAULT_IMAGE_RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4']

function getResolutionRank(value: string): number {
  const normalized = String(value || '').trim().toUpperCase()
  if (normalized.endsWith('K')) {
    return Number(normalized.slice(0, -1)) * 1000
  }
  return -1
}

export function findImageModelOption(
  models: ImageModelOptionLike[],
  modelName?: string,
  providerCode?: string,
): ImageModelOptionLike | undefined {
  if (!modelName) return undefined
  return models.find((model) => isGeneratorModelOptionSelected(model, modelName, providerCode))
}

export function getImageCapabilityFromConfig(
  config?: ImageModelRegistryConfig,
  fallbackModelName?: string,
): ImageGeneratorCapability {
  if (typeof config?.max_reference_images === 'number') {
    return {
      supportsReferenceImages: config.max_reference_images > 0,
      maxReferenceImages: Math.max(0, config.max_reference_images),
    }
  }
  return getImageGeneratorCapability(fallbackModelName)
}

export function getResolvedImageModelCapability(
  models: ImageModelOptionLike[],
  modelName?: string,
  providerCode?: string,
): ImageGeneratorCapability {
  const matchedModel = findImageModelOption(models, modelName, providerCode)
  return getImageCapabilityFromConfig(matchedModel?.config, modelName)
}

export function getAllowedImageResolutions(
  config?: ImageModelRegistryConfig,
  fallback = DEFAULT_IMAGE_RESOLUTIONS,
): string[] {
  return config?.allowed_sizes?.length ? config.allowed_sizes : fallback
}

export function getAllowedImageRatios(
  config?: ImageModelRegistryConfig,
  fallback = DEFAULT_IMAGE_RATIOS,
): string[] {
  if (config && Object.prototype.hasOwnProperty.call(config, 'allowed_aspect_ratios')) {
    return config.allowed_aspect_ratios ?? []
  }
  return fallback
}

export function getAllowedImageRatiosForResolution(
  config?: ImageModelRegistryConfig,
  resolution?: string,
  fallback = DEFAULT_IMAGE_RATIOS,
): string[] {
  if (
    resolution
    && config?.allowed_aspect_ratios_by_size
    && Object.prototype.hasOwnProperty.call(config.allowed_aspect_ratios_by_size, resolution)
  ) {
    return config.allowed_aspect_ratios_by_size[resolution] ?? []
  }
  return getAllowedImageRatios(config, fallback)
}

export function resolveImageModelSelection({
  config,
  currentResolution,
  currentAspectRatio,
  nextResolution,
  preferredAspectRatio = '1:1',
  fallbackResolutions = DEFAULT_IMAGE_RESOLUTIONS,
  fallbackRatios = DEFAULT_IMAGE_RATIOS,
}: {
  config?: ImageModelRegistryConfig
  currentResolution?: string
  currentAspectRatio?: string
  nextResolution?: string
  preferredAspectRatio?: string
  fallbackResolutions?: string[]
  fallbackRatios?: string[]
}): { resolution: string; aspect_ratio: string } {
  const allowedResolutions = getAllowedImageResolutions(config, fallbackResolutions)
  const requestedResolution = nextResolution || currentResolution
  const resolution = requestedResolution && allowedResolutions.includes(requestedResolution)
    ? requestedResolution
    : [...allowedResolutions].sort((left, right) => getResolutionRank(right) - getResolutionRank(left))[0] || fallbackResolutions[0] || '1K'
  const allowedRatios = getAllowedImageRatiosForResolution(config, resolution, fallbackRatios)
  if (allowedRatios.length === 0) {
    return {
      resolution,
      aspect_ratio: currentAspectRatio || preferredAspectRatio || fallbackRatios[0] || '1:1',
    }
  }
  const currentRatio = currentAspectRatio || preferredAspectRatio
  const aspectRatio = allowedRatios.includes(currentRatio)
    ? currentRatio
    : (allowedRatios.includes(preferredAspectRatio) ? preferredAspectRatio : (allowedRatios[0] || fallbackRatios[0] || '1:1'))
  return {
    resolution,
    aspect_ratio: aspectRatio,
  }
}
