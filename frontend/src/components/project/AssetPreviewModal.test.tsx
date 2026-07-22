import { createEvent, fireEvent, render, waitFor } from '@testing-library/react'
import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest'
import { AssetPreviewModal } from './AssetPreviewModal'
import type { AssetRead } from '@/api/endpoints/assets'

vi.mock('react-i18next', () => ({
  initReactI18next: {
    type: '3rdParty',
    init: () => {},
  },
  useTranslation: () => ({
    t: (_key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? _key,
  }),
}))

const asset: AssetRead = {
  id: 1,
  project_id: 10,
  user_id: 99,
  asset_type: 'image',
  url: 'https://example.com/sample.png',
  list_preview_url: 'https://example.com/sample__list_320.webp',
  list_preview_status: 'ready',
  created_at: '2026-03-18T12:00:00',
  updated_at: '2026-03-18T12:00:00',
  adder_avatar: null,
  adder_nickname: 'admin',
  is_favorite: false,
  project_name: 'Demo Project',
  origin_kind: 'ai_generated',
  canvas_item_id: null,
  source_asset_id: null,
}

const secondAsset: AssetRead = {
  ...asset,
  id: 2,
  url: 'https://example.com/sample-2.png',
  list_preview_url: 'https://example.com/sample-2__list_320.webp',
}

describe('AssetPreviewModal', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'ResizeObserver',
      vi.fn().mockImplementation(() => ({
        observe: vi.fn(),
        disconnect: vi.fn(),
        unobserve: vi.fn(),
      })),
    )
    window.HTMLElement.prototype.scrollTo = vi.fn(function scrollTo(
      this: HTMLElement,
      options?: ScrollToOptions | number,
      y?: number,
    ) {
      if (typeof options === 'object' && options !== null) {
        if (typeof options.left === 'number') {
          Object.defineProperty(this, 'scrollLeft', { configurable: true, value: options.left, writable: true })
        }
        if (typeof options.top === 'number') {
          Object.defineProperty(this, 'scrollTop', { configurable: true, value: options.top, writable: true })
        }
        return
      }

      if (typeof options === 'number') {
        Object.defineProperty(this, 'scrollLeft', { configurable: true, value: options, writable: true })
      }
      if (typeof y === 'number') {
        Object.defineProperty(this, 'scrollTop', { configurable: true, value: y, writable: true })
      }
    }) as typeof window.HTMLElement.prototype.scrollTo
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        headers: {
          get: vi.fn().mockReturnValue(String(2 * 1024 * 1024)),
        },
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  test('uses the unified app primary style for the download button', async () => {
    const { container } = render(<AssetPreviewModal assets={[asset]} initialIndex={0} onClose={() => {}} />)

    const button = container.querySelector('button.flex-1')
    expect(button).not.toBeNull()

    await waitFor(() => {
      expect(button).toHaveClass('bg-[var(--app-primary)]')
      expect(button).toHaveClass('text-[var(--app-primary-foreground)]')
      expect(button).toHaveClass('hover:bg-[var(--app-primary-hover)]')
    })
  })

  test('hides the download button when downloading is disabled', async () => {
    const { container } = render(<AssetPreviewModal assets={[asset]} initialIndex={0} onClose={() => {}} canDownload={false} />)

    await waitFor(() => {
      expect(container.querySelector('button.flex-1')).toBeNull()
    })
  })

  test('keeps the active thumbnail in view when arrow keys switch images', async () => {
    render(<AssetPreviewModal assets={[asset, secondAsset]} initialIndex={0} onClose={() => {}} />)

    fireEvent.keyDown(window, { key: 'ArrowRight' })

    await waitFor(() => {
      expect(window.HTMLElement.prototype.scrollTo).toHaveBeenCalled()
    })
  })

  test('does not wrap from the last image back to the first image', async () => {
    const { getByTestId } = render(<AssetPreviewModal assets={[asset, secondAsset]} initialIndex={1} onClose={() => {}} />)

    expect(getByTestId('asset-preview-next')).toBeDisabled()

    fireEvent.keyDown(window, { key: 'ArrowRight' })

    await waitFor(() => {
      expect(getByTestId('asset-preview-image')).toHaveAttribute('src', 'https://example.com/sample-2.png')
    })
  })

  test('supports wheel zoom for images', async () => {
    const { getByTestId } = render(<AssetPreviewModal assets={[asset]} initialIndex={0} onClose={() => {}} />)

    const stage = getByTestId('asset-preview-image-stage')
    const image = getByTestId('asset-preview-image')

    fireEvent.wheel(stage, { deltaY: -100 })

    await waitFor(() => {
      expect(image).toHaveStyle({ transform: 'translate(0px, 0px) scale(1.2)' })
    })
  })

  test('supports dragging the zoomed image to inspect different areas', async () => {
    const { getByTestId } = render(<AssetPreviewModal assets={[asset]} initialIndex={0} onClose={() => {}} />)

    const stage = getByTestId('asset-preview-image-stage')
    const image = getByTestId('asset-preview-image')

    fireEvent.wheel(stage, { deltaY: -100 })
    const pointerDown = createEvent.pointerDown(stage)
    Object.defineProperties(pointerDown, {
      pointerId: { value: 1 },
      clientX: { value: 100 },
      clientY: { value: 120 },
    })
    fireEvent(stage, pointerDown)

    const pointerMove = createEvent.pointerMove(stage)
    Object.defineProperties(pointerMove, {
      pointerId: { value: 1 },
      clientX: { value: 150 },
      clientY: { value: 170 },
    })
    fireEvent(stage, pointerMove)

    const pointerUp = createEvent.pointerUp(stage)
    Object.defineProperties(pointerUp, {
      pointerId: { value: 1 },
      clientX: { value: 150 },
      clientY: { value: 170 },
    })
    fireEvent(stage, pointerUp)

    await waitFor(() => {
      expect(image).toHaveStyle({ transform: 'translate(50px, 50px) scale(1.2)' })
    })
  })

  test('virtualizes the thumbnail strip instead of rendering every asset button at once', async () => {
    const assets = Array.from({ length: 120 }, (_, index) => ({
      ...asset,
      id: index + 1,
      url: `https://example.com/sample-${index + 1}.png`,
    }))

    const { getByTestId } = render(<AssetPreviewModal assets={assets} initialIndex={0} onClose={() => {}} />)

    const thumbnailStrip = getByTestId('asset-preview-thumbnails')

    await waitFor(() => {
      expect(thumbnailStrip.querySelectorAll('button').length).toBeLessThan(40)
    })
  })

  test('renders an end marker spacer after the last detail thumbnail', async () => {
    const { getByTestId } = render(<AssetPreviewModal assets={[asset, secondAsset]} initialIndex={1} onClose={() => {}} />)

    await waitFor(() => {
      expect(getByTestId('asset-preview-thumbnail-end-spacer')).toBeInTheDocument()
    })
  })

  test('keeps the preview modal main image on the original URL while thumbnail images prefer preview URLs', async () => {
    const { getByTestId, container } = render(<AssetPreviewModal assets={[asset, secondAsset]} initialIndex={0} onClose={() => {}} />)

    const mainImage = getByTestId('asset-preview-image')

    await waitFor(() => {
      expect(mainImage).toHaveAttribute('src', 'https://example.com/sample.png')
    })

    const thumbnailImage = container.querySelector('[data-testid="asset-preview-thumbnails"] img')
    expect(thumbnailImage).toHaveAttribute('src', 'https://example.com/sample__list_320.webp')
  })

  test('falls back to the original image when a detail thumbnail preview image fails to load', async () => {
    const { container } = render(<AssetPreviewModal assets={[asset]} initialIndex={0} onClose={() => {}} />)

    const thumbnailImage = container.querySelector('[data-testid="asset-preview-thumbnails"] img')
    expect(thumbnailImage).toHaveAttribute('src', 'https://example.com/sample__list_320.webp')

    fireEvent.error(thumbnailImage!)

    await waitFor(() => {
      expect(container.querySelector('[data-testid="asset-preview-thumbnails"] img')).toHaveAttribute(
        'src',
        'https://example.com/sample.png',
      )
    })
  })
})
