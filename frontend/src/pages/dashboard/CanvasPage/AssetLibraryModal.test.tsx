import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, test, vi } from 'vitest'

import { AssetLibraryModal } from './AssetLibraryModal'

const listAllMock = vi.fn()
const listMock = vi.fn()
const listProjectSummariesMock = vi.fn()
const listGroupsMock = vi.fn()
const intersectionCallbacks: Array<(entries: Array<{ isIntersecting: boolean }>) => void> = []
const PAGE_SIZE = 24

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, fallbackOrOptions?: string | { defaultValue?: string }) =>
      typeof fallbackOrOptions === 'string' ? fallbackOrOptions : fallbackOrOptions?.defaultValue ?? key,
  }),
}))

vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    listAll: (...args: unknown[]) => listAllMock(...args),
    list: (...args: unknown[]) => listMock(...args),
    listProjectSummaries: (...args: unknown[]) => listProjectSummariesMock(...args),
    listGroups: (...args: unknown[]) => listGroupsMock(...args),
  },
}))

describe('AssetLibraryModal', () => {
  beforeEach(() => {
    listAllMock.mockReset()
    listMock.mockReset()
    listProjectSummariesMock.mockReset()
    listGroupsMock.mockReset()
    intersectionCallbacks.length = 0
    window.localStorage.clear()

    if (!HTMLElement.prototype.hasPointerCapture) {
      HTMLElement.prototype.hasPointerCapture = () => false
    }
    if (!HTMLElement.prototype.releasePointerCapture) {
      HTMLElement.prototype.releasePointerCapture = () => undefined
    }
    if (!HTMLElement.prototype.setPointerCapture) {
      HTMLElement.prototype.setPointerCapture = () => undefined
    }
    if (!HTMLElement.prototype.scrollIntoView) {
      HTMLElement.prototype.scrollIntoView = () => undefined
    }

    vi.stubGlobal(
      'IntersectionObserver',
      vi.fn().mockImplementation((callback: (entries: Array<{ isIntersecting: boolean }>) => void) => {
        intersectionCallbacks.push(callback)
        return {
          observe: vi.fn(),
          disconnect: vi.fn(),
          unobserve: vi.fn(),
        }
      }),
    )

    listProjectSummariesMock.mockResolvedValue({
      data: [
        {
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 2,
          image_count: 2,
          video_count: 0,
          latest_asset_updated_at: '2026-04-01T12:00:00',
        },
      ],
    })

    listMock.mockResolvedValue({
      data: [
        {
          id: 1,
          project_id: 7,
          user_id: 1,
          url: 'https://example.com/image-1.png',
          asset_type: 'image',
          origin_kind: 'local_upload',
          source_asset_id: null,
          created_at: '2026-04-01T11:00:00',
          updated_at: '2026-04-01T12:00:00',
          is_favorite: false,
          project_name: 'Brand Refresh',
          canvas_item_id: null,
        },
        {
          id: 2,
          project_id: 7,
          user_id: 1,
          url: 'https://example.com/image-2.png',
          asset_type: 'image',
          origin_kind: 'local_upload',
          source_asset_id: null,
          created_at: '2026-04-01T10:00:00',
          updated_at: '2026-04-01T11:00:00',
          is_favorite: false,
          project_name: 'Brand Refresh',
          canvas_item_id: null,
        },
      ],
    })
    listGroupsMock.mockResolvedValue({ data: [] })
  })

  test('uses generator pick mode with project-first single selection', async () => {
    const user = userEvent.setup()
    const onImport = vi.fn()
    const onSelect = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <AssetLibraryModal
        open
        onOpenChange={onOpenChange}
        onImport={onImport}
        isDark={false}
        mode="generator-pick"
        assetType="image"
        selectionMode="single"
        onSelect={onSelect}
      />,
    )

    await waitFor(() => {
      expect(listProjectSummariesMock).toHaveBeenCalledWith({
        asset_type: 'image',
        favorite_only: undefined,
        skip: 0,
        limit: 24,
      })
    })

    expect(screen.queryByRole('tab', { name: '图片' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Brand Refresh/i }))

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledWith(7, {
        asset_type: 'image',
        favorite_only: undefined,
        skip: 0,
        limit: 24,
      })
    })

    const firstAsset = await screen.findByAltText('asset-1')
    const secondAsset = await screen.findByAltText('asset-2')

    await user.click(firstAsset)
    await user.click(secondAsset)
    await user.click(screen.getByRole('button', { name: '确认' }))

    expect(onImport).not.toHaveBeenCalled()
    expect(onSelect).toHaveBeenCalledWith([
      {
        id: 2,
        project_id: 7,
        url: 'https://example.com/image-2.png',
        type: 'image',
        origin_kind: 'local_upload',
        source_asset_id: null,
        canvas_item_id: null,
        canvas_group_id: null,
        canvas_group_name: null,
        name: 'image-2.png',
        list_preview_url: null,
        source_kind: 'asset_library',
      },
    ])
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('renders above the chat sidebar like image preview', async () => {
    render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
      />,
    )

    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveClass('!z-[2147483647]')
  })

  test('loads more projects and more project assets via intersection observers', async () => {
    const user = userEvent.setup()

    const firstProjectsPage = Array.from({ length: PAGE_SIZE }, (_, index) => ({
      project_id: index === 0 ? 7 : 100 + index,
      project_name: index === 0 ? 'Brand Refresh' : `Project ${index}`,
      asset_count: 2,
      image_count: 2,
      video_count: 0,
      latest_asset_updated_at: '2026-04-01T12:00:00',
    }))

    const firstAssetsPage = Array.from({ length: PAGE_SIZE }, (_, index) => ({
      id: index === 0 ? 11 : 200 + index,
      project_id: 7,
      user_id: 1,
      url: index === 0 ? 'https://example.com/project-7-image-1.png' : `https://example.com/project-7-image-${index}.png`,
      asset_type: 'image' as const,
      origin_kind: 'local_upload' as const,
      source_asset_id: null,
      created_at: '2026-04-01T11:00:00',
      updated_at: '2026-04-01T12:00:00',
      is_favorite: false,
      project_name: 'Brand Refresh',
      canvas_item_id: null,
    }))

    listProjectSummariesMock
      .mockResolvedValueOnce({
        data: firstProjectsPage,
      })
      .mockResolvedValueOnce({
        data: [
          {
            project_id: 8,
            project_name: 'Motion Pack',
            asset_count: 1,
            image_count: 1,
            video_count: 0,
            latest_asset_updated_at: '2026-04-01T09:00:00',
          },
        ],
      })

    listMock
      .mockResolvedValueOnce({
        data: firstAssetsPage,
      })
      .mockResolvedValueOnce({
        data: [
          {
            id: 12,
            project_id: 7,
            user_id: 1,
            url: 'https://example.com/project-7-image-2.png',
            asset_type: 'image',
            origin_kind: 'local_upload',
            source_asset_id: null,
            created_at: '2026-04-01T10:00:00',
            updated_at: '2026-04-01T11:00:00',
            is_favorite: false,
            project_name: 'Brand Refresh',
            canvas_item_id: null,
          },
        ],
      })

    render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
      />,
    )

    expect(await screen.findByRole('button', { name: /Brand Refresh/i })).toBeInTheDocument()

    await act(async () => {
      intersectionCallbacks[intersectionCallbacks.length - 1]?.([{ isIntersecting: true }])
    })

    await waitFor(() => {
      expect(listProjectSummariesMock).toHaveBeenNthCalledWith(2, {
        asset_type: 'image',
        favorite_only: undefined,
        skip: PAGE_SIZE,
        limit: PAGE_SIZE,
      })
    })

    expect(await screen.findByRole('button', { name: /Motion Pack/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Brand Refresh/i }))

    await waitFor(() => {
      expect(listMock).toHaveBeenNthCalledWith(1, 7, {
        asset_type: 'image',
        favorite_only: undefined,
        skip: 0,
        limit: PAGE_SIZE,
      })
    })

    expect(await screen.findByAltText('asset-11')).toBeInTheDocument()

    await act(async () => {
      intersectionCallbacks[intersectionCallbacks.length - 1]?.([{ isIntersecting: true }])
    })

    await waitFor(() => {
      expect(listMock).toHaveBeenNthCalledWith(2, 7, {
        asset_type: 'image',
        favorite_only: undefined,
        skip: PAGE_SIZE,
        limit: PAGE_SIZE,
      })
    })

    expect(await screen.findByAltText('asset-12')).toBeInTheDocument()
  })

  test('opens directly inside the provided initial project', async () => {
    render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
        initialProject={{
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 2,
        }}
      />,
    )

    await waitFor(() => {
      expect(listMock).toHaveBeenCalledWith(7, {
        asset_type: 'image',
        favorite_only: undefined,
        skip: 0,
        limit: PAGE_SIZE,
      })
    })

    expect(screen.queryByRole('button', { name: /Brand Refresh/i })).not.toBeInTheDocument()
    expect(await screen.findByAltText('asset-1')).toBeInTheDocument()
  })

  test('allows confirming generator pick mode with an empty selection when enabled', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()
    const onOpenChange = vi.fn()

    render(
      <AssetLibraryModal
        open
        onOpenChange={onOpenChange}
        onImport={vi.fn()}
        isDark={false}
        mode="generator-pick"
        assetType="image"
        selectionMode="multiple"
        allowEmptySelection
        initialProject={{
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 2,
        }}
        onSelect={onSelect}
      />,
    )

    await screen.findByAltText('asset-1')

    const confirmButton = screen.getByRole('button', { name: '确认' })
    expect(confirmButton).not.toBeDisabled()

    await user.click(confirmButton)

    expect(onSelect).toHaveBeenCalledWith([])
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  test('passes the selected canvas group to the project asset query', async () => {
    const user = userEvent.setup()

    listGroupsMock.mockResolvedValueOnce({
      data: [
        {
          group_id: 'group-lookbook',
          group_name: 'Lookbook',
          asset_count: 1,
          image_count: 1,
          video_count: 0,
          is_ungrouped: false,
        },
      ],
    })
    listMock
      .mockResolvedValueOnce({
        data: [
          {
            id: 1,
            project_id: 7,
            user_id: 1,
            url: 'https://example.com/image-1.png',
            asset_type: 'image',
            origin_kind: 'local_upload',
            source_asset_id: null,
            created_at: '2026-04-01T11:00:00',
            updated_at: '2026-04-01T12:00:00',
            is_favorite: false,
            project_name: 'Brand Refresh',
            canvas_item_id: 'image-1',
          },
        ],
      })
      .mockResolvedValueOnce({
        data: [
          {
            id: 2,
            project_id: 7,
            user_id: 1,
            url: 'https://example.com/lookbook.png',
            asset_type: 'image',
            origin_kind: 'local_upload',
            source_asset_id: null,
            created_at: '2026-04-01T11:00:00',
            updated_at: '2026-04-01T12:00:00',
            is_favorite: false,
            project_name: 'Brand Refresh',
            canvas_item_id: 'lookbook-image',
            canvas_group_id: 'group-lookbook',
            canvas_group_name: 'Lookbook',
          },
        ],
      })

    render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
        initialProject={{
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 2,
        }}
      />,
    )

    await screen.findByAltText('asset-1')

    await user.click(screen.getByLabelText('分组筛选'))
    await user.click(await screen.findByRole('option', { name: 'Lookbook' }))

    await waitFor(() => {
      expect(listMock).toHaveBeenNthCalledWith(2, 7, {
        asset_type: 'image',
        favorite_only: undefined,
        skip: 0,
        limit: PAGE_SIZE,
        canvas_group_id: 'group-lookbook',
      })
    })
    expect(await screen.findByAltText('asset-2')).toBeInTheDocument()
  })

  test('stores confirmed image selections as recently used assets', async () => {
    const user = userEvent.setup()

    const { unmount } = render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
        initialProject={{
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 2,
        }}
      />,
    )

    await user.click(await screen.findByAltText('asset-1'))
    await user.click(screen.getByRole('button', { name: '确认' }))

    expect(JSON.parse(window.localStorage.getItem('canvas.assetLibrary.recentImages.v1') || '[]')).toMatchObject([
      { id: 1, project_id: 7, url: 'https://example.com/image-1.png' },
    ])

    unmount()

    render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
        initialProject={{
          project_id: 7,
          project_name: 'Brand Refresh',
          asset_count: 2,
        }}
      />,
    )

    expect(await screen.findByText('最近常用')).toBeInTheDocument()
    expect(screen.getAllByAltText('asset-1')).toHaveLength(1)
  })
})
