import { useCallback, useEffect, useState } from 'react'
import i18n from '@/i18n'
import type { CanvasItem } from '@/api/endpoints/projects'
import { useAppConfigStore } from '@/store/appConfigStore'
import { resolveLocalizedProviderName } from '@/config/brand'
import { normalizeCanvasAgentMediaRef } from '../canvasMediaUrl'
import { DEFAULT_IMAGE_MODEL } from '../defaultModels'
import {
  normalizeReferenceImages,
} from '../generatorCapabilities'
import { loadCanvasModelCatalog } from '../canvasModelCatalog'
import { PROVIDER_RESOLUTION_MAPS, getCanvasItemDimensions } from '../mediaDimensions'
import {
  findImageModelOption,
  getAllowedImageRatios,
  getAllowedImageResolutions,
  getResolvedImageModelCapability,
} from '../imageModelConfig'
import {
  findVideoModelOption,
  getAllowedVideoRatios,
  getAllowedVideoResolutions,
  getResolvedVideoDurationsFromConfig,
  getResolvedVideoModelCapability,
} from '../videoModelConfig'

type ModelOption = {
  name: string
  value: string
  provider: string
  providerName: string
  isBuiltin: boolean
  config?: any
}

type UseGeneratorControlsArgs = {
  canvasItemsLoaded: boolean
  updateCanvasItems: (
    updater: (items: CanvasItem[]) => CanvasItem[],
    options?: { skipHistory?: boolean }
  ) => void
}

const HIDDEN_VIDEO_MODELS = new Set<string>()

const DEFAULT_VIDEO_MODEL = 'kling-v3'

function resolveDefaultVideoOption(videoModels: ModelOption[]) {
  return videoModels.find(model => model.value === DEFAULT_VIDEO_MODEL) || videoModels[0]
}

