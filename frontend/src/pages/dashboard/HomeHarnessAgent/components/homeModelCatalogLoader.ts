import { providersApi, type ModelRegistry, type ProviderStatus } from '@/api/endpoints/providers'
import { resolveLocalizedProviderName } from '@/config/brand'

import {
  buildHomepageSelectableModels,
  type HomeSelectableModel,
} from './homeChatModelPreferences'

interface HomeModelCatalogBrand {
  appName: string
  appNameEn: string
}

interface HomeModelCatalogData {
  providers: ProviderStatus[]
  registry: ModelRegistry
  enabledModelsByProvider: Record<string, Array<{ model_name: string; model_type: string; is_enabled?: boolean }>>
}

interface HomeModelCatalog {
  imageModels: HomeSelectableModel[]
  videoModels: HomeSelectableModel[]
  multimodalModels: HomeSelectableModel[]
}

let homeModelCatalogData: HomeModelCatalogData | null = null
let homeModelCatalogRequest: Promise<HomeModelCatalogData> | null = null

async function loadHomepageModelCatalogData(): Promise<HomeModelCatalogData> {
  if (homeModelCatalogData) {
    return homeModelCatalogData
  }
  if (homeModelCatalogRequest) {
    return homeModelCatalogRequest
  }

  homeModelCatalogRequest = (async () => {
    const [providersRes, registryRes] = await Promise.all([
      providersApi.list(),
      providersApi.getRegistry(),
    ])

    const authorizedProviders = providersRes.data.filter((provider) => provider.status === 'authorized')
    const enabledModelsByProvider: HomeModelCatalogData['enabledModelsByProvider'] = {}

    await Promise.all(authorizedProviders.map(async (provider) => {
      try {
        const modelsRes = await providersApi.listModels(provider.code)
        enabledModelsByProvider[provider.code] = (modelsRes.data || []).filter((model) => model.is_enabled)
      } catch {
        enabledModelsByProvider[provider.code] = []
      }
    }))

    const nextData: HomeModelCatalogData = {
      providers: authorizedProviders,
      registry: registryRes.data,
      enabledModelsByProvider,
    }
    homeModelCatalogData = nextData
    homeModelCatalogRequest = null
    return nextData
  })().catch((error) => {
    homeModelCatalogRequest = null
    throw error
  })

  return homeModelCatalogRequest
}

export async function loadHomepageModelCatalog(
  language: string,
  brand: HomeModelCatalogBrand,
): Promise<HomeModelCatalog> {
  const { providers, registry, enabledModelsByProvider } = await loadHomepageModelCatalogData()
  const localizedProviders = providers.map((provider) => ({
    ...provider,
    name: resolveLocalizedProviderName(language, brand, provider.code, provider.name),
  }))

  return buildHomepageSelectableModels(localizedProviders, registry, enabledModelsByProvider)
}

export const __homeModelCatalogLoaderTestUtils = {
  reset() {
    homeModelCatalogData = null
    homeModelCatalogRequest = null
  },
}
