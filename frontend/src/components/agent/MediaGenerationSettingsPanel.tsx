import { Check, ChevronDown, SlidersHorizontal } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import {
  getAllowedImageRatiosForResolution,
  getAllowedImageResolutions,
  type ImageModelRegistryConfig,
} from '@/pages/dashboard/CanvasPage/imageModelConfig'
import { getAllowedVideoDurations } from '@/pages/dashboard/CanvasPage/generatorCapabilities'
import {
  getAllowedVideoRatios,
  getAllowedVideoResolutions,
  getVideoCapabilityFromConfig,
  type VideoModelRegistryConfig,
} from '@/pages/dashboard/CanvasPage/videoModelConfig'
import type {
  ImageGenerationModelSettings,
  MediaGenerationSettings,
  VideoGenerationModelSettings,
} from '@/types/modelPreferences'

const AUTO_VALUE = '__auto__'

export type MediaGenerationSettingsType = 'image' | 'video'

export interface MediaGenerationModel {
  name?: string
  value?: string
  provider?: string
  config?: ImageModelRegistryConfig & VideoModelRegistryConfig
}

export interface MediaGenerationPreferences {
  media_generation_settings?: MediaGenerationSettings
}

interface MediaGenerationSettingsPanelProps {
  type: MediaGenerationSettingsType
  model?: MediaGenerationModel | null
  preferences: MediaGenerationPreferences
  onChange: (prefs: { media_generation_settings?: MediaGenerationSettings }) => void
  className?: string
  compact?: boolean
  showHeader?: boolean
}

type SettingValue = string | number | undefined

