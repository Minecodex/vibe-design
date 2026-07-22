import { createRef, useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, test, vi } from 'vitest'

import type { AnchoredVideoSourcePlacement } from '../imageAnchoredVideo'
import { ImageAnchoredVideoPanel } from './ImageAnchoredVideoPanel'

const referenceImages = Array.from({ length: 12 }, (_, index) => `https://example.com/reference-${index + 1}.png`)

function renderPanel(
  overrides: Partial<React.ComponentProps<typeof ImageAnchoredVideoPanel>> = {},
) {
  const onMoveSourcePlacement = vi.fn()

  const view = render(
    <ImageAnchoredVideoPanel
      draft={{
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'test-model',
        provider_code: 'provider',
        aspect_ratio: '1:1',
        duration: '5',
        resolution: '720p',
        sourcePlacement: 'reference',
        reference_images: referenceImages,
        first_frame_image: '',
        tail_frame_image: '',
      }}
      draftItem={{ reference_images: referenceImages }}
      capability={{
        supportsReferenceImages: true,
        maxReferenceImages: 14,
        supportsFirstFrame: false,
        supportsTailFrame: false,
        disableAspectRatioWhenImages: false,
        imageModesConflict: false,
      }}
      allowedDurations={['5']}
      availableVideoModels={[
        {
          value: 'test-model',
          name: 'Test Model',
          provider: 'provider',
          providerName: 'Provider',
          config: {
            allowed_sizes: ['720p'],
            allowed_aspect_ratios: ['1:1', '16:9', '9:16', '4:3', '3:4', '21:9', '9:21', '2:3', '3:2', '4:5', '5:4'],
          },
        },
      ]}
      isDark={false}
      t={(key, fallback) => fallback || key}
      amountCents={25}
      referenceInputRef={createRef<HTMLInputElement>()}
      firstFrameInputRef={createRef<HTMLInputElement>()}
      tailFrameInputRef={createRef<HTMLInputElement>()}
      onUpdateDraft={() => {}}
      onMoveSourcePlacement={onMoveSourcePlacement}
      onPreviewImage={() => {}}
      onGenerate={() => {}}
      onPickReferenceFromLibrary={() => {}}
      onPickFirstFrameFromLibrary={() => {}}
      onPickTailFrameFromLibrary={() => {}}
      {...overrides}
    />,
  )

  return { ...view, onMoveSourcePlacement }
}

