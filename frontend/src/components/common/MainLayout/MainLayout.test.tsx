import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MainLayout } from './index'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, defaultValue?: string) => defaultValue ?? key,
    i18n: {
      language: 'zh-CN',
      changeLanguage: vi.fn(),
    },
  }),
}))

const authStoreState = {
  user: {
    id: 1,
    role: 'admin',
    username: 'admin',
    nickname: 'admin',
    email: 'admin@admin.com',
    balance_cents: 9946,
  },
  logout: vi.fn(),
  refreshBalance: vi.fn(),
  fetchDeployType: vi.fn(),
  deployType: 'saas',
  licenseEdition: 'flagship',
  providerBalanceSyncEnabled: false,
}

const globalStoreState = {
  theme: 'light',
  setTheme: vi.fn(),
  dismissedBalanceAlert: false,
  setDismissedBalanceAlert: vi.fn(),
}

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector?: (state: typeof authStoreState) => unknown) =>
    selector ? selector(authStoreState) : authStoreState,
}))

vi.mock('@/store/globalStore', () => ({
  useGlobalStore: (selector?: (state: typeof globalStoreState) => unknown) =>
    selector ? selector(globalStoreState) : globalStoreState,
}))

vi.mock('@/utils/imageUrl', () => ({
  getImageUrl: () => '',
}))

vi.mock('@/api/endpoints/projects', () => ({
  projectsApi: {
    create: vi.fn(),
  },
}))

vi.mock('./OrganizationModal', () => ({
  OrganizationModal: () => null,
}))

vi.mock('./BillingModal', () => ({
  BillingModal: ({ open, onCancel }: { open: boolean; onCancel: () => void }) =>
    open ? (
      <div aria-label="任务日志">
        <button onClick={onCancel}>关闭</button>
        任务日志
      </div>
    ) : null,
}))

describe('MainLayout billing entry', () => {
  beforeEach(() => {
    vi.useRealTimers()
    authStoreState.refreshBalance.mockClear()
    authStoreState.fetchDeployType.mockClear()
    authStoreState.logout.mockClear()
    authStoreState.providerBalanceSyncEnabled = false
    authStoreState.user.balance_cents = 9946
    authStoreState.licenseEdition = 'flagship'

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: '',
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  it('refreshes the APIMart balance every five minutes', () => {
    vi.useFakeTimers()

    render(
      <MemoryRouter initialEntries={['/dashboard/projects']}>
        <Routes>
          <Route path="/dashboard/*" element={<MainLayout />}>
            <Route path="projects" element={<div>projects</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    expect(authStoreState.refreshBalance).toHaveBeenCalledTimes(1)
    act(() => {
      vi.advanceTimersByTime(300_000)
    })
    expect(authStoreState.refreshBalance).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })

  it('refreshes balance again when the user avatar menu opens', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/dashboard/projects']}>
        <Routes>
          <Route path="/dashboard/*" element={<MainLayout />}>
            <Route path="projects" element={<div>projects</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    expect(authStoreState.refreshBalance).toHaveBeenCalledTimes(1)
    expect(authStoreState.fetchDeployType).toHaveBeenCalledTimes(1)

    const avatarButton = screen.getByText('A').closest('button')
    expect(avatarButton).not.toBeNull()
    await user.click(avatarButton!)

    await waitFor(() => {
      expect(authStoreState.refreshBalance).toHaveBeenCalledTimes(2)
    })
  })

  it('hides local low-balance alerts in provider balance sync mode', () => {
    authStoreState.providerBalanceSyncEnabled = true
    authStoreState.user.balance_cents = 0

    render(
      <MemoryRouter initialEntries={['/dashboard/projects']}>
        <Routes>
          <Route path="/dashboard/*" element={<MainLayout />}>
            <Route path="projects" element={<div>projects</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    expect(screen.queryByText('余额低于 ¥7.00，请及时充值')).not.toBeInTheDocument()
  })

  it('closes the user dropdown after opening the billing modal', async () => {
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/dashboard/projects']}>
        <Routes>
          <Route path="/dashboard/*" element={<MainLayout />}>
            <Route path="projects" element={<div>projects</div>} />
            <Route path="users/:id" element={<div>user detail</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    const avatarButton = screen.getByText('A').closest('button')
    expect(avatarButton).not.toBeNull()
    await user.click(avatarButton!)
    await user.click(screen.getByText('余额'))

    expect(screen.getByText('任务日志')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.queryByText('个人设置')).not.toBeInTheDocument()
    })
  })
  it('keeps the dashboard layout constrained so nested pages can scroll internally', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/dashboard/projects']}>
        <Routes>
          <Route path="/dashboard/*" element={<MainLayout />}>
            <Route path="projects" element={<div>projects</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    )

    const appShell = Array.from(container.querySelectorAll('div')).find((element) => {
      const className = element.className
      return typeof className === 'string'
        && className.includes('min-h-screen')
        && className.includes('flex-col')
    }) as HTMLElement | undefined
    const contentRow = Array.from(container.querySelectorAll('div')).find((element) => {
      const className = element.className
      return typeof className === 'string'
        && className.includes('flex-row')
        && className.includes('flex-1')
    }) as HTMLElement | undefined
    const outletColumn = Array.from(container.querySelectorAll('div')).find((element) => {
      const className = element.className
      return typeof className === 'string'
        && className.includes('flex-col')
        && className.includes('m-0')
        && className.includes('p-0')
    }) as HTMLElement | undefined

    expect(appShell?.className).toContain('overflow-hidden')
    expect(contentRow?.className).toContain('min-h-0')
    expect(contentRow?.className).toContain('overflow-hidden')
    expect(outletColumn?.className).toContain('min-h-0')
    expect(outletColumn?.className).toContain('overflow-hidden')
  })

  it('hides the home navigation item for premium edition', () => {
    authStoreState.licenseEdition = 'premium'

    render(
      <MemoryRouter initialEntries={['/dashboard/projects']}>
        <Routes>
          <Route path="/dashboard/*" element={<MainLayout />}>
            <Route path="projects" element={<div>projects</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByText('主页')).not.toBeInTheDocument()

    authStoreState.licenseEdition = 'flagship'
  })
})

