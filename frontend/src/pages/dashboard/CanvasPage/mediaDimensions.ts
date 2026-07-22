import type { CanvasItem } from '@/api/endpoints/projects'
import { formatDimensionLabel } from './generatorOptionLabels'
import { estimateTextCanvasSize } from './textTypography'

export type RatioEntry = { width: number; height: number; label: string }
export type ResolutionRatioMap = Record<string, Record<string, RatioEntry>>
export type MediaDimensions = {
  configured: RatioEntry
  actual: RatioEntry | null
  display: RatioEntry
}

type ClosestImageGenerationDefaultsArgs = {
  sourceWidth?: number | null
  sourceHeight?: number | null
  providerCode?: string | null
  allowedRatios?: string[]
  allowedResolutions?: string[]
}

type DimensionFallback = {
  imageRatio?: string
  videoAspect?: string
  imageProvider?: string
  videoProvider?: string
  imageRes?: string
  videoResolution?: string
  imageModel?: string
  videoModel?: string
  imageModelConfig?: MediaDimensionConfig | null
  videoModelConfig?: MediaDimensionConfig | null
  imageModels?: ImageDimensionModelOption[]
  videoModels?: ImageDimensionModelOption[]
}

type MediaDimensionItem = Pick<CanvasItem, 'type' | 'aspect_ratio' | 'provider_code' | 'resolution' | 'model_name'>
type ActualMediaSize = { width?: number | null; height?: number | null }
type DimensionTableEntry = { width?: number | null; height?: number | null }
type DimensionTable = Record<string, Record<string, DimensionTableEntry>>
export type MediaDimensionConfig = {
  dimension_table?: DimensionTable
  dimension_policy?: string
  dimension_source?: string
  [key: string]: unknown
}
export type ImageDimensionConfig = MediaDimensionConfig
export type ImageDimensionModelOption = {
  value?: string
  model_name?: string
  provider?: string
  config?: MediaDimensionConfig | null
}

function withLabel(width: number, height: number): RatioEntry {
  return { width, height, label: formatDimensionLabel(width, height) }
}

function normalizeImageResolution(resolution?: string | null): string {
  if (!resolution) return '1K'
  const upper = resolution.toUpperCase()
  if (upper === '0.5K') return '0.5K'
  return upper
}

function normalizeVideoResolution(resolution?: string | null): string {
  if (!resolution) return '720p'
  const lower = resolution.toLowerCase()
  if (lower === '4k') return '4k'
  if (lower === '4k_audio') return '4k_audio'
  if (lower === '4k_video') return '4k_video'
  if (lower === '720p_audio') return '720p_audio'
  if (lower === '720p_video') return '720p_video'
  if (lower === '1080p_audio') return '1080p_audio'
  if (lower === '1080p_video') return '1080p_video'
  return lower
}

function buildAreaScaledDimensions(base: number, ratio: string): RatioEntry {
  const [rawW, rawH] = ratio.split(':').map(Number)
  if (!rawW || !rawH) return withLabel(base, base)

  const ratioValue = rawW / rawH
  const width = Math.round(Math.sqrt(base * base * ratioValue))
  const height = Math.round(width / ratioValue)
  return withLabel(width, height)
}

function buildShortSideVideoDimensions(shortSide: number, ratio: string): RatioEntry {
  const [rawW, rawH] = ratio.split(':').map(Number)
  if (!rawW || !rawH) return withLabel(shortSide, shortSide)

  if (rawW === rawH) {
    return withLabel(shortSide, shortSide)
  }

  if (rawW > rawH) {
    return withLabel(Math.round((shortSide * rawW) / rawH), shortSide)
  }

  return withLabel(shortSide, Math.round((shortSide * rawH) / rawW))
}

