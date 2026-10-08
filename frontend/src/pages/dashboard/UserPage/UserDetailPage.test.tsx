import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UserDetailPage } from './UserDetailPage'
import { useAppConfigStore } from '@/store/appConfigStore'

const getUserMock = vi.fn()
const changePasswordMock = vi.fn()
const uploadAvatarMock = vi.fn()
const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()
const appConfigState = vi.hoisted(() => ({
  state: {
    appName: '像素重组',
    appNameEn: 'Pixel Reorganization',
    uploadLimits: null as null | {
      avatar_max_bytes: number
      canvas_image_max_bytes: number
      canvas_video_max_bytes: number
      harness_attachment_max_bytes: number
    },
    isLoaded: false,
  },
}))

vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: '1' }),
}))

vi.mock('react-i18next', () => {
  const t = (key: string, fallback?: string) => fallback ?? key
  return { useTranslation: () => ({ t }) }
})

vi.mock('@/api/endpoints/users', () => ({
  usersApi: {
    getUser: (...args: unknown[]) => getUserMock(...args),
    updateUser: vi.fn(),
    uploadAvatar: (...args: unknown[]) => uploadAvatarMock(...args),
    changePassword: (...args: unknown[]) => changePasswordMock(...args),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: () => ({
    user: { id: 1, username: 'viewer', role: 'user' },
    updateUser: vi.fn(),
  }),
}))

vi.mock('@/store/appConfigStore', () => {
  const useAppConfigStore = vi.fn((selector?: (state: typeof appConfigState.state) => unknown) => (
    selector ? selector(appConfigState.state) : appConfigState.state
  )) as unknown as {
    (selector?: (state: typeof appConfigState.state) => unknown): unknown
    getState: () => typeof appConfigState.state
    setState: (next: Partial<typeof appConfigState.state>) => void
  }
  useAppConfigStore.getState = () => appConfigState.state
  useAppConfigStore.setState = (next: Partial<typeof appConfigState.state>) => {
    appConfigState.state = { ...appConfigState.state, ...next }
  }
  return { useAppConfigStore }
})

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/utils/imageUrl', () => ({
  getImageUrl: (value: string | null | undefined) => value ?? '',
}))

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}))

describe('UserDetailPage profile editing', () => {
  beforeEach(() => {
    getUserMock.mockReset()
    changePasswordMock.mockReset()
    uploadAvatarMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    useAppConfigStore.setState({
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
      uploadLimits: null,
      isLoaded: false,
    })
  })

  test('does not enter nickname or bio edit mode for the admin account', async () => {
    getUserMock.mockResolvedValue({
      data: {
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        avatar_url: null,
        nickname: 'Admin',
        bio: 'Admin bio',
      },
    })

    render(<UserDetailPage />)

    await waitFor(() => {
      expect(screen.getByText('Admin')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Admin'))
    fireEvent.click(screen.getByText('Admin bio'))

    expect(screen.queryByDisplayValue('Admin')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('Admin bio')).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })

  test('still allows regular users to edit nickname', async () => {
    getUserMock.mockResolvedValue({
      data: {
        id: 2,
        username: 'alice',
        email: 'alice@example.com',
        role: 'user',
        is_active: true,
        avatar_url: null,
        nickname: 'Alice',
        bio: 'Hello there',
      },
    })

    render(<UserDetailPage />)

    await waitFor(() => {
      expect(screen.getByText('Alice')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Alice'))

    expect(screen.getByDisplayValue('Alice')).toBeInTheDocument()
  })

  test('does not render the notification settings section', async () => {
    getUserMock.mockResolvedValue({
      data: {
        id: 3,
        username: 'bob',
        email: 'bob@example.com',
        role: 'user',
        is_active: true,
        avatar_url: null,
        nickname: 'Bob',
        bio: 'Hi',
      },
    })

    render(<UserDetailPage />)

    await waitFor(() => {
      expect(screen.getByText('Bob')).toBeInTheDocument()
    })

    expect(screen.queryByText('通知设置')).not.toBeInTheDocument()
    expect(screen.queryByText('创作任务生成完成通知')).not.toBeInTheDocument()
  })

  test('formats password change validation errors into a toast-safe string', async () => {
    getUserMock.mockResolvedValue({
      data: {
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        avatar_url: null,
        nickname: 'Admin',
        bio: 'Admin bio',
      },
    })
    changePasswordMock.mockRejectedValue({
      response: {
        data: {
          detail: [
            {
              type: 'value_error',
              loc: ['body', 'new_password'],
              msg: '密码需包含大写字母和数字',
              input: 'password1',
            },
          ],
        },
      },
    })

    render(<UserDetailPage />)

    await waitFor(() => {
      expect(screen.getByText('Admin')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'users.changePassword' }))

    const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]'))
    fireEvent.change(passwordInputs[0], { target: { value: 'OldPass1' } })
    fireEvent.change(passwordInputs[1], { target: { value: 'Password1' } })
    fireEvent.change(passwordInputs[2], { target: { value: 'Password1' } })

    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('密码需包含大写字母和数字')
    })
  })

  test('blocks password change submission when the new password misses required complexity', async () => {
    getUserMock.mockResolvedValue({
      data: {
        id: 1,
        username: 'admin',
        email: 'admin@example.com',
        role: 'admin',
        is_active: true,
        avatar_url: null,
        nickname: 'Admin',
        bio: 'Admin bio',
      },
    })

    render(<UserDetailPage />)

    await waitFor(() => {
      expect(screen.getByText('Admin')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: 'users.changePassword' }))

    const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]'))
    fireEvent.change(passwordInputs[0], { target: { value: 'OldPass1' } })
    fireEvent.change(passwordInputs[1], { target: { value: 'password1' } })
    fireEvent.change(passwordInputs[2], { target: { value: 'password1' } })

    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('密码需包含大写字母和数字')
    })

    expect(changePasswordMock).not.toHaveBeenCalled()
  })

  test('does not upload an avatar when the selected file exceeds public config limit', async () => {
    getUserMock.mockResolvedValue({
      data: {
        id: 1,
        username: 'viewer',
        email: 'viewer@example.com',
        role: 'user',
        is_active: true,
        avatar_url: null,
        nickname: 'Viewer',
        bio: 'Bio',
      },
    })
    useAppConfigStore.setState({
      uploadLimits: {
        avatar_max_bytes: 3,
        canvas_image_max_bytes: 10,
        canvas_video_max_bytes: 10,
        harness_attachment_max_bytes: 10,
      },
    })

    render(<UserDetailPage />)

    await waitFor(() => {
      expect(screen.getByText('Viewer')).toBeInTheDocument()
    })

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, {
      target: {
        files: [new File(['toolarge'], 'avatar.png', { type: 'image/png' })],
      },
    })

    expect(uploadAvatarMock).not.toHaveBeenCalled()
    expect(toastErrorMock).toHaveBeenCalled()
  })
})
