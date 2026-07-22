import '@/i18n'
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AssetCard } from '@/pages/dashboard/Assets/AssetCard'

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
  },
}))

describe('AssetCard', () => {
  it('shows a local-upload badge for locally uploaded assets', () => {
    const { container } = render(
      <AssetCard
        asset={{
          id: 7,
          project_id: 1,
          user_id: 1,
          asset_type: 'image',
          url: 'https://example.com/image.png',
          created_at: '2026-03-17T10:00:00',
          updated_at: '2026-03-18T10:00:00',
          is_favorite: false,
          origin_kind: 'local_upload',
          source_asset_id: null,
        }}
        isBatchMode={false}
        isSelected={false}
        onSelect={vi.fn()}
        onRefresh={vi.fn()}
      />
    )

    expect(screen.getByText(/本地上传|local upload/i)).toBeInTheDocument()
    expect(container.firstElementChild).toHaveClass('min-w-[250px]')
    expect(container.firstElementChild).toHaveClass('min-h-[250px]')
  })
})