const KLING_RATIO_MAPS: ResolutionRatioMap = {
  '1K': {
    '1:1': withLabel(1024, 1024),
    '4:3': withLabel(1024, 768),
    '3:4': withLabel(768, 1024),
    '3:2': withLabel(1024, 682),
    '2:3': withLabel(682, 1024),
    '16:9': withLabel(1024, 576),
    '9:16': withLabel(576, 1024),
    '21:9': withLabel(1024, 438),
  },
  '2K': {
    '1:1': withLabel(2048, 2048),
    '4:3': withLabel(2048, 1536),
    '3:4': withLabel(1536, 2048),
    '3:2': withLabel(2048, 1364),
    '2:3': withLabel(1364, 2048),
    '16:9': withLabel(2048, 1152),
    '9:16': withLabel(1152, 2048),
    '21:9': withLabel(2048, 876),
  },
}

const JIMENG_RATIO_MAPS: ResolutionRatioMap = {
  '1K': {
    '1:1': withLabel(1024, 1024),
  },
  '2K': {
    '1:1': withLabel(2048, 2048),
    '4:3': withLabel(2304, 1728),
    '3:2': withLabel(2496, 1664),
    '16:9': withLabel(2560, 1440),
    '21:9': withLabel(3024, 1296),
  },
  '4K': {
    '1:1': withLabel(4096, 4096),
    '4:3': withLabel(4694, 3520),
    '3:2': withLabel(4992, 3328),
    '16:9': withLabel(5404, 3040),
    '21:9': withLabel(6198, 2656),
  },
}

const VOLCARK_RATIO_MAPS: ResolutionRatioMap = {
  '2K': {
    '1:1': withLabel(2048, 2048),
    '4:3': withLabel(2304, 1728),
    '3:4': withLabel(1728, 2304),
    '16:9': withLabel(2848, 1600),
    '9:16': withLabel(1600, 2848),
    '3:2': withLabel(2496, 1664),
    '2:3': withLabel(1664, 2496),
    '21:9': withLabel(3136, 1344),
  },
  '3K': {
    '1:1': withLabel(3072, 3072),
    '4:3': withLabel(3456, 2592),
    '3:4': withLabel(2592, 3456),
    '16:9': withLabel(4096, 2304),
    '9:16': withLabel(2304, 4096),
    '2:3': withLabel(2496, 3744),
    '3:2': withLabel(3744, 2496),
    '21:9': withLabel(4704, 2016),
  },
}

export const PROVIDER_RESOLUTION_MAPS: Record<string, ResolutionRatioMap> = {
  kling: KLING_RATIO_MAPS,
  jimeng: JIMENG_RATIO_MAPS,
  volcark: VOLCARK_RATIO_MAPS,
}

export const BUILTIN_IMAGE_CFG: Record<string, { sizes: string[]; ratios: string[] }> = {
  'gemini-3.1-flash-image-preview-official': { sizes: ['0.5K', '1K', '2K', '4K'], ratios: ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '1:4', '4:1', '1:8', '8:1'] },
  'nano-banana-2': { sizes: ['1K', '2K', '4K'], ratios: ['auto', '1:1', '4:3', '3:4', '16:9', '9:16', '2:3', '3:2', '4:5', '5:4', '21:9'] },
  'gemini-3-pro-image-preview-official': { sizes: ['1K', '2K', '4K'], ratios: ['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9'] },
  'nano-banana-pro': { sizes: ['1K', '2K', '4K'], ratios: ['auto', '1:1', '4:3', '3:4', '16:9', '9:16', '2:3', '3:2', '4:5', '5:4', '21:9'] },
  'gemini-3-pro-image-preview': { sizes: ['1K', '2K', '4K'], ratios: ['1:1', '2:3', '3:2', '3:4', '4:3', '4:5', '5:4', '9:16', '16:9', '21:9'] },
  'imagen-4.0-apimart': { sizes: ['1K'], ratios: ['1:1', '4:3', '3:4', '16:9', '9:16'] },
  'gpt-image-2': { sizes: ['1K', '2K', '4K'], ratios: ['1:1', '16:9', '9:16', '2:1', '1:2', '4:3', '3:4', '3:2', '2:3', '5:4', '4:5', '21:9', '9:21', '3:1', '1:3'] },
  'doubao-seedream-4-5': { sizes: ['2K', '4K'], ratios: [] },
  'doubao-seedance-4-5': { sizes: ['2K', '4K'], ratios: ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '21:9', '9:21'] },
  'doubao-seedream-5-0-lite': { sizes: ['2K', '3K', '4K'], ratios: ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '21:9'] },
}

