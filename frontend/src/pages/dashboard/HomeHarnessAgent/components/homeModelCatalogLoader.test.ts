import { beforeEach, describe, expect, it, vi } from 'vitest'

const providersListMock = vi.fn()
const providersRegistryMock = vi.fn()
const providersModelsMock = vi.fn()

vi.mock('@/api/endpoints/providers', () => ({
  providersApi: {
    list: (...args: unknown[]) => providersListMock(...args),
    getRegistry: (...args: unknown[]) => providersRegistryMock(...args),
    listModels: (...args: unknown[]) => providersModelsMock(...args),
  },
}))

import {
  __homeModelCatalogLoaderTestUtils,
  loadHomepageModelCatalog,
} from './homeModelCatalogLoader'

describe('homeModelCatalogLoader', () => {
  beforeEach(() => {
    __homeModelCatalogLoaderTestUtils.reset()
    providersListMock.mockReset()
    providersRegistryMock.mockReset()
    providersModelsMock.mockReset()

    providersListMock.mockResolvedValue({
      data: [
        {
          code: 'builtin',
          name: 'Built-in',
          author: 'OpenAI',
          description: '',
          logo_url: '',
          tags: [],
          status: 'authorized',
          credential_count: 1,
          model_count: 3,
        },
      ],
    })
    providersRegistryMock.mockResolvedValue({
      data: {
        builtin: {
          models: {
            image: [{ model_name: 'img-fast', label: 'Image Fast' }],
            video: [{ model_name: 'vid-fast', label: 'Video Fast' }],
            multimodal: [{ model_name: 'mm-fast', label: 'Multimodal Fast' }],
          },
          credential_types: [],
          requires_endpoint: false,
        },
      },
    })
    providersModelsMock.mockResolvedValue({
      data: [
        { model_name: 'img-fast', model_type: 'image', is_enabled: true },
        { model_name: 'vid-fast', model_type: 'video', is_enabled: true },
        { model_name: 'mm-fast', model_type: 'multimodal', is_enabled: true },
      ],
    })
  })

  it('deduplicates concurrent provider catalog requests', async () => {
    const [first, second] = await Promise.all([
      loadHomepageModelCatalog('en-US', { appName: '像素重组', appNameEn: 'Pixel Reorganization' }),
      loadHomepageModelCatalog('en-US', { appName: '像素重组', appNameEn: 'Pixel Reorganization' }),
    ])

    expect(providersListMock).toHaveBeenCalledTimes(1)
    expect(providersRegistryMock).toHaveBeenCalledTimes(1)
    expect(providersModelsMock).toHaveBeenCalledTimes(1)
    expect(first.multimodalModels).toHaveLength(1)
    expect(second.multimodalModels).toHaveLength(1)
  })
})