export function useGeneratorControls({
  canvasItemsLoaded,
  updateCanvasItems,
}: UseGeneratorControlsArgs) {
  const appName = useAppConfigStore((s) => s.appName)
  const appNameEn = useAppConfigStore((s) => s.appNameEn)
  const brand = { appName, appNameEn }
  const [imageModel, setImageModel] = useState('')
  const [imageProvider, setImageProvider] = useState('')
  const [videoModel, setVideoModel] = useState('')
  const [videoProvider, setVideoProvider] = useState('')
  const [availableImageModels, setAvailableImageModels] = useState<ModelOption[]>([])
  const [availableVideoModels, setAvailableVideoModels] = useState<ModelOption[]>([])
  const [imageRes, setImageRes] = useState('1K')
  const [imageRatio, setImageRatio] = useState('1:1')
  const [videoAspect, setVideoAspect] = useState('16:9')
  const [videoDuration, setVideoDuration] = useState('5s')
  const [videoQuality, setVideoQuality] = useState('720p')

  const loadPersistedGeneratorMeta = useCallback((meta: any) => {
    if (!meta) return

    if (meta.imageModel) setImageModel(meta.imageModel)
    if (meta.imageProvider) setImageProvider(meta.imageProvider)
    setImageRes(meta.imageRes || '1K')
    setImageRatio(meta.imageRatio || '1:1')
    if (meta.videoModel && !HIDDEN_VIDEO_MODELS.has(meta.videoModel)) setVideoModel(meta.videoModel)
    if (meta.videoProvider && !HIDDEN_VIDEO_MODELS.has(meta.videoModel)) setVideoProvider(meta.videoProvider)
    setVideoAspect(meta.videoAspect || '16:9')
    setVideoDuration(meta.videoDuration || '5s')
    setVideoQuality(meta.videoResolution || meta.videoQuality || '720p')
  }, [])

  const buildCanvasMeta = useCallback(() => ({
    id: 'global_state',
    type: 'meta',
    imageModel,
    imageProvider,
    imageRes,
    imageRatio,
    videoModel,
    videoProvider,
    videoAspect,
    videoDuration,
    videoResolution: videoQuality,
  }), [imageModel, imageProvider, imageRes, imageRatio, videoModel, videoProvider, videoAspect, videoDuration, videoQuality])

  const getItemDims = useCallback((item: CanvasItem) => {
    const isImage = item.type === 'image' || item.type === 'image_generator'
    const resolvedImageModel = item.model_name || imageModel
    const resolvedImageProvider = item.provider_code || imageProvider
    const modelConfig = isImage
      ? findImageModelOption(availableImageModels, resolvedImageModel, resolvedImageProvider)?.config
      : findVideoModelOption(availableVideoModels, item.model_name || videoModel, item.provider_code || videoProvider)?.config
    return getCanvasItemDimensions(item, {
      imageRatio,
      videoAspect,
      imageProvider,
      videoProvider,
      imageRes,
      videoResolution: videoQuality,
      imageModel: imageModel,
      videoModel,
      imageModelConfig: isImage ? modelConfig : null,
      videoModelConfig: isImage ? null : modelConfig,
      imageModels: availableImageModels,
      videoModels: availableVideoModels,
    })
  }, [availableImageModels, availableVideoModels, imageModel, imageProvider, imageRatio, imageRes, videoAspect, videoModel, videoProvider, videoQuality])

  const getItemAmountCents = useCallback((item: CanvasItem): number | null => {
    const isImage = item.type === 'image_generator'
    const modelName = item.model_name || (isImage ? imageModel : videoModel)
    const providerCode = item.provider_code || (isImage ? imageProvider : videoProvider)
    if (providerCode !== 'builtin') return null

    const models = isImage ? availableImageModels : availableVideoModels
    const model = models.find(m => m.value === modelName)
    if (!model?.config?.pricing_cents) return null

    const pricing = model.config.pricing_cents as Record<string, number>
    const pricingMode = model.config.pricing_mode as string

    if (pricingMode === 'flat') {
      return pricing.flat || 0
    }
    if (pricingMode === 'per_resolution') {
      const res = isImage ? (item.resolution || imageRes) : (item.resolution || videoQuality)
      return pricing[res] || 0
    }
    if (pricingMode === 'per_second') {
      const baseResolution = item.resolution || videoQuality
      const duration = parseInt(item.duration || videoDuration) || 5
      let pricingKey = baseResolution
      if (modelName === 'kling-v3') {
        const normalizedResolution = baseResolution.toLowerCase()
        const baseKey = normalizedResolution.replace('_audio', '').replace('_video', '')
        const hasReferenceImages = normalizeReferenceImages(item).length > 0
        const hasFrameInputs = Boolean(item.first_frame_image || item.tail_frame_image)
        const hasImageInputs = hasReferenceImages || hasFrameInputs
        const hasAudio = Boolean((item as any).audio) || normalizedResolution.endsWith('_audio')

        if (hasAudio && pricing[`${baseKey}_audio`] != null) {
          pricingKey = `${baseKey}_audio`
        } else if (hasImageInputs && pricing[`${baseKey}_video`] != null) {
          pricingKey = `${baseKey}_video`
        } else {
          pricingKey = baseKey
        }
      }
      const rate = pricing[pricingKey] || 0
      return rate * duration
    }
    return null
  }, [
    availableImageModels,
    availableVideoModels,
    imageModel,
    imageProvider,
    imageRes,
    videoDuration,
    videoModel,
    videoProvider,
    videoQuality,
  ])

  const withReferenceImages = useCallback((referenceImages: string[]): Partial<CanvasItem> => {
    const normalizedReferenceImages = referenceImages
      .map((referenceImage) => normalizeCanvasAgentMediaRef(referenceImage))
      .filter(Boolean)
    return {
      reference_images: normalizedReferenceImages,
      reference_image: normalizedReferenceImages[0] || '',
    }
  }, [])

  const getItemReferenceImages = useCallback((item: CanvasItem) => (
    normalizeReferenceImages(item)
      .map((referenceImage) => normalizeCanvasAgentMediaRef(
        referenceImage,
        (item as any).agent_conversation_id ?? null,
      ))
      .filter(Boolean)
  ), [])

  const getResolvedImageCapability = useCallback((item: CanvasItem) => {
    return getResolvedImageModelCapability(
      availableImageModels,
      item.model_name || imageModel,
      item.provider_code || imageProvider,
    )
  }, [availableImageModels, imageModel, imageProvider])

  const getResolvedVideoCapability = useCallback((item: CanvasItem) => {
    return getResolvedVideoModelCapability(
      availableVideoModels,
      item.model_name || videoModel,
      item.provider_code || videoProvider,
    )
  }, [availableVideoModels, videoModel, videoProvider])

  const getResolvedVideoDurations = useCallback((
    item: CanvasItem,
    overrides?: Partial<CanvasItem>,
    modelNameOverride?: string,
    fallbackDurations?: string[],
  ) => {
    const nextItem = { ...item, ...overrides }
    const resolvedModelName = modelNameOverride || nextItem.model_name || videoModel
    return getResolvedVideoDurationsFromConfig(
      availableVideoModels,
      nextItem,
      resolvedModelName,
      nextItem.provider_code || item.provider_code || videoProvider,
      fallbackDurations,
    )
  }, [availableVideoModels, videoModel, videoProvider])

  useEffect(() => {
    if (!canvasItemsLoaded) return

    updateCanvasItems(prev => {
      let changed = false
      const next = prev.map(item => {
        if (item.type !== 'video_generator') return item

        const resolvedModelName = item.model_name || videoModel
        const modelConfig = availableVideoModels.find(model => model.value === resolvedModelName)?.config
        const allowedDurations = getResolvedVideoDurations(
          item,
          undefined,
          resolvedModelName,
          modelConfig?.allowed_durations,
        )
        const currentDuration = item.duration || videoDuration

        if (allowedDurations.length > 0 && !allowedDurations.includes(currentDuration)) {
          changed = true
          return { ...item, duration: allowedDurations[0] }
        }

        return item
      })

      return changed ? next : prev
    }, { skipHistory: true })
  }, [availableVideoModels, canvasItemsLoaded, getResolvedVideoDurations, updateCanvasItems, videoDuration, videoModel])

  useEffect(() => {
    async function fetchModels() {
      try {
        const { registry, providers } = await loadCanvasModelCatalog()

        const imageModels: ModelOption[] = []
        const videoModels: ModelOption[] = []

        for (const { provider, models } of providers) {
          try {
            let enabledModels = models.filter(model => model.is_enabled)

            if (provider.is_builtin && enabledModels.length === 0) {
              const providerRegistry = registry[provider.code]
              const text2image = providerRegistry?.models?.text2image || (providerRegistry as any)?.text2image || []
              const text2video = providerRegistry?.models?.text2video || (providerRegistry as any)?.text2video || []

              enabledModels = [
                ...text2image.map((model) => ({ model_name: model.model_name, model_type: 'text2image', is_enabled: true } as any)),
                ...text2video.map((model) => ({ model_name: model.model_name, model_type: 'text2video', is_enabled: true } as any)),
              ]
            }

            for (const model of enabledModels) {
              const providerRegistry = registry[provider.code]
              const typeModels = providerRegistry?.models?.[model.model_type] || (providerRegistry as any)?.[model.model_type] || []
              const registryModel = (typeModels as any[]).find(entry => entry.model_name === model.model_name)
              const label = registryModel?.label || model.model_name

              if (model.model_type === 'text2image') {
                imageModels.push({
                  name: label,
                  value: model.model_name,
                  provider: provider.code,
                  providerName: provider.code === 'builtin'
                    ? resolveLocalizedProviderName(i18n.language, brand, provider.code, provider.name)
                    : provider.name,
                  isBuiltin: !!provider.is_builtin,
                  config: registryModel?.config,
                })
              } else if (model.model_type === 'text2video') {
                videoModels.push({
                  name: label,
                  value: model.model_name,
                  provider: provider.code,
                  providerName: provider.code === 'builtin'
                    ? resolveLocalizedProviderName(i18n.language, brand, provider.code, provider.name)
                    : provider.name,
                  isBuiltin: !!provider.is_builtin,
                  config: registryModel?.config,
                })
              }
            }
          } catch (error) {
            console.error('Failed to fetch models for provider:', provider.code, error)
          }
        }

        setAvailableImageModels(imageModels)
        setAvailableVideoModels(videoModels)

        if (imageModels.length > 0) {
          const fallbackImageModel = imageModels.find(model => model.value === DEFAULT_IMAGE_MODEL) || imageModels[0]
          setImageModel(prev => prev || fallbackImageModel.value)
          setImageProvider(prev => prev || fallbackImageModel.provider)
        }
        if (videoModels.length > 0) {
          const defaultVideoModel = resolveDefaultVideoOption(videoModels)
          setVideoModel(prev => {
            if (!prev || HIDDEN_VIDEO_MODELS.has(prev) || !videoModels.some(model => model.value === prev)) {
              return defaultVideoModel.value
            }
            return prev
          })
          setVideoProvider(prev => prev || defaultVideoModel.provider)
        }
      } catch (error) {
        console.error('Failed to fetch models', error)
      }
    }

    fetchModels()
  }, [appName, appNameEn])

  useEffect(() => {
    if (availableImageModels.length === 0) return

    const currentModelExists = availableImageModels.some(model =>
      model.value === imageModel && model.provider === imageProvider,
    )

    if (!currentModelExists) {
      const fallbackImageModel = availableImageModels.find(model => model.value === DEFAULT_IMAGE_MODEL) || availableImageModels[0]
      if (imageModel !== fallbackImageModel.value) {
        setImageModel(fallbackImageModel.value)
      }
      if (imageProvider !== fallbackImageModel.provider) {
        setImageProvider(fallbackImageModel.provider)
      }
    }
  }, [availableImageModels, imageModel, imageProvider])

  useEffect(() => {
    const currentImageModel = findImageModelOption(availableImageModels, imageModel, imageProvider)
    const allowedSizes = getAllowedImageResolutions(currentImageModel?.config)
    const allowedRatios = getAllowedImageRatios(currentImageModel?.config)

    if (currentImageModel?.config) {
      if (!allowedSizes.includes(imageRes) && allowedSizes.length > 0) {
        setImageRes(allowedSizes[0])
      }
      if (!allowedRatios.includes(imageRatio) && allowedRatios.length > 0) {
        setImageRatio(allowedRatios[0])
      }
      return
    }

    const resolutionMap = PROVIDER_RESOLUTION_MAPS[imageProvider] || Object.values(PROVIDER_RESOLUTION_MAPS)[0]
    const resolutionTiers = Object.keys(resolutionMap)
    if (!resolutionTiers.includes(imageRes)) {
      setImageRes(resolutionTiers[0])
    }
    const ratioMap = resolutionMap[imageRes] || resolutionMap[resolutionTiers[0]] || {}
    if (!ratioMap[imageRatio]) {
      const firstRatio = Object.keys(ratioMap)[0]
      if (firstRatio) setImageRatio(firstRatio)
    }
  }, [availableImageModels, imageModel, imageProvider, imageRatio, imageRes])

  useEffect(() => {
    if (imageProvider === 'builtin') return

    const resolutionMap = PROVIDER_RESOLUTION_MAPS[imageProvider] || Object.values(PROVIDER_RESOLUTION_MAPS)[0]
    const ratioMap = resolutionMap[imageRes] || {}
    if (!ratioMap[imageRatio]) {
      const firstRatio = Object.keys(ratioMap)[0]
      if (firstRatio) setImageRatio(firstRatio)
    }
  }, [imageProvider, imageRatio, imageRes])

  useEffect(() => {
    const currentVideoModel = findVideoModelOption(availableVideoModels, videoModel, videoProvider)
    const allowedVideoSizes = getAllowedVideoResolutions(currentVideoModel?.config)
    const allowedVideoRatios = getAllowedVideoRatios(currentVideoModel?.config)
    const allowedVideoDurations = getResolvedVideoDurationsFromConfig(
      availableVideoModels,
      {},
      videoModel,
      videoProvider,
      currentVideoModel?.config?.allowed_durations,
    )

    if (currentVideoModel?.config) {
      if (!allowedVideoSizes.includes(videoQuality) && allowedVideoSizes.length > 0) {
        setVideoQuality(allowedVideoSizes[0])
      }
      if (!allowedVideoRatios.includes(videoAspect) && allowedVideoRatios.length > 0) {
        setVideoAspect(allowedVideoRatios[0])
      }
      if (!allowedVideoDurations.includes(videoDuration) && allowedVideoDurations.length > 0) {
        setVideoDuration(allowedVideoDurations[0])
      }
      return
    }

    const resolutionMap = PROVIDER_RESOLUTION_MAPS[videoProvider] || Object.values(PROVIDER_RESOLUTION_MAPS)[0]
    const ratioMap = resolutionMap[videoQuality] || resolutionMap[Object.keys(resolutionMap)[0]] || {}
    if (!ratioMap[videoAspect]) {
      const firstRatio = Object.keys(ratioMap)[0]
      if (firstRatio) setVideoAspect(firstRatio)
    }
  }, [availableVideoModels, videoAspect, videoDuration, videoModel, videoProvider, videoQuality])

  useEffect(() => {
    if (availableVideoModels.length === 0) return

    const defaultVideoModel = resolveDefaultVideoOption(availableVideoModels)
    const currentModel = availableVideoModels.find(model => model.value === videoModel)

    if (!currentModel) {
      if (videoModel !== defaultVideoModel.value) {
        setVideoModel(defaultVideoModel.value)
      }
      if (videoProvider !== defaultVideoModel.provider) {
        setVideoProvider(defaultVideoModel.provider)
      }
    }
  }, [availableVideoModels, videoModel, videoProvider])

  useEffect(() => {
    if (!canvasItemsLoaded || availableVideoModels.length === 0) return

    const defaultVideoModel = resolveDefaultVideoOption(availableVideoModels)

    updateCanvasItems(prev => {
      let changed = false
      const next = prev.map(item => {
        if (item.type !== 'video_generator') return item

        const modelHidden = !item.model_name || HIDDEN_VIDEO_MODELS.has(item.model_name)
        const modelMissing = !!item.model_name && !availableVideoModels.some(model => model.value === item.model_name)
        if (!modelHidden && !modelMissing) {
          return item
        }

        changed = true
        return {
          ...item,
          model_name: defaultVideoModel.value,
          provider_code: defaultVideoModel.provider,
        }
      })

      return changed ? next : prev
    }, { skipHistory: true })
  }, [availableVideoModels, canvasItemsLoaded, updateCanvasItems])

  return {
    imageModel,
    setImageModel,
    imageProvider,
    setImageProvider,
    videoModel,
    setVideoModel,
    videoProvider,
    setVideoProvider,
    availableImageModels,
    availableVideoModels,
    imageRes,
    setImageRes,
    imageRatio,
    setImageRatio,
    videoAspect,
    setVideoAspect,
    videoDuration,
    setVideoDuration,
    setVideoQuality,
    videoQuality,
    loadPersistedGeneratorMeta,
    buildCanvasMeta,
    getItemDims,
    getItemAmountCents,
    withReferenceImages,
    getItemReferenceImages,
    getResolvedImageCapability,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
  }
}
