import React from 'react'

import type { CanvasItem } from '@/api/endpoints/projects'

import { createCanvasWheelCameraScheduler } from '../canvasWheelCamera'
import { useCanvasCamera } from '../hooks/useCanvasCamera'
import { CanvasWorkspaceCanvasArea } from './CanvasWorkspaceCanvasArea'

function getCount() {
  if (typeof window === 'undefined') return 300
  const value = Number(new URLSearchParams(window.location.search).get('count') || '300')
  return Number.isFinite(value) ? Math.max(1, Math.min(1500, Math.round(value))) : 300
}

function createHarnessItems(count: number): CanvasItem[] {
  return Array.from({ length: count }, (_, index) => ({
    id: `perf-image-${index}`,
    type: 'image',
    url: `data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="${index % 2 ? '#dbeafe' : '#dcfce7'}"/><text x="12" y="64" font-family="Arial" font-size="22" fill="#111827">${index}</text></svg>`)}`,
    x: (index % 50) * 190 - 120,
    y: Math.floor(index / 50) * 150 - 80,
    width: 160,
    height: 120,
    z_index: index,
  }))
}

const noop = () => {}

export function CanvasPerfHarnessPage() {
  const canvasRef = React.useRef<HTMLDivElement | null>(null)
  const canvasContentRef = React.useRef<HTMLDivElement | null>(null)
  const [zoom, setZoom] = React.useState(100)
  const [offset, setOffset] = React.useState({ x: 0, y: 0 })
  const zoomRef = React.useRef(zoom)
  const offsetRef = React.useRef(offset)
  const [isWheeling, setIsWheeling] = React.useState(false)
  const count = React.useMemo(getCount, [])
  const canvasItems = React.useMemo(() => createHarnessItems(count), [count])
  const camera = useCanvasCamera({
    canvasContentRef,
    zoom,
    setZoom,
    zoomRef,
    offset,
    setOffset,
    offsetRef,
  })

  React.useEffect(() => {
    const scheduler = createCanvasWheelCameraScheduler({
      camera,
      zoomRef,
      offsetRef,
      getViewportElement: () => canvasRef.current,
      setIsWheeling,
    })
    const element = canvasRef.current
    if (!element) return undefined
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault()
      scheduler.handleWheel(event)
    }
    element.addEventListener('wheel', handleWheel, { passive: false })
    return () => {
      scheduler.cancel()
      element.removeEventListener('wheel', handleWheel)
    }
  }, [camera])

  return (
    <div data-testid="canvas-perf-harness" style={{ display: 'flex', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <CanvasWorkspaceCanvasArea
        projectId={null}
        canvasRef={canvasRef}
        canvasContentRef={canvasContentRef}
        canvasCamera={camera}
        canvasItems={canvasItems}
        selectedItems={[]}
        marks={[]}
        cropState={null}
        textRedrawExtractingItemIds={new Set<string>()}
        imageDetailItemId={null}
        imageAnchoredImageDraft={null}
        imageAnchoredVideoDraft={null}
        zoom={zoom}
        offset={offset}
        isDark={false}
        isPanning={false}
        isWheeling={isWheeling}
        brushDraft={null}
        projectedGuides={[]}
        selectionBox={null}
        activeTool="select"
        MARK_CURSOR="crosshair"
        getItemDims={(item: CanvasItem) => ({ width: item.width || 160, height: item.height || 120 })}
        handleMouseDown={() => {}}
        handleMouseMove={() => {}}
        handleMouseUp={() => {}}
        handleCanvasClick={() => {}}
        handleItemMouseDown={() => {}}
        setContextMenu={() => {}}
        setSelectedItems={() => {}}
        setActiveContextMenuItem={() => {}}
        setActiveDropdown={() => {}}
        activeDropdown={null}
        hoveredMarkableImageId={null}
        setHoveredMarkableImageId={() => {}}
        markModifierState={{}}
        isTransientMarkModeActive={() => false}
        isMarkModifierPressed={() => false}
        addMark={() => {}}
        handleAppendImageMentionToChat={() => {}}
        clampCanvasStackZIndex={(value: number) => value}
        isHoverOnlyFailedVideoTask={() => false}
        getMediaSelectionOverlayMetrics={() => ({ handleSize: 12, handleOffset: 6, borderWidth: 2 })}
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
        getVideoGeneratorCapability={() => null}
        getImageGeneratorCapability={() => ({ maxReferenceImages: 0, supportsReferenceImages: false })}
        getCanvasSelectionBorder={(width: number) => `${width}px solid var(--app-primary)`}
        getCanvasSelectionHandleAppearance={() => ({ border: '2px solid var(--app-primary)', backgroundColor: 'var(--app-control-thumb)' })}
        getCanvasSelectionContainerOverflow={() => 'hidden'}
        getMediaDisplayInitializationUpdate={() => null}
        getTextRedrawExtractingBadgeStyle={() => ({})}
        handleStartTextEdit={noop}
        handleCommitTextEdit={noop}
        handleCancelTextEdit={noop}
        updateItem={noop}
        beginTransaction={noop}
        setActiveGuides={() => {}}
        movingItemIdsRef={{ current: new Set<string>() }}
        setMediaResizeState={noop}
        setBrushResizeState={noop}
        resizingHandle={{ current: null }}
        dragItemStart={{ current: null }}
        resizingStart={{ current: null }}
        renderSelectionHandles={() => null}
        shouldShowGeneratorControlPanel={() => false}
        referenceImageInputRef={{ current: null }}
        openGeneratorAssetLibrary={noop}
        openGeneratorReferenceGallery={noop}
        firstFrameImageInputRef={{ current: null }}
        tailFrameImageInputRef={{ current: null }}
        handleGenerateImage={noop}
        handleGenerateVideo={noop}
        getItemAmountCents={() => null}
        formatResolutionOptionLabel={(value: string) => value}
        standardSuffix="standard"
        imageRes="1K"
        videoQuality="720p"
        videoDuration="5s"
        normalizeReferenceImages={(item: CanvasItem) => item.reference_images || []}
        withReferenceImages={(referenceImages: string[]) => ({ reference_images: referenceImages })}
        imageRatio="1:1"
        videoAspect="16:9"
        ratioHintLabels={{ square: 'square', landscape: 'landscape', portrait: 'portrait' }}
        formatAspectRatioOptionLabelWithDimensions={(value: string) => value}
        cropDragState={null}
        handleCropMoveMouseDown={noop}
        handleCropHandleMouseDown={noop}
        cropCommitMode="freeform"
        handleCropDimensionChange={noop}
        CROP_PRESET_GROUPS={[]}
        setCropExpandedGroups={noop}
        cropExpandedGroups={new Set<string>()}
        handleSelectCropPreset={noop}
        setCropState={noop}
        handleApplyCrop={noop}
        textEditingItemId={null}
        selectedSingleItemRect={null}
        selectedSingleItemCanvasRect={null}
        selectedSingleItem={null}
        imageDetailItem={null}
        imageDetailData={null}
        imageDetailPanelPosition={null}
        handleCloseImageDetails={noop}
        textRedrawState={null}
        textRedrawPanelPosition={null}
        TEXT_REDRAW_PANEL_TOKENS={{ panelRadius: 16, panelPadding: 16 }}
        handleChangeTextRedrawSegment={noop}
        handleCancelTextRedraw={noop}
        handleSubmitTextRedraw={noop}
        shouldShowImageToolbar={() => false}
        openImageAnchoredImageDraft={noop}
        openImageAnchoredVideoDraft={noop}
        handleOpenHDUpscale={noop}
        handleOpenCutout={noop}
        handleOpenImageErase={noop}
        handleOpenTextRedraw={noop}
        handleOpenSpatialAngle={noop}
        handleOpenCropPanel={noop}
        handleDeleteCanvasImage={noop}
        handleOpenImageDetails={noop}
        handleRetryFailedGeneration={noop}
        shouldRenderSelectedMeta={false}
        selectedSingleItemViewportWidth={0}
        selectedIsImageGroup={false}
        editingNameId={null}
        setEditingNameId={noop}
        selectedIsGenerator={false}
        formatDimensionLabel={(width: number, height: number) => `${width} x ${height}`}
        selectedSingleItemWidth={0}
        selectedSingleItemHeight={0}
        imageAnchoredImageDraftItem={null}
        anchoredImageReferenceInputRef={{ current: null }}
        updateImageAnchoredImageDraft={noop}
        setPreviewImageUrl={noop}
        handleGenerateAnchoredImage={noop}
        imageAnchoredVideoDraftItem={null}
        imageAnchoredVideoCapability={null}
        imageAnchoredVideoAllowedDurations={[]}
        anchoredReferenceImageInputRef={{ current: null }}
        anchoredFirstFrameImageInputRef={{ current: null }}
        anchoredTailFrameImageInputRef={{ current: null }}
        updateImageAnchoredVideoDraft={noop}
        handleMoveAnchoredVideoSourcePlacement={noop}
        handleGenerateAnchoredVideo={noop}
        handleContextMenuAction={() => {}}
        handleCanvasPaste={() => {}}
        t={((key: string) => key) as any}
      />
    </div>
  )
}
