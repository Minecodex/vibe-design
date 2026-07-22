import { DEFAULT_IMAGE_MODEL_LABEL } from './defaultModels'
import type { MediaGenerationSettings } from '@/types/modelPreferences'

export interface SelectableMultimodalModel {
  name: string
  value: string
  provider: string
  providerName?: string
  description?: string
  tag?: string
  supportsFastMode?: boolean
  supportsThinkingMode?: boolean
  thinkingVariantOf?: string
}

export interface SelectableMediaModel {
  name: string
  value: string
  provider: string
}

export interface CanvasModelPreferences {
  image_model?: string
  image_provider?: string
  video_model?: string
  video_provider?: string
  multimodal_model?: string
  multimodal_provider?: string
  media_generation_settings?: MediaGenerationSettings
  auto?: boolean
}

const DEFAULT_MULTIMODAL_MODELS = {
  fast: 'kimi-k2.5',
  plan: 'claude-opus-4-6-thinking',
} as const

export function pickDefaultMultimodalModel(
  models: SelectableMultimodalModel[],
  mode: 'plan' | 'fast',
) {
  const eligibleModels = filterMultimodalModelsForMode(models, mode)
  const ollamaModel = eligibleModels.find(model => model.provider === 'ollama')
  if (ollamaModel) return ollamaModel

  const preferredValue = DEFAULT_MULTIMODAL_MODELS[mode]
  const preferredByValue = eligibleModels.find(model => model.value === preferredValue)
  if (preferredByValue) return preferredByValue

  if (eligibleModels.length > 0) return eligibleModels[0]

  return models[0]
}

export function filterMultimodalModelsForMode(
  models: SelectableMultimodalModel[],
  mode: 'plan' | 'fast',
) {
  if (mode === 'plan') {
    return models.filter(model => model.provider === 'ollama' || model.supportsThinkingMode === true)
  }

  return models.filter(model => model.provider === 'ollama' || model.supportsFastMode === true)
}

type SelectedMultimodalModelRef = {
  value?: string
  provider?: string
}

function findSelectedModel(
  models: SelectableMultimodalModel[],
  current: SelectedMultimodalModelRef,
) {
  return models.find(model => model.value === current.value && model.provider === current.provider)
}

function findThinkingPair(
  models: SelectableMultimodalModel[],
  current: SelectedMultimodalModelRef,
) {
  return models.find(
    model =>
      model.provider === current.provider &&
      model.thinkingVariantOf === current.value &&
      model.supportsThinkingMode === true,
  )
}

function findFastPair(
  models: SelectableMultimodalModel[],
  currentModel: SelectableMultimodalModel | undefined,
) {
  if (!currentModel?.thinkingVariantOf) return undefined

  return models.find(
    model =>
      model.provider === currentModel.provider &&
      model.value === currentModel.thinkingVariantOf,
  )
}

export function isThinkingModeAvailableForMultimodalModel(
  models: SelectableMultimodalModel[],
  current: SelectedMultimodalModelRef,
) {
  const currentModel = findSelectedModel(models, current)
  if (current.provider === 'ollama') return true
  if (currentModel?.supportsThinkingMode === true) return true
  return Boolean(findThinkingPair(models, current))
}

export function getModeSwitchTargetMultimodalModel(
  models: SelectableMultimodalModel[],
  currentMode: 'plan' | 'fast',
  nextMode: 'plan' | 'fast',
  current: SelectedMultimodalModelRef,
) {
  const currentModel = findSelectedModel(models, current)

  if (nextMode === currentMode) {
    return currentModel
  }

  if (nextMode === 'plan') {
    if (current.provider === 'ollama') return currentModel
    return findThinkingPair(models, current) ?? pickDefaultMultimodalModel(models, nextMode)
  }

  if (current.provider === 'ollama') return currentModel
  if (currentModel?.supportsFastMode === true) return currentModel
  return findFastPair(models, currentModel) ?? pickDefaultMultimodalModel(models, nextMode)
}

export function resolveCanvasModelPreferences(
  prefs: CanvasModelPreferences,
  catalogs: {
    imageModels: SelectableMediaModel[]
    videoModels: SelectableMediaModel[]
    multimodalModels: SelectableMultimodalModel[]
  },
  mode: 'plan' | 'fast',
) {
  const next = { ...prefs }
  const currentImageValid = catalogs.imageModels.some(model =>
    model.value === next.image_model && model.provider === next.image_provider,
  )
  const currentVideoValid = catalogs.videoModels.some(model =>
    model.value === next.video_model && model.provider === next.video_provider,
  )
  const currentMultimodalValid = filterMultimodalModelsForMode(catalogs.multimodalModels, mode).some(model =>
    model.value === next.multimodal_model && model.provider === next.multimodal_provider,
  )

  if (!currentImageValid && catalogs.imageModels.length > 0) {
    const defaultImage = catalogs.imageModels.find(model => model.name === DEFAULT_IMAGE_MODEL_LABEL) || catalogs.imageModels[0]
    next.image_model = defaultImage.value
    next.image_provider = defaultImage.provider
  }

  if (!currentVideoValid && catalogs.videoModels.length > 0) {
    const defaultVideo = catalogs.videoModels.find(model => model.value === 'kling-v3') || catalogs.videoModels[0]
    next.video_model = defaultVideo.value
    next.video_provider = defaultVideo.provider
  }

  if (!currentMultimodalValid && catalogs.multimodalModels.length > 0) {
    const defaultMultimodal = pickDefaultMultimodalModel(catalogs.multimodalModels, mode)
    if (defaultMultimodal) {
      next.multimodal_model = defaultMultimodal.value
      next.multimodal_provider = defaultMultimodal.provider
    }
  }

  return next
}