describe('ImageAnchoredVideoPanel', () => {
  test('shows the locked source chip label in Chinese', () => {
    renderPanel()

    expect(screen.getByText('当前图片')).toBeInTheDocument()
  })

  test('does not show the drag hint by default', () => {
    renderPanel()

    expect(screen.queryByText('当前图片按住可拖拽')).not.toBeInTheDocument()
  })

  test('shows the drag hint when anchored video flow enables it', () => {
    renderPanel({
      showSourceDragHint: true,
    })

    expect(screen.getByText('当前图片按住可拖拽')).toBeInTheDocument()
  })

  test('does not show a price badge on the generate button', () => {
    renderPanel()

    expect(screen.getByText('Go')).toBeInTheDocument()
    expect(screen.queryByText('¥0.25')).not.toBeInTheDocument()
  })

  test('keeps the reference image button in the action row next to generate', () => {
    renderPanel()

    expect(screen.getByTestId('anchored-video-footer')).toHaveAttribute('data-layout', 'stacked')
    expect(screen.getByTestId('anchored-video-footer-actions')).toHaveAttribute('data-layout', 'action-row')
    expect(screen.getByText('参考图片 13/14')).toBeInTheDocument()
    expect(screen.getByText('Go')).toBeInTheDocument()
  })


  test('renders the ratio dropdown as a bounded scroll container', () => {
    renderPanel()

    fireEvent.click(screen.getByText((content) => content.includes('1:1')))

    const scrollArea = screen.getByTestId('anchored-video-ratio-dropdown')
    expect(scrollArea.style.maxHeight).toBe('280px')
    fireEvent.wheel(scrollArea, { deltaY: 120 })
    expect(screen.getByTestId('anchored-video-ratio-dropdown')).toBeInTheDocument()
  })

  test('limits the duration dropdown height to 200px', () => {
    renderPanel({
      draft: {
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'test-model',
        provider_code: 'provider',
        aspect_ratio: '1:1',
        duration: '1s',
        resolution: '720p',
        sourcePlacement: 'reference',
        reference_images: referenceImages,
        first_frame_image: '',
        tail_frame_image: '',
      },
      allowedDurations: Array.from({ length: 20 }, (_, index) => `${index + 1}s`),
      availableVideoModels: [
        {
          value: 'test-model',
          name: 'Test Model',
          provider: 'provider',
          providerName: 'Provider',
          config: {
            allowed_sizes: ['720p'],
            allowed_aspect_ratios: ['1:1', '16:9', '9:16'],
          },
        },
      ],
    })

    fireEvent.click(screen.getByText('1s'))

    const lastOption = screen.getByText('20s')
    const scrollArea = lastOption.parentElement as HTMLElement

    expect(scrollArea.style.maxHeight).toBe('200px')
    fireEvent.wheel(scrollArea, { deltaY: 120 })
    expect(screen.getByText('20s')).toBeInTheDocument()
  })

  test('switching to the Grok model resets the anchored video duration to the first supported option', async () => {
    const user = userEvent.setup()

    type DraftState = {
      sourceImageItemId: string
      sourceImageUrl: string
      prompt: string
      model_name: string
      provider_code: string
      aspect_ratio: string
      duration: string
      resolution: string
      sourcePlacement: AnchoredVideoSourcePlacement
      reference_images: string[]
      first_frame_image: string
      tail_frame_image: string
    }

    function Harness() {
      const [draft, setDraft] = useState<DraftState>({
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'test-model',
        provider_code: 'provider',
        aspect_ratio: '16:9',
        duration: '5s',
        resolution: '720p',
        sourcePlacement: 'reference',
        reference_images: [],
        first_frame_image: '',
        tail_frame_image: '',
      })

      return (
        <ImageAnchoredVideoPanel
          draft={draft}
          draftItem={draft}
          capability={{
            supportsReferenceImages: true,
            maxReferenceImages: 14,
            supportsFirstFrame: false,
            supportsTailFrame: false,
            disableAspectRatioWhenImages: false,
            imageModesConflict: false,
          }}
          allowedDurations={draft.model_name === 'grok-imagine-1.0-video-apimart' ? ['6s', '7s', '8s'] : ['5s', '10s']}
          availableVideoModels={[
            {
              value: 'test-model',
              name: 'Test Model',
              provider: 'provider',
              providerName: 'Provider',
              config: {
                allowed_sizes: ['720p'],
                allowed_aspect_ratios: ['16:9'],
              },
            },
            {
              value: 'grok-imagine-1.0-video-apimart',
              name: 'Grok-Imagine-video-1.0',
              provider: 'builtin',
              providerName: 'Builtin',
              config: {
                allowed_sizes: ['480p', '720p'],
                allowed_aspect_ratios: ['16:9'],
                min_duration: 6,
                max_duration: 30,
              },
            },
          ]}
          isDark={false}
          t={(key, fallback) => fallback || key}
          amountCents={220}
          referenceInputRef={createRef<HTMLInputElement>()}
          firstFrameInputRef={createRef<HTMLInputElement>()}
          tailFrameInputRef={createRef<HTMLInputElement>()}
          onUpdateDraft={(updates) => setDraft(prev => ({ ...prev, ...updates }))}
          onMoveSourcePlacement={() => {}}
          onPreviewImage={() => {}}
          onGenerate={() => {}}
          onPickReferenceFromLibrary={() => {}}
          onPickFirstFrameFromLibrary={() => {}}
          onPickTailFrameFromLibrary={() => {}}
        />
      )
    }

    render(<Harness />)

    expect(screen.getByText('5s')).toBeInTheDocument()

    await user.click(screen.getByText('Test Model'))
    await user.click(screen.getByText('Grok-Imagine-video-1.0'))

    expect(screen.getByText('6s')).toBeInTheDocument()
  })

  test('shows the locked source image even without uploaded references and lets it move to first frame', () => {
    const { onMoveSourcePlacement } = renderPanel({
      draft: {
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'test-model',
        provider_code: 'provider',
        aspect_ratio: '1:1',
        duration: '5',
        resolution: '720p',
        sourcePlacement: 'reference',
        reference_images: [],
        first_frame_image: '',
        tail_frame_image: '',
      },
      capability: {
        supportsReferenceImages: true,
        maxReferenceImages: 14,
        supportsFirstFrame: true,
        supportsTailFrame: true,
        disableAspectRatioWhenImages: false,
        imageModesConflict: false,
      },
    })

    const sourceImages = screen.getAllByAltText('Source')
    expect(sourceImages).toHaveLength(1)

    const dataTransfer = {
      effectAllowed: '',
      setData: vi.fn(),
    }

    fireEvent.dragStart(sourceImages[0], { dataTransfer })
    fireEvent.dragOver(screen.getByText('canvas.generator.first_frame'), { dataTransfer })
    fireEvent.drop(screen.getByText('canvas.generator.first_frame'), { dataTransfer })

    expect(onMoveSourcePlacement).toHaveBeenCalledWith('first_frame')
  })

  test('disables tail frame selection until a first frame is available for constrained models', () => {
    renderPanel({
      capability: {
        supportsReferenceImages: true,
        maxReferenceImages: 14,
        supportsFirstFrame: true,
        supportsTailFrame: true,
        requiresFirstFrameForTailFrame: true,
        disableAspectRatioWhenImages: false,
        imageModesConflict: false,
      },
      draft: {
        sourceImageItemId: 'source-1',
        sourceImageUrl: 'https://example.com/source.png',
        prompt: '',
        model_name: 'test-model',
        provider_code: 'provider',
        aspect_ratio: '1:1',
        duration: '5s',
        resolution: '720p',
        sourcePlacement: 'reference',
        reference_images: [],
        first_frame_image: '',
        tail_frame_image: '',
      },
      draftItem: {
        reference_images: ['https://example.com/source.png'],
        first_frame_image: '',
        tail_frame_image: '',
        resolution: '720p',
      },
    })

    expect(screen.getByLabelText('canvas.generator.tail_frame')).toBeDisabled()
  })
})
