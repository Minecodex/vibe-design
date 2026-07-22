import { act, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { ProjectDetailsView } from './ProjectDetailsView'

const resizeObserverInstances: Array<{ callback: ResizeObserverCallback }> = []

class MockResizeObserver {
  callback: ResizeObserverCallback

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback
    resizeObserverInstances.push({ callback })
  }

  observe() {}

  disconnect() {}

  unobserve() {}
}

const enTranslations: Record<string, string> = {
  'menu.projects': 'Projects',
  'projectDetails.teamMembers': 'Team Members',
  'projectDetails.assetLibrary': 'Asset Library',
  'projectDetails.all': 'All',
  'projectDetails.image': 'Image',
  'projectDetails.video': 'Video',
  'projectDetails.backToProjects': 'Back to Projects',
  'projectDetails.totalWorks': '{{count}} Works',
  'projectDetails.active': 'Active',
  'projectDetails.offline': 'Offline',
  'projectDetails.recentUpdate': 'Updated {{time}} ago',
  'my_favorites': 'My Favorites',
  'projectsPage.loading': 'Loading...',
  'projectsPage.statusPending': 'Pending',
}

const listMembersMock = vi.fn()
const listAssetsMock = vi.fn()

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string; count?: number; time?: string }) => {
      const template = enTranslations[key]
      if (!template) return options?.defaultValue ?? key
      return template
        .replace('{{count}}', String(options?.count ?? ''))
        .replace('{{time}}', String(options?.time ?? ''))
    },
  }),
}))

vi.mock('@/api/endpoints/projectMembers', () => ({
  projectMembersApi: {
    list: (...args: unknown[]) => listMembersMock(...args),
  },
}))

vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    list: (...args: unknown[]) => listAssetsMock(...args),
    batch: vi.fn(),
  },
}))

vi.mock('@/api/endpoints/projects', () => ({
  projectsApi: {
    update: vi.fn(),
  },
}))

vi.mock('@/api/endpoints/share', () => ({
  shareApi: {
    listSharedAssets: vi.fn(),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: { user: { id: number; username: string } }) => unknown) =>
    selector({ user: { id: 1, username: 'admin' } }),
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/components/project/AssetCard', () => ({
  AssetCard: ({ asset }: { asset: { id: number } }) => <div>{`asset card ${asset.id}`}</div>,
}))

vi.mock('@/components/project/AssetPreviewModal', () => ({
  AssetPreviewModal: () => null,
}))

vi.mock('@/components/ui/popover', () => ({
  Popover: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  PopoverContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/utils/imageUrl', () => ({
  getImageUrl: () => null,
}))

describe('ProjectDetailsView', () => {
  beforeEach(() => {
    resizeObserverInstances.length = 0
    listMembersMock.mockReset()
    listAssetsMock.mockReset()
    listMembersMock.mockResolvedValue({
      data: [
        {
          user_id: 1,
          role: 'owner',
          user: {
            username: 'admin',
            nickname: 'admin',
            avatar_url: null,
          },
        },
      ],
    })
    listAssetsMock.mockResolvedValue({ data: [] })
    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn().mockImplementation(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    )
    vi.stubGlobal('ResizeObserver', MockResizeObserver as unknown as typeof ResizeObserver)
  })

  test('shows the favorites toggle in English when the UI language is English', async () => {
    render(
      <ProjectDetailsView
        project={{
          id: 1,
          user_id: 1,
          title: 'Untitled',
          thumbnail_url: null,
          canvas_data: null,
          status: 'pending',
          share_token: null,
          share_permission: null,
          share_password: null,
          share_expiration: null,
          created_at: '2026-03-29T00:00:00Z',
          updated_at: '2026-03-29T00:00:00Z',
        }}
        onBack={() => {}}
        onUpdate={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('Team Members')).toBeInTheDocument()
    })

    expect(screen.getByText('My Favorites')).toBeInTheDocument()
  })

  test('virtualizes the project asset grid instead of rendering every card at once', async () => {
    listAssetsMock.mockResolvedValue({
      data: Array.from({ length: 120 }, (_, index) => ({
        id: index + 1,
        project_id: 1,
        user_id: 1,
        asset_type: 'image',
        url: `https://example.com/${index + 1}.png`,
        created_at: '2026-03-29T00:00:00Z',
        updated_at: '2026-03-29T00:00:00Z',
        adder_avatar: null,
        adder_nickname: 'admin',
        is_favorite: false,
        project_name: 'Untitled',
        canvas_item_id: null,
        origin_kind: 'ai_generated',
        source_asset_id: null,
      })),
    })

    const { container } = render(
      <ProjectDetailsView
        project={{
          id: 1,
          user_id: 1,
          title: 'Untitled',
          thumbnail_url: null,
          canvas_data: null,
          status: 'pending',
          share_token: null,
          share_permission: null,
          share_password: null,
          share_expiration: null,
          created_at: '2026-03-29T00:00:00Z',
          updated_at: '2026-03-29T00:00:00Z',
        }}
        onBack={() => {}}
        onUpdate={() => {}}
      />,
    )

    await waitFor(() => {
      expect(screen.getByText('asset card 1')).toBeInTheDocument()
    })

    const scrollContainer = container.querySelector('.flex-1.overflow-y-auto.overflow-x-hidden.pb-32') as HTMLDivElement
    const host = container.querySelector('[data-testid="virtualized-section-grid"]') as HTMLDivElement

    Object.defineProperty(scrollContainer, 'clientHeight', { configurable: true, value: 600 })
    Object.defineProperty(host, 'clientWidth', { configurable: true, value: 1040 })
    Object.defineProperty(host, 'offsetTop', { configurable: true, value: 0 })

    act(() => {
      resizeObserverInstances.forEach(({ callback }) => {
        callback(
          [
            {
              target: host,
              contentRect: { width: 1040, height: 0 } as DOMRectReadOnly,
            } as unknown as ResizeObserverEntry,
          ],
          {} as ResizeObserver,
        )
      })
    })

    await waitFor(() => {
      const cards = screen.getAllByText(/asset card /)
      expect(cards.length).toBeLessThan(40)
    })

    expect(screen.queryByText('asset card 120')).not.toBeInTheDocument()
  })
})
