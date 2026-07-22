import '@/i18n'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AssetLibraryModal } from '@/pages/dashboard/CanvasPage/AssetLibraryModal'

const listProjectSummariesMock = vi.fn()
const listMock = vi.fn()

vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    listProjectSummaries: (...args: unknown[]) => listProjectSummariesMock(...args),
    list: (...args: unknown[]) => listMock(...args),
  },
  getAssetListMediaUrl: (asset: { list_preview_url?: string | null; url: string }) => asset.list_preview_url ?? asset.url,
}))

describe('AssetLibraryModal', () => {
  beforeEach(() => {
    listProjectSummariesMock.mockReset()
    listMock.mockReset()
    listProjectSummariesMock.mockResolvedValue({
      data: [
        {
          project_id: 1,
          project_name: 'Project One',
          asset_count: 1,
          image_count: 1,
          video_count: 0,
          latest_asset_updated_at: '2026-03-18T10:00:00',
        },
      ],
    })
    listMock.mockResolvedValue({
      data: [
        {
          id: 11,
          project_id: 1,
          user_id: 2,
          asset_type: 'image',
          url: 'https://example.com/local.png',
          created_at: '2026-03-17T10:00:00',
          updated_at: '2026-03-18T10:00:00',
          is_favorite: false,
          origin_kind: 'local_upload',
          source_asset_id: null,
        },
      ],
    })
  })

  it('shows a favorites checkbox and a local-upload badge', async () => {
    const user = userEvent.setup()

    render(
      <AssetLibraryModal
        open
        onOpenChange={vi.fn()}
        onImport={vi.fn()}
        isDark={false}
      />
    )

    await waitFor(() => {
      expect(listProjectSummariesMock).toHaveBeenCalledWith({
        asset_type: 'image',
        favorite_only: undefined,
        skip: 0,
        limit: 24,
      })
    })

    await user.click(await screen.findByText('Project One'))

    expect(await screen.findByText(/本地上传|local upload/i)).toBeInTheDocument()

    const favoritesCheckbox = screen.getByRole('checkbox', { name: /收藏|favorites/i })
    await user.click(favoritesCheckbox)

    await waitFor(() => {
      expect(listProjectSummariesMock).toHaveBeenLastCalledWith({
        asset_type: 'image',
        favorite_only: true,
        skip: 0,
        limit: 24,
      })
    })
  })
})
