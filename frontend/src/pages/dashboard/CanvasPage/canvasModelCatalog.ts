import {
  providersApi,
  type ModelRead,
  type ModelRegistry,
  type ModelOption,
  type ProviderRegistryEntry,
  type ProviderStatus,
} from '@/api/endpoints/providers'

export interface CanvasAuthorizedProviderCatalogEntry {
  provider: ProviderStatus
  models: ModelRead[]
}

export interface CanvasModelCatalog {
  registry: ModelRegistry
  providers: CanvasAuthorizedProviderCatalogEntry[]
}

export function registryModels(entry: ProviderRegistryEntry | undefined, modelType: string): ModelOption[] {
  const canonical = entry?.models?.[modelType]
  if (canonical) return canonical
  // Retain the three supported flat registry forms from older API responses.
  if (modelType === 'text2image') return entry?.text2image || []
  if (modelType === 'text2video') return entry?.text2video || []
  if (modelType === 'multimodal') return entry?.multimodal || []
  return []
}

type EnabledCanvasModel = Pick<ModelRead, 'model_name' | 'model_type' | 'is_enabled'>
export function enabledProviderModels(
  entry: CanvasAuthorizedProviderCatalogEntry,
  registry: ModelRegistry,
  modelTypes: readonly string[],
): EnabledCanvasModel[] {
  const enabled = entry.models.filter(model => model.is_enabled)
  if (!entry.provider.is_builtin || enabled.length > 0) return enabled
  return modelTypes.flatMap(model_type => registryModels(registry[entry.provider.code], model_type)
    .map(model => ({ model_name: model.model_name, model_type, is_enabled: true })))
}

export interface CanvasSelectableModel {
  name: string
  value: string
  provider: string
  providerName: string
  isBuiltin: boolean
  description?: string
  tag?: string
  config?: ModelOption['config']
  supportsFastMode?: boolean
  supportsThinkingMode?: boolean
  thinkingVariantOf?: string
}

let cachedCatalog: CanvasModelCatalog | null = null
let catalogPromise: Promise<CanvasModelCatalog> | null = null

async function fetchCanvasModelCatalog(): Promise<CanvasModelCatalog> {
  const [providersRes, registryRes] = await Promise.all([
    providersApi.list(),
    providersApi.getRegistry(),
  ])

  const authorizedProviders = providersRes.data.filter(provider => provider.status === 'authorized')
  const providers = await Promise.all(
    authorizedProviders.map(async (provider) => {
      try {
        const modelsRes = await providersApi.listModels(provider.code)
        return {
          provider,
          models: modelsRes.data,
        }
      } catch {
        return {
          provider,
          models: [],
        }
      }
    }),
  )

  return {
    registry: registryRes.data,
    providers,
  }
}

export function loadCanvasModelCatalog(): Promise<CanvasModelCatalog> {
  if (cachedCatalog) {
    return Promise.resolve(cachedCatalog)
  }
  if (catalogPromise) {
    return catalogPromise
  }

  catalogPromise = fetchCanvasModelCatalog()
    .then((catalog) => {
      cachedCatalog = catalog
      return catalog
    })
    .finally(() => {
      catalogPromise = null
    })

  return catalogPromise
}

export const __canvasModelCatalogTestUtils = {
  reset() {
    cachedCatalog = null
    catalogPromise = null
  },
}
