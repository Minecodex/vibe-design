type HomepageProvider = {
  code: string
  name: string
  status?: string
  is_builtin?: boolean
}

type HomepageModelConfig = {
  typical_duration?: number
  supports_fast_mode?: boolean
  supports_thinking_mode?: boolean
  thinking_variant_of?: string
  max_reference_images?: number
  supports_reference_image?: boolean
  allowed_aspect_ratios?: string[]
  allowed_aspect_ratios_by_size?: Record<string, string[]>
  allowed_sizes?: string[]
  allowed_durations?: string[]
  allowed_durations_by_mode?: Partial<Record<'text' | 'reference' | 'frames', string[]>>
  min_duration?: number
  max_duration?: number
}

export type HomeSelectableModel = {
  name: string
  value: string
  provider: string
  providerName: string
  description?: string
  tag?: string
  config?: HomepageModelConfig
  supportsFastMode?: boolean
  supportsThinkingMode?: boolean
  thinkingVariantOf?: string
  maxReferenceImages?: number
  supportsReferenceImages?: boolean
}

type HomepageRegistryModel = {
  model_name: string
  label?: string
  description?: string
  config?: HomepageModelConfig
}

type HomepageRegistry = Record<string, {
  models?: Record<string, HomepageRegistryModel[]>
}>

type HomepageEnabledModel = {
  model_name: string
  model_type: string
  is_enabled?: boolean
}

export function buildHomepageSelectableModels(
  authorizedProviders: HomepageProvider[],
  registry: HomepageRegistry,
  enabledModelsByProvider: Record<string, HomepageEnabledModel[]>,
) {
  const imageModels: HomeSelectableModel[] = []
  const videoModels: HomeSelectableModel[] = []
  const multimodalModels: HomeSelectableModel[] = []

  for (const provider of authorizedProviders) {
    let enabledModels = (enabledModelsByProvider[provider.code] || []).filter(model => model.is_enabled)

    if (provider.is_builtin && enabledModels.length === 0) {
      const providerRegistry = registry[provider.code]
      const text2image = providerRegistry?.models?.text2image || []
      const text2video = providerRegistry?.models?.text2video || []
      const multimodal = providerRegistry?.models?.multimodal || []
      enabledModels = [
        ...text2image.map(model => ({ model_name: model.model_name, model_type: 'text2image', is_enabled: true })),
        ...text2video.map(model => ({ model_name: model.model_name, model_type: 'text2video', is_enabled: true })),
        ...multimodal.map(model => ({ model_name: model.model_name, model_type: 'multimodal', is_enabled: true })),
      ]
    }

    for (const model of enabledModels) {
      const providerRegistry = registry[provider.code]
      const typeModels = providerRegistry?.models?.[model.model_type] || []
      const registryModel = typeModels.find(entry => entry.model_name === model.model_name)
      const registryDescription = typeof registryModel?.description === 'string'
        ? registryModel.description
        : undefined
      const registryConfig = registryModel?.config
      const maxReferenceImages = typeof registryModel?.config?.max_reference_images === 'number'
        ? Math.max(0, registryModel.config.max_reference_images)
        : undefined

      const mappedModel: HomeSelectableModel = {
        name: registryModel?.label || model.model_name,
        value: model.model_name,
        provider: provider.code,
        providerName: provider.name,
        description: registryDescription || provider.name,
        tag: registryModel?.config?.typical_duration ? `${registryModel.config.typical_duration}s` : undefined,
        ...(registryConfig ? { config: registryConfig } : {}),
        supportsFastMode: registryModel?.config?.supports_fast_mode,
        supportsThinkingMode: registryModel?.config?.supports_thinking_mode,
        thinkingVariantOf: registryModel?.config?.thinking_variant_of,
        maxReferenceImages,
        supportsReferenceImages: maxReferenceImages != null
          ? maxReferenceImages > 0
          : registryModel?.config?.supports_reference_image,
      }

      if (model.model_type === 'text2image') {
        imageModels.push(mappedModel)
      } else if (model.model_type === 'text2video') {
        videoModels.push(mappedModel)
      } else if (model.model_type === 'multimodal') {
        multimodalModels.push(mappedModel)
      }
    }
  }

  return {
    imageModels,
    videoModels,
    multimodalModels,
  }
}

