import { createRef } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, test, vi } from 'vitest'

import { ImageAnchoredImagePanel } from './ImageAnchoredImagePanel'

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof ImageAnchoredImagePanel>> = {},
) {
  const onUpdateDraft = vi.fn()

  render(
    <ImageAnchoredImagePanel
      draft={{
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'gemini-3.1-flash-image-preview-official',
        provider_code: 'builtin',
        aspect_ratio: '1:1',
        resolution: '1K',
        reference_images: ['https://example.com/reference-1.png'],
      }}
      availableImageModels={[
        {
          value: 'gemini-3.1-flash-image-preview-official',
          name: 'Gemini 3.1 Flash Image',
          provider: 'builtin',
          providerName: 'Builtin',
          config: {
            allowed_sizes: ['1K', '2K'],
            allowed_aspect_ratios: ['1:1', '16:9'],
          },
        },
      ]}
      isDark={false}
      t={(key, fallback) => fallback || key}
      amountCents={12}
      referenceInputRef={createRef<HTMLInputElement>()}
      onUpdateDraft={onUpdateDraft}
      onPreviewImage={() => {}}
      onGenerate={() => {}}
      onPickReferenceFromLibrary={() => {}}
      {...overrides}
    />,
  )

  return { onUpdateDraft }
}

describe('ImageAnchoredImagePanel', () => {
  test('shows the locked source chip label in Chinese', () => {
    renderPanel()

    expect(screen.getByText('当前图片')).toBeInTheDocument()
  })

  test('does not show a price badge on the generate button', () => {
    renderPanel()

    expect(screen.getByText('Go')).toBeInTheDocument()
    expect(screen.queryByText('¥0.12')).not.toBeInTheDocument()
  })

  test('shows the locked source image without a delete control', () => {
    renderPanel()

    expect(screen.getByAltText('Source')).toBeInTheDocument()
    expect(screen.getAllByRole('button', { name: 'Remove reference' })).toHaveLength(1)
  })

  test('lets users remove uploaded references while keeping the source image locked', () => {
    const { onUpdateDraft } = renderPanel()

    fireEvent.click(screen.getByRole('button', { name: 'Remove reference' }))

    expect(onUpdateDraft).toHaveBeenCalledWith({
      reference_images: [],
    })
  })

  test('hides the ratio selector when the model does not expose selectable ratios', () => {
    renderPanel({
      draft: {
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'doubao-seedream-5-0-lite',
        provider_code: 'builtin',
        aspect_ratio: '1:1',
        resolution: '2K',
        reference_images: [],
      },
      availableImageModels: [
        {
          value: 'doubao-seedream-5-0-lite',
          name: 'Seedream 5.0 Lite',
          provider: 'builtin',
          providerName: 'Builtin',
          config: {
            allowed_sizes: ['2K'],
            allowed_aspect_ratios: [],
          },
        },
      ],
    })

    expect(screen.queryByText('画布比例')).not.toBeInTheDocument()
  })
})