export function MediaGenerationSettingsPanel({
  type,
  model,
  preferences,
  onChange,
  className,
  compact = false,
  showHeader = true,
}: MediaGenerationSettingsPanelProps) {
  const { t } = useTranslation()
  const modelKey = getMediaGenerationModelKey(model)
  const settings = getModelSettings(preferences.media_generation_settings, type, modelKey)

  const imageResolutionOptions = useMemo(
    () => (type === 'image' ? getAllowedImageResolutions(model?.config) : []),
    [model?.config, type],
  )
  const imageRatioOptions = useMemo(() => {
    if (type !== 'image') return []
    const scopedResolution = String(
      (settings as ImageGenerationModelSettings).resolution || imageResolutionOptions[0] || '',
    )
    return getAllowedImageRatiosForResolution(model?.config, scopedResolution)
  }, [imageResolutionOptions, model?.config, settings, type])

  const videoResolutionOptions = useMemo(
    () => (type === 'video' ? getAllowedVideoResolutions(model?.config) : []),
    [model?.config, type],
  )
  const videoRatioOptions = useMemo(
    () => (type === 'video' ? getAllowedVideoRatios(model?.config) : []),
    [model?.config, type],
  )
  const videoDurationOptions = useMemo(() => {
    if (type !== 'video') return []
    return getAllowedVideoDurations(
      getVideoCapabilityFromConfig(model?.config, model?.value),
      {},
      model?.config?.allowed_durations,
    )
  }, [model?.config, model?.value, type])

  if (!modelKey) {
    return null
  }
  const modelLabel = model?.name || model?.value || ''
  const gridMinWidth = compact ? 96 : 118

  const handleSettingChange = (field: string, value: SettingValue) => {
    const nextValue = value === AUTO_VALUE ? undefined : value
    const extraUpdates: Record<string, SettingValue> = {}

    if (type === 'image' && field === 'resolution') {
      const nextResolution = String(nextValue || imageResolutionOptions[0] || '')
      const nextRatios = getAllowedImageRatiosForResolution(model?.config, nextResolution)
      const currentRatio = (settings as ImageGenerationModelSettings).aspect_ratio
      if (currentRatio && nextRatios.length > 0 && !nextRatios.includes(currentRatio)) {
        extraUpdates.aspect_ratio = undefined
      }
    }

    onChange({
      media_generation_settings: updateMediaGenerationSettings(
        preferences.media_generation_settings,
        type,
        modelKey,
        {
          ...extraUpdates,
          [field]: nextValue,
        },
      ),
    })
  }

  return (
    <div
      className={cn(
        showHeader
          ? 'rounded-xl border border-[var(--app-border)] bg-[var(--app-control)] p-3 shadow-[var(--app-shadow-control)]'
          : 'rounded-lg border border-[var(--app-border)] bg-[var(--app-control)] p-2.5 shadow-none',
        className,
      )}
    >
      {showHeader ? (
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-2">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--app-control-track)] text-[var(--app-foreground-muted)]">
              <SlidersHorizontal className="h-3.5 w-3.5" />
            </span>
            <div className="min-w-0">
              <div className="truncate text-xs font-semibold text-[var(--app-foreground)]">
                {t('agent.modelGenerationSettings.title')}
              </div>
              <div className="truncate text-[11px] text-[var(--app-foreground-subtle)]">
                {modelLabel}
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(auto-fit, minmax(${gridMinWidth}px, 1fr))` }}
      >
        {type === 'image' ? (
          <>
            <SettingSelect
              label={t('agent.modelGenerationSettings.imageResolution')}
              value={(settings as ImageGenerationModelSettings).resolution}
              options={imageResolutionOptions}
              onChange={(value) => handleSettingChange('resolution', value)}
            />
            <SettingSelect
              label={t('agent.modelGenerationSettings.imageAspectRatio')}
              value={(settings as ImageGenerationModelSettings).aspect_ratio}
              options={imageRatioOptions}
              onChange={(value) => handleSettingChange('aspect_ratio', value)}
            />
          </>
        ) : (
          <>
            <SettingSelect
              label={t('agent.modelGenerationSettings.videoResolution')}
              value={(settings as VideoGenerationModelSettings).resolution}
              options={videoResolutionOptions}
              onChange={(value) => handleSettingChange('resolution', value)}
            />
            <SettingSelect
              label={t('agent.modelGenerationSettings.canvasAspectRatio')}
              value={(settings as VideoGenerationModelSettings).aspect_ratio}
              options={videoRatioOptions}
              onChange={(value) => handleSettingChange('aspect_ratio', value)}
            />
            <SettingSelect
              label={t('agent.modelGenerationSettings.videoDuration')}
              value={(settings as VideoGenerationModelSettings).duration}
              options={videoDurationOptions}
              formatOptionLabel={(value) => formatDurationLabel(t, value)}
              normalizeValue={(value) => parseDurationValue(value)}
              onChange={(value) => handleSettingChange('duration', value)}
            />
          </>
        )}
      </div>
    </div>
  )
}

function SettingSelect({
  label,
  value,
  options,
  onChange,
  formatOptionLabel,
  normalizeValue,
}: {
  label: string
  value: SettingValue
  options: string[]
  onChange: (value: SettingValue) => void
  formatOptionLabel?: (value: string) => string
  normalizeValue?: (value: string) => SettingValue
}) {
  const { t } = useTranslation()
  const normalizedOptions = normalizeOptionValues(options)
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const autoLabel = String(t('agent.modelGenerationSettings.auto'))
  const currentValue = value == null || value === '' ? AUTO_VALUE : String(value)
  const selectOptions = [
    { value: AUTO_VALUE, label: autoLabel },
    ...normalizedOptions.map(option => ({
      value: option,
      label: formatOptionLabel ? formatOptionLabel(option) : option,
    })),
  ]
  const selectedLabel = selectOptions.find(option => option.value === currentValue)?.label || autoLabel

  useEffect(() => {
    if (!open) return

    const handleDocumentMouseDown = (event: MouseEvent) => {
      const eventPath = event.composedPath()
      if (containerRef.current && eventPath.includes(containerRef.current)) return
      setOpen(false)
    }

    document.addEventListener('mousedown', handleDocumentMouseDown)
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown)
  }, [open])

  const handleSelect = (nextValue: string) => {
    if (nextValue === AUTO_VALUE) {
      onChange(undefined)
    } else {
      onChange(normalizeValue ? normalizeValue(nextValue) : nextValue)
    }
    setOpen(false)
  }

  return (
    <div ref={containerRef} className="relative min-w-0">
      <span className="mb-1 block truncate text-[11px] font-medium text-[var(--app-foreground-muted)]">
        {label}
      </span>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        data-agent-generation-select="true"
        className={cn(
          'flex h-8 w-full items-center justify-between gap-2 rounded-lg border border-[var(--app-border)] bg-[var(--app-control)] px-2 text-left text-xs text-[var(--app-foreground)] shadow-[var(--app-shadow-control)] outline-none transition-[background,border-color,color,box-shadow]',
          'hover:bg-[var(--app-control-hover)] focus-visible:border-[var(--app-border-strong)] focus-visible:ring-2 focus-visible:ring-[var(--app-focus-ring)]',
        )}
        onClick={(event) => {
          event.stopPropagation()
          setOpen(current => !current)
        }}
        onKeyDown={(event) => {
          event.stopPropagation()
          if (event.key === 'Escape') {
            setOpen(false)
          }
        }}
      >
        <span className="min-w-0 flex-1 truncate">{selectedLabel}</span>
        <ChevronDown
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-[var(--app-foreground-subtle)] transition-transform',
            open ? 'rotate-180' : '',
          )}
        />
      </button>
      {open ? (
        <div
          data-agent-generation-select="true"
          className={cn(
            'absolute left-0 right-0 top-[calc(100%+4px)] z-[2400] max-h-44 overflow-y-auto rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-glass)] p-1 text-popover-foreground shadow-[var(--app-shadow-panel)] backdrop-blur-2xl',
          )}
          role="listbox"
          onClick={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
          {selectOptions.map(option => {
            const selected = option.value === currentValue
            return (
              <button
                key={option.value}
                type="button"
                role="option"
                aria-selected={selected}
                className={cn(
                  'relative flex min-h-8 w-full items-center rounded-[var(--app-radius-xs)] py-1.5 pl-2 pr-7 text-left text-xs outline-none transition-colors',
                  selected
                    ? 'bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)]'
                    : 'text-[var(--app-foreground)] hover:bg-[var(--app-control-hover)]',
                )}
                onMouseDown={(event) => {
                  event.preventDefault()
                  event.stopPropagation()
                }}
                onClick={(event) => {
                  event.stopPropagation()
                  handleSelect(option.value)
                }}
              >
                <span className="min-w-0 flex-1 truncate">{option.label}</span>
                {selected ? (
                  <Check className="absolute right-2 h-3.5 w-3.5 text-[var(--app-primary)]" />
                ) : null}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

function getMediaGenerationModelKey(model?: MediaGenerationModel | null): string | null {
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

function updateMediaGenerationSettings(
  settings: MediaGenerationSettings | undefined,
  type: MediaGenerationSettingsType,
  modelKey: string,
  updates: Record<string, SettingValue>,
): MediaGenerationSettings | undefined {
  const nextSettings: MediaGenerationSettings = {
    ...(settings || {}),
    [type]: {
      ...(settings?.[type] || {}),
    },
  }
  const bucket = nextSettings[type] || {}
  const current = { ...(bucket[modelKey] || {}) } as Record<string, SettingValue>

  for (const [field, value] of Object.entries(updates)) {
    if (value == null || value === '') {
      delete current[field]
    } else {
      current[field] = value
    }
  }

  if (Object.keys(current).length > 0) {
    bucket[modelKey] = current as ImageGenerationModelSettings & VideoGenerationModelSettings
  } else {
    delete bucket[modelKey]
  }

  if (Object.keys(bucket).length > 0) {
    if (type === 'image') {
      nextSettings.image = bucket as Record<string, ImageGenerationModelSettings>
    } else {
      nextSettings.video = bucket as Record<string, VideoGenerationModelSettings>
    }
  } else {
    delete nextSettings[type]
  }

  return Object.keys(nextSettings).length > 0 ? nextSettings : undefined
}

function normalizeOptionValues(options: string[]): string[] {
  const seen = new Set<string>()
  const normalized: string[] = []
  for (const option of options) {
    const value = String(option || '').trim()
    if (!value || seen.has(value)) continue
    seen.add(value)
    normalized.push(value)
  }
  return normalized
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
