// @ts-nocheck

import { useMemo } from 'react'
import { CanvasBrushItem } from './CanvasBrushItem'
import { ImageAnchoredImagePanel } from './ImageAnchoredImagePanel'
import { ImageAnchoredVideoPanel } from './ImageAnchoredVideoPanel'
import { CanvasWorkspaceMediaRenderItem } from './CanvasWorkspaceMediaRenderItem'
import { CanvasWorkspaceTextRenderItem } from './CanvasWorkspaceTextRenderItem'
import { getAvailableVideoResolutions, getTailFrameConstraintState } from '../generatorCapabilities'
import {
  getCanvasViewportCullBounds,
  getCanvasSceneItemRenderMode,
  getVisibleCanvasSceneItems,
  isCanvasItemVisibleInViewport,
  shouldUseCanvasSceneRenderer,
} from '../canvasScene'
import { normalizeTextCanvasItem } from '../textTypography'
import { getViewportSidePanelPosition } from '../floatingPanelPosition'
import { getAllowedImageRatiosForResolution } from '../imageModelConfig'
import { isGeneratorModelOptionSelected } from '../generatorModelIdentity'

export function CanvasWorkspaceItemLayer(props: any) {
  const { canvasItems, clampCanvasStackZIndex, isHoverOnlyFailedVideoTask, getItemDims, activeDropdown, hoveredMarkableImageId, isTransientMarkModeActive, activeTool, markModifierState, cropState, selectedItems, getMediaSelectionOverlayMetrics, zoom, offset, canvasRef, selectedSingleItemRect, getResolvedImageCapability, getResolvedVideoCapability, getResolvedVideoDurations, availableImageModels, availableVideoModels, imageModel, imageProvider, videoModel, videoProvider, getItemReferenceImages, shouldDisableVideoAspectRatio, getVideoGeneratorCapability, getCanvasSelectionBorder, handleItemMouseDown, setSelectedItems, setContextMenu, setActiveContextMenuItem, beginTransaction, setActiveGuides, movingItemIdsRef, setMediaResizeState, resizingHandle, dragItemStart, resizingStart, getCanvasSelectionHandleAppearance, isDark, setBrushResizeState, setHoveredMarkableImageId, marks, textRedrawExtractingItemIds, isSceneReady, renderSnapshot, useWebGLRenderer, interactionPreview } = props
  const selectedItemIdSet = useMemo(() => new Set(selectedItems), [selectedItems])
  const activeDropdownState = useMemo(() => ({
    itemId: activeDropdown?.itemId ?? null,
    type: activeDropdown?.type ?? null,
  }), [activeDropdown])
  const overlayNodeById = useMemo(() => {
    if (!useWebGLRenderer || !renderSnapshot) return new Map()
    return new Map(renderSnapshot.overlayNodes.map((node: any) => [node.id, node]))
  }, [renderSnapshot, useWebGLRenderer])
  const selectedItemCount = selectedItems.length
  const viewportBounds = useMemo(() => getCanvasViewportCullBounds({
    zoom,
    offset,
    viewport: {
      width: canvasRef?.current?.clientWidth || 0,
      height: canvasRef?.current?.clientHeight || 0,
    },
  }), [canvasRef, offset, zoom])

  // Viewport culling + z-sort: memoized to avoid recalculation on unrelated prop changes
  const visibleItems = useMemo(() => {
    if (useWebGLRenderer && renderSnapshot) {
      const overlayIds = new Set(renderSnapshot.overlayNodes.map((node: any) => node.id))
      return [...canvasItems]
        .filter((item: any) => item.type !== 'group' && overlayIds.has(item.id))
        .sort((a: any, b: any) => (a.z_index || 0) - (b.z_index || 0))
    }
    return [...canvasItems].filter((item: any) => {
      if (item.type === 'group') return false
      if (selectedItemIdSet.has(item.id)) return true
      if (item.is_hidden) return false
      return isCanvasItemVisibleInViewport(item, {
        viewportBounds,
        getItemDims,
      })
    }).sort((a: any, b: any) => (a.z_index || 0) - (b.z_index || 0))
  }, [canvasItems, getItemDims, selectedItemIdSet, viewportBounds, renderSnapshot, useWebGLRenderer])

  // Hoist zoom-dependent metrics outside the per-item loop (same value for all items)
  const mediaSelectionMetrics = useMemo(() => getMediaSelectionOverlayMetrics(zoom), [getMediaSelectionOverlayMetrics, zoom])
  const sceneEligibleItems = useMemo(() => getVisibleCanvasSceneItems({
    canvasItems,
    selectedItems,
    marks,
    cropState,
    textRedrawExtractingItemIds,
    zoom,
    offset,
    viewport: {
      width: canvasRef?.current?.clientWidth || 0,
      height: canvasRef?.current?.clientHeight || 0,
    },
    getItemDims,
  }), [canvasItems, selectedItems, marks, cropState, textRedrawExtractingItemIds, zoom, offset, canvasRef, getItemDims])
  const useSceneRenderer = !useWebGLRenderer && shouldUseCanvasSceneRenderer({
    zoom,
    visibleItemCount: sceneEligibleItems.length,
  }) && isSceneReady

  return (
    <>
      {visibleItems.map((item: any) => {
        const isHidden = item.is_hidden
        const isImageGroup = item.type === 'image' || item.type === 'image_generator'
        const isMediaAsset = item.type === 'image' || item.type === 'video'
        const isGenerator = item.type === 'image_generator' || item.type === 'video_generator'
        const isMediaVisualItem = isMediaAsset || (isGenerator && Boolean(item.url))
        const isHoverOnlyFailedVideo = isHoverOnlyFailedVideoTask(item)
        const hoverErrorMessage = item.status === 'failed' && item.error_message ? item.error_message : undefined
        const dims = getItemDims(item)
        const actualWidth = item.width || dims.width
        const actualHeight = item.height || dims.height

        const isModelDropdownOpen = activeDropdownState.itemId === item.id && activeDropdownState.type === 'model'
        const isResDropdownOpen = activeDropdownState.itemId === item.id && activeDropdownState.type === 'res'
        const isVideoResolutionDropdownOpen = activeDropdownState.itemId === item.id && activeDropdownState.type === 'video_res'
        const isDurationDropdownOpen = activeDropdownState.itemId === item.id && activeDropdownState.type === 'duration'
        const isRatioDropdownOpen = activeDropdownState.itemId === item.id && activeDropdownState.type === 'ratio'
        const isMarkableImage = isImageGroup && Boolean(item.url)
        const isTransientMarkMode = isTransientMarkModeActive({
          activeTool,
          isHoveringMarkableImage: hoveredMarkableImageId === item.id,
          modifierState: markModifierState,
        })
        const isActiveCropItem = cropState?.itemId === item.id
        const isItemSelected = selectedItemIdSet.has(item.id)
        const shouldShowMediaSelectionOverlay = isMediaVisualItem && isItemSelected && selectedItemCount === 1 && !item.is_locked && !isActiveCropItem
        const cropPreviewFrame = isActiveCropItem && cropState
          ? {
            x: (cropState.x / cropState.sourceWidth) * actualWidth,
            y: (cropState.y / cropState.sourceHeight) * actualHeight,
            width: (cropState.width / cropState.sourceWidth) * actualWidth,
            height: (cropState.height / cropState.sourceHeight) * actualHeight,
          }
          : null
        const activeCropOutputSize = isActiveCropItem && cropState
          ? { width: cropState.width, height: cropState.height }
          : null
        const cropPanelViewportPosition = isActiveCropItem && selectedSingleItemRect && typeof window !== 'undefined'
          ? getViewportSidePanelPosition({
            anchorLeft: selectedSingleItemRect.left,
            anchorTop: selectedSingleItemRect.top,
            anchorWidth: selectedSingleItemRect.width,
            panelWidth: 300,
            panelHeight: 500,
            viewportWidth: window.innerWidth,
            viewportHeight: window.innerHeight,
          })
          : null
        const cropPanelOffset = cropPanelViewportPosition && selectedSingleItemRect
          ? {
            left: ((cropPanelViewportPosition.left - selectedSingleItemRect.left) * 100) / zoom,
            top: ((cropPanelViewportPosition.top - selectedSingleItemRect.top) * 100) / zoom,
          }
          : {
            left: actualWidth + (20 * 100 / zoom),
            top: 0,
          }

        const currentModel = (isImageGroup ? availableImageModels : availableVideoModels).find((m: any) => (
          isGeneratorModelOptionSelected(
            m,
            item.model_name || (isImageGroup ? imageModel : videoModel),
            item.provider_code || (isImageGroup ? imageProvider : videoProvider),
          )
        ))
        const currentConfig = currentModel?.config
        const imageCapability = isImageGroup ? getResolvedImageCapability(item) : null
        const videoCapability = !isImageGroup ? getResolvedVideoCapability(item) : null
        const allowedVideoDurations = !isImageGroup
          ? getResolvedVideoDurations(item, undefined, item.model_name || videoModel, currentConfig?.allowed_durations)
          : []
        const allowedVideoResolutions = !isImageGroup
          ? getAvailableVideoResolutions(
              videoCapability || getVideoGeneratorCapability(),
              item,
              currentConfig?.allowed_sizes && currentConfig.allowed_sizes.length > 0
                ? currentConfig.allowed_sizes
                : [props.videoQuality],
            )
          : []
        const referenceImages = getItemReferenceImages(item)
        const showReferenceButton = isImageGroup
          ? Boolean(imageCapability?.supportsReferenceImages)
          : Boolean(videoCapability?.supportsReferenceImages)
        const showFirstFrameButton = !isImageGroup && Boolean(videoCapability?.supportsFirstFrame)
        const tailFrameConstraint = !isImageGroup
          ? getTailFrameConstraintState(videoCapability || getVideoGeneratorCapability(), item, item.resolution || props.videoQuality)
          : { enabled: false, reason: 'unsupported' as const }
        const showTailFrameButton = !isImageGroup && Boolean(videoCapability?.supportsTailFrame)
        const showRatioSelector = isImageGroup
          ? getAllowedImageRatiosForResolution(currentConfig, item.resolution || props.imageRes).length > 0
          : !shouldDisableVideoAspectRatio(videoCapability || getVideoGeneratorCapability(), item)
        const optionColumnCount = isImageGroup
          ? (showRatioSelector ? 3 : 2)
          : (showRatioSelector ? 4 : 3)
        const normalizedTextItem = item.type === 'text' ? normalizeTextCanvasItem(item) : null
        const anchoredImagePanel = item.type === 'image' && props.imageAnchoredImageDraft && props.imageAnchoredImageDraft.sourceImageItemId === item.id && selectedItems.includes(item.id) && selectedItems.length === 1 && props.imageAnchoredImageDraftItem
          ? (
            <div style={{ position: 'absolute', top: actualHeight + (12 * 100 / zoom), left: actualWidth / 2, transform: `translateX(-50%) scale(${100 / zoom})`, transformOrigin: 'top center', zIndex: 2147483500 }}>
              <ImageAnchoredImagePanel draft={props.imageAnchoredImageDraft} availableImageModels={availableImageModels} isDark={isDark} t={props.t as any} amountCents={props.getItemAmountCents(props.imageAnchoredImageDraftItem)} referenceInputRef={props.anchoredImageReferenceInputRef} onUpdateDraft={props.updateImageAnchoredImageDraft} onPreviewImage={props.setPreviewImageUrl} onGenerate={props.handleGenerateAnchoredImage} onPickReferenceFromLibrary={() => props.openGeneratorAssetLibrary({ type: 'anchored-image', target: 'reference' })} onPickReferenceFromReferenceGallery={() => props.openGeneratorReferenceGallery({ type: 'anchored-image', target: 'reference' })} />
            </div>
          )
          : null
        const anchoredVideoPanel = item.type === 'image' && props.imageAnchoredVideoDraft && props.imageAnchoredVideoDraft.sourceImageItemId === item.id && selectedItems.includes(item.id) && selectedItems.length === 1 && props.imageAnchoredVideoDraftItem && props.imageAnchoredVideoCapability
          ? (
            <div style={{ position: 'absolute', top: actualHeight + (12 * 100 / zoom), left: actualWidth / 2, transform: `translateX(-50%) scale(${100 / zoom})`, transformOrigin: 'top center', zIndex: 2147483500 }}>
              <ImageAnchoredVideoPanel draft={props.imageAnchoredVideoDraft} draftItem={props.imageAnchoredVideoDraftItem} capability={props.imageAnchoredVideoCapability} allowedDurations={props.imageAnchoredVideoAllowedDurations} availableVideoModels={availableVideoModels} isDark={isDark} t={props.t as any} amountCents={props.getItemAmountCents(props.imageAnchoredVideoDraftItem)} referenceInputRef={props.anchoredReferenceImageInputRef} firstFrameInputRef={props.anchoredFirstFrameImageInputRef} tailFrameInputRef={props.anchoredTailFrameImageInputRef} onUpdateDraft={props.updateImageAnchoredVideoDraft} onMoveSourcePlacement={props.handleMoveAnchoredVideoSourcePlacement} onPreviewImage={props.setPreviewImageUrl} onGenerate={props.handleGenerateAnchoredVideo} onPickReferenceFromLibrary={() => props.openGeneratorAssetLibrary({ type: 'anchored-video', target: 'reference' })} onPickFirstFrameFromLibrary={() => props.openGeneratorAssetLibrary({ type: 'anchored-video', target: 'first_frame' })} onPickTailFrameFromLibrary={() => props.openGeneratorAssetLibrary({ type: 'anchored-video', target: 'tail_frame' })} onPickReferenceFromReferenceGallery={() => props.openGeneratorReferenceGallery({ type: 'anchored-video', target: 'reference' })} onPickFirstFrameFromReferenceGallery={() => props.openGeneratorReferenceGallery({ type: 'anchored-video', target: 'first_frame' })} onPickTailFrameFromReferenceGallery={() => props.openGeneratorReferenceGallery({ type: 'anchored-video', target: 'tail_frame' })} showSourceDragHint />
            </div>
          )
          : null

        if (item.type === 'text' && normalizedTextItem) {
          return (
            <CanvasWorkspaceTextRenderItem
              key={item.id}
              {...props}
              item={item}
              normalizedTextItem={normalizedTextItem}
              isHidden={isHidden}
              isItemSelected={isItemSelected}
              actualWidth={actualWidth}
              actualHeight={actualHeight}
              mediaSelectionMetrics={mediaSelectionMetrics}
            />
          )
        }

        if (item.type === 'brush_path') {
          const showBrushSelectionOverlay = isItemSelected && selectedItemCount === 1 && !item.is_locked
          const overlayNode = overlayNodeById.get(item.id)
          const renderMode = useWebGLRenderer && overlayNode
            ? overlayNode.overlayKind
            : getCanvasSceneItemRenderMode({
              useSceneRenderer: useSceneRenderer || (useWebGLRenderer && !isItemSelected),
              item,
              selectedItems,
              marks,
              cropState,
              textRedrawExtractingItemIds,
            })

          if (renderMode === 'interaction-shell') {
            return (
              <div
                key={item.id}
                id={`item-${item.id}`}
                style={{
                  display: isHidden ? 'none' : 'flex',
                  flexDirection: 'column',
                  gap: 12,
                  position: 'absolute',
                  top: item.y,
                  left: item.x,
                  zIndex: clampCanvasStackZIndex(item.z_index),
                  overflow: 'visible',
                }}
              >
                <div
                  style={{
                    position: 'relative',
                    width: actualWidth,
                    height: actualHeight,
                    overflow: 'visible',
                    cursor: item.is_locked ? 'default' : (activeTool === 'hand' ? 'inherit' : (activeTool === 'brush' ? 'crosshair' : 'default')),
                    backgroundColor: 'transparent',
                  }}
                  onClick={(e) => {
                    e.stopPropagation()
                    if (item.is_locked) return
                    setSelectedItems([item.id])
                  }}
                  onMouseDown={(e) => {
                    if (!item.is_locked) handleItemMouseDown(e, item.id)
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    if (!selectedItemIdSet.has(item.id)) setSelectedItems([item.id])
                    setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
                    setActiveContextMenuItem(null)
                  }}
                />
              </div>
            )
          }

          return (
            <div
              key={item.id}
              id={`item-${item.id}`}
              style={{
                display: isHidden ? 'none' : 'flex',
                flexDirection: 'column',
                gap: 12,
                position: 'absolute',
                top: item.y,
                left: item.x,
                zIndex: isItemSelected ? 2147483400 : clampCanvasStackZIndex(item.z_index),
                overflow: 'visible',
              }}
            >
              <div
                style={{
                  position: 'relative',
                  width: actualWidth,
                  height: actualHeight,
                  overflow: 'visible',
                  cursor: item.is_locked ? 'default' : (activeTool === 'hand' ? 'inherit' : (activeTool === 'brush' ? 'crosshair' : 'default')),
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  if (item.is_locked) return
                  setSelectedItems([item.id])
                }}
                onMouseDown={(e) => {
                  if (!item.is_locked) handleItemMouseDown(e, item.id)
                }}
                onContextMenu={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                    if (!selectedItemIdSet.has(item.id)) setSelectedItems([item.id])
                  setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
                  setActiveContextMenuItem(null)
                }}
              >
                <div
                  style={{
                    width: actualWidth,
                    height: actualHeight,
                    outline: showBrushSelectionOverlay ? getCanvasSelectionBorder(mediaSelectionMetrics.borderWidth) : 'none',
                    borderRadius: 8,
                    boxSizing: 'border-box',
                    padding: 4,
                  }}
                >
                  <CanvasBrushItem item={item} />
                </div>
                {showBrushSelectionOverlay && (
                  <>
                    {(['nw', 'ne', 'sw', 'se'] as const).map((handle) => (
                      <div
                        key={`${item.id}-${handle}`}
                        onMouseDown={(e) => {
                          e.stopPropagation()
                          beginTransaction()
                          interactionPreview?.begin(canvasItems)
                          setActiveGuides([])
                          movingItemIdsRef.current = new Set()
                          setBrushResizeState({
                            itemId: item.id,
                            handle,
                            startRect: {
                              x: item.x,
                              y: item.y,
                              width: actualWidth,
                              height: actualHeight,
                            },
                          })
                          resizingHandle.current = handle
                          dragItemStart.current = { x: e.clientX, y: e.clientY }
                          resizingStart.current = { x: item.x, y: item.y, w: actualWidth, h: actualHeight, top: item.y, left: item.x }
                        }}
                        style={{
                          position: 'absolute',
                          top: handle.includes('n') ? 0 : '100%',
                          left: handle.includes('w') ? 0 : '100%',
                          width: mediaSelectionMetrics.handleSize,
                          height: mediaSelectionMetrics.handleSize,
                          transform: `translate(${-mediaSelectionMetrics.handleOffset}px, ${-mediaSelectionMetrics.handleOffset}px)`,
                          borderRadius: '50%',
                          cursor: `${handle}-resize`,
                          boxShadow: 'var(--app-shadow-control)',
                          ...getCanvasSelectionHandleAppearance({ borderWidth: mediaSelectionMetrics.borderWidth, isDark }),
                        }}
                      />
                    ))}
                  </>
                )}
              </div>
            </div>
          )
        }

        const overlayNode = overlayNodeById.get(item.id)
        const renderMode = useWebGLRenderer && overlayNode
          ? overlayNode.overlayKind
          : getCanvasSceneItemRenderMode({
            useSceneRenderer: useSceneRenderer || (useWebGLRenderer && !isItemSelected),
            item,
            selectedItems,
            marks,
            cropState,
            textRedrawExtractingItemIds,
          })

        if (renderMode === 'interaction-shell') {
          return (
            <div
              key={item.id}
              id={`item-${item.id}`}
              style={{
                display: isHidden ? 'none' : 'flex',
                flexDirection: 'column',
                gap: 12,
                position: 'absolute',
                top: item.y,
                left: item.x,
                zIndex: clampCanvasStackZIndex(item.z_index),
                overflow: 'visible',
              }}
            >
              <div
                style={{
                  position: 'relative',
                  width: actualWidth,
                  height: actualHeight,
                  overflow: 'visible',
                  backgroundColor: 'transparent',
                  cursor: item.is_locked ? 'default' : (
                    isTransientMarkMode || activeTool === 'mark'
                      ? props.MARK_CURSOR
                      : (activeTool === 'select' ? 'default' : (activeTool === 'hand' ? 'inherit' : (activeTool === 'brush' ? 'crosshair' : 'pointer')))
                  ),
                }}
                onMouseEnter={() => {
                  if (isMarkableImage) setHoveredMarkableImageId(item.id)
                }}
                onMouseLeave={() => {
                  setHoveredMarkableImageId((prev: any) => (prev === item.id ? null : prev))
                }}
                onClick={(e) => {
                  e.stopPropagation()
                  setContextMenu(null)
                  setActiveContextMenuItem(null)
                  if (item.is_locked) return
                  if (props.imageAnchoredVideoDraft && item.id !== props.imageAnchoredVideoDraft.sourceImageItemId) return
                  if (props.imageDetailItemId === item.id) return
                  if (activeTool === 'mark' || (activeTool === 'select' && props.isMarkModifierPressed({
                    altKey: e.altKey,
                    metaKey: e.metaKey,
                    ctrlKey: e.ctrlKey,
                  }))) {
                    const isImageItem = item.type === 'image' || item.type === 'image_generator'
                    if (isImageItem && item.url) {
                      props.addMark(item, e)
                      return
                    }
                  }
                  if (activeTool === 'select') {
                    setSelectedItems([item.id])
                  }
                }}
                onMouseDown={(e) => {
                  if (activeTool === 'mark') return
                  if (props.imageDetailItemId === item.id) return
                  if (activeTool === 'select' && isMarkableImage && props.isMarkModifierPressed({
                    altKey: e.altKey,
                    metaKey: e.metaKey,
                    ctrlKey: e.ctrlKey,
                  })) return
                  if (!item.is_locked) handleItemMouseDown(e, item.id)
                }}
                onDoubleClick={(e) => {
                  if (item.type !== 'image' || !item.url) return
                  e.stopPropagation()
                  props.handleAppendImageMentionToChat(item.id)
                }}
                onContextMenu={(e) => {
                  e.preventDefault()
                  e.stopPropagation()
                  if (!selectedItemIdSet.has(item.id)) {
                    setSelectedItems([item.id])
                  }
                  setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
                  setActiveContextMenuItem(null)
                }}
                title={hoverErrorMessage}
              >
                {shouldShowMediaSelectionOverlay && (
                  <>
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        border: getCanvasSelectionBorder(mediaSelectionMetrics.borderWidth),
                        borderRadius: 8,
                        boxSizing: 'border-box',
                        pointerEvents: 'none',
                        zIndex: 35,
                      }}
                    />
                    {([
                      { handle: 'nw', top: -mediaSelectionMetrics.handleOffset, left: -mediaSelectionMetrics.handleOffset, cursor: 'nwse-resize' },
                      { handle: 'ne', top: -mediaSelectionMetrics.handleOffset, right: -mediaSelectionMetrics.handleOffset, cursor: 'nesw-resize' },
                      { handle: 'sw', bottom: -mediaSelectionMetrics.handleOffset, left: -mediaSelectionMetrics.handleOffset, cursor: 'nesw-resize' },
                      { handle: 'se', bottom: -mediaSelectionMetrics.handleOffset, right: -mediaSelectionMetrics.handleOffset, cursor: 'nwse-resize' },
                    ] as const).map(({ handle, cursor, ...position }) => (
                      <div
                        key={handle}
                        onMouseDown={(event) => {
                          event.stopPropagation()
                          beginTransaction()
                          interactionPreview?.begin(canvasItems)
                          setActiveGuides([])
                          movingItemIdsRef.current = new Set()
                          dragItemStart.current = { x: event.clientX, y: event.clientY }
                          setMediaResizeState({
                            itemId: item.id,
                            handle,
                            startRect: {
                              x: item.x,
                              y: item.y,
                              width: actualWidth,
                              height: actualHeight,
                            },
                          })
                        }}
                        style={{
                          position: 'absolute',
                          width: mediaSelectionMetrics.handleSize,
                          height: mediaSelectionMetrics.handleSize,
                          borderRadius: '50%',
                          boxShadow: 'var(--app-shadow-control)',
                          cursor,
                          zIndex: 36,
                          ...position,
                          ...getCanvasSelectionHandleAppearance({ borderWidth: mediaSelectionMetrics.borderWidth, isDark }),
                        }}
                      />
                    ))}
                  </>
                )}
                {anchoredImagePanel}
                {anchoredVideoPanel}
              </div>
            </div>
          )
        }

        return (
          <CanvasWorkspaceMediaRenderItem
            key={item.id}
            {...props}
            item={item}
            isHidden={isHidden}
            isImageGroup={isImageGroup}
            isMediaAsset={isMediaAsset}
            isGenerator={isGenerator}
            isHoverOnlyFailedVideo={isHoverOnlyFailedVideo}
            actualWidth={actualWidth}
            actualHeight={actualHeight}
            isModelDropdownOpen={isModelDropdownOpen}
            isResDropdownOpen={isResDropdownOpen}
            isVideoResolutionDropdownOpen={isVideoResolutionDropdownOpen}
            isDurationDropdownOpen={isDurationDropdownOpen}
            isRatioDropdownOpen={isRatioDropdownOpen}
            isMarkableImage={isMarkableImage}
            isTransientMarkMode={isTransientMarkMode}
            isActiveCropItem={isActiveCropItem}
            isItemSelected={isItemSelected}
            mediaSelectionMetrics={mediaSelectionMetrics}
            shouldShowMediaSelectionOverlay={shouldShowMediaSelectionOverlay}
            cropPreviewFrame={cropPreviewFrame}
            activeCropOutputSize={activeCropOutputSize}
            cropPanelOffset={cropPanelOffset}
            currentModel={currentModel}
            currentConfig={currentConfig}
            imageCapability={imageCapability}
            videoCapability={videoCapability}
            allowedVideoDurations={allowedVideoDurations}
            allowedVideoResolutions={allowedVideoResolutions}
            tailFrameConstraint={tailFrameConstraint}
            referenceImages={referenceImages}
            showReferenceButton={showReferenceButton}
            showFirstFrameButton={showFirstFrameButton}
            showTailFrameButton={showTailFrameButton}
            showRatioSelector={showRatioSelector}
            optionColumnCount={optionColumnCount}
          />
        )
      })}
    </>
  )
}
