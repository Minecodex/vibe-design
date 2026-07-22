import {
  providersApi,
  type ModelRead,
  type ModelRegistry,
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
