// @ts-nocheck
import { CanvasBrushToolPanel } from './CanvasBrushToolPanel'
import { CanvasBrushToolbar } from './CanvasBrushToolbar'
import { CanvasLeftToolbar } from './CanvasLeftToolbar'
import { CanvasTextToolbar } from './CanvasTextToolbar'
import { CanvasWorkspaceBottomBar } from './CanvasWorkspaceBottomBar'
import { CanvasWorkspaceCanvasArea } from './CanvasWorkspaceCanvasArea'

export function CanvasWorkspace(props: any) {
  const {
    isGuest,
    isDark,
    tools,
    selectTools,
    addTools,
    activeTool,
    setActiveTool,
    isSelectMenuOpen,
    setIsSelectMenuOpen,
    hoveredSelectTool,
    setHoveredSelectTool,
    isAddMenuOpen,
    setIsAddMenuOpen,
    hoveredAddTool,
    setHoveredAddTool,
    addNewGenerator,
    imageInputRef,
    videoInputRef,
    setIsAssetLibraryOpen,
    canvasRef,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    setContextMenu,
    setSelectedItems,
    setActiveContextMenuItem,
    handleCanvasClick,
    handlePlaceTextAtPoint,
    isPanning,
    isWheeling,
    MARK_CURSOR,
    canvasContentRef,
    offset,
    zoom,
    zoomIn,
    zoomOut,
    canvasItems,
    handleItemMouseDown,
    getCanvasSelectionBorder,
    beginTransaction,
    setActiveGuides,
    movingItemIdsRef,
    setResizingGroupId,
    setMediaResizeState,
    setBrushResizeState,
    resizingHandle,
    dragItemStart,
    resizingStart,
    getCanvasSelectionHandleAppearance,
    editingNameId,
    setEditingNameId,
    clampCanvasStackZIndex,
    isHoverOnlyFailedVideoTask,
    getItemDims,
    activeDropdown,
    setActiveDropdown,
    isTransientMarkModeActive,
    hoveredMarkableImageId,
    markModifierState,
    cropState,
    selectedItems,
    selectionBox,
    getMediaSelectionOverlayMetrics,
    getResolvedImageCapability,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    getItemReferenceImages,
    shouldDisableVideoAspectRatio,
    getVideoGeneratorCapability,
    availableImageModels,
    availableVideoModels,
    imageModel,
    videoModel,
    imageRes,
    imageRatio,
    videoAspect,
    videoQuality,
    referenceImageInputRef,
    firstFrameImageInputRef,
    tailFrameImageInputRef,
    anchoredImageReferenceInputRef,
    anchoredReferenceImageInputRef,
    anchoredFirstFrameImageInputRef,
    anchoredTailFrameImageInputRef,
    setHoveredMarkableImageId,
    imageAnchoredImageDraft,
    imageAnchoredVideoDraft,
    imageDetailItemId,
    addMark,
    isMarkModifierPressed,
    handleOpenHDUpscale,
    handleOpenCutout,
    handleOpenImageErase,
    handleOpenTextRedraw,
    handleOpenSpatialAngle,
    handleOpenCropPanel,
    handleDeleteCanvasImage,
    handleOpenImageDetails,
    t,
    updateItem,
    getCanvasSelectionContainerOverflow,
    textRedrawState,
    textRedrawExtractingItemIds,
    getTextRedrawExtractingBadgeStyle,
    cropDragState,
    handleCropMoveMouseDown,
    handleCropHandleMouseDown,
    renderSelectionHandles,
    shouldShowGeneratorControlPanel,
    getMediaDisplayInitializationUpdate,
    normalizeReferenceImages,
    getImageGeneratorCapability,
    withReferenceImages,
    videoDuration,
    ratioHintLabels,
    standardSuffix,
    formatResolutionOptionLabel,
    formatAspectRatioOptionLabelWithDimensions,
    formatDimensionLabel,
    shouldShowImageToolbar,
    imageAnchoredImageDraftItem,
    updateImageAnchoredImageDraft,
    openGeneratorAssetLibrary,
    openImageAnchoredImageDraft,
    handleGenerateAnchoredImage,
    imageAnchoredVideoDraftItem,
    imageAnchoredVideoCapability,
    imageAnchoredVideoAllowedDurations,
    updateImageAnchoredVideoDraft,
    openImageAnchoredVideoDraft,
    handleMoveAnchoredVideoSourcePlacement,
    setPreviewImageUrl,
    handleGenerateAnchoredVideo,
    getItemAmountCents,
    handleGenerateImage,
    handleGenerateVideo,
    handleRetryFailedGeneration,
    handleAppendImageMentionToChat,
    cropCommitMode,
    setCropExpandedGroups,
    cropExpandedGroups,
    CROP_PRESET_GROUPS,
    handleSelectCropPreset,
    handleCropDimensionChange,
    setCropState,
    handleApplyCrop,
    marks,
    multiSelectToolsOpen,
    setMultiSelectToolsOpen,
    handleCreateGroup,
    handleMergeLayers,
    handleUngroup,
    setGroupBackgroundColor,
    handleAlign,
    handleAutoArrange,
    handleSpacing,
    handleBulkExport,
    isLayerPanelOpen,
    setIsLayerPanelOpen,
    imageDetailItem,
    imageDetailData,
    imageDetailPanelPosition,
    handleCloseImageDetails,
    TEXT_REDRAW_PANEL_TOKENS,
    textRedrawPanelPosition,
    handleChangeTextRedrawSegment,
    handleCancelTextRedraw,
    handleSubmitTextRedraw,
    selectedSingleItem,
    selectedSingleItemRect,
    textEditingItemId,
    textToolbarState,
    setTextToolbarState,
    brushDraft,
    brushToolState,
    setBrushToolState,
    brushToolbarState,
    setBrushToolbarState,
    handleStartTextEdit,
    handleCancelTextEdit,
    handleCommitTextEdit,
    updateTextStyle,
    updateBrushItem,
    selectedSingleItemViewportWidth,
    shouldRenderSelectedMeta,
    selectedIsImageGroup,
    selectedIsGenerator,
    selectedSingleItemWidth,
    selectedSingleItemHeight,
    projectedGuides,
  } = props

  const textToolbarLabels = {
    fill: t('canvas.text_toolbar.fill', '濉厖'),
    stroke: t('canvas.text_toolbar.stroke', '鎻忚竟'),
    font: t('canvas.text_toolbar.font', '瀛椾綋'),
    variant: t('canvas.text_toolbar.variant', '瀛楅噸'),
    size: t('canvas.text_toolbar.size', '瀛楀彿'),
    align: t('canvas.text_toolbar.align', '瀵归綈'),
    more: t('canvas.text_toolbar.more', '鏇村'),
    vertical: t('canvas.text_toolbar.vertical', '绔栨帓'),
  }

  const brushToolbarLabels = {
    color: t('canvas.brush_toolbar.color', 'Color'),
    size: t('canvas.brush_toolbar.size', 'Size'),
    width: t('canvas.brush_toolbar.width', 'W'),
    height: t('canvas.brush_toolbar.height', 'H'),
  }

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
      <div style={{ flex: 1, display: 'flex', position: 'relative', overflow: 'hidden' }}>
        <CanvasLeftToolbar
          isGuest={isGuest}
          isDark={isDark}
          tools={tools}
          selectTools={selectTools}
          addTools={addTools}
          activeTool={activeTool}
          setActiveTool={setActiveTool}
          isSelectMenuOpen={isSelectMenuOpen}
          setIsSelectMenuOpen={setIsSelectMenuOpen}
          hoveredSelectTool={hoveredSelectTool}
          setHoveredSelectTool={setHoveredSelectTool}
          isAddMenuOpen={isAddMenuOpen}
          setIsAddMenuOpen={setIsAddMenuOpen}
          hoveredAddTool={hoveredAddTool}
          setHoveredAddTool={setHoveredAddTool}
          addNewGenerator={addNewGenerator}
          imageInputRef={imageInputRef}
          videoInputRef={videoInputRef}
          setIsAssetLibraryOpen={setIsAssetLibraryOpen}
        />
        <CanvasBrushToolPanel
          isDark={isDark}
          activeTool={activeTool}
          state={brushToolState}
          setState={setBrushToolState}
          brushToolIndex={tools.findIndex((tool: any) => tool.key === 'brush')}
          totalTools={tools.length}
        />

        <CanvasWorkspaceCanvasArea {...props} />
      </div>

      {selectedSingleItem?.type === 'text' && selectedSingleItemRect && (
        <CanvasTextToolbar
          item={selectedSingleItem}
          rect={selectedSingleItemRect}
          isDark={isDark}
          labels={textToolbarLabels}
          state={textToolbarState}
          setState={setTextToolbarState}
          updateTextStyle={updateTextStyle}
        />
      )}

      {selectedSingleItem?.type === 'brush_path' && selectedSingleItemRect && (
        <CanvasBrushToolbar
          item={selectedSingleItem}
          rect={selectedSingleItemRect}
          isDark={isDark}
          colorLabel={brushToolbarLabels.color}
          sizeLabel={brushToolbarLabels.size}
          widthLabel={brushToolbarLabels.width}
          heightLabel={brushToolbarLabels.height}
          state={brushToolbarState}
          setState={setBrushToolbarState}
          updateBrushItem={updateBrushItem}
        />
      )}

      <CanvasWorkspaceBottomBar
        isDark={isDark}
        isLayerPanelOpen={isLayerPanelOpen}
        setIsLayerPanelOpen={setIsLayerPanelOpen}
        zoomOut={zoomOut}
        zoom={zoom}
        zoomIn={zoomIn}
        t={t}
      />
    </div>
  )
}
