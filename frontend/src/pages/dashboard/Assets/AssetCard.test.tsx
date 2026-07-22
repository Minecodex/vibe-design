import type { ReactNode } from 'react'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'
import { AssetCard } from './AssetCard'
import type { AssetRead } from '@/api/endpoints/assets'

const {
  batchMock,
  globalBatchMock,
  toastSuccessMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  batchMock: vi.fn(),
  globalBatchMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (_key: string, fallback?: string, options?: { count?: number }) =>
      fallback?.replace('{{count}}', String(options?.count ?? '')) ?? _key,
  }),
}))

vi.mock('@/api/endpoints/assets', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/endpoints/assets')>()
  return {
    ...actual,
    assetsApi: {
      batch: batchMock,
      globalBatch: globalBatchMock,
    },
  }
})

vi.mock('sonner', () => ({
  toast: {
    success: toastSuccessMock,
    error: toastErrorMock,
  },
}))

vi.mock('@/hooks/useTheme', () => ({
  useIsDarkMode: () => false,
}))

vi.mock('@/components/ui/context-menu', () => ({
  ContextMenu: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ContextMenuTrigger: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ContextMenuContent: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ContextMenuItem: ({
    children,
    className,
    onClick,
  }: {
    children: ReactNode
    className?: string
    onClick?: () => void
  }) => (
    <button type="button" className={className} onClick={onClick}>
      {children}
    </button>
  ),
  ContextMenuSeparator: () => <div />,
}))

const asset: AssetRead = {
  id: 2,
  project_id: 10,
  user_id: 20,
  asset_type: 'image',
  url: 'https://example.com/library.png',
  list_preview_url: 'https://example.com/library__list_320.webp',
  list_preview_status: 'ready',
  created_at: '2026-03-18T12:00:00',
  updated_at: '2026-03-18T13:00:00',
  adder_avatar: null,
  adder_nickname: 'designer',
  is_favorite: false,
  project_name: 'Brand Refresh',
  origin_kind: 'ai_generated',
  canvas_item_id: null,
  source_asset_id: null,
}

describe('AssetsPage AssetCard', () => {
  test('matches the project-details hover treatment classes', () => {
    const { container } = render(
      <AssetCard
        asset={asset}
        isBatchMode={false}
        isSelected={false}
        onSelect={() => {}}
        onRefresh={() => {}}
        activeTab="all"
      />,
    )

    const root = container.querySelector('.aspect-square')
    expect(root).toHaveClass('aspect-square')
    expect(root).toHaveClass('hover:scale-[1.02]')
    expect(root).toHaveClass('group')

    const overlay = container.querySelector('div[class*="bg-gradient-to-t"]')
    expect(overlay).toHaveClass('opacity-0')
    expect(overlay).toHaveClass('group-hover:opacity-100')

    const name = screen.getByText('designer')
    const contentLayer = name.closest('div[class*="group-hover:visible"]')
    expect(contentLayer).toHaveClass('invisible')
    expect(contentLayer).not.toHaveClass('opacity-0')
  })

  test('requires confirmation before deleting an asset', async () => {
    const user = userEvent.setup()
    const onRefresh = vi.fn()
    globalBatchMock.mockResolvedValue({ success: true })

    render(
      <AssetCard
        asset={asset}
        isBatchMode={false}
        isSelected={false}
        onSelect={() => {}}
        onRefresh={onRefresh}
        activeTab="all"
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Delete' }))

    expect(globalBatchMock).not.toHaveBeenCalled()
    expect(screen.getByText('确定要删除该素材吗？')).toBeInTheDocument()

    const dialog = screen.getByRole('alertdialog')
    await user.click(within(dialog).getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(globalBatchMock).toHaveBeenCalledWith({ asset_ids: [asset.id], action: 'delete' })
    })
    expect(onRefresh).toHaveBeenCalled()
    expect(toastSuccessMock).toHaveBeenCalled()
  })

  test('prefers the list preview URL for image cards', () => {
    const { container } = render(
      <AssetCard
        asset={asset}
        isBatchMode={false}
        isSelected={false}
        onSelect={() => {}}
        onRefresh={() => {}}
        activeTab="all"
      />,
    )

    expect(container.querySelector('img')).toHaveAttribute('src', 'https://example.com/library__list_320.webp')
  })
})
