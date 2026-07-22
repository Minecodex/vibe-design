import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigateMock = vi.fn()
const authStoreState = {
  isAuthenticated: false,
  licenseStatus: 'invalid' as 'active' | 'expired' | 'invalid' | 'missing' | null,
  licenseExpiresAt: null as string | null,
  fetchDeployType: vi.fn().mockResolvedValue(undefined),
}

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      language: 'zh-CN',
      changeLanguage: vi.fn(),
    },
  }),
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authStoreState) => unknown) =>
    selector ? selector(authStoreState) : authStoreState,
}))

vi.mock('@/api/endpoints/license', () => ({
  licenseApi: {
    activate: vi.fn(),
  },
}))

import { ActivationPage } from './index'

describe('ActivationPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    authStoreState.fetchDeployType.mockClear()
    authStoreState.isAuthenticated = false
    authStoreState.licenseExpiresAt = null
  })

  it('shows expired messaging for expired licenses', async () => {
    authStoreState.licenseStatus = 'expired'

    render(<ActivationPage />)
    await waitFor(() => expect(authStoreState.fetchDeployType).toHaveBeenCalled())

    expect(screen.getByText('activation.expired_title')).toBeInTheDocument()
    expect(screen.getByText('activation.expired_subtitle')).toBeInTheDocument()
    expect(screen.queryByText('activation.inactive_title')).not.toBeInTheDocument()
  })

  it('shows inactive messaging for invalid licenses', async () => {
    authStoreState.licenseStatus = 'invalid'

    render(<ActivationPage />)
    await waitFor(() => expect(authStoreState.fetchDeployType).toHaveBeenCalled())

    expect(screen.getByText('activation.inactive_title')).toBeInTheDocument()
    expect(screen.getByText('activation.inactive_subtitle')).toBeInTheDocument()
    expect(screen.queryByText('activation.expired_title')).not.toBeInTheDocument()
  })
})
