import '@/i18n'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { AssetsPage } from '@/pages/dashboard/Assets'

const listAllMock = vi.fn()
const currentDir = dirname(fileURLToPath(import.meta.url))
const assetGridSource = readFileSync(
  resolve(currentDir, '../../../../src/pages/dashboard/Assets/AssetGrid.tsx'),
  'utf8',
)
const projectDetailsSource = readFileSync(
  resolve(currentDir, '../../../../src/components/project/ProjectDetailsView.tsx'),
  'utf8',
)

vi.mock('@/api/endpoints/assets', () => ({
  assetsApi: {
    listAll: (...args: unknown[]) => listAllMock(...args),
    list: vi.fn(),
    batch: vi.fn(),
    globalBatch: vi.fn(),
  },
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('AssetsPage', () => {
  beforeEach(() => {
    listAllMock.mockReset()
    listAllMock.mockResolvedValue({ data: [] })
  })

  it('uses a favorites toggle filter instead of a secondary tab', async () => {
    const user = userEvent.setup()

    render(<AssetsPage />)

    await waitFor(() => {
      expect(listAllMock).toHaveBeenCalledWith({ origin_kind: 'ai_generated' })
    })

    await user.click(screen.getByText(/我的收藏|my favorites/i))

    await waitFor(() => {
      expect(listAllMock).toHaveBeenLastCalledWith({
        origin_kind: 'ai_generated',
        favorite_only: true,
      })
    })

    expect(screen.queryByRole('tab', { name: /我的收藏|my favorites/i })).not.toBeInTheDocument()
  })

  it('uses responsive grids with a 250px minimum track size in assets and project details', () => {
    expect(assetGridSource).toContain('grid-cols-[repeat(auto-fill,minmax(250px,1fr))]')
    expect(projectDetailsSource).toContain('grid-cols-[repeat(auto-fill,minmax(250px,1fr))]')
  })
})