function parseAspectRatio(ratio: string): number | null {
  const [rawW, rawH] = ratio.split(':').map(Number)
  if (!rawW || !rawH) return null
  return rawW / rawH
}

const BUILTIN_IMAGE_BASE: Record<string, number> = {
  '0.5K': 512,
  '1K': 1024,
  '2K': 2048,
  '3K': 3072,
  '4K': 4096,
}

const BUILTIN_IMAGE_FALLBACK = withLabel(1024, 1024)
const GPT_IMAGE_2_MAX_EDGE = 3840
const GPT_IMAGE_2_MAX_PIXELS = 8294400
const GPT_IMAGE_2_MIN_PIXELS = 655360
const GPT_IMAGE_2_MAX_ASPECT_RATIO = 3
const GPT_IMAGE_2_SIZE_MULTIPLE = 16

const VIDEO_SHORT_SIDE_BY_RESOLUTION: Record<string, number> = {
  '480p': 480,
  '720p': 720,
  '720p_audio': 720,
  '720p_video': 720,
  '768p': 768,
  '1080p': 1080,
  '1080p_audio': 1080,
  '1080p_video': 1080,
  '4k': 2160,
  '4k_audio': 2160,
  '4k_video': 2160,
}

const DEFAULT_IMAGE_DIMENSIONS = BUILTIN_IMAGE_FALLBACK

function resolveBuiltinImageDimensions(ratio: string, resolution: string): RatioEntry {
  const base = BUILTIN_IMAGE_BASE[normalizeImageResolution(resolution)] || BUILTIN_IMAGE_BASE['1K']
  return buildAreaScaledDimensions(base, ratio)
}

function findImageModelConfig(
  item: MediaDimensionItem,
  fallback?: DimensionFallback,
): MediaDimensionConfig | null {
  if (fallback?.imageModelConfig) return fallback.imageModelConfig
  const modelName = item.model_name || fallback?.imageModel
  if (!modelName || !fallback?.imageModels?.length) return null
  const provider = item.provider_code || fallback.imageProvider || ''
  const model = fallback.imageModels.find((option) => {
    const optionName = option.value || option.model_name
    if (optionName !== modelName) return false
    return !provider || !option.provider || option.provider === provider
  })
  return model?.config || null
}

function findVideoModelConfig(
  item: MediaDimensionItem,
  fallback?: DimensionFallback,
): MediaDimensionConfig | null {
  if (fallback?.videoModelConfig) return fallback.videoModelConfig
  const modelName = item.model_name || fallback?.videoModel
  if (!modelName || !fallback?.videoModels?.length) return null
  const provider = item.provider_code || fallback.videoProvider || ''
  const model = fallback.videoModels.find((option) => {
    const optionName = option.value || option.model_name
    if (optionName !== modelName) return false
    return !provider || !option.provider || option.provider === provider
  })
  return model?.config || null
}

function resolveDimensionTableDimensions(
  config: MediaDimensionConfig | null | undefined,
  resolution: string,
  ratio: string,
): RatioEntry | null {
  const table = config?.dimension_table
  const ratioMap = table?.[normalizeImageResolution(resolution)] || table?.[normalizeVideoResolution(resolution)] || table?.[resolution]
  const entry = ratioMap?.[ratio]
  if (!entry?.width || !entry?.height) return null
  return withLabel(entry.width, entry.height)
}

function roundToMultiple(value: number): number {
  return Math.max(GPT_IMAGE_2_SIZE_MULTIPLE, Math.round(value / GPT_IMAGE_2_SIZE_MULTIPLE) * GPT_IMAGE_2_SIZE_MULTIPLE)
}

