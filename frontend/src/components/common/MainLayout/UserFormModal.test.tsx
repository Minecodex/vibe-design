import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { UserFormModal } from './UserFormModal'

const createUserMock = vi.fn()
const getApimartKeyStatusMock = vi.fn()
const revokeApimartKeyMock = vi.fn()
const updateCurrentUserMock = vi.fn()
const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}))

vi.mock('@/api/endpoints/users', () => ({
  usersApi: {
    createUser: (...args: unknown[]) => createUserMock(...args),
    updateUser: vi.fn(),
    getApimartKeyStatus: (...args: unknown[]) => getApimartKeyStatusMock(...args),
    revokeApimartKey: (...args: unknown[]) => revokeApimartKeyMock(...args),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: {
    getState: () => ({
      user: {
        id: 7,
        username: 'admin01',
        email: 'admin@example.com',
        role: 'admin',
        balance_cents: 8000,
      },
      updateUser: updateCurrentUserMock,
    }),
  },
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('sonner', () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}))

describe('UserFormModal validation errors', () => {
  beforeEach(() => {
    createUserMock.mockReset()
    getApimartKeyStatusMock.mockReset()
    revokeApimartKeyMock.mockReset()
    updateCurrentUserMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
  })

  test('formats validation error arrays into a toast-safe string when create user fails', async () => {
    createUserMock.mockRejectedValue({
      response: {
        data: {
          detail: [
            {
              type: 'value_error',
              loc: ['body', 'username'],
              msg: '用户名已存在',
              input: 'admin',
            },
          ],
        },
      },
    })

    render(<UserFormModal open user={null} onCancel={() => {}} onSuccess={() => {}} />)

    const inputs = screen.getAllByRole('textbox')

    fireEvent.change(inputs[0], { target: { value: 'admin01' } })
    fireEvent.change(inputs[1], { target: { value: 'admin@admin.com' } })
    fireEvent.change(inputs[2], { target: { value: 'admin' } })
    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled()
    })

    expect(toastErrorMock).toHaveBeenCalledWith('用户名已存在')
  })

  test('blocks create user submission when username is shorter than six characters', async () => {
    render(<UserFormModal open user={null} onCancel={() => {}} onSuccess={() => {}} />)

    const inputs = screen.getAllByRole('textbox')
    fireEvent.change(inputs[0], { target: { value: 'admin' } })
    fireEvent.change(inputs[1], { target: { value: 'admin@example.com' } })
    fireEvent.change(inputs[2], { target: { value: 'Admin' } })
    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('用户名至少 6 个字符')
    })

    expect(createUserMock).not.toHaveBeenCalled()
  })

  test('blocks create user submission when email format is invalid', async () => {
    render(<UserFormModal open user={null} onCancel={() => {}} onSuccess={() => {}} />)

    const inputs = screen.getAllByRole('textbox')
    fireEvent.change(inputs[0], { target: { value: 'admin01' } })
    fireEvent.change(inputs[1], { target: { value: 'admin' } })
    fireEvent.change(inputs[2], { target: { value: 'Admin' } })
    fireEvent.click(screen.getByRole('button', { name: '确定' }))

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('请输入有效的邮箱地址')
    })

    expect(createUserMock).not.toHaveBeenCalled()
  })

  test('clears the current user balance immediately after revoking their APIMart Key', async () => {
    getApimartKeyStatusMock.mockResolvedValue({
      data: { configured: true, status: 'active', key_hint: 'sk***01' },
    })
    revokeApimartKeyMock.mockResolvedValue({
      data: { configured: false, status: 'revoked', key_hint: null },
    })

    render(
      <UserFormModal
        open
        user={{
          id: 7,
          username: 'admin01',
          email: 'admin@example.com',
          nickname: 'Admin',
          role: 'admin',
          is_active: true,
          avatar_url: null,
        }}
        onCancel={() => {}}
        onSuccess={() => {}}
      />
    )

    const revokeButton = await screen.findByRole('button', { name: '撤销' })
    fireEvent.click(revokeButton)

    await waitFor(() => {
      expect(revokeApimartKeyMock).toHaveBeenCalledWith(7)
      expect(updateCurrentUserMock).toHaveBeenCalledWith(
        expect.objectContaining({ id: 7, balance_cents: 0 })
      )
    })
  })
})