export function fillHomepageDefaultModelPreferences(
  prefs: {
    image_model?: string
    image_provider?: string
    video_model?: string
    video_provider?: string
    multimodal_model?: string
    multimodal_provider?: string
    auto?: boolean
  },
  catalogs: {
    imageModels: HomeSelectableModel[]
    videoModels: HomeSelectableModel[]
    multimodalModels: HomeSelectableModel[]
  },
  thinkingEnabled: boolean,
) {
  const next = { ...prefs }
  const preferredVideoModel = catalogs.videoModels.find((model) => model.value === 'kling-v3')
  const currentImageValid = catalogs.imageModels.some(model =>
    model.value === next.image_model && model.provider === next.image_provider,
  )
  const currentVideoValid = catalogs.videoModels.some(model =>
    model.value === next.video_model && model.provider === next.video_provider,
  )

  if (!currentImageValid && catalogs.imageModels.length > 0) {
    next.image_model = catalogs.imageModels[0].value
    next.image_provider = catalogs.imageModels[0].provider
  }

  if (!currentVideoValid && catalogs.videoModels.length > 0) {
    next.video_model = (preferredVideoModel || catalogs.videoModels[0]).value
    next.video_provider = (preferredVideoModel || catalogs.videoModels[0]).provider
  }

  const filteredMultimodalModels = filterHomepageMultimodalModels(catalogs.multimodalModels, thinkingEnabled)
  const currentMultimodalValid = filteredMultimodalModels.some(model =>
    model.value === next.multimodal_model && model.provider === next.multimodal_provider,
  )

  if (!currentMultimodalValid) {
    const defaultMultimodal = pickHomepageDefaultMultimodalModel(catalogs.multimodalModels, thinkingEnabled)
    if (defaultMultimodal) {
      next.multimodal_model = defaultMultimodal.value
      next.multimodal_provider = defaultMultimodal.provider
    }
  }

  return next
}

const DEFAULT_MULTIMODAL_MODEL_BY_MODE = {
  fast: 'kimi-k2.5',
} as const

export function filterHomepageMultimodalModels(
  models: HomeSelectableModel[],
  thinkingEnabled: boolean,
) {
  if (thinkingEnabled) {
    return models.filter(model => model.provider === 'ollama' || model.supportsThinkingMode === true)
  }

  return models.filter(model => model.provider === 'ollama' || model.supportsFastMode === true)
}

export function pickHomepageDefaultMultimodalModel(
  models: HomeSelectableModel[],
  thinkingEnabled: boolean,
) {
  const eligibleModels = filterHomepageMultimodalModels(models, thinkingEnabled)
  const defaultValue = thinkingEnabled ? undefined : DEFAULT_MULTIMODAL_MODEL_BY_MODE.fast

  if (defaultValue) {
    const preferredModel = eligibleModels.find(model => model.value === defaultValue)
    if (preferredModel) {
      return preferredModel
    }
  }

  if (eligibleModels.length > 0) {
    return eligibleModels[0]
  }

  return models[0]
}

type HomepageSelectedMultimodalModelRef = {
  value?: string
  provider?: string
}

function findHomepageSelectedModel(
  models: HomeSelectableModel[],
  current: HomepageSelectedMultimodalModelRef,
) {
  return models.find(model => model.value === current.value && model.provider === current.provider)
}

function findHomepageThinkingPair(
  models: HomeSelectableModel[],
  current: HomepageSelectedMultimodalModelRef,
) {
  return models.find(
    model =>
      model.provider === current.provider &&
      model.thinkingVariantOf === current.value &&
      model.supportsThinkingMode === true,
  )
}

function findHomepageFastPair(
  models: HomeSelectableModel[],
  currentModel: HomeSelectableModel | undefined,
) {
  if (!currentModel?.thinkingVariantOf) return undefined

  return models.find(
    model =>
      model.provider === currentModel.provider &&
      model.value === currentModel.thinkingVariantOf,
  )
}

export function isHomepageThinkingModeAvailableForModel(
  models: HomeSelectableModel[],
  current: HomepageSelectedMultimodalModelRef,
) {
  const currentModel = findHomepageSelectedModel(models, current)
  if (current.provider === 'ollama') return true
  if (currentModel?.supportsThinkingMode === true) return true
  return Boolean(findHomepageThinkingPair(models, current))
}

export function getHomepageModeSwitchTargetMultimodalModel(
  models: HomeSelectableModel[],
  thinkingEnabled: boolean,
  nextThinkingEnabled: boolean,
  current: HomepageSelectedMultimodalModelRef,
) {
  const currentModel = findHomepageSelectedModel(models, current)

  if (thinkingEnabled === nextThinkingEnabled) {
    return currentModel
  }

  if (nextThinkingEnabled) {
    if (current.provider === 'ollama') return currentModel
    return findHomepageThinkingPair(models, current) ?? pickHomepageDefaultMultimodalModel(models, true)
  }

  if (current.provider === 'ollama') return currentModel
  if (currentModel?.supportsFastMode === true) return currentModel
  return findHomepageFastPair(models, currentModel) ?? pickHomepageDefaultMultimodalModel(models, false)
}
