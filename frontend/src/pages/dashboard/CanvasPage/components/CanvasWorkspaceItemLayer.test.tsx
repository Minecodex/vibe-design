import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { canvasViewportFixture } from '@/store/testing/canvasViewportFixture'
import { createTranslationFixture } from '@/store/testing/translationFixture'
import { canvasRenderFixture } from '@/store/testing/canvasRenderFixture'
import type { CanvasItem } from '@/api/endpoints/projects'

import type { CanvasWorkspaceItemLayerProps } from './canvasRenderContracts'
import { normalizeReferenceImages } from '../generatorCapabilities'
import { CanvasWorkspaceItemLayer } from './CanvasWorkspaceItemLayer'

describe('CanvasWorkspaceItemLayer', () => {
  function renderItemLayer(
    item: CanvasItem,
    selectedItems: string[] = [],
    overrides: Partial<React.ComponentProps<typeof CanvasWorkspaceItemLayer>> = {},
  ) {
    return render(
      <TestItemLayer
        canvasItems={[item]}
        clampCanvasStackZIndex={(value?: number) => value ?? 0}
        isHoverOnlyFailedVideoTask={() => false}
        getItemDims={(currentItem: CanvasItem) => ({ width: currentItem.width || 1, height: currentItem.height || 1 })}
        activeDropdown={null}
        hoveredMarkableImageId={null}
        isTransientMarkModeActive={() => false}
        activeTool="select"
        markModifierState={{ altKey: false, metaKey: false, ctrlKey: false }}
        cropState={null}
        selectedItems={selectedItems}
        getMediaSelectionOverlayMetrics={() => ({ handleSize: 12, handleOffset: 6, borderWidth: 5 })}
        zoom={100}
        offset={{ x: 0, y: 0 }}
        canvasRef={canvasViewportFixture()}
        selectedSingleItemRect={null}
        getResolvedImageCapability={() => null}
        getResolvedVideoCapability={() => null}
        getResolvedVideoDurations={() => []}
        availableImageModels={[]}
        availableVideoModels={[]}
        imageModel=""
        imageProvider=""
        videoModel=""
        videoProvider=""
        getItemReferenceImages={() => []}
        shouldDisableVideoAspectRatio={() => false}
        getVideoGeneratorCapability={() => ({ supportsReferenceImages: false, maxReferenceImages: 0, supportsFirstFrame: false, supportsTailFrame: false, disableAspectRatioWhenImages: false, imageModesConflict: false })}
        getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
        textEditingItemId={null}
        handleStartTextEdit={vi.fn()}
        handleCommitTextEdit={vi.fn()}
        handleCancelTextEdit={vi.fn()}
        handleItemMouseDown={vi.fn()}
        setSelectedItems={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        beginTransaction={vi.fn()}
        setActiveGuides={vi.fn()}
        movingItemIdsRef={{ current: new Set() }}
        setMediaResizeState={vi.fn()}
        resizingHandle={{ current: null }}
        dragItemStart={{ current: null }}
        resizingStart={{ current: null }}
        getCanvasSelectionHandleAppearance={vi.fn(() => ({
          border: '2px solid rgb(59, 130, 246)',
          backgroundColor: '#fff',
        }))}
        isDark={false}
        setBrushResizeState={vi.fn()}
        setHoveredMarkableImageId={vi.fn()}
        getCanvasSelectionContainerOverflow={() => 'hidden'}
        MARK_CURSOR="crosshair"
        imageAnchoredVideoDraft={null}
        imageDetailItemId={null}
        isMarkModifierPressed={() => false}
        addMark={vi.fn()}
        handleAppendImageMentionToChat={vi.fn()}
        updateItem={vi.fn()}
        getMediaDisplayInitializationUpdate={() => null}
        getTextRedrawExtractingBadgeStyle={vi.fn(() => ({}))}
        t={createTranslationFixture()}
        cropDragState={null}
        handleCropMoveMouseDown={vi.fn()}
        handleCropHandleMouseDown={vi.fn()}
        renderSelectionHandles={vi.fn()}
        shouldShowGeneratorControlPanel={() => false}
        setActiveDropdown={vi.fn()}
        referenceImageInputRef={{ current: null }}
        openGeneratorAssetLibrary={vi.fn()}
        openGeneratorReferenceGallery={vi.fn()}
        firstFrameImageInputRef={{ current: null }}
        tailFrameImageInputRef={{ current: null }}
        handleGenerateImage={vi.fn()}
        handleGenerateVideo={vi.fn()}
        getItemAmountCents={() => null}
        formatResolutionOptionLabel={(value: string) => value}
        standardSuffix="standard"
        imageRes="1K"
        videoQuality="720p"
        videoDuration="5"
        normalizeReferenceImages={normalizeReferenceImages}
        withReferenceImages={(reference_images) => ({ reference_images })}
        getImageGeneratorCapability={() => ({ supportsReferenceImages: false, maxReferenceImages: 0 })}
        imageRatio="1:1"
        videoAspect="16:9"
        ratioHintLabels={{ square: 'square', landscape: 'landscape', portrait: 'portrait' }}
        formatAspectRatioOptionLabelWithDimensions={(value: string) => value}
        cropCommitMode="freeform"
        handleCropDimensionChange={vi.fn()}
        CROP_PRESET_GROUPS={[]}
        setCropExpandedGroups={vi.fn()}
        cropExpandedGroups={{}}
        handleSelectCropPreset={vi.fn()}
        setCropState={vi.fn()}
        handleApplyCrop={vi.fn()}
        imageAnchoredImageDraft={null}
        imageAnchoredImageDraftItem={null}
        anchoredImageReferenceInputRef={{ current: null }}
        updateImageAnchoredImageDraft={vi.fn()}
        setPreviewImageUrl={vi.fn()}
        handleGenerateAnchoredImage={vi.fn()}
        imageAnchoredVideoDraftItem={null}
        imageAnchoredVideoCapability={null}
        imageAnchoredVideoAllowedDurations={[]}
        anchoredReferenceImageInputRef={{ current: null }}
        anchoredFirstFrameImageInputRef={{ current: null }}
        anchoredTailFrameImageInputRef={{ current: null }}
        updateImageAnchoredVideoDraft={vi.fn()}
        handleMoveAnchoredVideoSourcePlacement={vi.fn()}
        handleGenerateAnchoredVideo={vi.fn()}
        marks={[]}
        textRedrawExtractingItemIds={new Set<string>()}
        isSceneReady={false}
        {...overrides}
      />,
    )
  }

  it('matches the image selection border and corner handle styling for selected brush items', () => {
    const item: CanvasItem = {
      id: 'brush-1',
      type: 'brush_path',
      url: '',
      x: 20,
      y: 30,
      width: 120,
      height: 80,
      z_index: 5,
      brushColor: '#111111',
      brushSize: 8,
      points: [{ x: 0.1, y: 0.2 }, { x: 0.7, y: 0.8 }],
    }

    const { container } = render(
      <TestItemLayer
        canvasItems={[item]}
        clampCanvasStackZIndex={(value?: number) => value ?? 0}
        isHoverOnlyFailedVideoTask={() => false}
        getItemDims={(currentItem: CanvasItem) => ({ width: currentItem.width || 1, height: currentItem.height || 1 })}
        activeDropdown={null}
        hoveredMarkableImageId={null}
        isTransientMarkModeActive={() => false}
        activeTool="select"
        markModifierState={{ altKey: false, metaKey: false, ctrlKey: false }}
        cropState={null}
        selectedItems={['brush-1']}
        getMediaSelectionOverlayMetrics={() => ({ handleSize: 12, handleOffset: 6, borderWidth: 2 })}
        zoom={100}
        offset={{ x: 0, y: 0 }}
        canvasRef={canvasViewportFixture()}
        selectedSingleItemRect={null}
        getResolvedImageCapability={() => null}
        getResolvedVideoCapability={() => null}
        getResolvedVideoDurations={() => []}
        availableImageModels={[]}
        availableVideoModels={[]}
        imageModel=""
        videoModel=""
        getItemReferenceImages={() => []}
        shouldDisableVideoAspectRatio={() => false}
        getVideoGeneratorCapability={() => ({ supportsReferenceImages: false, maxReferenceImages: 0, supportsFirstFrame: false, supportsTailFrame: false, disableAspectRatioWhenImages: false, imageModesConflict: false })}
        getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
        textEditingItemId={null}
        handleStartTextEdit={vi.fn()}
        handleCommitTextEdit={vi.fn()}
        handleCancelTextEdit={vi.fn()}
        handleItemMouseDown={vi.fn()}
        setSelectedItems={vi.fn()}
        setContextMenu={vi.fn()}
        setActiveContextMenuItem={vi.fn()}
        beginTransaction={vi.fn()}
        setActiveGuides={vi.fn()}
        movingItemIdsRef={{ current: new Set() }}
        setMediaResizeState={vi.fn()}
        resizingHandle={{ current: null }}
        dragItemStart={{ current: null }}
        resizingStart={{ current: null }}
        getCanvasSelectionHandleAppearance={({ borderWidth }: { borderWidth: number }) => ({
          border: `${borderWidth}px solid rgb(59, 130, 246)`,
          backgroundColor: '#fff',
        })}
        isDark={false}
        setBrushResizeState={vi.fn()}
        setHoveredMarkableImageId={vi.fn()}
        marks={[]}
        textRedrawExtractingItemIds={new Set<string>()}
        isSceneReady={false}
      />,
    )

    const selectedFrame = container.querySelector('#item-brush-1 > div > div') as HTMLElement
    expect(selectedFrame.style.outline).toBe('2px solid rgb(59, 130, 246)')

    const handles = Array.from(container.querySelectorAll('div')).filter((node) => {
      const element = node as HTMLElement
      return element.style.cursor.includes('resize')
    }) as HTMLElement[]

    expect(handles).toHaveLength(4)
    expect(handles[0].style.width).toBe('12px')
    expect(handles[0].style.height).toBe('12px')
    expect(handles[0].style.border).toBe('2px solid rgb(59, 130, 246)')
  })

  it('uses the shared image selection border for selected generator cards', () => {
    const item: CanvasItem = {
      id: 'generator-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'generating',
      progress: 42,
    }

    const { container } = renderItemLayer(item, ['generator-1'])

    const selectedFrame = container.querySelector('#item-generator-1 > div > div') as HTMLElement
    expect(selectedFrame.style.outline).toBe('5px solid rgb(59, 130, 246)')
  })

  it('uses a darker light-theme border for unselected generator cards so they stay distinct from the canvas', () => {
    const item: CanvasItem = {
      id: 'generator-border-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'generating',
    }

    const { container } = renderItemLayer(item)

    const generatorCard = container.querySelector('#item-generator-border-1 > div > div') as HTMLElement
    expect(generatorCard.style.border).toBe('1px solid var(--app-border)')
  })

  it('does not show a price badge in the selected generator action button', () => {
    const item: CanvasItem = {
      id: 'generator-price-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'generating',
      prompt: 'test prompt',
      model_name: 'test-model',
      provider_code: 'builtin',
      resolution: '1K',
      aspect_ratio: '1:1',
    }

    renderItemLayer(item, ['generator-price-1'], {
      selectedSingleItemRect: { left: 20, top: 30, width: 240, height: 160 },
      shouldShowGeneratorControlPanel: () => true,
      getItemAmountCents: () => 123,
    })

    expect(screen.getByText('Go')).toBeInTheDocument()
    expect(screen.queryByText('¥1.23')).not.toBeInTheDocument()
  })

  it('renders the aliased model name in the selected image generator panel', () => {
    const item: CanvasItem = {
      id: 'generator-alias-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'generating',
      prompt: 'test prompt',
      model_name: 'doubao-seedream-5-0-260128',
      provider_code: 'builtin',
      resolution: '2K',
      aspect_ratio: '1:1',
    }

    renderItemLayer(item, ['generator-alias-1'], {
      selectedSingleItemRect: { left: 20, top: 30, width: 240, height: 160 },
      shouldShowGeneratorControlPanel: () => true,
    })

    expect(screen.getByText('Seedream 5.0')).toBeInTheDocument()
    expect(screen.queryByText('doubao-seedream-5-0-260128')).not.toBeInTheDocument()
  })

  it('updates image generator ratio options with model-resolved dimensions', async () => {
    const user = userEvent.setup()
    const updateItem = vi.fn()
    const item: CanvasItem = {
      id: 'generator-dimension-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 2880,
      height: 2880,
      z_index: 5,
      status: 'generating',
      model_name: 'gpt-image-2',
      provider_code: 'builtin',
      resolution: '4K',
      aspect_ratio: '1:1',
    }

    renderItemLayer(item, ['generator-dimension-1'], {
      activeDropdown: { itemId: 'generator-dimension-1', type: 'ratio' },
      selectedSingleItemRect: { left: 20, top: 30, width: 240, height: 160 },
      shouldShowGeneratorControlPanel: () => true,
      imageModel: 'gpt-image-2',
      imageProvider: 'builtin',
      imageRes: '4K',
      availableImageModels: [
        {
          name: 'GPT-Image 2',
          value: 'gpt-image-2',
          provider: 'builtin',
          providerName: 'Builtin',
          isBuiltin: true,
          config: {
            allowed_sizes: ['4K'],
            allowed_aspect_ratios: ['1:1', '16:9'],
          },
        },
      ],
      getItemDims: (currentItem: CanvasItem) => (
        currentItem.aspect_ratio === '16:9'
          ? { width: 3840, height: 2160 }
          : { width: 2880, height: 2880 }
      ),
      formatAspectRatioOptionLabelWithDimensions: (value: string, _labels: any, dims: { width: number; height: number }) =>
        `${value} ${dims.width} × ${dims.height}`,
      updateItem,
    })

    await user.click(screen.getByText('16:9 3840 × 2160'))

    expect(updateItem).toHaveBeenCalledWith('generator-dimension-1', {
      aspect_ratio: '16:9',
      width: 3840,
      height: 2160,
    })
  })

  it('marks only the selected provider when image models share the same model name', () => {
    const item: CanvasItem = {
      id: 'generator-provider-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'completed',
      model_name: 'gpt-image-2',
      provider_code: 'ollama',
    }

    renderItemLayer(item, ['generator-provider-1'], {
      activeDropdown: { itemId: 'generator-provider-1', type: 'model' },
      shouldShowGeneratorControlPanel: () => true,
      imageModel: 'gpt-image-2',
      imageProvider: 'ollama',
      availableImageModels: [
        {
          name: 'GPT-Image 2',
          value: 'gpt-image-2',
          provider: 'builtin',
          providerName: 'Builtin',
          isBuiltin: true,
        },
        {
          name: 'Ollama Image (gpt-image-2)',
          value: 'gpt-image-2',
          provider: 'ollama',
          providerName: 'Ollama',
          isBuiltin: true,
        },
      ],
    })

    const builtinOption = screen.getByText('Builtin').parentElement as HTMLElement
    const ollamaOption = screen.getByText('Ollama').parentElement as HTMLElement

    expect(builtinOption.style.backgroundColor).toBe('transparent')
    expect(ollamaOption.style.backgroundColor).toBe('var(--app-control-selected)')
  })

  it('resets the selected video generator duration to the Grok-supported minimum when switching models', async () => {
    const user = userEvent.setup()
    const itemId = 'video-generator-grok-duration'

    function Harness() {
      const [items, setItems] = useState<CanvasItem[]>([
        {
          id: itemId,
          type: 'video_generator',
          url: '',
          x: 20,
          y: 30,
          width: 960,
          height: 540,
          z_index: 5,
          model_name: 'seedance-1.0',
          provider_code: 'builtin',
          resolution: '720p',
          aspect_ratio: '16:9',
          duration: '5s',
          prompt: 'test prompt',
        },
      ])
      const [activeDropdown, setActiveDropdown] = useState<any>(null)

      return (
        <TestItemLayer
          canvasItems={items}
          clampCanvasStackZIndex={(value?: number) => value ?? 0}
          isHoverOnlyFailedVideoTask={() => false}
          getItemDims={(currentItem: CanvasItem) => ({ width: currentItem.width || 1, height: currentItem.height || 1 })}
          activeDropdown={activeDropdown}
          hoveredMarkableImageId={null}
          isTransientMarkModeActive={() => false}
          activeTool="select"
          markModifierState={{ altKey: false, metaKey: false, ctrlKey: false }}
          cropState={null}
          selectedItems={[itemId]}
          getMediaSelectionOverlayMetrics={() => ({ handleSize: 12, handleOffset: 6, borderWidth: 5 })}
          zoom={100}
          offset={{ x: 0, y: 0 }}
          canvasRef={canvasViewportFixture()}
          selectedSingleItemRect={{ left: 20, top: 30, width: 960, height: 540 }}
          getResolvedImageCapability={() => null}
          getResolvedVideoCapability={() => ({ disableAspectRatioWhenImages: false, 
            supportsReferenceImages: false,
            maxReferenceImages: 0,
            supportsFirstFrame: false,
            supportsTailFrame: false,
            imageModesConflict: false,
          })}
          getResolvedVideoDurations={(item: CanvasItem, overrides?: Partial<CanvasItem>, modelNameOverride?: string) => {
            const resolvedModel = modelNameOverride || overrides?.model_name || item.model_name
            return resolvedModel === 'grok-imagine-1.0-video-apimart'
              ? ['6s', '7s', '8s']
              : ['5s', '10s']
          }}
          availableImageModels={[]}
          availableVideoModels={[
            {
              name: 'Seedance',
              value: 'seedance-1.0',
              provider: 'builtin',
              providerName: 'Builtin',
              isBuiltin: true,
              config: {
                allowed_sizes: ['720p'],
                allowed_aspect_ratios: ['16:9'],
              },
            },
            {
              name: 'Grok-Imagine-video-1.0',
              value: 'grok-imagine-1.0-video-apimart',
              provider: 'builtin',
              providerName: 'Builtin',
              isBuiltin: true,
              config: {
                allowed_sizes: ['480p', '720p'],
                allowed_aspect_ratios: ['16:9'],
              },
            },
          ]}
          imageModel=""
          videoModel="seedance-1.0"
          getItemReferenceImages={() => []}
          shouldDisableVideoAspectRatio={() => false}
          getVideoGeneratorCapability={() => ({ disableAspectRatioWhenImages: false, 
            supportsReferenceImages: false,
            maxReferenceImages: 0,
            supportsFirstFrame: false,
            supportsTailFrame: false,
            imageModesConflict: false,
          })}
          getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
          textEditingItemId={null}
          handleStartTextEdit={vi.fn()}
          handleCommitTextEdit={vi.fn()}
          handleCancelTextEdit={vi.fn()}
          handleItemMouseDown={vi.fn()}
          setSelectedItems={vi.fn()}
          setContextMenu={vi.fn()}
          setActiveContextMenuItem={vi.fn()}
          beginTransaction={vi.fn()}
          setActiveGuides={vi.fn()}
          movingItemIdsRef={{ current: new Set() }}
          setMediaResizeState={vi.fn()}
          resizingHandle={{ current: null }}
          dragItemStart={{ current: null }}
          resizingStart={{ current: null }}
          getCanvasSelectionHandleAppearance={vi.fn(() => ({
            border: '2px solid rgb(59, 130, 246)',
            backgroundColor: '#fff',
          }))}
          isDark={false}
          setBrushResizeState={vi.fn()}
          setHoveredMarkableImageId={vi.fn()}
          getCanvasSelectionContainerOverflow={() => 'hidden'}
          MARK_CURSOR="crosshair"
          imageAnchoredVideoDraft={null}
          imageDetailItemId={null}
          isMarkModifierPressed={() => false}
          addMark={vi.fn()}
          handleAppendImageMentionToChat={vi.fn()}
          updateItem={(targetItemId: string, updates: any) => {
            setItems(prev => prev.map(item => item.id === targetItemId ? { ...item, ...updates } : item))
          }}
          getMediaDisplayInitializationUpdate={() => null}
          getTextRedrawExtractingBadgeStyle={vi.fn(() => ({}))}
          t={createTranslationFixture()}
          cropDragState={null}
          handleCropMoveMouseDown={vi.fn()}
          handleCropHandleMouseDown={vi.fn()}
          renderSelectionHandles={vi.fn()}
          shouldShowGeneratorControlPanel={() => true}
          setActiveDropdown={setActiveDropdown}
          referenceImageInputRef={{ current: null }}
          openGeneratorAssetLibrary={vi.fn()}
        openGeneratorReferenceGallery={vi.fn()}
          firstFrameImageInputRef={{ current: null }}
          tailFrameImageInputRef={{ current: null }}
          handleGenerateImage={vi.fn()}
          handleGenerateVideo={vi.fn()}
          getItemAmountCents={() => null}
          formatResolutionOptionLabel={(value: string) => value}
          standardSuffix="standard"
          imageRes="1K"
          videoQuality="720p"
          videoDuration="5s"
          normalizeReferenceImages={() => []}
          withReferenceImages={() => ({ reference_images: [] })}
          getImageGeneratorCapability={() => ({ maxReferenceImages: 0, supportsReferenceImages: false })}
          imageRatio="1:1"
          videoAspect="16:9"
          ratioHintLabels={{ square: 'square', landscape: 'landscape', portrait: 'portrait' }}
          formatAspectRatioOptionLabelWithDimensions={(value: string) => value}
          cropCommitMode="freeform"
          handleCropDimensionChange={vi.fn()}
          CROP_PRESET_GROUPS={[]}
          setCropExpandedGroups={vi.fn()}
          cropExpandedGroups={{}}
          handleSelectCropPreset={vi.fn()}
          setCropState={vi.fn()}
          handleApplyCrop={vi.fn()}
          imageAnchoredImageDraft={null}
          imageAnchoredImageDraftItem={null}
          anchoredImageReferenceInputRef={{ current: null }}
          updateImageAnchoredImageDraft={vi.fn()}
          setPreviewImageUrl={vi.fn()}
          handleGenerateAnchoredImage={vi.fn()}
          imageAnchoredVideoDraftItem={null}
          imageAnchoredVideoCapability={null}
          imageAnchoredVideoAllowedDurations={[]}
          anchoredReferenceImageInputRef={{ current: null }}
          anchoredFirstFrameImageInputRef={{ current: null }}
          anchoredTailFrameImageInputRef={{ current: null }}
          updateImageAnchoredVideoDraft={vi.fn()}
          handleMoveAnchoredVideoSourcePlacement={vi.fn()}
          handleGenerateAnchoredVideo={vi.fn()}
          marks={[]}
          textRedrawExtractingItemIds={new Set<string>()}
          isSceneReady={false}
        />
      )
    }

    render(<Harness />)

    expect(screen.getByText('5s')).toBeInTheDocument()

    await user.click(screen.getByText('Seedance'))
    await user.click(screen.getByText('Grok-Imagine-video-1.0'))

    expect(screen.getByText('6s')).toBeInTheDocument()
  })

  it('switches seedance button sets from reference mode to first-tail-frame mode when changing models', async () => {
    const user = userEvent.setup()
    const itemId = 'video-generator-seedance-toggle'

    function Harness() {
      const [items, setItems] = useState<CanvasItem[]>([
        {
          id: itemId,
          type: 'video_generator',
          url: '',
          x: 20,
          y: 30,
          width: 960,
          height: 540,
          z_index: 5,
          model_name: 'doubao-seedance-2.0',
          provider_code: 'builtin',
          resolution: '720p',
          aspect_ratio: '16:9',
          duration: '5s',
          prompt: 'test prompt',
          reference_images: ['https://example.com/reference-1.png'],
        },
      ])
      const [activeDropdown, setActiveDropdown] = useState<any>(null)

      return (
        <TestItemLayer
          canvasItems={items}
          clampCanvasStackZIndex={(value?: number) => value ?? 0}
          isHoverOnlyFailedVideoTask={() => false}
          getItemDims={(currentItem: CanvasItem) => ({ width: currentItem.width || 1, height: currentItem.height || 1 })}
          activeDropdown={activeDropdown}
          hoveredMarkableImageId={null}
          isTransientMarkModeActive={() => false}
          activeTool="select"
          markModifierState={{ altKey: false, metaKey: false, ctrlKey: false }}
          cropState={null}
          selectedItems={[itemId]}
          getMediaSelectionOverlayMetrics={() => ({ handleSize: 12, handleOffset: 6, borderWidth: 5 })}
          zoom={100}
          offset={{ x: 0, y: 0 }}
          canvasRef={canvasViewportFixture()}
          selectedSingleItemRect={{ left: 20, top: 30, width: 960, height: 540 }}
          getResolvedImageCapability={() => null}
          getResolvedVideoCapability={(item: CanvasItem) => (
            item.model_name === 'doubao-seedance-1-5-pro'
              ? { disableAspectRatioWhenImages: false, 
                  supportsReferenceImages: false,
                  maxReferenceImages: 0,
                  supportsFirstFrame: true,
                  supportsTailFrame: true,
                  imageModesConflict: false,
                }
              : { disableAspectRatioWhenImages: false, 
                  supportsReferenceImages: true,
                  maxReferenceImages: 9,
                  supportsFirstFrame: true,
                  supportsTailFrame: true,
                  imageModesConflict: true,
                }
          )}
          getResolvedVideoDurations={() => ['5s', '6s']}
          availableImageModels={[]}
          availableVideoModels={[
            {
              name: 'Seedance 2.0',
              value: 'doubao-seedance-2.0',
              provider: 'builtin',
              providerName: 'Builtin',
              isBuiltin: true,
              config: {
                allowed_sizes: ['720p'],
                allowed_aspect_ratios: ['16:9'],
                supports_first_frame: true,
                supports_tail_frame: true,
                image_modes_conflict: true,
                max_image_inputs: 9,
              },
            },
            {
              name: 'Seedance 1.5 Pro',
              value: 'doubao-seedance-1-5-pro',
              provider: 'builtin',
              providerName: 'Builtin',
              isBuiltin: true,
              config: {
                allowed_sizes: ['720p'],
                allowed_aspect_ratios: ['16:9'],
                supports_first_frame: true,
                supports_tail_frame: true,
                max_image_inputs: 0,
              },
            },
          ]}
          imageModel=""
          videoModel="doubao-seedance-2.0"
          getItemReferenceImages={(item: CanvasItem) => item.reference_images || []}
          shouldDisableVideoAspectRatio={() => false}
          getVideoGeneratorCapability={() => ({ disableAspectRatioWhenImages: false, 
            supportsReferenceImages: true,
            maxReferenceImages: 9,
            supportsFirstFrame: true,
            supportsTailFrame: true,
            imageModesConflict: true,
          })}
          getCanvasSelectionBorder={(width: number) => `${width}px solid rgb(59, 130, 246)`}
          textEditingItemId={null}
          handleStartTextEdit={vi.fn()}
          handleCommitTextEdit={vi.fn()}
          handleCancelTextEdit={vi.fn()}
          handleItemMouseDown={vi.fn()}
          setSelectedItems={vi.fn()}
          setContextMenu={vi.fn()}
          setActiveContextMenuItem={vi.fn()}
          beginTransaction={vi.fn()}
          setActiveGuides={vi.fn()}
          movingItemIdsRef={{ current: new Set() }}
          setMediaResizeState={vi.fn()}
          resizingHandle={{ current: null }}
          dragItemStart={{ current: null }}
          resizingStart={{ current: null }}
          getCanvasSelectionHandleAppearance={vi.fn(() => ({
            border: '2px solid rgb(59, 130, 246)',
            backgroundColor: '#fff',
          }))}
          isDark={false}
          setBrushResizeState={vi.fn()}
          setHoveredMarkableImageId={vi.fn()}
          getCanvasSelectionContainerOverflow={() => 'hidden'}
          MARK_CURSOR="crosshair"
          imageAnchoredVideoDraft={null}
          imageDetailItemId={null}
          isMarkModifierPressed={() => false}
          addMark={vi.fn()}
          handleAppendImageMentionToChat={vi.fn()}
          updateItem={(targetItemId: string, updates: any) => {
            setItems(prev => prev.map(item => item.id === targetItemId ? { ...item, ...updates } : item))
          }}
          getMediaDisplayInitializationUpdate={() => null}
          getTextRedrawExtractingBadgeStyle={vi.fn(() => ({}))}
          t={createTranslationFixture()}
          cropDragState={null}
          handleCropMoveMouseDown={vi.fn()}
          handleCropHandleMouseDown={vi.fn()}
          renderSelectionHandles={vi.fn()}
          shouldShowGeneratorControlPanel={() => true}
          setActiveDropdown={setActiveDropdown}
          referenceImageInputRef={{ current: null }}
          openGeneratorAssetLibrary={vi.fn()}
        openGeneratorReferenceGallery={vi.fn()}
          firstFrameImageInputRef={{ current: null }}
          tailFrameImageInputRef={{ current: null }}
          handleGenerateImage={vi.fn()}
          handleGenerateVideo={vi.fn()}
          getItemAmountCents={() => null}
          formatResolutionOptionLabel={(value: string) => value}
          standardSuffix="standard"
          imageRes="1K"
          videoQuality="720p"
          videoDuration="5s"
          normalizeReferenceImages={() => []}
          withReferenceImages={() => ({ reference_images: [], reference_image: '' })}
          getImageGeneratorCapability={() => ({ maxReferenceImages: 0, supportsReferenceImages: false })}
          imageRatio="1:1"
          videoAspect="16:9"
          ratioHintLabels={{ square: 'square', landscape: 'landscape', portrait: 'portrait' }}
          formatAspectRatioOptionLabelWithDimensions={(value: string) => value}
          cropCommitMode="freeform"
          handleCropDimensionChange={vi.fn()}
          CROP_PRESET_GROUPS={[]}
          setCropExpandedGroups={vi.fn()}
          cropExpandedGroups={{}}
          handleSelectCropPreset={vi.fn()}
          setCropState={vi.fn()}
          handleApplyCrop={vi.fn()}
          imageAnchoredImageDraft={null}
          imageAnchoredImageDraftItem={null}
          anchoredImageReferenceInputRef={{ current: null }}
          updateImageAnchoredImageDraft={vi.fn()}
          setPreviewImageUrl={vi.fn()}
          handleGenerateAnchoredImage={vi.fn()}
          imageAnchoredVideoDraftItem={null}
          imageAnchoredVideoCapability={null}
          imageAnchoredVideoAllowedDurations={[]}
          anchoredReferenceImageInputRef={{ current: null }}
          anchoredFirstFrameImageInputRef={{ current: null }}
          anchoredTailFrameImageInputRef={{ current: null }}
          updateImageAnchoredVideoDraft={vi.fn()}
          handleMoveAnchoredVideoSourcePlacement={vi.fn()}
          handleGenerateAnchoredVideo={vi.fn()}
          marks={[]}
          textRedrawExtractingItemIds={new Set<string>()}
          isSceneReady={false}
        />
      )
    }

    render(<Harness />)

    expect(screen.getByText('Reference image 1/9')).toBeInTheDocument()
    expect(screen.getByText('canvas.generator.first_frame')).toBeInTheDocument()
    expect(screen.getByText('canvas.generator.tail_frame')).toBeInTheDocument()

    await user.click(screen.getByText('Seedance 2.0'))
    await user.click(screen.getByText('Seedance 1.5 Pro'))

    expect(screen.queryByText('Reference image')).not.toBeInTheDocument()
    expect(screen.getByText('canvas.generator.first_frame')).toBeInTheDocument()
    expect(screen.getByText('canvas.generator.tail_frame')).toBeInTheDocument()
  })

  it('renders an internal error label for failed generator cards that never created a generation task', () => {
    const item: CanvasItem = {
      id: 'generator-internal-failed-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'failed',
      failure_kind: 'internal_failed',
      error_message: '内部服务异常',
    }

    renderItemLayer(item)

    expect(screen.getByText('内部错误')).toBeInTheDocument()
  })

  it('adds the error message to failed generator cards so hovering the element can reveal it', () => {
    const item: CanvasItem = {
      id: 'generator-failed-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'failed',
      error_message: '模型服务暂时不可用',
    }

    const { container } = renderItemLayer(item)
    const failedCard = container.querySelector('#item-generator-failed-1 > div > div') as HTMLElement

    expect(failedCard.title).toBe('模型服务暂时不可用')
  })

  it('renders the loading state for binding task generator cards before a task id exists', () => {
    const item: CanvasItem = {
      id: 'generator-binding-1',
      type: 'image_generator',
      url: '',
      x: 20,
      y: 30,
      width: 240,
      height: 160,
      z_index: 5,
      status: 'binding_task',
      progress: 0,
      client_request_id: 'binding-request-1',
    }

    renderItemLayer(item)

    expect(screen.getByText('canvas.generator.generating_progress')).toBeInTheDocument()
  })
})

function TestItemLayer(props: Partial<CanvasWorkspaceItemLayerProps> & Pick<CanvasWorkspaceItemLayerProps, 'canvasItems'>) {
const item = props.canvasItems[0] ?? {id:'fixture',type:'image',url:'',x:0,y:0}
return <CanvasWorkspaceItemLayer {...canvasRenderFixture(item)} {...props} />
}
