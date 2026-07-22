import '@/i18n'
import { render } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { AssetCard } from './AssetCard'

describe('Project AssetCard', () => {
  it('keeps a minimum 250 by 250 footprint so overlay controls remain clickable', () => {
    const { container } = render(
      <AssetCard
        asset={{
          id: 8,
          project_id: 1,
          user_id: 1,
          asset_type: 'image',
          url: 'https://example.com/project-image.png',
          list_preview_url: 'https://example.com/project-image__list_320.webp',
          list_preview_status: 'ready',
          created_at: '2026-03-17T10:00:00',
          updated_at: '2026-03-18T10:00:00',
          is_favorite: false,
          origin_kind: 'ai_generated',
          source_asset_id: null,
        }}
        onToggleFavorite={vi.fn()}
        onClick={vi.fn()}
      />
    )

    expect(container.firstElementChild).toHaveClass('min-w-[250px]')
    expect(container.firstElementChild).toHaveClass('min-h-[250px]')
    expect(container.querySelector('img')).toHaveAttribute('src', 'https://example.com/project-image__list_320.webp')
  })
})
