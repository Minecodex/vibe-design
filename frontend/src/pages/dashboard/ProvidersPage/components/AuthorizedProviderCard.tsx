import { Settings, Plus, ChevronDown, Coins } from 'lucide-react'
import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import ModelConfigModal from './ModelConfigModal'
import AddModelModal from './AddModelModal'
import ManageCredentialsModal from './ManageCredentialsModal'
import AuthConfigModal from './AuthConfigModal'
import { providersApi } from '@/api/endpoints/providers'
import type { ModelRead, CredentialRead, ProviderRegistryEntry, ModelOption } from '@/api/endpoints/providers'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { formatProviderPricingItems } from '../pricingFormatter'

interface Props {
  providerCode: string
  name: string
  logoUrl: string
  tags: string[]
  registry: ProviderRegistryEntry
  onRefresh: () => void
}

export default function AuthorizedProviderCard({ providerCode, name, logoUrl, tags, registry, onRefresh }: Props) {
  const { t } = useTranslation()
  const [isModelsExpanded] = useState(true)
  const [selectedModel, setSelectedModel] = useState<ModelRead | null>(null)
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false)
  const [isAddModelModalOpen, setIsAddModelModalOpen] = useState(false)
  const [isManageCredentialsModalOpen, setIsManageCredentialsModalOpen] = useState(false)
  const [isAuthConfigModalOpen, setIsAuthConfigModalOpen] = useState(false)

  const [models, setModels] = useState<ModelRead[]>([])
  const [credentials, setCredentials] = useState<CredentialRead[]>([])

  const fetchData = async () => {
    try {
      const [mRes, cRes] = await Promise.all([
        providersApi.listModels(providerCode),
        providersApi.listCredentials(providerCode),
      ])
      
      // For built-in provider, backend might return 403 or empty lists, 
      // fallback to registry models if so.
      if (registry.is_builtin && mRes.data.length === 0) {
        const text2image = registry.models?.text2image?.map(m => ({
          id: m.model_name,
          provider_code: providerCode,
          model_name: m.label || m.model_name,
          model_type: 'text2image',
          is_enabled: true,
          credential_id: 1,
          endpoint: null
        })) || []
        const text2video = registry.models?.text2video?.map(m => ({
          id: m.model_name,
          provider_code: providerCode,
          model_name: m.label || m.model_name,
          model_type: 'text2video',
          is_enabled: true,
          credential_id: 1,
          endpoint: null
        })) || []
        const multimodal = registry.models?.multimodal?.map(m => ({
          id: m.model_name,
          provider_code: providerCode,
          model_name: m.label || m.model_name,
          model_type: 'multimodal',
          is_enabled: true,
          credential_id: 1,
          endpoint: null
        })) || []
        setModels([...text2image, ...text2video, ...multimodal] as any)
      } else {
        setModels(mRes.data)
      }
      setCredentials(cRes.data)
    } catch {
      if (registry.is_builtin) {
        const text2image = registry.models?.text2image?.map(m => ({
          id: m.model_name,
          provider_code: providerCode,
          model_name: m.label || m.model_name,
          model_type: 'text2image',
          is_enabled: true,
          credential_id: 1,
          endpoint: null
        })) || []
        const text2video = registry.models?.text2video?.map(m => ({
          id: m.model_name,
          provider_code: providerCode,
          model_name: m.label || m.model_name,
          model_type: 'text2video',
          is_enabled: true,
          credential_id: 1,
          endpoint: null
        })) || []
        const multimodal = registry.models?.multimodal?.map(m => ({
          id: m.model_name,
          provider_code: providerCode,
          model_name: m.label || m.model_name,
          model_type: 'multimodal',
          is_enabled: true,
          credential_id: 1,
          endpoint: null
        })) || []
        setModels([...text2image, ...text2video, ...multimodal] as any)
      }
    }
  }

  useEffect(() => {
    fetchData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerCode])

  const handleConfigureModel = (model: ModelRead) => {
    setSelectedModel(model)
    setIsConfigModalOpen(true)
  }

  const handleToggleModel = async (model: ModelRead, enabled: boolean) => {
    try {
      await providersApi.updateModel(providerCode, model.id, { is_enabled: enabled })
      await fetchData()
    } catch {
      toast.error(t('providers.saveFailed'))
    }
  }

  const modelTypeTags = (m: ModelRead) => {
    if (m.model_type === 'text2image') return [t('providers.textToImage')]
    if (m.model_type === 'multimodal') return [t('providers.multimodal')]
    return [t('providers.textToVideo')]
  }

  // Build a lookup map: model_name -> config (for builtin provider pricing display)
  const modelConfigMap = useMemo(() => {
    if (!registry.is_builtin) return new Map<string, ModelOption['config']>()
    const map = new Map<string, ModelOption['config']>()
    for (const models of Object.values(registry.models || {})) {
      for (const m of models) {
        if (m.config) map.set(m.model_name, m.config)
      }
    }
    return map
  }, [registry])

  return (
    <div className="mb-4 overflow-hidden rounded-[var(--app-radius-md)] border border-[var(--app-border)] bg-[var(--app-surface)] shadow-[var(--app-shadow-control)]">
      <div className="px-6 py-5 flex justify-between items-center">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <img src={logoUrl} alt={name} className="w-8 h-8 rounded-md object-contain" />
            <span className="text-base font-semibold text-foreground">{name}</span>
            <div className="w-1.5 h-1.5 rounded-full bg-green-500" />
          </div>
          <div className="flex flex-wrap gap-1">
            {tags.map(tag => (
              <span key={tag} className="rounded-[var(--app-radius-xs)] border border-[var(--app-border)] bg-[var(--app-control)] px-2 py-0.5 text-xs text-muted-foreground">
                {tag}
              </span>
            ))}
          </div>
        </div>
      </div>

      {isModelsExpanded && models.length > 0 && (
        <div className="px-6 pb-4 flex flex-col gap-3">
          {models.map(model => {
            const config = modelConfigMap.get(String(model.id))
            const pricingItems = config ? formatProviderPricingItems(config, t) : null
            return (
              <div key={model.id} className="flex justify-between items-center">
                <div className="flex items-center gap-3 min-w-0">
                  <img src={logoUrl} alt={name} className="w-6 h-6 rounded object-contain flex-shrink-0" />
                  <span className="whitespace-nowrap text-[15px] font-medium text-foreground">{model.model_name}</span>
                  <div className="flex flex-wrap gap-1">
                    {modelTypeTags(model).map(tag => (
                      <span key={tag} className="rounded-[var(--app-radius-xs)] border border-[var(--app-border)] bg-[var(--app-control)] px-2 py-0.5 text-xs text-muted-foreground">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {pricingItems && (
                    <div className="flex items-center gap-1.5 flex-wrap justify-end">
                      <Coins className="h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
                      {pricingItems.map((item, idx) => (
                        <span key={idx} className="rounded-[var(--app-radius-xs)] border border-[color-mix(in_srgb,var(--app-warning)_32%,var(--app-border))] bg-[var(--app-tint-warning)] px-1.5 py-0.5 font-mono text-xs text-[color-mix(in_srgb,var(--app-warning)_72%,var(--app-foreground))]">
                          {item.label}
                        </span>
                      ))}
                    </div>
                  )}
                  {!registry.is_builtin && (
                    <>
                      <Button variant="outline" size="sm" className="gap-1.5" onClick={() => handleConfigureModel(model)}>
                        <Settings className="w-4 h-4" />{t('providers.configure')}
                      </Button>
                      <Switch checked={model.is_enabled} onCheckedChange={(checked) => handleToggleModel(model, checked)} />
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      <div className={cn(
        'flex items-center justify-between border-t border-[var(--app-border)] bg-[var(--app-surface-muted)] px-6 py-3'
      )}>
        <div
          className="flex items-center gap-1 text-[13px] font-medium text-muted-foreground"
        >
          <span>
            {models.length > 0 ? t('providers.modelsCount', { count: models.length }) : t('providers.showModels')}
          </span>
          {models.length > 0 && <ChevronDown className="w-2.5 h-2.5" />}
        </div>
        <div className="flex items-center gap-4">
          {!registry.is_builtin && (
            <>
              <span
                className="text-[13px] text-blue-500 cursor-pointer font-medium"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); setIsManageCredentialsModalOpen(true) }}
              >
                {t('providers.manageCredentials')}
              </span>
              <div
                className="flex cursor-pointer items-center gap-1 text-[13px] text-muted-foreground transition-colors hover:text-foreground"
                onClick={() => setIsAddModelModalOpen(true)}
              >
                <Plus className="w-3 h-3" />
                <span>{t('providers.addModel')}</span>
              </div>
            </>
          )}
        </div>
      </div>

      {selectedModel && (
        <ModelConfigModal
          isOpen={isConfigModalOpen}
          onClose={() => { setIsConfigModalOpen(false); fetchData() }}
          providerCode={providerCode}
          model={selectedModel}
          logoUrl={logoUrl}
          credentials={credentials}
        />
      )}

      <AddModelModal
        isOpen={isAddModelModalOpen}
        onClose={() => { setIsAddModelModalOpen(false); fetchData(); onRefresh() }}
        providerCode={providerCode}
        providerName={name}
        logoUrl={logoUrl}
        registry={registry.models}
        credentials={credentials}
        existingModels={models}
        requiresEndpoint={registry.requires_endpoint}
      />

      <ManageCredentialsModal
        isOpen={isManageCredentialsModalOpen}
        onClose={() => { setIsManageCredentialsModalOpen(false); fetchData() }}
        providerCode={providerCode}
        providerName={name}
        logoUrl={logoUrl}
        credentials={credentials}
        onAddCredential={() => {
          setIsManageCredentialsModalOpen(false)
          setIsAuthConfigModalOpen(true)
        }}
        onRefresh={fetchData}
      />

      <AuthConfigModal
        isOpen={isAuthConfigModalOpen}
        onClose={() => { setIsAuthConfigModalOpen(false); fetchData(); onRefresh() }}
        providerCode={providerCode}
        providerName={name}
        credentialTypes={registry.credential_types}
      />
    </div>
  )
}
