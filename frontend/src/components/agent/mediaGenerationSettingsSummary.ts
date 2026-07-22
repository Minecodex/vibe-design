import type { TFunction } from 'i18next'

import type {
  ImageGenerationModelSettings,
  MediaGenerationSettings,
  VideoGenerationModelSettings,
} from '@/types/modelPreferences'

export type MediaGenerationSettingsType = 'image' | 'video'

export interface MediaGenerationSummaryModel {
  value?: string
  provider?: string
}

export interface MediaGenerationSummaryPreferences {
  media_generation_settings?: MediaGenerationSettings
}

export function getMediaGenerationSettingsSummary({
  type,
  model,
  preferences,
  t,
}: {
  type: MediaGenerationSettingsType
  model?: MediaGenerationSummaryModel | null
  preferences: MediaGenerationSummaryPreferences
  t: TFunction
}): string[] {
  const modelKey = getMediaGenerationModelKey(model)
  const settings = getModelSettings(preferences.media_generation_settings, type, modelKey)
  const autoLabel = String(t('agent.modelGenerationSettings.auto'))

  if (type === 'image') {
    const imageSettings = settings as ImageGenerationModelSettings
    return [
      `${t('agent.modelGenerationSettings.imageResolution')}: ${imageSettings.resolution || autoLabel}`,
      `${t('agent.modelGenerationSettings.imageAspectRatio')}: ${imageSettings.aspect_ratio || autoLabel}`,
    ]
  }

  const videoSettings = settings as VideoGenerationModelSettings
  return [
    `${t('agent.modelGenerationSettings.videoResolution')}: ${videoSettings.resolution || autoLabel}`,
    `${t('agent.modelGenerationSettings.canvasAspectRatio')}: ${videoSettings.aspect_ratio || autoLabel}`,
    `${t('agent.modelGenerationSettings.videoDuration')}: ${
      videoSettings.duration == null ? autoLabel : formatDurationLabel(t, String(videoSettings.duration))
    }`,
  ]
}

function getMediaGenerationModelKey(model?: MediaGenerationSummaryModel | null): string | null {
  const modelName = String(model?.value || '').trim()
  if (!modelName) return null
  return `${String(model?.provider || 'builtin').trim() || 'builtin'}:${modelName}`
}

function getModelSettings(
  settings: MediaGenerationSettings | undefined,
  type: MediaGenerationSettingsType,
  modelKey: string | null,
): ImageGenerationModelSettings | VideoGenerationModelSettings {
  if (!modelKey) return {}
  return { ...settings?.[type]?.[modelKey] }
}

function parseDurationValue(value: string): number | undefined {
  const normalized = String(value || '').trim().toLowerCase().replace(/s$/, '')
  const parsed = Number.parseInt(normalized, 10)
  return Number.isFinite(parsed) ? parsed : undefined
}

function formatDurationLabel(t: TFunction, value: string) {
  const duration = parseDurationValue(value)
  if (duration == null) return value
  return String(t('agent.modelGenerationSettings.seconds', { count: duration, defaultValue: '{{count}}s' }))
}
