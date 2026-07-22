import '@/i18n'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '@/i18n'

import { ActivationPage } from '@/pages/ActivationPage'

const activateMock = vi.fn()
const fetchDeployTypeMock = vi.fn()
const navigateMock = vi.fn()

let authState = {
  isAuthenticated: false,
  licenseExpired: true,
  licenseExpiresAt: null as string | null,
}

vi.mock('@/api/endpoints/license', () => ({
  licenseApi: {
    activate: (...args: unknown[]) => activateMock(...args),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: any) => unknown) =>
    selector({
      ...authState,
      fetchDeployType: fetchDeployTypeMock,
    }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

describe('ActivationPage', () => {
  beforeEach(() => {
    void i18n.changeLanguage('en-US')
    activateMock.mockReset()
    fetchDeployTypeMock.mockReset()
    navigateMock.mockReset()
    fetchDeployTypeMock.mockResolvedValue(undefined)
    activateMock.mockResolvedValue({ data: { expired: false } })
    authState = {
      isAuthenticated: false,
      licenseExpired: true,
      licenseExpiresAt: null,
    }
  })

  it('submits activation code and returns anonymous users to the login page', async () => {
    const user = userEvent.setup()

    render(<ActivationPage />)

    await user.type(screen.getByLabelText(/activation code/i), 'signed-license-code')
    await user.click(screen.getByRole('button', { name: /activate/i }))

    await waitFor(() => {
      expect(activateMock).toHaveBeenCalledWith({ code: 'signed-license-code' })
      expect(fetchDeployTypeMock).toHaveBeenCalled()
      expect(navigateMock).toHaveBeenCalledWith('/', { replace: true })
    })
  })

  it('returns authenticated users to the dashboard after successful activation', async () => {
    const user = userEvent.setup()
    authState.isAuthenticated = true

    render(<ActivationPage />)

    await user.type(screen.getByLabelText(/activation code/i), 'signed-license-code')
    await user.click(screen.getByRole('button', { name: /activate/i }))

    await waitFor(() => {
      expect(navigateMock).toHaveBeenCalledWith('/dashboard/projects', { replace: true })
    })
  })

  it('switches between English and Chinese copy', async () => {
    const user = userEvent.setup()

    render(<ActivationPage />)

    expect(screen.getByText(/Usage has expired/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /English/i }))
    await user.click(screen.getByText(/中文/))

    await waitFor(() => {
      expect(screen.getByText(/使用已到期，请申请新的密钥/)).toBeInTheDocument()
    })
  })
})
