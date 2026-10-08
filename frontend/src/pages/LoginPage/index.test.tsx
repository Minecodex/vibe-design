import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginPage } from './index'

const navigateMock = vi.fn()
const changeLanguageMock = vi.fn()
const loginMock = vi.fn()
const clearErrorMock = vi.fn()

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
    isAuthenticated: false,
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
})
