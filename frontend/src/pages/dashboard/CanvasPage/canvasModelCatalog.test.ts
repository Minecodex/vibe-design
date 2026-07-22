import { beforeEach, describe, expect, it, vi } from 'vitest'

const providerMocks = vi.hoisted(() => ({
  list: vi.fn(),
  getRegistry: vi.fn(),
  listModels: vi.fn(),
}))

vi.mock('@/api/endpoints/providers', () => ({
  providersApi: {
    list: providerMocks.list,
    getRegistry: providerMocks.getRegistry,
    listModels: providerMocks.listModels,
  },
}))

import {
  __canvasModelCatalogTestUtils,
  loadCanvasModelCatalog,
} from './canvasModelCatalog'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('canvasModelCatalog', () => {
  beforeEach(() => {
    __canvasModelCatalogTestUtils.reset()
    providerMocks.list.mockReset()
    providerMocks.getRegistry.mockReset()
    providerMocks.listModels.mockReset()
  })

  it('dedupes concurrent catalog loads and reuses the resolved cache', async () => {
    const providersDeferred = deferred<{ data: Array<{ code: string, status: string, is_builtin?: boolean, name: string }> }>()
    const registryDeferred = deferred<{ data: Record<string, any> }>()
    const modelDeferred = deferred<{ data: Array<{ model_name: string, model_type: string, is_enabled: boolean }> }>()

    providerMocks.list.mockReturnValue(providersDeferred.promise)
    providerMocks.getRegistry.mockReturnValue(registryDeferred.promise)
    providerMocks.listModels.mockReturnValue(modelDeferred.promise)

    const firstRequest = loadCanvasModelCatalog()
    const secondRequest = loadCanvasModelCatalog()

    expect(providerMocks.list).toHaveBeenCalledTimes(1)
    expect(providerMocks.getRegistry).toHaveBeenCalledTimes(1)

    providersDeferred.resolve({
      data: [
        { code: 'builtin', status: 'authorized', is_builtin: true, name: 'Builtin' },
        { code: 'blocked', status: 'unauthorized', name: 'Blocked' },
      ],
    })
    registryDeferred.resolve({
      data: {
        builtin: { models: { text2image: [] } },
      },
    })
    modelDeferred.resolve({
      data: [
        { model_name: 'seedream', model_type: 'text2image', is_enabled: true },
      ],
    })

    const [firstCatalog, secondCatalog] = await Promise.all([firstRequest, secondRequest])

    expect(firstCatalog).toEqual(secondCatalog)
    expect(providerMocks.listModels).toHaveBeenCalledTimes(1)
    expect(providerMocks.listModels).toHaveBeenCalledWith('builtin')

    const thirdCatalog = await loadCanvasModelCatalog()

    expect(thirdCatalog).toEqual(firstCatalog)
    expect(providerMocks.list).toHaveBeenCalledTimes(1)
    expect(providerMocks.getRegistry).toHaveBeenCalledTimes(1)
    expect(providerMocks.listModels).toHaveBeenCalledTimes(1)
  })

  it('keeps authorized builtin Ollama text-to-image models in the catalog', async () => {
    providerMocks.list.mockResolvedValue({
      data: [
        { code: 'ollama', status: 'authorized', is_builtin: true, name: 'Ollama' },
      ],
    })
    providerMocks.getRegistry.mockResolvedValue({
      data: {
        ollama: {
          models: {
            text2image: [
              {
                model_name: 'gpt-image-2',
                label: 'Ollama Image (gpt-image-2)',
                config: { supports_reference_image: true },
              },
            ],
          },
        },
      },
    })
    providerMocks.listModels.mockResolvedValue({ data: [] })

    const catalog = await loadCanvasModelCatalog()

    expect(catalog.providers).toEqual([
      {
        provider: { code: 'ollama', status: 'authorized', is_builtin: true, name: 'Ollama' },
        models: [],
      },
    ])
    expect(catalog.registry.ollama.models.text2image[0].model_name).toBe('gpt-image-2')
    expect(catalog.registry.ollama.models.text2image[0].label).toBe('Ollama Image (gpt-image-2)')
  })
})
