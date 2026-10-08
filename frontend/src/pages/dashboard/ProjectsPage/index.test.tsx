import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, test, vi } from 'vitest'
import { ProjectsPage } from './index'
import { applyProjectUsersUpdate, getNextRenderedProjectCount } from './projectListUtils'
import { resetProjectListStore } from '@/store/projectListStore'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')
const projectCardSource = readFileSync(resolve(currentDir, 'ProjectCard.tsx'), 'utf8')

const listProjectsMock = vi.fn()
const navigateMock = vi.fn()
const mockUser = { id: 99, username: 'member-user', role: 'user' }
const tMock = (key: string) => key

function openMoreActionsMenu() {
  const trigger = screen.getByRole('button', { name: /more actions/i })
  fireEvent.click(trigger)
  return trigger
}

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: tMock,
  }),
}))

vi.mock('react-router-dom', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/api/endpoints/projects', () => ({
  projectsApi: {
    list: (...args: unknown[]) => listProjectsMock(...args),
    create: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('@/store/authStore', () => ({
  useAuthStore: (selector: (state: { user: { id: number; username: string; role: string } | null }) => unknown) =>
    selector({ user: mockUser }),
}))

vi.mock('@/components/project/ShareModal', () => ({
  ShareModal: () => null,
}))

vi.mock('@/components/project/MembersModal', () => ({
  MembersModal: (props: any) => props.open ? (
    <button
      type="button"
      onClick={() => props.onMembersChange?.([
        {
          id: 99,
          nickname: 'Admin',
          username: 'admin',
          avatar_url: null,
          role: 'admin',
        },
      ])}
    >
      sync-members
    </button>
  ) : null,
}))

vi.mock('@/components/project/ProjectDetailsView', () => ({
  ProjectDetailsView: ({ onBack, project }: { onBack: () => void; project: { title: string } }) => (
    <div>
      <div>detail:{project.title}</div>
      <button type="button" onClick={onBack}>back-to-projects</button>
    </div>
  ),
}))

describe('ProjectsPage permissions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  beforeEach(() => {
    resetProjectListStore()
    listProjectsMock.mockReset()
    navigateMock.mockReset()
    mockUser.id = 99
    mockUser.username = 'member-user'
    mockUser.role = 'user'
    listProjectsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            user_id: 1,
            title: 'Shared Project',
            thumbnail_url: null,
            canvas_data: [],
            status: 'pending',
            share_token: null,
            share_permission: null,
            share_password: null,
            share_expiration: null,
            created_at: '2026-03-18T12:00:00',
            updated_at: '2026-03-18T12:00:00',
            users: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    })
  })

  test.skip('disables member config and sharing for non-owners with a manager-only hint', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    openMoreActionsMenu()

    const memberConfig = screen.getByText('projectsPage.userConfig').closest('div')
    const shareConfig = screen.getByText('projectsPage.projectShare').closest('div')

    expect(memberConfig).toHaveAttribute('title', '只有管理员才能点击')
    expect(memberConfig).toHaveAttribute('aria-disabled', 'true')
    expect(memberConfig).toHaveClass('cursor-not-allowed')

    expect(shareConfig).toHaveAttribute('title', '只有管理员才能点击')
    expect(shareConfig).toHaveAttribute('aria-disabled', 'true')
    expect(shareConfig).toHaveClass('cursor-not-allowed')
  })

  test('renders member config and sharing as disabled buttons for non-owners', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    openMoreActionsMenu()

    const memberConfig = await screen.findByRole('menuitem', { name: /projectsPage\.userConfig/i })
    const shareConfig = await screen.findByRole('menuitem', { name: /projectsPage\.projectShare/i })

    expect(memberConfig).toHaveAttribute('title')
    expect(memberConfig).toHaveAttribute('data-disabled')
    expect(memberConfig).toHaveAttribute('aria-disabled', 'true')
    expect(memberConfig).toHaveClass('cursor-not-allowed')

    expect(shareConfig).toHaveAttribute('title')
    expect(shareConfig).toHaveAttribute('data-disabled')
    expect(shareConfig).toHaveAttribute('aria-disabled', 'true')
    expect(shareConfig).toHaveClass('cursor-not-allowed')
  })

  test('keeps the more-actions dropdown open after clicking the trigger', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    const trigger = openMoreActionsMenu()

    await waitFor(() => {
      expect(trigger).toHaveAttribute('aria-expanded', 'true')
    })

    expect(await screen.findByRole('menuitem', { name: /projectsPage\.userConfig/i })).toBeInTheDocument()
  })

  test('allows admins to access member config and sharing actions', async () => {
    mockUser.role = 'admin'

    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    openMoreActionsMenu()

    const memberConfig = await screen.findByRole('menuitem', { name: /projectsPage\.userConfig/i })
    const shareConfig = await screen.findByRole('menuitem', { name: /projectsPage\.projectShare/i })
    const deleteAction = await screen.findByRole('menuitem', { name: /projectsPage\.delete/i })

    expect(memberConfig).not.toHaveAttribute('aria-disabled')
    expect(memberConfig).not.toHaveClass('cursor-not-allowed')

    expect(shareConfig).not.toHaveAttribute('aria-disabled')
    expect(shareConfig).not.toHaveClass('cursor-not-allowed')

    expect(deleteAction).toBeInTheDocument()
  })

  test('opens project details when admin clicks a project they have not joined', async () => {
    mockUser.role = 'admin'

    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Shared Project'))

    expect(navigateMock).not.toHaveBeenCalled()
    expect(await screen.findByText('detail:Shared Project')).toBeInTheDocument()
  })

  test('enters canvas when admin clicks a project they have already joined', async () => {
    mockUser.role = 'admin'
    listProjectsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            user_id: 1,
            title: 'Joined Project',
            thumbnail_url: null,
            canvas_data: [],
            status: 'pending',
            share_token: null,
            share_permission: null,
            share_password: null,
            share_expiration: null,
            created_at: '2026-03-18T12:00:00',
            updated_at: '2026-03-18T12:00:00',
            users: [
              { id: 99, nickname: 'Admin', username: 'admin', avatar_url: null, role: 'admin' },
            ],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    })

    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Joined Project')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Joined Project'))

    expect(navigateMock).toHaveBeenCalledWith('/canvas/1')
    expect(screen.queryByText('detail:Joined Project')).not.toBeInTheDocument()
  })

  test('applies refreshed members to the matching project after member management changes', () => {
    const projects = [
      {
        id: 1,
        user_id: 1,
        title: 'Shared Project',
        thumbnail_url: null,
        canvas_data: [],
        status: 'pending',
        share_token: null,
        share_permission: null,
        share_password: null,
        share_expiration: null,
        created_at: '2026-03-18T12:00:00',
        updated_at: '2026-03-18T12:00:00',
        users: [],
      },
    ]

    const nextProjects = applyProjectUsersUpdate(projects, 1, [
      { id: 99, nickname: 'Admin', username: 'admin', avatar_url: null, role: 'admin' },
    ])

    expect(nextProjects[0].users).toEqual([
      { id: 99, nickname: 'Admin', username: 'admin', avatar_url: null, role: 'admin' },
    ])
    expect(projects[0].users).toEqual([])
  })

  test('sorts projects by most recently updated first while keeping full list rendering', async () => {
    listProjectsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 2,
            user_id: 1,
            title: 'Newest Project',
            thumbnail_url: null,
            canvas_data: [],
            status: 'pending',
            share_token: null,
            share_permission: null,
            share_password: null,
            share_expiration: null,
            created_at: '2026-03-18T12:00:00',
            updated_at: '2026-03-20T12:00:00',
            users: [],
          },
          {
            id: 1,
            user_id: 1,
            title: 'Older Project',
            thumbnail_url: null,
            canvas_data: [],
            status: 'pending',
            share_token: null,
            share_permission: null,
            share_password: null,
            share_expiration: null,
            created_at: '2026-03-18T12:00:00',
            updated_at: '2026-03-18T12:00:00',
            users: [],
          },
        ],
        total: 2,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    })

    render(<ProjectsPage />)

    expect(await screen.findByText('Older Project')).toBeInTheDocument()
    expect(screen.getByText('Newest Project')).toBeInTheDocument()

    const projectTitles = screen
      .getAllByText(/Project$/)
      .filter(element => element.textContent !== 'projectsPage.newProject')
      .map(element => element.textContent)

    expect(projectTitles).toEqual(['Newest Project', 'Older Project'])
  })

  test('refreshes project data when the page becomes visible again after the cache becomes stale', async () => {
    let now = new Date('2026-03-18T12:00:00Z').valueOf()
    const dateNowSpy = vi.spyOn(Date, 'now').mockImplementation(() => now)

    listProjectsMock
      .mockResolvedValueOnce({
        data: {
          items: [
            {
              id: 1,
              user_id: 1,
              title: 'Shared Project',
              thumbnail_url: null,
              canvas_data: [],
              status: 'pending',
              share_token: null,
              share_permission: null,
              share_password: null,
              share_expiration: null,
              created_at: '2026-03-18T12:00:00',
              updated_at: '2026-03-18T12:00:00',
              users: [],
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          total_pages: 1,
        },
      })
      .mockResolvedValueOnce({
        data: {
          items: [
            {
              id: 1,
              user_id: 1,
              title: 'Shared Project',
              thumbnail_url: null,
              canvas_data: [],
              status: 'pending',
              share_token: null,
              share_permission: null,
              share_password: null,
              share_expiration: null,
              created_at: '2026-03-18T12:00:00',
              updated_at: '2026-03-20T12:00:00',
              users: [],
            },
          ],
          total: 1,
          page: 1,
          page_size: 20,
          total_pages: 1,
        },
      })

    render(<ProjectsPage />)

    await waitFor(() => {
      expect(listProjectsMock).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      now += 61_000
      fireEvent(document, new Event('visibilitychange'))
    })

    await waitFor(() => {
      expect(listProjectsMock).toHaveBeenCalledTimes(2)
    })

    dateNowSpy.mockRestore()
  })

  test('refreshes the project list when the projects route remounts while keeping cached projects visible', async () => {
    const firstRender = render(<ProjectsPage />)

    await waitFor(() => {
      expect(listProjectsMock).toHaveBeenCalledTimes(1)
    })

    firstRender.unmount()

    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    expect(listProjectsMock).toHaveBeenCalledTimes(2)
  })

  test('refreshes the project list when returning from project details', async () => {
    mockUser.role = 'admin'

    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByText('Shared Project'))
    expect(await screen.findByText('detail:Shared Project')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'back-to-projects' }))

    await waitFor(() => {
      expect(listProjectsMock).toHaveBeenCalledTimes(2)
    })
  })

  test('does not refresh project data on visibilitychange while the cache is still fresh', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(listProjectsMock).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      fireEvent(document, new Event('visibilitychange'))
    })

    expect(listProjectsMock).toHaveBeenCalledTimes(1)
  })

  test('raises a hovered project card above neighboring cards so its menus stay visible', () => {
    expect(projectCardSource).toContain('hover:z-20')
  })

  test('renders project title and updated time with shared foreground tokens in the card footer', () => {
    expect(projectCardSource).toContain('truncate text-[15px] font-bold tracking-tight text-foreground')
    expect(projectCardSource).toContain('text-[11px] font-medium text-[var(--app-foreground-muted)]')
  })

  test('keeps the projects page inside an internal vertical scroll container', () => {
    render(<ProjectsPage />)

    const scrollPane = screen.getByTestId('projects-page-scroll')

    expect(scrollPane?.className).toContain('min-h-0')
    expect(scrollPane?.className).toContain('overflow-y-auto')
    expect(scrollPane?.className).toContain('overflow-x-hidden')
  })

  test('renders visible projects through the extracted ProjectCard component', () => {
    expect(source).toContain("from './ProjectCard'")
    expect(source).toContain('<ProjectCard')
  })

  test('stages project card mounting across frames instead of rendering the full page at once', () => {
    expect(source).toContain('const projectRenderChunkSize = 6')
    expect(source).toContain('getNextRenderedProjectCount')
    expect(source).toContain('window.setTimeout(step, 32)')
    expect(source).toContain('const stagedVisibleProjects = visibleProjects.slice(0, renderedProjectCount)')
  })

  test('keeps already rendered project cards mounted when pagination appends more projects', () => {
    expect(getNextRenderedProjectCount({
      currentRenderedCount: 20,
      projectRenderChunkSize: 6,
      visibleProjectCount: 40,
    })).toBe(20)
  })

  test('derives visible projects from deferred search input to keep typing responsive', () => {
    expect(source).toContain('useDeferredValue')
    expect(source).toContain('const deferredSearchQuery = useDeferredValue(searchQuery)')
    expect(source).toContain("project.title.toLowerCase().includes(deferredSearchQuery.toLowerCase())")
  })

  test('lazy-loads heavy project overlays so the list page does not eagerly import them on first paint', () => {
    expect(source).toContain("const ShareModal = lazy(() => import('@/components/project/ShareModal').then")
    expect(source).toContain("const MembersModal = lazy(() => import('@/components/project/MembersModal').then")
    expect(source).toContain("const ProjectDetailsView = lazy(() => import('@/components/project/ProjectDetailsView').then")
    expect(source).toContain('<Suspense fallback={null}>')
  })

  test('renders the more-actions menu through dropdown menu content instead of an in-card absolute popup', () => {
    expect(projectCardSource).toContain('DropdownMenuContent')
    expect(projectCardSource).toContain('DropdownMenuTrigger')
    expect(projectCardSource).not.toContain('role="menu"')
    expect(projectCardSource).toContain("align=\"end\"")
  })

  test('activates heavy project preview media only after the card nears the viewport', async () => {
    const observers: Array<{
      callback: IntersectionObserverCallback
      observe: ReturnType<typeof vi.fn>
      disconnect: ReturnType<typeof vi.fn>
      unobserve: ReturnType<typeof vi.fn>
    }> = []

    const MockIntersectionObserver = class {
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
      root = null
      rootMargin = '0px'
      thresholds = [0]

      constructor(callback: IntersectionObserverCallback) {
        observers.push({
          callback,
          observe: this.observe,
          disconnect: this.disconnect,
          unobserve: this.unobserve,
        })
      }

      takeRecords() {
        return []
      }
    }

    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver as unknown as typeof IntersectionObserver)

    listProjectsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            user_id: 1,
            title: 'Viewport Project',
            thumbnail_url: null,
            project_preview_items: [
              { asset_type: 'image', url: 'https://example.com/viewport-1.png' },
              { asset_type: 'image', url: 'https://example.com/viewport-2.png' },
            ],
            status: 'pending',
            share_token: null,
            share_permission: null,
            share_password: null,
            share_expiration: null,
            created_at: '2026-03-18T12:00:00',
            updated_at: '2026-03-18T12:00:00',
            users: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    })

    const { container } = render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Viewport Project')).toBeInTheDocument()
    })

    expect(container.querySelectorAll('img[src*="viewport-"]')).toHaveLength(0)
    expect(observers).toHaveLength(1)

    act(() => {
      observers[0].callback([
        {
          isIntersecting: true,
          target: document.createElement('div'),
        } as unknown as IntersectionObserverEntry,
      ], {} as IntersectionObserver)
    })

    await waitFor(() => {
      expect(container.querySelectorAll('img[src*="viewport-"]')).toHaveLength(2)
    })

    act(() => {
      observers[0].callback([
        {
          isIntersecting: false,
          target: document.createElement('div'),
        } as unknown as IntersectionObserverEntry,
      ], {} as IntersectionObserver)
    })

    expect(container.querySelectorAll('img[src*="viewport-"]')).toHaveLength(2)
  })

  test('renders project preview images with lazy and async loading hints', async () => {
    const observers: Array<{ callback: IntersectionObserverCallback }> = []

    const MockIntersectionObserver = class {
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
      root = null
      rootMargin = '0px'
      thresholds = [0]

      constructor(callback: IntersectionObserverCallback) {
        observers.push({ callback })
      }

      takeRecords() {
        return []
      }
    }

    vi.stubGlobal('IntersectionObserver', MockIntersectionObserver as unknown as typeof IntersectionObserver)

    listProjectsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            user_id: 1,
            title: 'Image Project',
            thumbnail_url: null,
            project_preview_items: [
              { asset_type: 'image', url: 'https://example.com/preview-1.png' },
              { asset_type: 'image', url: 'https://example.com/preview-2.png' },
            ],
            status: 'pending',
            share_token: null,
            share_permission: null,
            share_password: null,
            share_expiration: null,
            created_at: '2026-03-18T12:00:00',
            updated_at: '2026-03-18T12:00:00',
            users: [],
          },
        ],
        total: 1,
        page: 1,
        page_size: 20,
        total_pages: 1,
      },
    })

    const { container } = render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Image Project')).toBeInTheDocument()
    })

    act(() => {
      observers[0].callback([
        {
          isIntersecting: true,
          target: document.createElement('div'),
        } as unknown as IntersectionObserverEntry,
      ], {} as IntersectionObserver)
    })

    await waitFor(() => {
      expect(container.querySelectorAll('img[src*="preview-"]')).toHaveLength(2)
    })

    const previewImages = Array.from(container.querySelectorAll('img'))
      .filter(image => image.getAttribute('src')?.includes('preview-'))

    expect(previewImages.length).toBeGreaterThan(0)
    previewImages.forEach(image => {
      expect(image).toHaveAttribute('loading', 'lazy')
      expect(image).toHaveAttribute('decoding', 'async')
    })
  })

  test('uses targeted transitions on the project card shell instead of broad transition-all styling', () => {
    expect(projectCardSource).toContain('transition-transform transition-shadow')
    expect(projectCardSource).not.toContain('group transition-all flex flex-col')
    expect(projectCardSource).not.toContain('backdrop-blur-2xl border-t px-5 flex items-center justify-between transition-all')
    expect(projectCardSource).not.toContain('group-hover/people:visible transition-all')
  })

  test('applies containment hints so offscreen project cards stay cheaper to paint', () => {
    expect(projectCardSource).toContain("contentVisibility: 'auto'")
    expect(projectCardSource).toContain("containIntrinsicSize: '260px'")
    expect(projectCardSource).toContain("contain: 'layout style'")
    expect(projectCardSource).not.toContain("contain: 'layout paint style'")
  })

  test('reveals the project card more-actions menu through a click-triggered menu button', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    const trigger = screen.getByRole('button', { name: /more actions/i })
    expect(screen.queryByRole('menuitem', { name: /projectsPage\.userConfig/i })).not.toBeInTheDocument()
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu')
    fireEvent.click(trigger)
    await waitFor(() => {
      expect(trigger).toHaveAttribute('aria-expanded', 'true')
      expect(screen.getByRole('menuitem', { name: /projectsPage\.userConfig/i })).toBeVisible()
    })
  })

  test('closes the more-actions menu when clicking outside the card', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    const trigger = openMoreActionsMenu()
    expect(await screen.findByRole('menuitem', { name: /projectsPage\.userConfig/i })).toBeVisible()

    fireEvent.pointerDown(document.body)

    await waitFor(() => {
      expect(screen.queryByRole('menuitem', { name: /projectsPage\.userConfig/i })).not.toBeInTheDocument()
    })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })

  test('closes the more-actions menu when pressing escape', async () => {
    render(<ProjectsPage />)

    await waitFor(() => {
      expect(screen.getByText('Shared Project')).toBeInTheDocument()
    })

    const trigger = openMoreActionsMenu()
    expect(await screen.findByRole('menuitem', { name: /projectsPage\.userConfig/i })).toBeVisible()

    fireEvent.keyDown(document, { key: 'Escape' })

    await waitFor(() => {
      expect(screen.queryByRole('menuitem', { name: /projectsPage\.userConfig/i })).not.toBeInTheDocument()
    })
    expect(trigger).toHaveAttribute('aria-expanded', 'false')
  })
})
