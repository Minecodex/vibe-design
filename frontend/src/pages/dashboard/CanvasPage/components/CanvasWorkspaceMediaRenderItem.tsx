// @ts-nocheck

import React from 'react'
import {
  ChevronDown,
  ChevronRight,
  Loader2,
} from 'lucide-react'
import { getModelDisplayName } from '@/utils/modelDisplayName'

import { CanvasVideoItem } from './CanvasVideoItem'
import { GeneratorImageSourcePicker } from './GeneratorImageSourcePicker'
import { GeneratorReferenceStrip, useGeneratorReferenceChips } from './GeneratorReferenceStrip'
import { ImageAnchoredImagePanel } from './ImageAnchoredImagePanel'
import { ImageAnchoredVideoPanel } from './ImageAnchoredVideoPanel'
import {
  getAllowedImageRatiosForResolution,
  getAllowedImageResolutions,
  resolveImageModelSelection,
} from '../imageModelConfig'
import {
  getAvailableVideoResolutions as getCapabilityAvailableVideoResolutions,
  getTailFrameConstraintState,
  getVideoImageInputMode,
  normalizeVideoResolution,
} from '../generatorCapabilities'
import { getAllowedVideoRatios, getAllowedVideoResolutions, getVideoCapabilityFromConfig } from '../videoModelConfig'
import { handleScrollableWheel } from '../scrollableWheel'
import { isInternalFailedGenerationItem } from '../generationFailure'
import { isGenerationTaskPendingStatus } from '../generationTaskBinding'
import {
  getGeneratorModelOptionKey,
  isGeneratorModelOptionSelected,
} from '../generatorModelIdentity'

function areMediaItemPropsEqual(prev: any, next: any) {
  // Core item data changed => must re-render
  if (prev.item !== next.item) return false
  if (prev.isHidden !== next.isHidden) return false
  if (prev.isItemSelected !== next.isItemSelected) return false
  if (prev.actualWidth !== next.actualWidth) return false
  if (prev.actualHeight !== next.actualHeight) return false

  // Selected items need zoom-dependent UI (handles, panels, metrics)
  // so always re-render when any prop changes
  if (prev.isItemSelected || next.isItemSelected) return false

  // Generators, items without a URL, and video items use counter-scaled UI (scale(100/zoom)).
  // Generators/empty: placeholders, status indicators, control panels.
  // Video: hover controls (duration, fullscreen button).
  // They MUST re-render when zoom changes to keep the counter-scale correct.
  const itemType = next.item?.type
  const isGeneratorType = itemType === 'image_generator' || itemType === 'video_generator'
  const isVideoType = itemType === 'video'
  const hasNoMedia = !next.item?.url
  if ((isGeneratorType || hasNoMedia || isVideoType) && prev.zoom !== next.zoom) return false

  // For NON-selected items with media, only check visually-affecting props.
  // Skip zoom, offset, function refs — they don't affect non-selected rendered items.
  if (prev.isDark !== next.isDark) return false
  if (prev.activeTool !== next.activeTool) return false
  if (prev.isTransientMarkMode !== next.isTransientMarkMode) return false
  if (prev.marks !== next.marks) return false
  if (prev.textRedrawExtractingItemIds !== next.textRedrawExtractingItemIds) return false
  if (prev.imageAnchoredImageDraft !== next.imageAnchoredImageDraft) return false
  if (prev.imageAnchoredVideoDraft !== next.imageAnchoredVideoDraft) return false
  if (prev.imageDetailItemId !== next.imageDetailItemId) return false
  if (prev.cropState !== next.cropState) return false

  return true
}

