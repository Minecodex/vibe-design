import { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Bot, Box, Check, Film, Image as ImageIcon, SlidersHorizontal, X } from 'lucide-react'

import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import type { ModelPreferences } from '@/store/homeHarnessStore'
import { useAppConfigStore } from '@/store/appConfigStore'
import { MediaGenerationSettingsPanel } from '@/components/agent/MediaGenerationSettingsPanel'
import { getMediaGenerationSettingsSummary } from '@/components/agent/mediaGenerationSettingsSummary'
import {
  fillHomepageDefaultModelPreferences,
  filterHomepageMultimodalModels,
  type HomeSelectableModel,
} from './homeChatModelPreferences'
import { loadHomepageModelCatalog } from './homeModelCatalogLoader'

type HomeModelTab = 'image' | 'video' | 'multimodal'

interface HomeChatModelPickerProps {
  isDark: boolean
  thinkingEnabled: boolean
  value: ModelPreferences
  onChange: (prefs: Partial<ModelPreferences>) => void
  onImageModelsChange?: (models: HomeSelectableModel[]) => void
  onMultimodalModelsChange?: (models: HomeSelectableModel[]) => void
}

export function HomeChatModelPicker({
  thinkingEnabled,
  value,
  onChange,
  onImageModelsChange,
  onMultimodalModelsChange,
}: HomeChatModelPickerProps) {
  const { t, i18n } = useTranslation()
  const [open, setOpen] = useState(false)
  const [hovered, setHovered] = useState(false)
  const [tab, setTab] = useState<HomeModelTab>('multimodal')
  const [expandedSettingsKey, setExpandedSettingsKey] = useState<string | null>(null)
  const [imageModels, setImageModels] = useState<HomeSelectableModel[]>([])
  const [videoModels, setVideoModels] = useState<HomeSelectableModel[]>([])
  const [multimodalModels, setMultimodalModels] = useState<HomeSelectableModel[]>([])
  const containerRef = useRef<HTMLDivElement>(null)
  const appName = useAppConfigStore((s) => s.appName)
  const appNameEn = useAppConfigStore((s) => s.appNameEn)
  const brand = useMemo(() => ({ appName, appNameEn }), [appName, appNameEn])

  useEffect(() => {
    if (!open) return

    const handleClickOutside = (event: MouseEvent) => {
      const eventPath = event.composedPath()
      const isGenerationSelectEvent = eventPath.some((target) => (
        target instanceof Element &&
        target.closest('[data-agent-generation-select="true"]')
      ))
      if (isGenerationSelectEvent) return
      if (containerRef.current && !eventPath.includes(containerRef.current)) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  useEffect(() => {
    setExpandedSettingsKey(null)
  }, [tab])

  useEffect(() => {
    if (!open) {
      setExpandedSettingsKey(null)
    }
  }, [open])

  useEffect(() => {
    if (!open && !hovered && !onImageModelsChange && !onMultimodalModelsChange) return

    let disposed = false

    const fetchModels = async () => {
      const {
        imageModels: nextImageModels,
        videoModels: nextVideoModels,
        multimodalModels: nextMultimodalModels,
      } = await loadHomepageModelCatalog(i18n.language, brand)

      if (disposed) return

      setImageModels(nextImageModels)
      setVideoModels(nextVideoModels)
      setMultimodalModels(nextMultimodalModels)
      onImageModelsChange?.(nextImageModels)
      onMultimodalModelsChange?.(nextMultimodalModels)
    }

    void fetchModels()

    return () => {
      disposed = true
    }
  }, [brand, hovered, i18n.language, onImageModelsChange, onMultimodalModelsChange, open])

  const filteredMultimodalModels = useMemo(() => {
    return filterHomepageMultimodalModels(multimodalModels, thinkingEnabled)
  }, [multimodalModels, thinkingEnabled])

  useEffect(() => {
    const nextPreferences = fillHomepageDefaultModelPreferences(
      value,
      {
        imageModels,
        videoModels,
        multimodalModels,
      },
      thinkingEnabled,
    )

    if (
      nextPreferences.image_model !== value.image_model ||
      nextPreferences.image_provider !== value.image_provider ||
      nextPreferences.video_model !== value.video_model ||
      nextPreferences.video_provider !== value.video_provider ||
      nextPreferences.multimodal_model !== value.multimodal_model ||
      nextPreferences.multimodal_provider !== value.multimodal_provider
    ) {
      onChange(nextPreferences)
    }
  }, [imageModels, multimodalModels, onChange, thinkingEnabled, value, videoModels])

  const selectedSummary = useMemo(() => {
    const imageModel = imageModels.find(model =>
      model.value === value.image_model && model.provider === value.image_provider,
    )
    const videoModel = videoModels.find(model =>
      model.value === value.video_model && model.provider === value.video_provider,
    )
    const multimodalModel = filteredMultimodalModels.find(model =>
      model.value === value.multimodal_model && model.provider === value.multimodal_provider,
    )

    return [
      {
        label: t('home.chat.current_image_model', 'Current image model'),
        value: imageModel?.name || value.image_model || '-',
        icon: ImageIcon,
      },
      {
        label: t('home.chat.current_video_model', 'Current video model'),
        value: videoModel?.name || value.video_model || '-',
        icon: Film,
      },
      {
        label: t('home.chat.current_multimodal_model', 'Current multimodal model'),
        value: multimodalModel?.name || value.multimodal_model || '-',
        icon: Bot,
      },
    ]
  }, [
    filteredMultimodalModels,
    imageModels,
    t,
    value.image_model,
    value.image_provider,
    value.multimodal_model,
    value.multimodal_provider,
    value.video_model,
    value.video_provider,
    videoModels,
  ])

  return (
    <div
      ref={containerRef}
      className="relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <button
        type="button"
        aria-label={t('home.chat.model_settings', 'Model Settings')}
        aria-expanded={open}
        className={cn(
          'p-2 rounded-lg transition-colors focus:outline-none',
          open
            ? 'text-blue-500 bg-blue-500/10 border border-blue-500/20'
            : 'border border-transparent text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
        )}
        onClick={() => setOpen(current => !current)}
      >
        <Box className="w-4 h-4" />
      </button>

      {hovered && !open ? (
        <div
          className={cn(
            'absolute bottom-full right-0 mb-3 w-[300px] rounded-xl border p-3 shadow-2xl z-20',
            'border-[var(--app-border)] bg-[var(--app-glass)] text-foreground backdrop-blur-2xl',
          )}
        >
          <div className="text-sm font-semibold mb-3">
            {t('home.chat.model_settings', 'Model Settings')}
          </div>
          <div className="space-y-3">
            {selectedSummary.map((item) => {
              const Icon = item.icon
              return (
                <div key={item.label} className="flex items-start gap-2">
                  <div className={cn(
                    'mt-0.5 w-7 h-7 rounded-full flex items-center justify-center shrink-0',
                    'bg-[var(--app-control)] text-muted-foreground',
                  )}>
                    <Icon className="w-3.5 h-3.5" />
                  </div>
                  <div className="min-w-0">
                    <div className="text-xs text-zinc-500">{item.label}</div>
                    <div className="text-sm font-medium leading-5 break-words">{item.value}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      {open ? (
        <div
          className={cn(
            'absolute bottom-full right-0 mb-3 w-[380px] max-w-[calc(100vw-32px)] overflow-hidden rounded-2xl border shadow-2xl z-30',
            'border-[var(--app-border)] bg-[var(--app-glass)] text-foreground backdrop-blur-2xl',
          )}
        >
          <div className="p-4 pb-2.5 flex items-start justify-between gap-3">
            <div>
              <div className="text-base font-bold">{t('home.chat.model_settings', 'Model Settings')}</div>
              <p className="text-sm text-zinc-500 mt-1">
                {selectedSummary[2].label}: {selectedSummary[2].value}
              </p>
            </div>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setOpen(false)}
              className={cn(
                'p-2 rounded-full transition-colors',
                'text-muted-foreground hover:bg-[var(--app-control-hover)]',
              )}
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="px-4 pb-2.5">
            <Tabs value={tab} onValueChange={(nextTab) => setTab(nextTab as HomeModelTab)}>
              <TabsList className="grid w-full grid-cols-3 rounded-xl bg-[var(--app-control-track)]">
                <TabsTrigger value="image">{t('agent.modelGenerationSettings.imageTab')}</TabsTrigger>
                <TabsTrigger value="video">{t('agent.modelGenerationSettings.videoTab')}</TabsTrigger>
                <TabsTrigger value="multimodal">{t('providers.multimodal', 'Multimodal')}</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>

          <div className="max-h-[280px] overflow-y-auto px-3 pb-4">
            {getVisibleModels(tab, imageModels, videoModels, filteredMultimodalModels).map((model) => {
              const selected = tab === 'image'
                ? value.image_model === model.value && value.image_provider === model.provider
                : tab === 'video'
                  ? value.video_model === model.value && value.video_provider === model.provider
                  : value.multimodal_model === model.value && value.multimodal_provider === model.provider

              const Icon = tab === 'image' ? ImageIcon : tab === 'video' ? Film : Bot
              const generationType = tab === 'image' || tab === 'video' ? tab : null
              const settingsKey = `${tab}-${model.provider}-${model.value}`
              const settingsExpanded = expandedSettingsKey === settingsKey
              const settingsSummary = generationType
                ? getMediaGenerationSettingsSummary({
                    type: generationType,
                    model,
                    preferences: value,
                    t,
                  }).join(' · ')
                : ''
              const selectModel = () => {
                if (tab === 'image') {
                  onChange({ image_model: model.value, image_provider: model.provider })
                } else if (tab === 'video') {
                  onChange({ video_model: model.value, video_provider: model.provider })
                } else {
                  onChange({ multimodal_model: model.value, multimodal_provider: model.provider })
                }
              }

              return (
                <div
                  key={`${tab}-${model.provider}-${model.value}`}
                >
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={selectModel}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        selectModel()
                      }
                    }}
                    className={cn(
                      'w-full mt-2 rounded-xl border px-3 py-2.5 text-left transition-all flex items-start gap-2.5 focus:outline-none focus:ring-2 focus:ring-blue-500/25',
                      selected
                        ? 'border-blue-500/30 bg-blue-500/10'
                        : 'border-[var(--app-border)] hover:bg-[var(--app-control-hover)]',
                    )}
                  >
                    <div className={cn(
                      'w-8 h-8 rounded-full flex items-center justify-center shrink-0',
                      selected ? 'bg-blue-500/10 text-blue-500' : 'bg-[var(--app-control)] text-muted-foreground',
                    )}>
                      <Icon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-sm">{model.name}</span>
                        {selected ? <Check className="w-4 h-4 text-blue-500" /> : null}
                      </div>
                      <div className="text-xs text-[var(--app-foreground-subtle)] mt-1">
                        {model.description || model.providerName}
                      </div>
                      {(model.tag || generationType) ? (
                        <div className="mt-2 flex min-h-6 items-center justify-between gap-2">
                          {generationType ? (
                            <div
                              className="min-w-0 flex-1 truncate text-[10px] leading-4 text-[var(--app-foreground-subtle)]"
                              title={settingsSummary}
                            >
                              {settingsSummary}
                            </div>
                          ) : model.tag ? (
                            <div className="inline-flex rounded-md bg-[var(--app-control)] px-2 py-0.5 text-[10px] text-[var(--app-foreground-subtle)]">
                              {model.tag}
                            </div>
                          ) : (
                            <span />
                          )}
                          {generationType ? (
                            <button
                              type="button"
                              aria-label={String(t('agent.modelGenerationSettings.title'))}
                              aria-expanded={settingsExpanded}
                              title={String(t('agent.modelGenerationSettings.title'))}
                              onKeyDown={(event) => {
                                event.stopPropagation()
                              }}
                              onClick={(event) => {
                                event.stopPropagation()
                                setExpandedSettingsKey(current => (
                                  current === settingsKey ? null : settingsKey
                                ))
                              }}
                              className={cn(
                                'ml-auto inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border transition-colors',
                                settingsExpanded
                                  ? 'border-blue-500/30 bg-blue-500/10 text-blue-500'
                                  : 'border-[var(--app-border)] bg-[var(--app-control)] text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground',
                              )}
                            >
                              <SlidersHorizontal className="h-3.5 w-3.5" />
                            </button>
                          ) : null}
                        </div>
                      ) : null}
                    </div>
                  </div>
                  {generationType && settingsExpanded ? (
                    <div className="pt-1.5">
                      <MediaGenerationSettingsPanel
                        type={generationType}
                        model={model}
                        preferences={value}
                        onChange={onChange}
                        compact
                        showHeader={false}
                      />
                    </div>
                  ) : null}
                </div>
              )
            })}

            {tab === 'multimodal' && filteredMultimodalModels.length === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-zinc-500">
                {thinkingEnabled
                  ? t('canvas.chat.model_selector.no_thinking_models')
                  : t('canvas.chat.model_selector.no_quick_models')}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  )
}

function getVisibleModels(
  tab: HomeModelTab,
  imageModels: HomeSelectableModel[],
  videoModels: HomeSelectableModel[],
  filteredMultimodalModels: HomeSelectableModel[],
) {
  if (tab === 'image') return imageModels
  if (tab === 'video') return videoModels
  return filteredMultimodalModels
}
