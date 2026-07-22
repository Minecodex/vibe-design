import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, test, vi, beforeEach } from 'vitest'
import { ShareViewPage } from '@/pages/dashboard/ShareViewPage'

const getInfoMock = vi.fn()
const accessProjectMock = vi.fn()
const setThemeMock = vi.fn()
const changeLanguageMock = vi.fn()

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? _key,
    i18n: {
      language: 'zh-CN',
      changeLanguage: changeLanguageMock,
    },
  }),
}))

vi.mock('react-router-dom', () => ({
  useParams: () => ({ token: 'viewer-token' }),
  useNavigate: () => vi.fn(),
}))

vi.mock('@/api/endpoints/share', () => ({
  shareApi: {
    getInfo: (...args: unknown[]) => getInfoMock(...args),
    accessProject: (...args: unknown[]) => accessProjectMock(...args),
    joinProject: vi.fn(),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: { isAuthenticated: boolean }) => unknown) =>
    selector({ isAuthenticated: false }),
}))

vi.mock('@/store/globalStore', () => ({
  useGlobalStore: (
    selector: (state: {
      theme: 'light' | 'dark' | 'system'
      setTheme: (theme: 'light' | 'dark' | 'system') => void
    }) => unknown
  ) => selector({ theme: 'light', setTheme: setThemeMock }),
}))

vi.mock('@/pages/dashboard/CanvasPage', () => ({
  CanvasPage: () => <div>Canvas Page</div>,
}))

vi.mock('@/components/project/ProjectDetailsView', () => ({
  ProjectDetailsView: ({ project, mode }: { project: { title: string }; mode?: string }) => (
    <div>
      <span>{project.title}</span>
      <span>{mode}</span>
    </div>
  ),
}))

describe('ShareViewPage', () => {
  beforeEach(() => {
    getInfoMock.mockReset()
    accessProjectMock.mockReset()
    getInfoMock.mockResolvedValue({ data: { require_password: false, permission: 'viewer' } })
    accessProjectMock.mockResolvedValue({
      data: {
        permission: 'viewer',
        require_password: false,
        project: {
          id: 10,
          user_id: 1,
          title: 'Viewer Shared Project',
          thumbnail_url: null,
          canvas_data: null,
          status: 'pending',
          share_token: 'viewer-token',
          share_permission: 'viewer',
          share_password: null,
          share_expiration: null,
          created_at: '2026-03-18T12:00:00',
          updated_at: '2026-03-18T12:00:00',
        },
      },
    })
  })

  test('renders readonly project details instead of canvas for viewer links', async () => {
    render(<ShareViewPage />)

    await waitFor(() => {
      expect(screen.getByText('Viewer Shared Project')).toBeInTheDocument()
    })

    expect(screen.getByText('share-readonly')).toBeInTheDocument()
    expect(screen.queryByText('Canvas Page')).not.toBeInTheDocument()
  })

  test('shows language and theme controls for guest viewers', async () => {
    render(<ShareViewPage />)

    await waitFor(() => {
      expect(screen.getByLabelText('切换主题')).toBeInTheDocument()
    })

    expect(screen.getByLabelText('切换语言')).toBeInTheDocument()
  })
})
