import { act, fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from './index'

const navigateMock = vi.fn()
const changeLanguageMock = vi.fn()
const loginMock = vi.fn()
const clearErrorMock = vi.fn()
const authState = { isAuthenticated: false }

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: vi.fn() },
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => defaultValue ?? key,
    i18n: {
      language: 'zh-CN',
      changeLanguage: changeLanguageMock,
    },
  }),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/store/globalStore', () => ({
  useGlobalStore: () => ({
    theme: 'light',
    setTheme: vi.fn(),
  }),
}))

vi.mock('@/store/authStore', () => {
  const useAuthStore = () => ({
    login: loginMock,
    isLoading: false,
    error: null,
    clearError: clearErrorMock,
    isAuthenticated: authState.isAuthenticated,
    licenseExpired: false,
  })

  useAuthStore.getState = () => ({
    licenseExpired: false,
  })

  return { useAuthStore }
})

describe('LoginPage', () => {
  beforeEach(() => {
    navigateMock.mockReset()
    changeLanguageMock.mockReset()
    loginMock.mockReset()
    clearErrorMock.mockReset()
    authState.isAuthenticated = false
  })

  it('renders a muted looping background video on the login page', () => {
    render(<LoginPage />)

    const video = screen.getByTestId('login-background-video') as HTMLVideoElement

    expect(video.autoplay).toBe(true)
    expect(video.loop).toBe(true)
    expect(video.muted).toBe(true)
    expect(video.playsInline).toBe(true)
    expect(video.querySelector('source')).toHaveAttribute(
      'src',
      expect.stringContaining('60f53aed34c133842c4d9bb4d05f0b31.mp4')
    )
  })

  it('does not redirect again after a pending login finishes following navigation', async () => {
    let finishLogin!: () => void
    loginMock.mockReturnValue(new Promise<void>(resolve => { finishLogin = resolve }))
    const view = render(<LoginPage />)
    const inputs = view.container.querySelectorAll('input')
    fireEvent.change(inputs[0], { target: { value: 'ciadmin' } })
    fireEvent.change(inputs[1], { target: { value: 'CI-public-fixture-123!' } })
    fireEvent.submit(view.container.querySelector('form')!)
    expect(loginMock).toHaveBeenCalledTimes(1)

    authState.isAuthenticated = true
    view.rerender(<LoginPage />)
    expect(navigateMock).toHaveBeenCalledTimes(1)
    expect(navigateMock).toHaveBeenCalledWith('/dashboard/projects', { replace: true })
    view.unmount()
    // A user may enter a project while deployment metadata is still loading.
    await act(async () => { finishLogin() })
    expect(navigateMock).toHaveBeenCalledTimes(1)
  })
})