const CanvasWorkspaceMediaRenderItemInner = React.memo(function CanvasWorkspaceMediaRenderItemInner(props: any) {
  const { item, isHidden, isImageGroup, isMediaAsset, isGenerator, isHoverOnlyFailedVideo, actualWidth, actualHeight, isModelDropdownOpen, isResDropdownOpen, isVideoResolutionDropdownOpen, isDurationDropdownOpen, isRatioDropdownOpen, isMarkableImage, isTransientMarkMode, isActiveCropItem, isItemSelected, mediaSelectionMetrics, shouldShowMediaSelectionOverlay, cropPreviewFrame, activeCropOutputSize, cropPanelOffset, currentModel, currentConfig, imageCapability, videoCapability, allowedVideoDurations, allowedVideoResolutions, tailFrameConstraint, referenceImages, showReferenceButton, showFirstFrameButton, showTailFrameButton, showRatioSelector, optionColumnCount, clampCanvasStackZIndex, selectedItems, activeTool, MARK_CURSOR, imageAnchoredVideoDraft, imageDetailItemId, isMarkModifierPressed, addMark, setSelectedItems, handleItemMouseDown, handleAppendImageMentionToChat, setContextMenu, setActiveContextMenuItem, setHoveredMarkableImageId, cropState, getCanvasSelectionContainerOverflow, isDark, zoom, activeVideoPreviewItemId, updateItem, getMediaDisplayInitializationUpdate, textRedrawExtractingItemIds, getTextRedrawExtractingBadgeStyle, t, cropDragState, handleCropMoveMouseDown, handleCropHandleMouseDown, getCanvasSelectionBorder, getCanvasSelectionHandleAppearance, beginTransaction, setActiveGuides, movingItemIdsRef, dragItemStart, setMediaResizeState, renderSelectionHandles, marks, shouldShowGeneratorControlPanel, setActiveDropdown, referenceImageInputRef, openGeneratorAssetLibrary, openGeneratorReferenceGallery, firstFrameImageInputRef, tailFrameImageInputRef, handleGenerateImage, handleGenerateVideo, getItemAmountCents, formatResolutionOptionLabel, standardSuffix, imageRes, videoQuality, videoDuration, normalizeReferenceImages, withReferenceImages, getImageGeneratorCapability, getResolvedVideoDurations, imageRatio, videoAspect, ratioHintLabels, formatAspectRatioOptionLabelWithDimensions, getItemDims, availableImageModels, availableVideoModels, imageModel, imageProvider, videoModel, videoProvider, cropCommitMode, handleCropDimensionChange, CROP_PRESET_GROUPS, setCropExpandedGroups, cropExpandedGroups, handleSelectCropPreset, setCropState, handleApplyCrop, imageAnchoredImageDraft, imageAnchoredImageDraftItem, anchoredImageReferenceInputRef, updateImageAnchoredImageDraft, setPreviewImageUrl, handleGenerateAnchoredImage, imageAnchoredVideoDraftItem, imageAnchoredVideoCapability, imageAnchoredVideoAllowedDurations, anchoredReferenceImageInputRef, anchoredFirstFrameImageInputRef, anchoredTailFrameImageInputRef, updateImageAnchoredVideoDraft, handleMoveAnchoredVideoSourcePlacement, handleGenerateAnchoredVideo, interactionPreview, canvasItems } = props
  const isPendingGeneration = isGenerationTaskPendingStatus(item.status)
  const selectedModelName = item.model_name || (isImageGroup ? imageModel : videoModel)
  const selectedModelProvider = item.provider_code || (isImageGroup ? imageProvider : videoProvider)
  const selectedModelDisplayName = getModelDisplayName(item.model_label || currentModel?.name, selectedModelName)
  const allowedImageResolutions = isImageGroup ? getAllowedImageResolutions(currentConfig) : []
  const allowedImageRatios = isImageGroup
    ? getAllowedImageRatiosForResolution(currentConfig, item.resolution || imageRes)
    : []
  const shouldShowRatioSelector = isImageGroup ? allowedImageRatios.length > 0 : showRatioSelector
  const allowedPanelVideoResolutions = !isImageGroup ? allowedVideoResolutions : []
  const allowedPanelVideoRatios = !isImageGroup ? getAllowedVideoRatios(currentConfig) : []
  const hoverErrorMessage = item.status === 'failed' && item.error_message ? item.error_message : undefined
  const isInternalFailure = isInternalFailedGenerationItem(item)
  const referenceImagesRef = React.useRef(referenceImages)
  referenceImagesRef.current = referenceImages
  const removeReferenceLabel = t('canvas.generator.remove_reference', 'Remove reference')
  const removeFirstFrameLabel = t('canvas.generator.remove_first_frame', 'Remove first frame')
  const removeTailFrameLabel = t('canvas.generator.remove_tail_frame', 'Remove tail frame')
  const referenceImageLabel = t('canvas.generator.reference_image', 'Reference image')
  const firstFrameLabel = t('canvas.generator.first_frame', 'First Frame')
  const tailFrameLabel = t('canvas.generator.tail_frame', 'Tail Frame')
  const generatorReferenceChips = useGeneratorReferenceChips({
    imageUrls: referenceImages,
    alt: referenceImageLabel,
    removeLabel: removeReferenceLabel,
  })
  const firstFrameChips = useGeneratorReferenceChips({
    imageUrls: showFirstFrameButton && item.first_frame_image ? [item.first_frame_image] : [],
    alt: firstFrameLabel,
    removeLabel: removeFirstFrameLabel,
    idPrefix: 'first:',
  })
  const tailFrameChips = useGeneratorReferenceChips({
    imageUrls: showTailFrameButton && item.tail_frame_image ? [item.tail_frame_image] : [],
    alt: tailFrameLabel,
    removeLabel: removeTailFrameLabel,
    idPrefix: 'tail:',
  })
  const handleRemoveGeneratorReference = React.useCallback((chipId: string) => {
    const index = Number(chipId.split(':', 1)[0])
    if (!Number.isFinite(index)) return
    const referenceImages = referenceImagesRef.current
    const nextReferenceImages = referenceImages.filter((_: string, imageIndex: number) => imageIndex !== index)
    updateItem(item.id, withReferenceImages(nextReferenceImages))
  }, [item.id, updateItem, withReferenceImages])
  const handleRemoveFirstFrame = React.useCallback(() => {
    updateItem(item.id, { first_frame_image: '' })
  }, [item.id, updateItem])
  const handleRemoveTailFrame = React.useCallback(() => {
    updateItem(item.id, { tail_frame_image: '' })
  }, [item.id, updateItem])

  return (
    <div
      key={item.id}
      id={`item-${item.id}`}
      data-canvas-item-id={item.id}
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
          cursor: item.is_locked ? 'default' : (
            isTransientMarkMode || activeTool === 'mark'
              ? MARK_CURSOR
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
          if (imageAnchoredVideoDraft && item.id !== imageAnchoredVideoDraft.sourceImageItemId) return
          if (imageDetailItemId === item.id) return
          if (activeTool === 'mark' || (activeTool === 'select' && isMarkModifierPressed({
            altKey: e.altKey,
            metaKey: e.metaKey,
            ctrlKey: e.ctrlKey,
          }))) {
            const isImageItem = item.type === 'image' || item.type === 'image_generator'
            if (isImageItem && item.url) {
              addMark(item, e)
              return
            }
          }
          if (activeTool === 'select') {
            setSelectedItems([item.id])
          }
        }}
        onMouseDown={(e) => {
          if (activeTool === 'mark') return
          if (imageDetailItemId === item.id) return
          if (activeTool === 'select' && isMarkableImage && isMarkModifierPressed({
            altKey: e.altKey,
            metaKey: e.metaKey,
            ctrlKey: e.ctrlKey,
          })) return
          if (!item.is_locked) handleItemMouseDown(e, item.id)
        }}
        onDoubleClick={(e) => {
          if (item.type !== 'image' || !item.url) return
          e.stopPropagation()
          handleAppendImageMentionToChat(item.id)
        }}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (!selectedItems.includes(item.id)) {
            setSelectedItems([item.id])
          }
          setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
          setActiveContextMenuItem(null)
        }}
      >
        <div
          style={{
            width: '100%',
            height: '100%',
            borderRadius: 8,
            border: isGenerator ? '1px solid var(--app-border)' : 'none',
            boxSizing: 'border-box',
            overflow: getCanvasSelectionContainerOverflow(shouldShowMediaSelectionOverlay || isActiveCropItem),
            boxShadow: 'var(--app-shadow-control)',
            backgroundColor: isPendingGeneration
              ? 'var(--app-control-hover)'
              : isInternalFailure
                ? (isDark ? 'color-mix(in srgb, var(--app-danger) 16%, transparent)' : 'color-mix(in srgb, var(--app-danger) 12%, transparent)')
              : (item.url ? 'transparent' : (isGenerator ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'var(--app-surface-muted)')),
            outline: isItemSelected && !shouldShowMediaSelectionOverlay
              ? getCanvasSelectionBorder(mediaSelectionMetrics.borderWidth)
              : 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative',
          }}
          title={hoverErrorMessage}
        >
          {isPendingGeneration ? (
            <div
              style={{
                transform: `scale(${100 / zoom})`,
                transformOrigin: 'center center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                color: 'var(--app-foreground-muted)',
              }}
            >
              <Loader2 className="w-6 h-6 animate-spin" />
              <span style={{ fontSize: 13, fontWeight: 500 }}>
                {t('canvas.generator.generating_progress', { progress: item.progress ?? 0 })}
              </span>
              <div
                style={{
                  width: 160,
                  height: 4,
                  backgroundColor: 'var(--app-control-track)',
                  borderRadius: 2,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${item.progress ?? 0}%`,
                    height: '100%',
                    backgroundColor: 'var(--app-primary)',
                    borderRadius: 2,
                    transition: 'width 0.5s ease',
                  }}
                />
              </div>
            </div>
          ) : item.status === 'failed' ? (
            <div
              style={{
                transform: `scale(${100 / zoom})`,
                transformOrigin: 'center center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                color: 'var(--app-danger)',
              }}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" /></svg>
              <span style={{ fontSize: 13, fontWeight: 500 }}>
                {isInternalFailure
                  ? t('canvas.generator.internal_error_label', '内部错误')
                  : (isImageGroup ? t('canvas.generator.failed_image') : t('canvas.generator.failed_video'))}
              </span>
            </div>
          ) : item.url ? (
            isImageGroup ? (
              <img
                src={item.url}
                alt="canvas item"
                data-canvas-media-img="true"
                style={{ width: '100%', height: '100%', objectFit: 'contain' }}
                draggable={false}
                onLoad={(e) => {
                  const img = e.currentTarget
                  const nextDisplay = getMediaDisplayInitializationUpdate({
                    item,
                    intrinsicWidth: img.naturalWidth,
                    intrinsicHeight: img.naturalHeight,
                  })
                  if (nextDisplay) {
                    updateItem(item.id, nextDisplay)
                  }
                }}
              />
            ) : (
              <CanvasVideoItem
                url={item.url}
                zoom={zoom}
                autoPreview={activeVideoPreviewItemId === item.id}
                onLoadedMetadata={(e) => {
                  const video = e.currentTarget
                  const nextDisplay = getMediaDisplayInitializationUpdate({
                    item,
                    intrinsicWidth: video.videoWidth,
                    intrinsicHeight: video.videoHeight,
                  })
                  if (nextDisplay) {
                    updateItem(item.id, nextDisplay)
                  }
                }}
              />
            )
          ) : (
            <div
              style={{
                transform: `scale(${100 / zoom})`,
                transformOrigin: 'center center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 12,
                color: 'var(--app-primary)',
              }}
            >
              {isImageGroup ? (
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 15l4-4 4 4" /><path d="M13 13l3-3 5 5" /><path d="M21 5l-2.5-.5-.5-2.5-.5 2.5-2.5.5 2.5.5.5 2.5.5-2.5z" /></svg>
              ) : (
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="2" /><polygon points="10 8 16 12 10 16 10 8" /><path d="M21 5l-2.5-.5-.5-2.5-.5 2.5-2.5.5 2.5.5.5 2.5.5-2.5z" /></svg>
              )}
              <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--app-primary)' }}>{isImageGroup ? t('canvas.generator.image_title') : t('canvas.generator.video_title')}</span>
            </div>
          )}
          {textRedrawExtractingItemIds?.has(item.id) && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                background: 'var(--app-media-scrim)',
                backdropFilter: 'blur(10px)',
                WebkitBackdropFilter: 'blur(10px)',
                zIndex: 24,
                pointerEvents: 'none',
              }}
            >
              <div
                style={{
                  ...getTextRedrawExtractingBadgeStyle({ zoom }),
                }}
              >
                {t('canvas.text_redraw.extracting', 'Extracting text')}
              </div>
            </div>
          )}
          {cropPreviewFrame && cropState && (
            <div
              style={{
                position: 'absolute',
                left: cropPreviewFrame.x,
                top: cropPreviewFrame.y,
                width: cropPreviewFrame.width,
                height: cropPreviewFrame.height,
                border: getCanvasSelectionBorder(2 * 100 / zoom),
                borderRadius: 8,
                boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.28)',
                pointerEvents: 'auto',
                zIndex: 30,
                backgroundColor: 'transparent',
                cursor: cropDragState?.handle === 'move' ? 'grabbing' : 'move',
              }}
              onMouseDown={handleCropMoveMouseDown}
            >
              {[1, 2].map((step) => (
                <div
                  key={`v-${step}`}
                  style={{
                    position: 'absolute',
                    left: `${(step / 3) * 100}%`,
                    top: 0,
                    width: 1 * 100 / zoom,
                    height: '100%',
                    backgroundColor: 'rgba(255,255,255,0.65)',
                  }}
                />
              ))}
              {[1, 2].map((step) => (
                <div
                  key={`h-${step}`}
                  style={{
                    position: 'absolute',
                    top: `${(step / 3) * 100}%`,
                    left: 0,
                    width: '100%',
                    height: 1 * 100 / zoom,
                    backgroundColor: 'rgba(255,255,255,0.65)',
                  }}
                />
              ))}
              <div onMouseDown={(event) => handleCropHandleMouseDown('top-left', event)} style={{ position: 'absolute', top: -(8 * 100 / zoom), left: -(8 * 100 / zoom), width: 16 * 100 / zoom, height: 16 * 100 / zoom, borderRadius: '50%', cursor: 'nwse-resize', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 2 * 100 / zoom, isDark, fillColor: 'var(--app-primary-foreground)' }) }} />
              <div onMouseDown={(event) => handleCropHandleMouseDown('top-right', event)} style={{ position: 'absolute', top: -(8 * 100 / zoom), right: -(8 * 100 / zoom), width: 16 * 100 / zoom, height: 16 * 100 / zoom, borderRadius: '50%', cursor: 'nesw-resize', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 2 * 100 / zoom, isDark, fillColor: 'var(--app-primary-foreground)' }) }} />
              <div onMouseDown={(event) => handleCropHandleMouseDown('bottom-left', event)} style={{ position: 'absolute', bottom: -(8 * 100 / zoom), left: -(8 * 100 / zoom), width: 16 * 100 / zoom, height: 16 * 100 / zoom, borderRadius: '50%', cursor: 'nesw-resize', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 2 * 100 / zoom, isDark, fillColor: 'var(--app-primary-foreground)' }) }} />
              <div onMouseDown={(event) => handleCropHandleMouseDown('bottom-right', event)} style={{ position: 'absolute', bottom: -(8 * 100 / zoom), right: -(8 * 100 / zoom), width: 16 * 100 / zoom, height: 16 * 100 / zoom, borderRadius: '50%', cursor: 'nwse-resize', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 2 * 100 / zoom, isDark, fillColor: 'var(--app-primary-foreground)' }) }} />
            </div>
          )}
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
        </div>
        {isActiveCropItem && activeCropOutputSize && (
          <div
            className="nowheel"
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            onWheel={(e) => e.stopPropagation()}
            style={{
              position: 'absolute',
              left: cropPanelOffset.left,
              top: cropPanelOffset.top,
              width: 300,
              maxHeight: 500,
              display: 'flex',
              flexDirection: 'column',
              backgroundColor: 'var(--app-glass)',
              border: '1px solid var(--app-border)',
              borderRadius: 8,
              boxShadow: 'var(--app-shadow-panel)',
              overflow: 'hidden',
              zIndex: 120,
              pointerEvents: 'auto',
              transform: `scale(${100 / zoom})`,
              transformOrigin: 'top left',
            }}
          >
            <div style={{ padding: '14px 14px 10px', fontSize: 16, fontWeight: 700, color: 'var(--app-foreground)' }}>
              {t('canvas.crop.title', '裁剪')}
            </div>
            <div style={{ padding: '0 14px 10px', display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ flex: 1, height: 38, display: 'flex', alignItems: 'center', gap: 8, backgroundColor: 'var(--app-control)', borderRadius: 8, padding: '0 12px', color: 'var(--app-foreground)' }}>
                <span style={{ fontSize: 13, color: 'var(--app-foreground-muted)', fontWeight: 500 }}>W</span>
                <input type="number" min={1} max={cropState.sourceWidth} value={Math.round(activeCropOutputSize.width)} onChange={(e) => handleCropDimensionChange('width', e.target.value)} style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', color: 'var(--app-foreground)', fontSize: 14, fontWeight: 600 }} />
              </div>
              <div style={{ color: 'var(--app-foreground-subtle)', display: 'flex', alignItems: 'center' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M7 10l5 5 5-5" /><path d="M7 14l5-5 5 5" /></svg>
              </div>
              <div style={{ flex: 1, height: 38, display: 'flex', alignItems: 'center', gap: 8, backgroundColor: 'var(--app-control)', borderRadius: 8, padding: '0 12px', color: 'var(--app-foreground)' }}>
                <span style={{ fontSize: 13, color: 'var(--app-foreground-muted)', fontWeight: 500 }}>H</span>
                <input type="number" min={1} max={cropState.sourceHeight} value={Math.round(activeCropOutputSize.height)} onChange={(e) => handleCropDimensionChange('height', e.target.value)} style={{ width: '100%', border: 'none', outline: 'none', background: 'transparent', color: 'var(--app-foreground)', fontSize: 14, fontWeight: 600 }} />
              </div>
            </div>
            <div style={{ padding: '0 14px 10px', fontSize: 11, lineHeight: 1.45, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-muted)' }}>
              {(cropCommitMode as string) === 'noop'
                ? t('canvas.crop.noop_hint', 'The current image is already within the target size.')
                : t('canvas.crop.crop_hint', 'Applying will replace the current image with the cropped result.')}
            </div>
            <div style={{ padding: '8px 14px 4px', fontSize: 13, fontWeight: 600, color: isDark ? 'var(--app-foreground-subtle)' : 'var(--app-foreground-subtle)' }}>
              {t('canvas.crop.presets_label', '预设')}
            </div>
            <div style={{ flex: 1, overflowY: 'auto', padding: '0 8px 8px' }}>
              {CROP_PRESET_GROUPS.map((group: any) => (
                <div key={group.id} style={{ marginBottom: 4 }}>
                  <button
                    type="button"
                    onClick={() => setCropExpandedGroups((prev: any) => ({ ...prev, [group.id]: !prev[group.id] }))}
                    style={{
                      width: '100%',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 6,
                      padding: '8px 10px',
                      color: 'var(--app-foreground)',
                      background: 'transparent',
                      border: 'none',
                      cursor: 'pointer',
                      fontSize: 13,
                      fontWeight: 600,
                    }}
                  >
                    {cropExpandedGroups[group.id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    <span>{group.label}</span>
                  </button>
                  {cropExpandedGroups[group.id] && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '0 6px 2px 22px' }}>
                      {group.presets.map((preset: any) => (
                        <button
                          key={preset.id}
                          type="button"
                          onClick={() => handleSelectCropPreset(preset.id)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            gap: 8,
                            padding: '9px 10px',
                            borderRadius: 10,
                            border: preset.id === cropState?.presetId ? '1px solid var(--app-primary)' : '1px solid var(--app-border)',
                            backgroundColor: preset.id === cropState?.presetId ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'var(--app-surface-muted)',
                            color: 'var(--app-foreground)',
                            cursor: 'pointer',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div
                              style={{
                                width: 14,
                                height: 14,
                                borderRadius: 4,
                                border: preset.id === cropState?.presetId ? '5px solid var(--app-primary)' : '1px solid var(--app-foreground-subtle)',
                                backgroundColor: 'var(--app-surface-solid)',
                                boxSizing: 'border-box',
                              }}
                            />
                            <span style={{ fontSize: 13, fontWeight: 500 }}>{preset.label}</span>
                          </div>
                          {preset.kind === 'platform' && (
                              <span style={{ fontSize: 11, color: 'var(--app-foreground-subtle)' }}>
                              {preset.width}x{preset.height}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--app-border)' }}>
              <button
                type="button"
                onClick={() => setCropState(null)}
                disabled={cropState?.isApplying}
                style={{
                  flex: 1,
                  height: 36,
                  borderRadius: 12,
                  border: '1px solid var(--app-border)',
                  backgroundColor: 'transparent',
                  color: 'var(--app-foreground)',
                  cursor: cropState?.isApplying ? 'not-allowed' : 'pointer',
                  opacity: cropState?.isApplying ? 0.6 : 1,
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                {t('cancel', 'Cancel')}
              </button>
              <button
                type="button"
                onClick={handleApplyCrop}
                disabled={cropState?.isApplying}
                style={{
                  flex: 1,
                  height: 36,
                  borderRadius: 12,
                  border: 'none',
                  backgroundColor: 'var(--app-primary)',
                  color: 'var(--app-primary-foreground)',
                  cursor: cropState?.isApplying ? 'not-allowed' : 'pointer',
                  opacity: cropState?.isApplying ? 0.6 : 1,
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                {cropState?.isApplying ? t('processing', '处理中...') : t('done', '完成')}
              </button>
            </div>
          </div>
        )}
        {marks.filter((mark: any) => mark.imageItemId === item.id).map((mark: any) => (
          <div
            key={mark.id}
            style={{
              position: 'absolute',
              left: `${mark.relativeX * 100}%`,
              top: `${mark.relativeY * 100}%`,
              transform: `translate(-50%, -100%) scale(${100 / zoom})`,
              transformOrigin: 'bottom center',
              pointerEvents: 'auto',
              zIndex: 50,
              display: 'flex',
              alignItems: 'flex-end',
              gap: 4,
            }}
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div style={{ width: 28, height: 28, borderRadius: '50%', backgroundColor: 'var(--app-primary)', color: 'var(--app-primary-foreground)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, fontWeight: 700, boxShadow: 'var(--app-shadow-control)', border: '2px solid var(--app-surface-solid)', position: 'relative' }}>
              {mark.isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : mark.number}
            </div>
            <div
              style={{ width: 20, height: 20, borderRadius: '50%', backgroundColor: 'var(--app-surface-solid)', boxShadow: 'var(--app-shadow-control)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', marginBottom: 4 }}
              onClick={(e) => { e.stopPropagation() }}
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="var(--app-foreground-muted)" strokeWidth="2.5">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                <path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
              </svg>
            </div>
          </div>
        ))}
        {isItemSelected && selectedItems.length === 1 && !isMediaAsset && renderSelectionHandles()}
      </div>
      {shouldShowGeneratorControlPanel(item, { isHoverOnlyFailedVideo }) && selectedItems.includes(item.id) && selectedItems.length === 1 && (
        <div
          className="nowheel"
          style={{
            width: 720,
            backgroundColor: 'var(--app-glass)',
            borderRadius: 16,
            boxShadow: 'var(--app-shadow-panel)',
            border: '1px solid var(--app-border)',
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: 24,
            zIndex: 2147483500,
            position: 'absolute',
            top: actualHeight + (12 * 100 / zoom),
            left: actualWidth / 2,
            transform: `translateX(-50%) scale(${100 / zoom})`,
            transformOrigin: 'top center',
          }}
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => { e.stopPropagation(); setActiveDropdown(null) }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--app-foreground)' }}>
              {t('canvas.generator.describe_imagination', 'Describe what you want to generate')}
            </div>
            <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', borderRadius: 12, border: '1px solid var(--app-border)', backgroundColor: 'var(--app-control)', overflow: 'hidden' }}>
              <textarea
                value={item.prompt || ''}
                onChange={(e) => updateItem(item.id, { prompt: e.target.value })}
                placeholder={isImageGroup ? t('canvas.generator.prompt_placeholder_image') : t('canvas.generator.prompt_placeholder_video')}
                onClick={() => setActiveDropdown(null)}
                style={{ width: '100%', height: 120, padding: '16px', border: 'none', fontSize: 15, resize: 'none', outline: 'none', backgroundColor: 'transparent', color: 'var(--app-foreground)' }}
              />
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12, padding: '12px 16px', backgroundColor: 'transparent' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  {showReferenceButton && referenceImages.length > 0 && (
                    <GeneratorReferenceStrip
                      chips={generatorReferenceChips}
                      isDark={isDark}
                      onPreviewImage={setPreviewImageUrl}
                      onRemove={handleRemoveGeneratorReference}
                    />
                  )}
                  {showFirstFrameButton && item.first_frame_image && (
                    <GeneratorReferenceStrip
                      chips={firstFrameChips}
                      isDark={isDark}
                      onPreviewImage={setPreviewImageUrl}
                      onRemove={handleRemoveFirstFrame}
                    />
                  )}
                  {showTailFrameButton && item.tail_frame_image && (
                    <GeneratorReferenceStrip
                      chips={tailFrameChips}
                      isDark={isDark}
                      onPreviewImage={setPreviewImageUrl}
                      onRemove={handleRemoveTailFrame}
                    />
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12, flexWrap: 'wrap' }}>
                  {showReferenceButton && (() => {
                    const maxRef = (isImageGroup ? imageCapability?.maxReferenceImages : videoCapability?.maxReferenceImages) || 0
                    const refDisabled = maxRef > 0 && referenceImages.length >= maxRef
                    return (
                      <GeneratorImageSourcePicker
                        isDark={isDark}
                        label={t('canvas.generator.reference_image', 'Reference image')}
                        countLabel={`${t('canvas.generator.reference_image', 'Reference image')}${maxRef > 1 ? ` ${referenceImages.length}/${maxRef}` : ''}`}
                        localLabel={t('canvas.generator.local_image', 'Local Image')}
                        libraryLabel={t('canvas.generator.source_asset_library', 'Asset Library')}
                        referenceLibraryLabel={t('canvas.generator.reference_gallery', 'Reference Gallery')}
                        active={referenceImages.length > 0 && !refDisabled}
                        localDisabled={refDisabled}
                        libraryDisabled={refDisabled}
                        referenceLibraryDisabled={refDisabled}
                        onPickLocal={() => referenceImageInputRef.current?.click()}
                        onPickFromLibrary={() => openGeneratorAssetLibrary({ type: 'canvas-item', itemId: item.id, target: 'reference' })}
                        onPickFromReferenceLibrary={() => openGeneratorReferenceGallery({ type: 'canvas-item', itemId: item.id, target: 'reference' })}
                      />
                    )
                  })()}
                  {showFirstFrameButton && (
                    <GeneratorImageSourcePicker
                      isDark={isDark}
                      label={t('canvas.generator.first_frame')}
                      localLabel={t('canvas.generator.local_image', 'Local Image')}
                      libraryLabel={t('canvas.generator.source_asset_library', 'Asset Library')}
                      referenceLibraryLabel={t('canvas.generator.reference_gallery', 'Reference Gallery')}
                      active={Boolean(item.first_frame_image)}
                      onPickLocal={() => firstFrameImageInputRef.current?.click()}
                      onPickFromLibrary={() => openGeneratorAssetLibrary({ type: 'canvas-item', itemId: item.id, target: 'first_frame' })}
                      onPickFromReferenceLibrary={() => openGeneratorReferenceGallery({ type: 'canvas-item', itemId: item.id, target: 'first_frame' })}
                    />
                  )}
                  {showTailFrameButton && (
                    <GeneratorImageSourcePicker
                      isDark={isDark}
                      label={t('canvas.generator.tail_frame')}
                      localLabel={t('canvas.generator.local_image', 'Local Image')}
                      libraryLabel={t('canvas.generator.source_asset_library', 'Asset Library')}
                      referenceLibraryLabel={t('canvas.generator.reference_gallery', 'Reference Gallery')}
                      active={Boolean(item.tail_frame_image)}
                      disabled={!tailFrameConstraint?.enabled}
                      localDisabled={!tailFrameConstraint?.enabled}
                      libraryDisabled={!tailFrameConstraint?.enabled}
                      referenceLibraryDisabled={!tailFrameConstraint?.enabled}
                      onPickLocal={() => tailFrameImageInputRef.current?.click()}
                      onPickFromLibrary={() => openGeneratorAssetLibrary({ type: 'canvas-item', itemId: item.id, target: 'tail_frame' })}
                      onPickFromReferenceLibrary={() => openGeneratorReferenceGallery({ type: 'canvas-item', itemId: item.id, target: 'tail_frame' })}
                    />
                  )}
                  <div
                    onClick={(e) => {
                      e.stopPropagation()
                      if (isPendingGeneration) return
                      if (isImageGroup) handleGenerateImage(item.id)
                      else handleGenerateVideo(item.id)
                    }}
                    style={{ height: 38, borderRadius: 12, backgroundColor: isPendingGeneration ? 'var(--app-control)' : 'var(--app-primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: isPendingGeneration ? 'not-allowed' : 'pointer', color: 'var(--app-primary-foreground)', padding: '0 16px', gap: 6, boxShadow: 'var(--app-shadow-control)', flexShrink: 0, whiteSpace: 'nowrap', opacity: isPendingGeneration ? 0.7 : 1 }}
                  >
                    <span style={{ fontSize: 16 }}>Go</span>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{t('canvas.generator.generate_now', '立即生成')}</span>
                  </div>
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: `repeat(${optionColumnCount}, 1fr)`, gap: 16 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
                    {t('canvas.generator.model_label', '生成模型')}
                  </div>
                  <div style={{ position: 'relative' }}>
                    <div onClick={(e) => { e.stopPropagation(); setActiveDropdown(isModelDropdownOpen ? null : { itemId: item.id, type: 'model' }) }} style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}>
                      <span style={{ fontWeight: 500, color: 'var(--app-foreground)', display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {selectedModelDisplayName || selectedModelName}
                      </span>
                      <div style={{ flexShrink: 0 }}>
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--app-foreground-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="7 10 12 15 17 10" /></svg>
                      </div>
                    </div>
                    {isModelDropdownOpen && (
                      <div style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', backdropFilter: 'var(--app-blur)', WebkitBackdropFilter: 'var(--app-blur)', padding: 8, width: '100%', minWidth: 200, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 200, overflowY: 'auto' }}>
                        {(isImageGroup ? availableImageModels : availableVideoModels).map((m: any, index: number) => {
                          const isSelectedModel = isGeneratorModelOptionSelected(
                            m,
                            selectedModelName,
                            selectedModelProvider,
                          )
                          return (
                          <div
                            key={getGeneratorModelOptionKey(m, index)}
                            onClick={(e) => {
                              e.stopPropagation()
                              const updates: any = { model_name: m.value, provider_code: m.provider }
                              const newConfig = m.config
                              const nextReferenceImages = normalizeReferenceImages(item)
                              if (newConfig) {
                                if (isImageGroup) {
                                  const nextSelection = resolveImageModelSelection({
                                    config: newConfig,
                                    currentResolution: item.resolution || imageRes,
                                    currentAspectRatio: item.aspect_ratio || imageRatio,
                                  })
                                  if (nextSelection.resolution !== (item.resolution || imageRes)) updates.resolution = nextSelection.resolution
                                  if (nextSelection.aspect_ratio !== (item.aspect_ratio || imageRatio)) updates.aspect_ratio = nextSelection.aspect_ratio
                                  if (updates.resolution || updates.aspect_ratio) {
                                    const dims = getItemDims({ ...item, ...updates })
                                    updates.width = dims.width
                                    updates.height = dims.height
                                  }
                                } else {
                                  const currentRatio = item.aspect_ratio || videoAspect
                                  const currentResolution = item.resolution || videoQuality
                                  if (newConfig.allowed_sizes && !newConfig.allowed_sizes.includes(currentResolution)) updates.resolution = newConfig.allowed_sizes[0] || videoQuality
                                  if (newConfig.allowed_aspect_ratios && !newConfig.allowed_aspect_ratios.includes(currentRatio)) updates.aspect_ratio = newConfig.allowed_aspect_ratios[0] || '16:9'
                                }
                              }
                              if (isImageGroup) {
                                const capability = m.config?.max_reference_images != null
                                  ? {
                                      supportsReferenceImages: m.config.max_reference_images > 0,
                                      maxReferenceImages: Math.max(0, m.config.max_reference_images),
                                    }
                                  : getImageGeneratorCapability(m.value)
                                if (!capability.supportsReferenceImages) {
                                  Object.assign(updates, withReferenceImages([]))
                                } else if (nextReferenceImages.length > capability.maxReferenceImages) {
                                  Object.assign(updates, withReferenceImages(nextReferenceImages.slice(0, capability.maxReferenceImages)))
                                }
                              } else {
                                const capability = getVideoCapabilityFromConfig(m.config, m.value)
                                const currentInputMode = getVideoImageInputMode(videoCapability || capability, item)
                                if (!capability.supportsReferenceImages && nextReferenceImages.length > 0) {
                                  Object.assign(updates, withReferenceImages([]))
                                } else if (capability.supportsReferenceImages && nextReferenceImages.length > capability.maxReferenceImages) {
                                  Object.assign(updates, withReferenceImages(nextReferenceImages.slice(0, capability.maxReferenceImages)))
                                }
                                if (!capability.supportsFirstFrame) updates.first_frame_image = ''
                                if (!capability.supportsTailFrame) updates.tail_frame_image = ''
                                let nextVideoItem = { ...item, ...updates }
                                let nextModeReferenceImages = normalizeReferenceImages(nextVideoItem)
                                const hasReferenceMode = nextModeReferenceImages.length > 0
                                const hasFrameMode = Boolean(nextVideoItem.first_frame_image || nextVideoItem.tail_frame_image)
                                if (capability.imageModesConflict && hasReferenceMode && hasFrameMode) {
                                  if (currentInputMode === 'reference' && capability.supportsReferenceImages) {
                                    updates.first_frame_image = ''
                                    updates.tail_frame_image = ''
                                  } else {
                                    Object.assign(updates, withReferenceImages([]))
                                  }
                                }
                                nextVideoItem = { ...item, ...updates }
                                const baseAllowedResolutions = newConfig?.allowed_sizes?.length
                                  ? newConfig.allowed_sizes
                                  : getAllowedVideoResolutions(newConfig)
                                const nextAvailableResolutions = getCapabilityAvailableVideoResolutions(
                                  capability,
                                  nextVideoItem,
                                  baseAllowedResolutions,
                                )
                                const nextResolution = normalizeVideoResolution(
                                  (updates.resolution as string | undefined) || item.resolution || videoQuality,
                                )
                                const resolvedResolutionOptions = nextAvailableResolutions.length > 0
                                  ? nextAvailableResolutions
                                  : baseAllowedResolutions
                                if (
                                  resolvedResolutionOptions.length > 0 &&
                                  !resolvedResolutionOptions.some((resolution) => normalizeVideoResolution(resolution) === nextResolution)
                                ) {
                                  updates.resolution = resolvedResolutionOptions[0] || videoQuality
                                }
                                nextVideoItem = { ...item, ...updates }
                                nextModeReferenceImages = normalizeReferenceImages(nextVideoItem)
                                const tailFrameConstraint = getTailFrameConstraintState(
                                  capability,
                                  nextVideoItem,
                                  nextVideoItem.resolution || videoQuality,
                                )
                                if (!tailFrameConstraint.enabled && nextVideoItem.tail_frame_image) {
                                  updates.tail_frame_image = ''
                                  nextVideoItem = { ...item, ...updates }
                                  nextModeReferenceImages = normalizeReferenceImages(nextVideoItem)
                                }
                                const nextAllowedDurations = getResolvedVideoDurations(item, updates, m.value, newConfig?.allowed_durations)
                                const nextDuration = (updates.duration as string | undefined) || item.duration || videoDuration
                                if (nextAllowedDurations.length > 0 && !nextAllowedDurations.includes(nextDuration)) {
                                  updates.duration = nextAllowedDurations[0] || '5s'
                                }
                                if (updates.resolution || updates.aspect_ratio) {
                                  const dims = getItemDims({ ...item, ...updates })
                                  updates.width = dims.width
                                  updates.height = dims.height
                                }
                              }
                              updateItem(item.id, updates)
                              setActiveDropdown(null)
                            }}
                            style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', display: 'flex', flexDirection: 'column', gap: 2, backgroundColor: isSelectedModel ? 'var(--app-control-selected)' : 'transparent' }}
                            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = isSelectedModel ? 'var(--app-control-selected)' : 'var(--app-control-hover)' }}
                            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = isSelectedModel ? 'var(--app-control-selected)' : 'transparent' }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--app-foreground)' }}>{getModelDisplayName(m.name, m.value)}</span>
                              {isSelectedModel && <div style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: 'var(--app-primary)' }} />}
                            </div>
                            <span style={{ fontSize: 11, color: 'var(--app-foreground-subtle)' }}>{m.providerName}</span>
                          </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>
                    {t('canvas.generator.resolution_label', '精度设置')}
                  </div>
                  <div style={{ position: 'relative' }}>
                    <div onClick={(e) => { e.stopPropagation(); setActiveDropdown((isImageGroup ? isResDropdownOpen : isVideoResolutionDropdownOpen) ? null : { itemId: item.id, type: isImageGroup ? 'res' : 'video_res' }) }} style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, overflow: 'hidden' }}>
                        <span style={{ color: 'var(--app-foreground)', fontWeight: 400, flexShrink: 0 }}>
                          {t('canvas.generator.resolution_prefix', '精度: ')}
                        </span>
                        <span style={{ fontWeight: 500, color: 'var(--app-foreground)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {formatResolutionOptionLabel(item.resolution || (isImageGroup ? imageRes : videoQuality), standardSuffix)}
                        </span>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', marginLeft: 4, flexShrink: 0 }}>
                        <div style={{ padding: '2px', backgroundColor: 'var(--app-primary)', borderRadius: 4, display: 'flex', alignItems: 'center' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--app-primary-foreground)" strokeWidth="2.5"><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M9 21V9" /></svg>
                        </div>
                      </div>
                    </div>
                    {(isImageGroup ? isResDropdownOpen : isVideoResolutionDropdownOpen) && (
                      <div style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: 8, width: '100%', minWidth: 100, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2 }}>
                        {(isImageGroup ? allowedImageResolutions : allowedPanelVideoResolutions).map((opt: string) => (
                          <div
                            key={opt}
                            onClick={(e) => {
                              e.stopPropagation()
                              if (isImageGroup) {
                                const nextSelection = resolveImageModelSelection({
                                  config: currentConfig,
                                  currentResolution: item.resolution || imageRes,
                                  currentAspectRatio: item.aspect_ratio || imageRatio,
                                  nextResolution: opt,
                                })
                                const dims = getItemDims({ ...item, ...nextSelection })
                                updateItem(item.id, { ...nextSelection, width: dims.width, height: dims.height })
                              } else {
                                const dims = getItemDims({ ...item, resolution: opt })
                                updateItem(item.id, { resolution: opt, width: dims.width, height: dims.height })
                              }
                              setActiveDropdown(null)
                            }}
                            style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: 'var(--app-foreground)', backgroundColor: (item.resolution || (isImageGroup ? imageRes : videoQuality)) === opt ? 'var(--app-control-selected)' : 'transparent' }}
                            onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = (item.resolution || (isImageGroup ? imageRes : videoQuality)) === opt ? 'var(--app-control-selected)' : 'var(--app-control-hover)' }}
                            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = (item.resolution || (isImageGroup ? imageRes : videoQuality)) === opt ? 'var(--app-control-selected)' : 'transparent' }}
                          >
                            {formatResolutionOptionLabel(opt, standardSuffix)}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
                {!isImageGroup && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>{t('canvas.generator.duration_label', '时长设置')}</div>
                    <div style={{ position: 'relative' }}>
                      <div onClick={(e) => { e.stopPropagation(); setActiveDropdown(isDurationDropdownOpen ? null : { itemId: item.id, type: 'duration' }) }} style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, overflow: 'hidden' }}>
                          <span style={{ color: 'var(--app-foreground)', fontWeight: 400, flexShrink: 0 }}>{t('canvas.generator.duration_prefix', '时长: ')}</span>
                          <span style={{ fontWeight: 500, color: 'var(--app-foreground)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{item.duration || videoDuration}</span>
                        </div>
                      </div>
                      {isDurationDropdownOpen && (
                        <div onWheel={handleScrollableWheel} style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: 8, width: '100%', minWidth: 100, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 200, overflowY: 'auto' }}>
                          {allowedVideoDurations.map((opt: string) => (
                            <div key={opt} onClick={(e) => { e.stopPropagation(); updateItem(item.id, { duration: opt }); setActiveDropdown(null) }} style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: 'var(--app-foreground)', backgroundColor: (item.duration || videoDuration) === opt ? 'var(--app-control-selected)' : 'transparent' }}>
                              {opt}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
                {shouldShowRatioSelector && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--app-foreground-muted)' }}>{t('canvas.generator.ratio_label', '画布比例')}</div>
                    <div style={{ position: 'relative' }}>
                      <div onClick={(e) => { e.stopPropagation(); setActiveDropdown(isRatioDropdownOpen ? null : { itemId: item.id, type: 'ratio' }) }} style={{ height: 42, padding: '0 12px', borderRadius: 10, border: '1px solid var(--app-border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', fontSize: 14, backgroundColor: 'var(--app-control)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4, overflow: 'hidden' }}>
                          <span style={{ color: 'var(--app-foreground)', fontWeight: 400, flexShrink: 0 }}>{t('canvas.generator.ratio_prefix', '比例: ')}</span>
                          <span style={{ fontWeight: 500, color: 'var(--app-foreground)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {formatAspectRatioOptionLabelWithDimensions(item.aspect_ratio || (isImageGroup ? imageRatio : videoAspect), ratioHintLabels, getItemDims(item))}
                          </span>
                        </div>
                      </div>
                      {isRatioDropdownOpen && (
                        <div onWheel={handleScrollableWheel} style={{ position: 'absolute', bottom: '110%', left: 0, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: 8, width: '100%', minWidth: 120, zIndex: 1001, display: 'flex', flexDirection: 'column', gap: 2, maxHeight: 200, overflowY: 'auto' }}>
                          {(isImageGroup ? allowedImageRatios : allowedPanelVideoRatios).map((r: string) => (
                            <div key={r} onClick={(e) => { e.stopPropagation(); const dims = getItemDims({ ...item, aspect_ratio: r }); updateItem(item.id, { aspect_ratio: r, width: dims.width, height: dims.height }); setActiveDropdown(null) }} style={{ padding: '8px 12px', borderRadius: 8, cursor: 'pointer', fontSize: 13, color: 'var(--app-foreground)', backgroundColor: (item.aspect_ratio || (isImageGroup ? imageRatio : videoAspect)) === r ? 'var(--app-control-selected)' : 'transparent' }}>
                              {formatAspectRatioOptionLabelWithDimensions(r, ratioHintLabels, getItemDims({ ...item, aspect_ratio: r }))}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
      {item.type === 'image' && imageAnchoredImageDraft && imageAnchoredImageDraft.sourceImageItemId === item.id && selectedItems.includes(item.id) && selectedItems.length === 1 && imageAnchoredImageDraftItem && (
        <div style={{ position: 'absolute', top: actualHeight + (12 * 100 / zoom), left: actualWidth / 2, transform: `translateX(-50%) scale(${100 / zoom})`, transformOrigin: 'top center', zIndex: 2147483500 }}>
          <ImageAnchoredImagePanel draft={imageAnchoredImageDraft} availableImageModels={availableImageModels} isDark={isDark} t={t as any} amountCents={getItemAmountCents(imageAnchoredImageDraftItem)} referenceInputRef={anchoredImageReferenceInputRef} onUpdateDraft={updateImageAnchoredImageDraft} onPreviewImage={setPreviewImageUrl} onGenerate={handleGenerateAnchoredImage} onPickReferenceFromLibrary={() => openGeneratorAssetLibrary({ type: 'anchored-image', target: 'reference' })} onPickReferenceFromReferenceGallery={() => openGeneratorReferenceGallery({ type: 'anchored-image', target: 'reference' })} />
        </div>
      )}
      {item.type === 'image' && imageAnchoredVideoDraft && imageAnchoredVideoDraft.sourceImageItemId === item.id && selectedItems.includes(item.id) && selectedItems.length === 1 && imageAnchoredVideoDraftItem && imageAnchoredVideoCapability && (
        <div style={{ position: 'absolute', top: actualHeight + (12 * 100 / zoom), left: actualWidth / 2, transform: `translateX(-50%) scale(${100 / zoom})`, transformOrigin: 'top center', zIndex: 2147483500 }}>
          <ImageAnchoredVideoPanel draft={imageAnchoredVideoDraft} draftItem={imageAnchoredVideoDraftItem} capability={imageAnchoredVideoCapability} allowedDurations={imageAnchoredVideoAllowedDurations} availableVideoModels={availableVideoModels} isDark={isDark} t={t as any} amountCents={getItemAmountCents(imageAnchoredVideoDraftItem)} referenceInputRef={anchoredReferenceImageInputRef} firstFrameInputRef={anchoredFirstFrameImageInputRef} tailFrameInputRef={anchoredTailFrameImageInputRef} onUpdateDraft={updateImageAnchoredVideoDraft} onMoveSourcePlacement={handleMoveAnchoredVideoSourcePlacement} onPreviewImage={setPreviewImageUrl} onGenerate={handleGenerateAnchoredVideo} onPickReferenceFromLibrary={() => openGeneratorAssetLibrary({ type: 'anchored-video', target: 'reference' })} onPickFirstFrameFromLibrary={() => openGeneratorAssetLibrary({ type: 'anchored-video', target: 'first_frame' })} onPickTailFrameFromLibrary={() => openGeneratorAssetLibrary({ type: 'anchored-video', target: 'tail_frame' })} onPickReferenceFromReferenceGallery={() => openGeneratorReferenceGallery({ type: 'anchored-video', target: 'reference' })} onPickFirstFrameFromReferenceGallery={() => openGeneratorReferenceGallery({ type: 'anchored-video', target: 'first_frame' })} onPickTailFrameFromReferenceGallery={() => openGeneratorReferenceGallery({ type: 'anchored-video', target: 'tail_frame' })} showSourceDragHint />
        </div>
      )}
    </div>
  )
}, areMediaItemPropsEqual)

export { CanvasWorkspaceMediaRenderItemInner as CanvasWorkspaceMediaRenderItem }