function floorToMultiple(value: number): number {
  return Math.max(GPT_IMAGE_2_SIZE_MULTIPLE, Math.floor(value / GPT_IMAGE_2_SIZE_MULTIPLE) * GPT_IMAGE_2_SIZE_MULTIPLE)
}

function fitsGptImage2Size(width: number, height: number): boolean {
  if (width <= 0 || height <= 0) return false
  if (width > GPT_IMAGE_2_MAX_EDGE || height > GPT_IMAGE_2_MAX_EDGE) return false
  const pixels = width * height
  if (pixels > GPT_IMAGE_2_MAX_PIXELS || pixels < GPT_IMAGE_2_MIN_PIXELS) return false
  const longest = Math.max(width, height)
  const shortest = Math.min(width, height)
  return longest <= shortest * GPT_IMAGE_2_MAX_ASPECT_RATIO
}

function sizeForShortEdge(shortEdge: number, ratio: string): RatioEntry {
  const [rawW, rawH] = ratio.split(':').map(Number)
  if (!rawW || !rawH) return withLabel(shortEdge, shortEdge)
  if (rawW >= rawH) {
    return withLabel(roundToMultiple((shortEdge * rawW) / rawH), shortEdge)
  }
  return withLabel(shortEdge, roundToMultiple((shortEdge * rawH) / rawW))
}

function sizeForLongEdge(longEdge: number, ratio: string): RatioEntry {
  const [rawW, rawH] = ratio.split(':').map(Number)
  if (!rawW || !rawH) return withLabel(longEdge, longEdge)
  if (rawW >= rawH) {
    return withLabel(longEdge, roundToMultiple((longEdge * rawH) / rawW))
  }
  return withLabel(roundToMultiple((longEdge * rawW) / rawH), longEdge)
}

function largestValidGptImage2Size(ratio: string): RatioEntry {
  const [rawW, rawH] = ratio.split(':').map(Number)
  if (!rawW || !rawH) return withLabel(2880, 2880)
  if (rawW >= rawH) {
    for (let width = GPT_IMAGE_2_MAX_EDGE; width > 0; width -= GPT_IMAGE_2_SIZE_MULTIPLE) {
      const height = floorToMultiple((width * rawH) / rawW)
      if (fitsGptImage2Size(width, height)) return withLabel(width, height)
    }
  } else {
    for (let height = GPT_IMAGE_2_MAX_EDGE; height > 0; height -= GPT_IMAGE_2_SIZE_MULTIPLE) {
      const width = floorToMultiple((height * rawW) / rawH)
      if (fitsGptImage2Size(width, height)) return withLabel(width, height)
    }
  }
  return BUILTIN_IMAGE_FALLBACK
}

function resolveOllamaImageDimensions(ratio: string, resolution: string): RatioEntry {
  const tier = normalizeImageResolution(resolution)
  if (tier === '1K') return sizeForShortEdge(1024, ratio)
  if (tier === '2K') return sizeForLongEdge(2048, ratio)
  if (tier === '4K') return largestValidGptImage2Size(ratio)
  return resolveBuiltinImageDimensions(ratio, resolution)
}

function resolveLiteralDimensions(resolution?: string | null): RatioEntry | null {
  const raw = String(resolution || '').trim()
  const match = raw.match(/^(\d{2,6})\s*[x×]\s*(\d{2,6})$/i)
  if (!match) return null
  const width = Number(match[1])
  const height = Number(match[2])
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null
  return withLabel(width, height)
}

function resolveProviderMapDimensions(provider: string, resolution: string, ratio: string): RatioEntry | null {
  const resolutionMap = PROVIDER_RESOLUTION_MAPS[provider]
  if (!resolutionMap) return null
  const ratioMap = resolutionMap[resolution] || Object.values(resolutionMap)[0] || {}
  const defaultRect = ratioMap['1:1'] || Object.values(ratioMap)[0] || null
  return ratioMap[ratio] || defaultRect
}

