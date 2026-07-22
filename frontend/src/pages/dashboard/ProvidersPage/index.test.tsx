import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ProvidersPage } from './index'

const listProvidersMock = vi.fn()
const getRegistryMock = vi.fn()
const listModelsMock = vi.fn()
let providerBalanceSyncEnabled = false

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (key: string, second?: string | Record<string, unknown>) => typeof second === 'string' ? second : key,
    i18n: {
      language: 'zh-CN',
    },
  }),
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/api/endpoints/providers', () => ({
  providersApi: {
    list: (...args: unknown[]) => listProvidersMock(...args),
    getRegistry: (...args: unknown[]) => getRegistryMock(...args),
    listModels: (...args: unknown[]) => listModelsMock(...args),
  },
}))

vi.mock('@/store/appConfigStore', () => ({
  useAppConfigStore: (selector: (state: { appName: string; appNameEn: string }) => string) =>
    selector({
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
    }),
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: { providerBalanceSyncEnabled: boolean }) => unknown) =>
    selector({ providerBalanceSyncEnabled }),
}))

describe('ProvidersPage layout', () => {
  beforeEach(() => {
    listProvidersMock.mockReset()
    getRegistryMock.mockReset()
    listModelsMock.mockReset()
    providerBalanceSyncEnabled = false

    listProvidersMock.mockResolvedValue({
      data: [
        {
          code: 'builtin',
          name: 'Builtin',
          status: 'authorized',
          is_builtin: true,
          logo_url: '',
        },
      ],
    })
    getRegistryMock.mockResolvedValue({
      data: {
        builtin: {
          models: {
            text2image: [
              {
                model_name: 'test-model',
                label: 'Test Model',
                config: {
                  pricing_mode: 'flat',
                  pricing_cents: { flat: 28 },
                },
              },
            ],
          },
        },
      },
    })
    listModelsMock.mockResolvedValue({ data: [] })
  })

  test('keeps the model list inside an internal vertical scroll container', async () => {
    render(<ProvidersPage />)

    await waitFor(() => {
      expect(listProvidersMock).toHaveBeenCalled()
    })

    const scrollPane = screen.getByTestId('providers-page-scroll')
    expect(scrollPane.className).toContain('min-h-0')
    expect(scrollPane.className).toContain('overflow-y-auto')
    expect(scrollPane.className).toContain('overflow-x-hidden')
  })

  test('shows model pricing when Provider Balance Sync Mode is inactive', async () => {
    render(<ProvidersPage />)

    expect(await screen.findByText('providers.pricingFlat')).toBeInTheDocument()
  })

  test('hides the model pricing column when Provider Balance Sync Mode is active', async () => {
    providerBalanceSyncEnabled = true

    render(<ProvidersPage />)

    await waitFor(() => {
      expect(listProvidersMock).toHaveBeenCalled()
    })
    expect(screen.queryByText('providers.pricingFlat')).not.toBeInTheDocument()
  })

  test('shows builtin Ollama text-to-image registry models without user credentials', async () => {
    listProvidersMock.mockResolvedValue({
      data: [
        {
          code: 'ollama',
          name: 'Ollama',
          status: 'authorized',
          is_builtin: true,
          logo_url: '',
        },
      ],
    })
    getRegistryMock.mockResolvedValue({
      data: {
        ollama: {
          models: {
            text2image: [
              {
                model_name: 'gpt-image-2',
                label: 'Ollama Image (gpt-image-2)',
                config: {
                  pricing_mode: 'flat',
                  pricing_cents: { flat: 0 },
                },
              },
            ],
          },
        },
      },
    })
    listModelsMock.mockResolvedValue({ data: [] })

    render(<ProvidersPage />)

    expect(await screen.findByText('Ollama Image (gpt-image-2)')).toBeInTheDocument()
    expect(screen.getAllByText('providers.textToImage').length).toBeGreaterThan(0)
  })
})
