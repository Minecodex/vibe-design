import { Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useState, useEffect, useCallback, useMemo } from 'react'
import { providersApi } from '@/api/endpoints/providers'
import type { ModelRead, ModelOption } from '@/api/endpoints/providers'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { motion, AnimatePresence } from 'framer-motion'
import { useAppConfigStore } from '@/store/appConfigStore'
import { useAuthStore } from '@/store/authStore'
import { getLocalizedAppName } from '@/config/brand'
import { formatProviderPricingItems } from './pricingFormatter'

import kelingLogo from '../../../image/keling.png'
import jimengLogo from '../../../image/jimeng.jpeg'
import volcarkLogo from '../../../image/volcark.png'

const LOGO_MAP: Record<string, string> = {
  kling: kelingLogo,
  jimeng: jimengLogo,
  volcark: volcarkLogo,
  ollama: '/favicon.svg',
  builtin: '/favicon.svg'
}

type ModelType = 'all' | 'text2image' | 'text2video' | 'multimodal'

interface FlatModel extends ModelRead {
  provider_name: string
  logo_url: string
  pricing_items: { label: string }[] | null
}

export function ProvidersPage() {
  const { t, i18n } = useTranslation()
  const appName = useAppConfigStore((s) => s.appName)
  const appNameEn = useAppConfigStore((s) => s.appNameEn)
  const providerBalanceSyncEnabled = useAuthStore((s) => s.providerBalanceSyncEnabled)
  const appDisplayName = getLocalizedAppName(i18n.language, { appName, appNameEn })

  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<ModelType>('all')
  const [allModels, setAllModels] = useState<FlatModel[]>([])

  const formatPricing = useCallback(
    (config: ModelOption['config'] | undefined) => formatProviderPricingItems(config, t),
    [t]
  )

  const fetchAllData = useCallback(async () => {
    try {
      const [provRes, regRes] = await Promise.all([
        providersApi.list(),
        providersApi.getRegistry(),
      ])


      const providersData = provRes.data
      const registryData = regRes.data

      // Fetch models for each authorized provider
      const modelPromises = providersData
        .filter(p => (p.status === 'authorized' || p.is_builtin))
        .map(async (p) => {
          try {
            const mRes = await providersApi.listModels(p.code)
            let models = mRes.data
            
            // Build-in provider fallback logic
            const regEntry = registryData[p.code]
            if (p.is_builtin && models.length === 0 && regEntry) {
              const text2image = regEntry.models?.text2image?.map(m => ({
                id: m.model_name,
                provider_code: p.code,
                model_name: m.label || m.model_name,
                model_type: 'text2image',
                is_enabled: true,
                credential_id: 1,
                endpoint: null
              })) || []
              const text2video = regEntry.models?.text2video?.map(m => ({
                id: m.model_name,
                provider_code: p.code,
                model_name: m.label || m.model_name,
                model_type: 'text2video',
                is_enabled: true,
                credential_id: 1,
                endpoint: null
              })) || []
              const multimodal = regEntry.models?.multimodal?.map(m => ({
                id: m.model_name,
                provider_code: p.code,
                model_name: m.label || m.model_name,
                model_type: 'multimodal',
                is_enabled: true,
                credential_id: 1,
                endpoint: null
              })) || []
              models = [...text2image, ...text2video, ...multimodal] as any
            }

            // Map pricing
            const modelConfigMap = new Map<string, ModelOption['config']>()
            if (regEntry?.models) {
              for (const categoryModels of Object.values(regEntry.models)) {
                for (const m of categoryModels) {
                  if (m.config) modelConfigMap.set(m.model_name, m.config)
                }
              }
            }

            return models.map(m => ({
              ...m,
              provider_name: p.name,
              logo_url: LOGO_MAP[p.code] || p.logo_url,
              pricing_items: formatPricing(modelConfigMap.get(m.model_name) || modelConfigMap.get(String(m.id)) || undefined)
            }))
          } catch (e) {
            console.error(`Failed to fetch models for ${p.code}`, e)
            return []
          }
        })

      const results = await Promise.all(modelPromises)
      const flattened = results.flat()
      setAllModels(flattened as FlatModel[])

    } catch (e) {
      toast.error(t('providers.fetchFailed'))
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [t, formatPricing])

  useEffect(() => {
    fetchAllData()
  }, [fetchAllData])

  const filteredModels = useMemo(() => {
    if (activeTab === 'all') return allModels
    return allModels.filter(m => m.model_type === activeTab)
  }, [allModels, activeTab])
  const showPricingColumn = !providerBalanceSyncEnabled && filteredModels.some(model => model.pricing_items && model.pricing_items.length > 0)
  const modelGridClassName = showPricingColumn ? 'grid-cols-[1.5fr_1fr_2fr]' : 'grid-cols-[1.5fr_1fr]'

  if (loading) {
    return (
      <div className="flex justify-center items-center h-full flex-1">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  const tabs: { key: ModelType; label: string }[] = [
    { key: 'all', label: t('providers.all') },
    { key: 'text2image', label: t('providers.textToImage') },
    { key: 'text2video', label: t('providers.textToVideo') },
    { key: 'multimodal', label: t('providers.multimodal') },
  ]

  return (
    <div data-testid="providers-page-scroll" className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-8 transition-colors duration-500 bg-transparent">
      <div className="max-w-[1100px] mx-auto space-y-8">
        {/* Page Title */}
        <h1 className="mb-4 px-2 text-2xl font-bold text-foreground">
          {t('providers.title')}
        </h1>

        {/* Main Glass Container */}
        <div className="relative overflow-hidden rounded-[var(--app-radius-xl)] border border-[var(--app-border)] bg-[var(--app-glass)] shadow-[var(--app-shadow-panel)] backdrop-blur-2xl">
          {/* Container Header */}
          <div className="flex items-center justify-between border-b border-[var(--app-border)] px-10 py-8">
            <div className="flex items-center gap-5">
              <div className={cn(
                'flex h-14 w-14 items-center justify-center rounded-[18px] bg-[var(--app-control-selected)] text-2xl font-bold text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]'
              )}>
                M
              </div>
              <div className="flex flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <h2 className="text-xl font-bold text-foreground">{appDisplayName}</h2>
                  <div className="h-2 w-2 rounded-full bg-[var(--app-success)] shadow-[0_0_8px_var(--app-tint-success)]" />
                </div>
              </div>
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-1 rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-control-track)] p-1 shadow-[var(--app-shadow-control)]">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={cn(
                    'px-6 py-2.5 rounded-xl text-xs font-bold transition-all duration-300 uppercase tracking-wider',
                    activeTab === tab.key
                      ? 'scale-[1.02] bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-[var(--app-shadow-selected)]'
                      : 'text-muted-foreground hover:bg-[var(--app-control-hover)] hover:text-foreground'
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* Table Content */}
          <div className="px-10 py-6 overflow-hidden">
            <div className={cn('grid px-4 mb-8', modelGridClassName)}>
              <span className="text-xs font-bold uppercase tracking-widest text-muted-foreground">
                {t('providers.modelName')}
              </span>
              <span className="text-center text-xs font-bold uppercase tracking-widest text-muted-foreground">
                {t('providers.category')}
              </span>
              {showPricingColumn && (
                <span className="text-right text-xs font-bold uppercase tracking-widest text-muted-foreground">
                  {t('providers.pricingPlan')}
                </span>
              )}
            </div>

            <div className="space-y-4 pb-10">
              <AnimatePresence mode="popLayout">
                {filteredModels.map((model) => (
                  <motion.div
                    layout
                    key={`${model.provider_code}-${model.id}`}
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95 }}
                    className={cn(
                      'grid items-center px-4 py-4 rounded-2xl transition-all duration-300 group',
                      modelGridClassName,
                      'shadow-sm hover:bg-[var(--app-control-hover)]'
                    )}
                  >
                    {/* Model Name & Logo */}
                    <div className="flex items-center gap-4">
                      <div className={cn(
                        'w-10 h-10 rounded-xl flex items-center justify-center p-1.5 flex-shrink-0 transition-transform group-hover:scale-110 duration-300',
                        'bg-[var(--app-control-selected)] shadow-[var(--app-shadow-selected)]'
                      )}>
                        <img src={model.logo_url} alt={model.model_name} className="w-full h-full object-contain" />
                      </div>
                      <span className="truncate text-base font-semibold text-foreground">
                        {model.model_name}
                      </span>
                    </div>

                    {/* Category Tag */}
                    <div className="flex justify-center">
                      <span className={cn(
                        'px-4 py-1.5 rounded-full text-xs font-bold tracking-tight transition-colors duration-300',
                        model.model_type === 'text2image' ? 'text-blue-500' :
                        model.model_type === 'text2video' ? 'text-purple-500' : 'text-emerald-500'
                      )}>
                        {model.model_type === 'text2image' ? t('providers.textToImage') : 
                         model.model_type === 'text2video' ? t('providers.textToVideo') : t('providers.multimodal')}
                      </span>
                    </div>

                    {/* Pricing */}
                    {showPricingColumn && (
                      <div className="flex flex-wrap justify-end gap-2">
                      {model.pricing_items && model.pricing_items.length > 0 ? (
                        model.pricing_items.map((item, idx) => (
                          <span key={idx} className={cn(
                            'rounded-[var(--app-radius-sm)] border border-[var(--app-border)] bg-[var(--app-surface)] px-4 py-2 text-xs font-bold tracking-tight text-muted-foreground shadow-sm transition-all duration-300 hover:translate-y-[-1px] hover:shadow-md'
                          )}>
                            {item.label}
                          </span>
                        ))
                      ) : (
                        <span />
                      )}
                      </div>
                    )}
                  </motion.div>
                ))}
              </AnimatePresence>
              
              {filteredModels.length === 0 && (
                <div className="py-20 text-center">
                  <p className="text-zinc-500 font-medium">{t('common.no_data')}</p>
                </div>
              )}
            </div>
          </div>

          {/* Table Footer */}
          <div className="flex items-center justify-between border-t border-[var(--app-border)] px-10 py-6">
            <div className="text-sm font-medium text-muted-foreground">
              {t('providers.modelsCount', { count: filteredModels.length })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