function resolvePolicyDimensions(
  policy: string | null | undefined,
  kind: 'image' | 'video',
  ratio: string,
  resolution: string,
): RatioEntry | null {
  if (!policy) return null
  if (policy === 'ollama_gpt_image_2') {
    return resolveOllamaImageDimensions(ratio, resolution)
  }
  if (policy === 'video_short_side') {
    return resolveVideoDimensions(ratio, resolution)
  }
  if (policy === 'image_area' && kind === 'image') {
    return resolveBuiltinImageDimensions(ratio, resolution)
  }
  return null
}

export function resolveMediaModelDimensions({
  config,
  provider,
  model: _model,
  resolution,
  ratio,
  kind = 'image',
}: {
  config?: MediaDimensionConfig | null
  provider?: string | null
  model?: string | null
  resolution?: string | null
  ratio?: string | null
  kind?: 'image' | 'video'
}): RatioEntry {
  const normalizedProvider = provider || ''
  const normalizedRatio = ratio || (kind === 'image' ? '1:1' : '16:9')
  const normalizedResolution = kind === 'image'
    ? normalizeImageResolution(resolution)
    : normalizeVideoResolution(resolution)

  const modelConfigDimensions = resolveDimensionTableDimensions(config, normalizedResolution, normalizedRatio)
  if (modelConfigDimensions) {
    return modelConfigDimensions
  }

  const policyDimensions = resolvePolicyDimensions(
    typeof config?.dimension_policy === 'string' ? config.dimension_policy : null,
    kind,
    normalizedRatio,
    normalizedResolution,
  )
  if (policyDimensions) {
    return policyDimensions
  }

  if (kind === 'image') {
    const providerMapDimensions = resolveProviderMapDimensions(normalizedProvider, normalizedResolution, normalizedRatio)
    if (providerMapDimensions) {
      return providerMapDimensions
    }
  }

  const literalDimensions = resolveLiteralDimensions(normalizedResolution)
  if (literalDimensions) {
    return literalDimensions
  }

  if (kind === 'video') {
    return resolveVideoDimensions(normalizedRatio, normalizedResolution)
  }

  if (normalizedProvider === 'builtin') {
    return resolveBuiltinImageDimensions(normalizedRatio, normalizedResolution)
  }

  if (normalizedProvider === 'ollama') {
    return resolveOllamaImageDimensions(normalizedRatio, normalizedResolution)
  }

  return DEFAULT_IMAGE_DIMENSIONS
}

export function resolveImageModelDimensions(
  config: MediaDimensionConfig | null | undefined,
  provider: string | null | undefined,
  model: string | null | undefined,
  resolution: string,
  ratio: string,
): RatioEntry {
  return resolveMediaModelDimensions({ config, provider, model, resolution, ratio, kind: 'image' })
}

function resolveVideoDimensions(ratio: string, resolution?: string): RatioEntry {
  const shortSide = VIDEO_SHORT_SIDE_BY_RESOLUTION[normalizeVideoResolution(resolution)] || VIDEO_SHORT_SIDE_BY_RESOLUTION['1080p']
  return buildShortSideVideoDimensions(shortSide, ratio)
}

export function resolveConfiguredMediaDimensions(
  item: MediaDimensionItem,
  fallback?: DimensionFallback,
): RatioEntry {
  const isImage = item.type === 'image' || item.type === 'image_generator'
  const ratio = item.aspect_ratio || (isImage ? fallback?.imageRatio : fallback?.videoAspect) || (isImage ? '1:1' : '16:9')
  const provider = item.provider_code || (isImage ? fallback?.imageProvider : fallback?.videoProvider) || ''
  const resolution = isImage
    ? normalizeImageResolution(item.resolution || fallback?.imageRes || '1K')
    : normalizeVideoResolution(item.resolution || fallback?.videoResolution || '720p')

  return resolveMediaModelDimensions({
    config: isImage ? findImageModelConfig(item, fallback) : findVideoModelConfig(item, fallback),
    provider,
    model: item.model_name || (isImage ? fallback?.imageModel : fallback?.videoModel),
    resolution,
    ratio,
    kind: isImage ? 'image' : 'video',
  })
}

export function toRatioEntry(actual?: ActualMediaSize | null): RatioEntry | null {
  if (!actual?.width || !actual?.height) return null
  return withLabel(actual.width, actual.height)
}

export function getMediaDimensions(
  item: MediaDimensionItem,
  fallback?: DimensionFallback,
  actual?: ActualMediaSize | null,
): MediaDimensions {
  const configured = resolveConfiguredMediaDimensions(item, fallback)
  const actualDimensions = toRatioEntry(actual)
  return {
    configured,
    actual: actualDimensions,
    display: actualDimensions || configured,
  }
}

export function getCanvasItemDimensions(
  item: MediaDimensionItem,
  fallback?: DimensionFallback,
): RatioEntry {
  if (item.type === 'brush_path') {
    const brushItem = item as CanvasItem
    return withLabel(brushItem.width || 1, brushItem.height || 1)
  }
  if (item.type === 'text') {
    const estimated = estimateTextCanvasSize({
      text: (item as CanvasItem).text,
      fontSize: (item as CanvasItem).fontSize,
      lineHeight: (item as CanvasItem).lineHeight,
      writingMode: (item as CanvasItem).writingMode,
      width: (item as CanvasItem).width,
      height: (item as CanvasItem).height,
    })
    return withLabel(estimated.width, estimated.height)
  }
  return resolveConfiguredMediaDimensions(item, fallback)
}

export function getCanvasItemPixelSize(
  item: MediaDimensionItem,
  fallback?: DimensionFallback,
) {
  const dimensions = resolveConfiguredMediaDimensions(item, fallback)
  return { w: dimensions.width, h: dimensions.height }
}

export function getClosestImageGenerationDefaults({
  sourceWidth,
  sourceHeight,
  providerCode,
  allowedRatios = ['1:1'],
  allowedResolutions = ['1K'],
}: ClosestImageGenerationDefaultsArgs) {
  const fallback = {
    aspect_ratio: allowedRatios[0] || '1:1',
    resolution: allowedResolutions[0] || '1K',
  }

  if (!sourceWidth || !sourceHeight || sourceWidth <= 0 || sourceHeight <= 0) {
    return fallback
  }

  const sourceRatio = sourceWidth / sourceHeight
  const bestRatio = allowedRatios.reduce((best, candidate) => {
    const candidateRatio = parseAspectRatio(candidate)
    if (!candidateRatio) return best
    const candidateScore = Math.abs(candidateRatio - sourceRatio)
    if (!best) return { value: candidate, score: candidateScore }
    if (candidateScore < best.score) return { value: candidate, score: candidateScore }
    return best
  }, null as { value: string; score: number } | null)

  const aspectRatio = bestRatio?.value || fallback.aspect_ratio
  const resolution = allowedResolutions.reduce((best, candidate) => {
    const dimensions = resolveConfiguredMediaDimensions({
      type: 'image_generator',
      aspect_ratio: aspectRatio,
      provider_code: providerCode || undefined,
      resolution: candidate,
    })
    const widthDelta = Math.abs(dimensions.width - sourceWidth)
    const heightDelta = Math.abs(dimensions.height - sourceHeight)
    const areaDelta = Math.abs((dimensions.width * dimensions.height) - (sourceWidth * sourceHeight))
    const score = areaDelta + ((widthDelta + heightDelta) * 1000)

    if (!best) return { value: candidate, score }
    if (score < best.score) return { value: candidate, score }
    return best
  }, null as { value: string; score: number } | null)

  return {
    aspect_ratio: aspectRatio,
    resolution: resolution?.value || fallback.resolution,
  }
}

export function getDefaultMediaSize(type: CanvasItem['type']): { width: number; height: number } {
  if (type === 'brush_path') {
    return { width: 1, height: 1 }
  }
  if (type === 'text') {
    return estimateTextCanvasSize({})
  }
  const dims = type === 'video' || type === 'video_generator'
    ? resolveVideoDimensions('16:9', '1080p')
    : DEFAULT_IMAGE_DIMENSIONS
  return { width: dims.width, height: dims.height }
}
