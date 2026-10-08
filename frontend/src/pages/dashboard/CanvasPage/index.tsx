import { useState, useRef, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { useTranslation } from 'react-i18next'

import { useIsDarkMode } from '@/hooks/useTheme'
import { useCanvasHistory } from '@/hooks/useCanvasHistory'
import { projectsApi } from '@/api/endpoints/projects'
import { agentApi } from '@/api/endpoints/agent'
import { useChatStore } from '@/store/canvasAgentStore'
import { useAuthStore } from '@/store/authStore'
import { validateUploadFileSize } from '@/utils/uploadLimits'

import { ChatSidebar } from './ChatSidebar'
import { AssetLibraryModal, type AssetLibrarySelectedAsset } from './AssetLibraryModal'
import { ReferenceGalleryPickerModal } from '../ReferenceGallery/ReferenceGalleryPickerModal'
import type {
  EcommerceReferenceImageRequestOptions,
  EcommerceReferenceImageSource,
} from '@/components/agent/EcommerceInteractionCard'
import {
  getVideoGeneratorCapability,
  normalizeReferenceImages,
  shouldDisableVideoAspectRatio,
} from './generatorCapabilities'
import { getResolvedImageModelCapability } from './imageModelConfig'
import { isHoverOnlyFailedVideoTask } from './imageAnchoredVideo'
import {
  isMarkModifierPressed,
  isTransientMarkModeActive,
} from './gestureMode'
import { CROP_PRESET_GROUPS } from './cropUtils'
import {
  clampCanvasStackZIndex,
  shouldShowGeneratorControlPanel,
  shouldShowImageToolbar,
} from './imageActions'
import { MARK_CURSOR } from './constants'
import { createInitialAgentGeneratedMediaState } from './agentGeneratedMedia'
import { getCanvasToolDefinitions } from './canvasToolDefinitions'
import { useCanvasAgentUpdates } from './hooks/useCanvasAgentUpdates'
import { useAssetLibraryImport } from './hooks/useAssetLibraryImport'
import { useGeneratorControls } from './hooks/useGeneratorControls'
import { useCanvasController } from './hooks/useCanvasController'
import { CanvasTopBar } from './components/CanvasTopBar'
import { CanvasLayerPanel } from './components/CanvasLayerPanel'
import { CanvasWorkspace } from './components/CanvasWorkspace'
import { CanvasContextMenu } from './components/CanvasContextMenu'
import { CanvasStaleOverlay } from './components/CanvasStaleOverlay'
import { ImagePreviewOverlay } from './components/ImagePreviewOverlay'
import { ImageEraseOverlay } from './components/ImageEraseOverlay'
import { SpatialAngleOverlay } from './components/SpatialAngleOverlay'
import {
  formatAspectRatioOptionLabelWithDimensions,
  formatDimensionLabel,
  formatResolutionOptionLabel,
} from './generatorOptionLabels'
import {
  getMediaDisplayInitializationUpdate,
  getMediaSelectionOverlayMetrics,
} from './mediaSelectionResize'
import { createCanvasWheelCameraScheduler } from './canvasWheelCamera'
import { findEmptyPosition } from './canvasLayout'
import {
  getCanvasSelectionBorder,
  getCanvasSelectionContainerOverflow,
  getCanvasSelectionHandleAppearance,
} from './selectionStyles'
import {
  TEXT_REDRAW_PANEL_TOKENS,
  getTextRedrawExtractingBadgeStyle,
} from './textRedrawUi'

type GeneratorAssetLibraryContext =
  | { type: 'canvas-item'; itemId: string; target: 'reference' | 'first_frame' | 'tail_frame' }
  | { type: 'anchored-image'; target: 'reference' }
  | { type: 'anchored-video'; target: 'reference' | 'first_frame' | 'tail_frame' }
  | { type: 'chat-attachment' }
  | { type: 'ecommerce-reference'; onSelect: (urls: string[]) => void; maxSelection?: number }

// ---------- component ----------
export function CanvasPage({ isGuest = false, guestProject = null }: { isGuest?: boolean, guestProject?: any }) {
  const { t } = useTranslation()
  const isDark = useIsDarkMode()
  const navigate = useNavigate()
  const { user, deployType } = useAuthStore()
  const ratioHintLabels = {
    square: t('canvas.generator.ratio_hint_square', 'Square'),
    landscape: t('canvas.generator.ratio_hint_landscape', 'Landscape'),
    portrait: t('canvas.generator.ratio_hint_portrait', 'Portrait'),
  }
  const standardSuffix = t('canvas.generator.standard_suffix', 'Standard')
  const { tools, selectTools, addTools } = getCanvasToolDefinitions(t)
  const { id } = useParams<{ id: string }>()
  const canvasRef = useRef<HTMLDivElement>(null)
  const canvasContentRef = useRef<HTMLDivElement>(null)
  const chatAppendMentionNonceRef = useRef(0)
  const chatAttachmentSelectionNonceRef = useRef(0)

  const [title, setTitle] = useState('Untitled')
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [editingTitleValue, setEditingTitleValue] = useState('')
  const [chatAppendMentionRequest, setChatAppendMentionRequest] = useState<{ itemId: string, nonce: number } | null>(null)
  const [chatAttachmentSelection, setChatAttachmentSelection] = useState<{ assets: AssetLibrarySelectedAsset[], nonce: number } | null>(null)
  const [generatorAssetLibraryContext, setGeneratorAssetLibraryContext] = useState<GeneratorAssetLibraryContext | null>(null)
  const [isReferenceGalleryPickerOpen, setIsReferenceGalleryPickerOpen] = useState(false)
  const titleInputRef = useRef<HTMLInputElement>(null)
  const {
    canvasItems, marks,
    updateCanvasItems, updateMarks,
    beginTransaction, commitTransaction,
    undo, redo,
    initializeState,
  } = useCanvasHistory({ maxHistory: 50 })
  const [canvasItemsLoaded, setCanvasItemsLoaded] = useState(false)
  const [hasInitialJumped, setHasInitialJumped] = useState(false)

  const setOnCanvasUpdate = useChatStore(s => s.setOnCanvasUpdate)
  const createAgentConversation = useChatStore(s => s.createConversation)
  const agentGeneratedMediaRef = useRef(createInitialAgentGeneratedMediaState())

  const {
    imageModel,
    imageProvider,
    videoModel,
    videoProvider,
    availableImageModels,
    availableVideoModels,
    imageRes,
    imageRatio,
    videoAspect,
    videoDuration,
    videoQuality,
    loadPersistedGeneratorMeta,
    buildCanvasMeta,
    getItemDims,
    getItemAmountCents,
    withReferenceImages,
    getItemReferenceImages,
    getResolvedImageCapability,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
  } = useGeneratorControls({
    canvasItemsLoaded,
    updateCanvasItems,
  })



  const {
    activeTool,
    setActiveTool,
    markModifierState,
    hoveredMarkableImageId,
    setHoveredMarkableImageId,
    isSelectMenuOpen,
    setIsSelectMenuOpen,
    hoveredSelectTool,
    setHoveredSelectTool,
    isAddMenuOpen,
    setIsAddMenuOpen,
    hoveredAddTool,
    setHoveredAddTool,
    isLayerPanelOpen,
    setIsLayerPanelOpen,
    selectedItems,
    setSelectedItems,
    contextMenu,
    setContextMenu,
    activeContextMenuItem,
    setActiveContextMenuItem,
    isAssetLibraryOpen,
    setIsAssetLibraryOpen,
    deletedAgentMediaKeys,
    imageDetailItemId,
    imageDetailPanelPosition,
    textEditingItemId,
    textToolbarState,
    setTextToolbarState,
    brushDraft,
    brushToolState,
    setBrushToolState,
    brushToolbarState,
    setBrushToolbarState,
    textRedrawState,
    textRedrawExtractingItemIds,
    textRedrawPanelPosition,
    imageEraseSession,
    imageErasePreviewRect,
    cropState,
    setCropState,
    cropDragState,
    cropExpandedGroups,
    setCropExpandedGroups,
    activeDropdown,
    setActiveDropdown,
    multiSelectToolsOpen,
    setMultiSelectToolsOpen,
    editingNameId,
    setEditingNameId,
    layerDragId,
    setLayerDragId,
    layerDropTarget,
    setLayerDropTarget,
    clipboardItems,
    clipboardSource,
    canPasteExternalClipboard,
    zoom,
    offset,
    isChatSidebarOpen,
    setIsChatSidebarOpen,
    zoomRef,
    offsetRef,
    canvasCamera,
    isPanning,
    isWheeling,
    setIsWheeling,
    selectionBox,
    setActiveGuides,
    setResizingGroupId,
    setMediaResizeState,
    setBrushResizeState,
    imageInputRef,
    videoInputRef,
    referenceImageInputRef,
    firstFrameImageInputRef,
    tailFrameImageInputRef,
    anchoredImageReferenceInputRef,
    anchoredReferenceImageInputRef,
    anchoredFirstFrameImageInputRef,
    anchoredTailFrameImageInputRef,
    previewImageUrl,
    setPreviewImageUrl,
    movingItemIdsRef,
    resizingHandle,
    dragItemStart,
    resizingStart,
    saveCanvasItems,
    applyAgentCanvasItems,
    isCanvasStale,
    isRefreshingCanvas,
    refreshCanvasFromServer,
    syncCanvasRevisionFromAgentPatch,
    currentSelectionItems,
    selectionContextMenuItems,
    firstSelectedItem,
    cropCommitMode,
    handleFocusItem,
    addMark,
    removeMark,
    updateMarkLabel,
    clearMarks,
    zoomIn,
    zoomOut,
    resetZoom,
    handleMouseDown,
    handleItemMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleCanvasClick,
    handlePlaceTextAtPoint,
    handleOpenImageDetails,
    handleCloseImageDetails,
    handleDeleteCanvasImage,
    handleContextMenuAction,
    handleBulkExport,
    handleMergeLayers,
    updateItem,
    handleStartTextEdit,
    handleCancelTextEdit,
    handleCommitTextEdit,
    updateTextStyle,
    updateBrushItem,
    handleOpenCutout,
    handleOpenImageErase,
    handleOpenHDUpscale,
    handleCancelImageErase,
    handleSubmitImageErase,
    handleUndoImageErase,
    handleRedoImageErase,
    handleChangeImageEraseMode,
    handleChangeImageEraseBrushSize,
    handleImageErasePointerDown,
    handleImageErasePointerMove,
    handleImageErasePointerUp,
    handleOpenTextRedraw,
    handleChangeTextRedrawSegment,
    handleCancelTextRedraw,
    handleSubmitTextRedraw,
    handleOpenCropPanel,
    handleSelectCropPreset,
    handleCropDimensionChange,
    handleCropHandleMouseDown,
    handleCropMoveMouseDown,
    handleApplyCrop,
    handleUploadImage,
    handleCanvasPaste,
    handleUploadVideo,
    handleUploadReferenceImage,
    handleUploadFirstFrameImage,
    handleUploadTailFrameImage,
    handleUploadAnchoredImageReference,
    openImageAnchoredImageDraft,
    updateImageAnchoredImageDraft,
    handleGenerateAnchoredImage,
    openImageAnchoredVideoDraft,
    updateImageAnchoredVideoDraft,
    handleMoveAnchoredVideoSourcePlacement,
    handleUploadAnchoredReferenceImage,
    handleUploadAnchoredFirstFrameImage,
    handleUploadAnchoredTailFrameImage,
    handleGenerateAnchoredVideo,
    applyAssetLibraryToCanvasItem,
    applyAssetLibraryToAnchoredImageDraft,
    applyAssetLibraryToAnchoredVideoDraft,
    handleFitView,
    selectAndCenterCanvasItem,
    loadProjectAssets,
    handleAlign,
    handleSpacing,
    handleAutoArrange,
    handleCreateGroup,
    handleUngroup,
    setGroupBackgroundColor,
    handleLayerDrop,
    handleJumpToItem,
    handleGenerateImage,
    handleGenerateVideo,
    handleRetryFailedGeneration,
    addNewGenerator,
    renderSelectionHandles,
    interactionPreview,
    imageEraseCanvasRef,
    projectedGuides,
    imageDetailItem,
    imageDetailData,
    imageAnchoredImageDraft,
    imageAnchoredImageDraftItem,
    imageAnchoredVideoDraft,
    imageAnchoredVideoDraftItem,
    imageAnchoredVideoCapability,
    imageAnchoredVideoAllowedDurations,
    spatialAngleSession,
    handleOpenSpatialAngle,
    handleCancelSpatialAngle,
    handleSubmitSpatialAngle,
    selectedSingleItem,
    selectedSingleItemRect,
    selectedSingleItemCanvasRect,
    selectedSingleItemViewportWidth,
    selectedSingleItemWidth,
    selectedSingleItemHeight,
    selectedIsImageGroup,
    selectedIsGenerator,
    shouldRenderSelectedMeta,
  } = useCanvasController({
    t,
    isDark,
    navigate,
    user,
    deployType,
    setTitle,
    title,
    isEditingTitle,
    editingTitleValue,
    setEditingTitleValue,
    setIsEditingTitle,
    titleInputRef,
    id,
    isGuest,
    guestProject,
    canvasRef,
    canvasContentRef,
    canvasItems,
    marks,
    updateCanvasItems,
    updateMarks,
    beginTransaction,
    commitTransaction,
    initializeState,
    canvasItemsLoaded,
    setCanvasItemsLoaded,
    hasInitialJumped,
    setHasInitialJumped,
    setOnCanvasUpdate,
    imageModel,
    imageProvider,
    videoModel,
    videoProvider,
    availableImageModels,
    availableVideoModels,
    imageRes,
    imageRatio,
    videoAspect,
    videoDuration,
    videoQuality,
    buildCanvasMeta,
    loadPersistedGeneratorMeta,
    getItemDims,
    getItemAmountCents,
    withReferenceImages,
    getItemReferenceImages,
    getResolvedImageCapability,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    undo,
    redo,
    tools,
    selectTools,
    addTools,
  })

  useCanvasAgentUpdates({
    canvasItems,
    imageRatio,
    videoAspect,
    imageProvider,
    videoProvider,
    imageModel,
    videoModel,
    availableImageModels,
    availableVideoModels,
    imageRes,
    videoQuality,
    zoomRef,
    offsetRef,
    setOnCanvasUpdate,
    updateCanvasItems,
    applyAgentCanvasItems,
    syncCanvasRevisionFromAgentPatch,
    selectAndCenterCanvasItem,
    agentGeneratedMediaRef,
    deletedAgentMediaKeys,
  })

  const handleStartEditingTitle = () => {
    setEditingTitleValue(title)
    setIsEditingTitle(true)
  }

  const handleCommitTitle = () => {
    const newTitle = editingTitleValue.trim()
    if (newTitle && newTitle !== title) {
      setTitle(newTitle)
      if (id) {
        projectsApi.update(Number(id), { title: newTitle }).catch(() => {
          toast.error(t('canvas.project_name_update_failed'))
        })
      }
    } else {
      setEditingTitleValue(title)
    }
    setIsEditingTitle(false)
  }

  const imageEraseOverlayRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const el = imageEraseOverlayRef.current
    if (!el) return
    const scheduler = createCanvasWheelCameraScheduler({
      camera: canvasCamera,
      zoomRef,
      offsetRef,
      getViewportElement: () => canvasRef.current,
      setIsWheeling,
    })
    const handler = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey) {
        e.preventDefault()
        scheduler.handleWheel(e)
      }
    }
    el.addEventListener('wheel', handler, { passive: false })
    return () => {
      scheduler.cancel()
      el.removeEventListener('wheel', handler)
    }
  }, [imageEraseSession, canvasRef, zoomRef, offsetRef, canvasCamera, setIsWheeling])

  const handleAssetLibraryImport = useAssetLibraryImport({
    canvasItems,
    zoomRef,
    offsetRef,
    updateCanvasItems,
    saveCanvasItems,
    setSelectedItems,
    setActiveTool,
    handleJumpToItem,
    t,
    findPosition: findEmptyPosition,
  })

  const openGeneratorAssetLibrary = (context: GeneratorAssetLibraryContext) => {
    setGeneratorAssetLibraryContext(context)
    setIsAssetLibraryOpen(true)
  }

  const openGeneratorReferenceGallery = (context: GeneratorAssetLibraryContext) => {
    setGeneratorAssetLibraryContext(context)
    setIsReferenceGalleryPickerOpen(true)
  }

  const handleRequestEcommerceReferenceImages = (
    source: EcommerceReferenceImageSource,
    onSelect: (urls: string[]) => void,
    options?: EcommerceReferenceImageRequestOptions,
  ) => {
    const context: GeneratorAssetLibraryContext = {
      type: 'ecommerce-reference',
      onSelect,
      maxSelection: options?.maxSelection,
    }
    if (source === 'reference_gallery') {
      openGeneratorReferenceGallery(context)
      return
    }
    openGeneratorAssetLibrary(context)
  }

  const handleUploadEcommerceReferenceImage = async (file: File): Promise<string | null> => {
    if (!validateUploadFileSize(file, 'harness_attachment_max_bytes', t)) {
      return null
    }
    let convId = useChatStore.getState().conversationId
    if (!convId && id) {
      await createAgentConversation(Number(id))
      convId = useChatStore.getState().conversationId
    }
    if (!convId) {
      toast.error(t('canvas.chat.upload_failed', '上传失败'))
      return null
    }
    const response = await agentApi.uploadHarnessAttachment(String(convId), file)
    return response.data.url || null
  }

  const handleAssetLibraryOpenChange = (open: boolean) => {
    setIsAssetLibraryOpen(open)
    if (!open) {
      setGeneratorAssetLibraryContext(null)
    }
  }

  const handleReferenceGalleryPickerOpenChange = (open: boolean) => {
    setIsReferenceGalleryPickerOpen(open)
    if (!open) {
      setGeneratorAssetLibraryContext(null)
    }
  }

  const handleGeneratorAssetLibrarySelect = (assets: AssetLibrarySelectedAsset[]) => {
    if (!generatorAssetLibraryContext || assets.length === 0) return

    if (generatorAssetLibraryContext.type === 'chat-attachment') {
      chatAttachmentSelectionNonceRef.current += 1
      setChatAttachmentSelection({
        assets,
        nonce: chatAttachmentSelectionNonceRef.current,
      })
      return
    }

    if (generatorAssetLibraryContext.type === 'ecommerce-reference') {
      generatorAssetLibraryContext.onSelect(assets.map((asset) => asset.url).filter(Boolean))
      setGeneratorAssetLibraryContext(null)
      return
    }

    if (generatorAssetLibraryContext.type === 'canvas-item') {
      applyAssetLibraryToCanvasItem(
        generatorAssetLibraryContext.itemId,
        generatorAssetLibraryContext.target,
        assets,
      )
      return
    }

    if (generatorAssetLibraryContext.type === 'anchored-image') {
      applyAssetLibraryToAnchoredImageDraft(assets)
      return
    }

    applyAssetLibraryToAnchoredVideoDraft(generatorAssetLibraryContext.target, assets)
  }

  const generatorAssetLibraryConfig = (() => {
    if (!generatorAssetLibraryContext) return null

    if (generatorAssetLibraryContext.type === 'chat-attachment') {
      return { selectionMode: 'multiple' as const }
    }

    if (generatorAssetLibraryContext.type === 'ecommerce-reference') {
      return {
        selectionMode: 'multiple' as const,
        maxSelection: generatorAssetLibraryContext.maxSelection,
      }
    }

    if (generatorAssetLibraryContext.type === 'canvas-item') {
      const item = canvasItems.find((canvasItem) => canvasItem.id === generatorAssetLibraryContext.itemId)
      if (!item) return null
      if (generatorAssetLibraryContext.target !== 'reference') {
        return { selectionMode: 'single' as const, maxSelection: 1 }
      }
      const currentReferences = getItemReferenceImages(item)
      const maxReferenceImages = item.type === 'image_generator'
        ? getResolvedImageCapability(item).maxReferenceImages
        : getResolvedVideoCapability(item).maxReferenceImages
      return {
        selectionMode: 'multiple' as const,
        maxSelection: maxReferenceImages > 0 ? Math.max(0, maxReferenceImages - currentReferences.length) : 0,
      }
    }

    if (generatorAssetLibraryContext.type === 'anchored-image') {
      if (!imageAnchoredImageDraft) return null
      const maxReferenceImages = getResolvedImageModelCapability(
        availableImageModels,
        imageAnchoredImageDraft.model_name,
        imageAnchoredImageDraft.provider_code,
      ).maxReferenceImages
      const totalReferenceCount = imageAnchoredImageDraft.reference_images.length + 1
      return {
        selectionMode: 'multiple' as const,
        maxSelection: maxReferenceImages > 0 ? Math.max(0, maxReferenceImages - totalReferenceCount) : 0,
      }
    }

    if (!imageAnchoredVideoDraft || !imageAnchoredVideoCapability) return null
    if (generatorAssetLibraryContext.target !== 'reference') {
      return { selectionMode: 'single' as const, maxSelection: 1 }
    }
    const totalReferenceCount = imageAnchoredVideoDraft.reference_images.length + (imageAnchoredVideoDraft.sourcePlacement === 'reference' ? 1 : 0)
    return {
      selectionMode: 'multiple' as const,
      maxSelection: imageAnchoredVideoCapability.maxReferenceImages > 0
        ? Math.max(0, imageAnchoredVideoCapability.maxReferenceImages - totalReferenceCount)
        : 0,
    }
  })()

  const handleAppendImageMentionToChat = (itemId: string) => {
    chatAppendMentionNonceRef.current += 1
    setIsChatSidebarOpen(true)
    setChatAppendMentionRequest({
      itemId,
      nonce: chatAppendMentionNonceRef.current,
    })
  }

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        display: 'flex',
        flexDirection: 'column',
        backgroundColor: 'var(--app-bg)',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* Hidden file inputs */}
      <input ref={imageInputRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={handleUploadImage} />
      <input ref={videoInputRef} type="file" accept="video/*" style={{ display: 'none' }} onChange={handleUploadVideo} />
      <input ref={referenceImageInputRef} type="file" accept="image/*" multiple={Boolean(firstSelectedItem && (
        firstSelectedItem.type === 'image_generator'
          ? getResolvedImageCapability(firstSelectedItem).maxReferenceImages > 1
          : getResolvedVideoCapability(firstSelectedItem).maxReferenceImages > 1
      ))} style={{ display: 'none' }} onChange={(e) => {
        if (firstSelectedItem) handleUploadReferenceImage(e, firstSelectedItem.id)
      }} />
      <input ref={firstFrameImageInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => {
        if (firstSelectedItem) handleUploadFirstFrameImage(e, firstSelectedItem.id)
      }} />
      <input ref={tailFrameImageInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={(e) => {
        if (firstSelectedItem) handleUploadTailFrameImage(e, firstSelectedItem.id)
      }} />
      <input
        ref={anchoredImageReferenceInputRef}
        type="file"
        accept="image/*"
        multiple={Boolean(imageAnchoredImageDraftItem && getResolvedImageCapability(imageAnchoredImageDraftItem as any).maxReferenceImages > 2)}
        style={{ display: 'none' }}
        onChange={handleUploadAnchoredImageReference}
      />
      <input
        ref={anchoredReferenceImageInputRef}
        type="file"
        accept="image/*"
        multiple={Boolean(imageAnchoredVideoCapability && imageAnchoredVideoCapability.maxReferenceImages > 1)}
        style={{ display: 'none' }}
        onChange={handleUploadAnchoredReferenceImage}
      />
      <input
        ref={anchoredFirstFrameImageInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleUploadAnchoredFirstFrameImage}
      />
      <input
        ref={anchoredTailFrameImageInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleUploadAnchoredTailFrameImage}
      />

      <AssetLibraryModal
        open={isAssetLibraryOpen}
        onOpenChange={handleAssetLibraryOpenChange}
        isDark={isDark}
        onImport={handleAssetLibraryImport}
        mode={generatorAssetLibraryContext ? 'generator-pick' : 'canvas-import'}
        assetType="image"
        selectionMode={generatorAssetLibraryConfig?.selectionMode}
        maxSelection={generatorAssetLibraryConfig?.maxSelection}
        onSelect={handleGeneratorAssetLibrarySelect}
      />
      <ReferenceGalleryPickerModal
        open={isReferenceGalleryPickerOpen}
        onOpenChange={handleReferenceGalleryPickerOpenChange}
        isDark={isDark}
        selectionMode={generatorAssetLibraryConfig?.selectionMode}
        maxSelection={generatorAssetLibraryConfig?.maxSelection}
        onSelect={handleGeneratorAssetLibrarySelect}
      />

      {/* ===== Main Content Area ===== */}
      <div style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>

        <CanvasLayerPanel
          isOpen={isLayerPanelOpen}
          isDark={isDark}
          t={t}
          canvasItems={canvasItems}
          selectedItems={selectedItems}
          setSelectedItems={setSelectedItems}
          layerDragId={layerDragId}
          setLayerDragId={setLayerDragId}
          layerDropTarget={layerDropTarget}
          setLayerDropTarget={setLayerDropTarget}
          editingNameId={editingNameId}
          setEditingNameId={setEditingNameId}
          updateItem={updateItem}
          handleLayerDrop={handleLayerDrop}
          handleJumpToItem={handleJumpToItem}
          handleContextMenuAction={handleContextMenuAction}
          setContextMenu={setContextMenu}
          setActiveContextMenuItem={setActiveContextMenuItem}
          setIsLayerPanelOpen={setIsLayerPanelOpen}
        />

        {/* ===== Right Area (Canvas + Bottom Bar) ===== */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>

          <CanvasTopBar
            isDark={isDark}
            navigate={navigate}
            isEditingTitle={isEditingTitle}
            titleInputRef={titleInputRef}
            editingTitleValue={editingTitleValue}
            setEditingTitleValue={setEditingTitleValue}
            title={title}
            setIsEditingTitle={setIsEditingTitle}
            isChatSidebarOpen={isChatSidebarOpen}
            setIsChatSidebarOpen={setIsChatSidebarOpen}
            t={t}
            onStartEditingTitle={handleStartEditingTitle}
            onCommitTitle={handleCommitTitle}
          />

          <CanvasWorkspace
            projectId={id ? Number(id) : null}
            user={user}
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
            isCanvasStale={isCanvasStale}
            isRefreshingCanvas={isRefreshingCanvas}
            onRefreshCanvas={refreshCanvasFromServer}
            canvasRef={canvasRef}
            handleMouseDown={handleMouseDown}
            handleMouseMove={handleMouseMove}
            handleMouseUp={handleMouseUp}
            setContextMenu={setContextMenu}
            handleContextMenuAction={handleContextMenuAction}
            setSelectedItems={setSelectedItems}
            setActiveContextMenuItem={setActiveContextMenuItem}
            handleCanvasClick={handleCanvasClick}
            handleCanvasPaste={handleCanvasPaste}
            handlePlaceTextAtPoint={handlePlaceTextAtPoint}
            isPanning={isPanning}
            isWheeling={isWheeling}
            MARK_CURSOR={MARK_CURSOR}
            canvasContentRef={canvasContentRef}
            offset={offset}
            canvasCamera={canvasCamera}
            zoom={zoom}
            zoomIn={zoomIn}
            zoomOut={zoomOut}
            canvasItems={canvasItems}
            handleItemMouseDown={handleItemMouseDown}
            getCanvasSelectionBorder={getCanvasSelectionBorder}
            beginTransaction={beginTransaction}
            setActiveGuides={setActiveGuides}
            movingItemIdsRef={movingItemIdsRef}
            setResizingGroupId={setResizingGroupId}
            setMediaResizeState={setMediaResizeState}
            setBrushResizeState={setBrushResizeState}
            resizingHandle={resizingHandle}
            dragItemStart={dragItemStart}
            resizingStart={resizingStart}
            getCanvasSelectionHandleAppearance={getCanvasSelectionHandleAppearance}
            editingNameId={editingNameId}
            setEditingNameId={setEditingNameId}
            clampCanvasStackZIndex={clampCanvasStackZIndex}
            isHoverOnlyFailedVideoTask={isHoverOnlyFailedVideoTask}
            getItemDims={getItemDims}
            activeDropdown={activeDropdown}
            setActiveDropdown={setActiveDropdown}
            isTransientMarkModeActive={isTransientMarkModeActive}
            hoveredMarkableImageId={hoveredMarkableImageId}
            markModifierState={markModifierState}
            cropState={cropState}
            selectedItems={selectedItems}
            selectionBox={selectionBox}
            getMediaSelectionOverlayMetrics={getMediaSelectionOverlayMetrics}
            getResolvedImageCapability={getResolvedImageCapability}
            getResolvedVideoCapability={getResolvedVideoCapability}
            getResolvedVideoDurations={getResolvedVideoDurations}
            getItemReferenceImages={getItemReferenceImages}
            shouldDisableVideoAspectRatio={shouldDisableVideoAspectRatio}
            getVideoGeneratorCapability={getVideoGeneratorCapability}
            availableImageModels={availableImageModels}
            availableVideoModels={availableVideoModels}
            imageModel={imageModel}
            imageProvider={imageProvider}
            videoModel={videoModel}
            videoProvider={videoProvider}
            imageRes={imageRes}
            imageRatio={imageRatio}
            videoAspect={videoAspect}
            videoQuality={videoQuality}
            referenceImageInputRef={referenceImageInputRef}
            firstFrameImageInputRef={firstFrameImageInputRef}
            tailFrameImageInputRef={tailFrameImageInputRef}
            anchoredImageReferenceInputRef={anchoredImageReferenceInputRef}
            anchoredReferenceImageInputRef={anchoredReferenceImageInputRef}
            anchoredFirstFrameImageInputRef={anchoredFirstFrameImageInputRef}
            anchoredTailFrameImageInputRef={anchoredTailFrameImageInputRef}
            setHoveredMarkableImageId={setHoveredMarkableImageId}
            imageAnchoredImageDraft={imageAnchoredImageDraft}
            imageAnchoredVideoDraft={imageAnchoredVideoDraft}
            imageDetailItemId={imageDetailItemId}
            addMark={addMark}
            isMarkModifierPressed={isMarkModifierPressed}
            handleOpenHDUpscale={handleOpenHDUpscale}
            handleOpenCutout={handleOpenCutout}
            handleOpenImageErase={handleOpenImageErase}
            handleOpenTextRedraw={handleOpenTextRedraw}
            handleOpenCropPanel={handleOpenCropPanel}
            handleDeleteCanvasImage={handleDeleteCanvasImage}
            handleOpenImageDetails={handleOpenImageDetails}
            t={t}
            updateItem={updateItem}
            getCanvasSelectionContainerOverflow={getCanvasSelectionContainerOverflow}
            textRedrawState={textRedrawState}
            textRedrawExtractingItemIds={textRedrawExtractingItemIds}
            getTextRedrawExtractingBadgeStyle={getTextRedrawExtractingBadgeStyle}
            cropDragState={cropDragState}
            handleCropMoveMouseDown={handleCropMoveMouseDown}
            handleCropHandleMouseDown={handleCropHandleMouseDown}
            renderSelectionHandles={renderSelectionHandles}
            interactionPreview={interactionPreview}
            shouldShowGeneratorControlPanel={shouldShowGeneratorControlPanel}
            getMediaDisplayInitializationUpdate={getMediaDisplayInitializationUpdate}
            normalizeReferenceImages={normalizeReferenceImages}
            getImageGeneratorCapability={(modelName?: string) =>
              getResolvedImageModelCapability(availableImageModels, modelName)
            }
            withReferenceImages={withReferenceImages}
            videoDuration={videoDuration}
            ratioHintLabels={ratioHintLabels}
            standardSuffix={standardSuffix}
            formatResolutionOptionLabel={formatResolutionOptionLabel}
            formatAspectRatioOptionLabelWithDimensions={formatAspectRatioOptionLabelWithDimensions}
            formatDimensionLabel={formatDimensionLabel}
            shouldShowImageToolbar={shouldShowImageToolbar}
            imageAnchoredImageDraftItem={imageAnchoredImageDraftItem}
            updateImageAnchoredImageDraft={updateImageAnchoredImageDraft}
            openGeneratorAssetLibrary={openGeneratorAssetLibrary}
            openGeneratorReferenceGallery={openGeneratorReferenceGallery}
            openImageAnchoredImageDraft={openImageAnchoredImageDraft}
            handleGenerateAnchoredImage={handleGenerateAnchoredImage}
            imageAnchoredVideoDraftItem={imageAnchoredVideoDraftItem}
            imageAnchoredVideoCapability={imageAnchoredVideoCapability}
            imageAnchoredVideoAllowedDurations={imageAnchoredVideoAllowedDurations}
            updateImageAnchoredVideoDraft={updateImageAnchoredVideoDraft}
            openImageAnchoredVideoDraft={openImageAnchoredVideoDraft}
            handleMoveAnchoredVideoSourcePlacement={handleMoveAnchoredVideoSourcePlacement}
            setPreviewImageUrl={setPreviewImageUrl}
            handleGenerateAnchoredVideo={handleGenerateAnchoredVideo}
            getItemAmountCents={getItemAmountCents}
            handleGenerateImage={handleGenerateImage}
            handleGenerateVideo={handleGenerateVideo}
            handleRetryFailedGeneration={handleRetryFailedGeneration}
            cropCommitMode={cropCommitMode}
            setCropExpandedGroups={setCropExpandedGroups}
            cropExpandedGroups={cropExpandedGroups}
            CROP_PRESET_GROUPS={CROP_PRESET_GROUPS}
            handleSelectCropPreset={handleSelectCropPreset}
            handleCropDimensionChange={handleCropDimensionChange}
            setCropState={setCropState}
            handleApplyCrop={handleApplyCrop}
            marks={marks}
            multiSelectToolsOpen={multiSelectToolsOpen}
            setMultiSelectToolsOpen={setMultiSelectToolsOpen}
            clipboardItems={clipboardItems}
            clipboardSource={clipboardSource}
            handleCreateGroup={handleCreateGroup}
            handleMergeLayers={handleMergeLayers}
            handleUngroup={handleUngroup}
            setGroupBackgroundColor={setGroupBackgroundColor}
            handleAlign={handleAlign}
            handleAutoArrange={handleAutoArrange}
            handleSpacing={handleSpacing}
            handleBulkExport={handleBulkExport}
            isLayerPanelOpen={isLayerPanelOpen}
            setIsLayerPanelOpen={setIsLayerPanelOpen}
            loadProjectAssets={loadProjectAssets}
            imageDetailItem={imageDetailItem}
            imageDetailData={imageDetailData}
            imageDetailPanelPosition={imageDetailPanelPosition}
            handleCloseImageDetails={handleCloseImageDetails}
            TEXT_REDRAW_PANEL_TOKENS={TEXT_REDRAW_PANEL_TOKENS}
            textRedrawPanelPosition={textRedrawPanelPosition}
            handleChangeTextRedrawSegment={handleChangeTextRedrawSegment}
            handleCancelTextRedraw={handleCancelTextRedraw}
            handleSubmitTextRedraw={handleSubmitTextRedraw}
            handleOpenSpatialAngle={handleOpenSpatialAngle}
            selectedSingleItem={selectedSingleItem}
            selectedSingleItemRect={selectedSingleItemRect}
            selectedSingleItemCanvasRect={selectedSingleItemCanvasRect}
            textEditingItemId={textEditingItemId}
            textToolbarState={textToolbarState}
            setTextToolbarState={setTextToolbarState}
            brushDraft={brushDraft}
            brushToolState={brushToolState}
            setBrushToolState={setBrushToolState}
            brushToolbarState={brushToolbarState}
            setBrushToolbarState={setBrushToolbarState}
            handleStartTextEdit={handleStartTextEdit}
            handleCancelTextEdit={handleCancelTextEdit}
            handleCommitTextEdit={handleCommitTextEdit}
            updateTextStyle={updateTextStyle}
            updateBrushItem={updateBrushItem}
            selectedSingleItemViewportWidth={selectedSingleItemViewportWidth}
            shouldRenderSelectedMeta={shouldRenderSelectedMeta}
            selectedIsImageGroup={selectedIsImageGroup}
            selectedIsGenerator={selectedIsGenerator}
            selectedSingleItemWidth={selectedSingleItemWidth}
            selectedSingleItemHeight={selectedSingleItemHeight}
            projectedGuides={projectedGuides}
            handleAppendImageMentionToChat={handleAppendImageMentionToChat}
          />
        </div>
      </div>

      <CanvasContextMenu
        contextMenu={contextMenu}
        isDark={isDark}
        setContextMenu={setContextMenu}
        setActiveContextMenuItem={setActiveContextMenuItem}
        activeContextMenuItem={activeContextMenuItem}
        selectionContextMenuItems={selectionContextMenuItems}
        firstSelectedItem={firstSelectedItem}
        clipboardItems={clipboardItems}
        canPasteExternalClipboard={canPasteExternalClipboard}
        currentSelectionItems={currentSelectionItems}
        selectedItems={selectedItems}
        handleCreateGroup={handleCreateGroup}
        handleMergeLayers={handleMergeLayers}
        handleUngroup={handleUngroup}
        handleBulkExport={handleBulkExport}
        handleContextMenuAction={handleContextMenuAction}
        zoomIn={zoomIn}
        zoomOut={zoomOut}
        resetZoom={resetZoom}
        handleFitView={handleFitView}
        t={t}
      />

      {imageEraseSession && selectedSingleItemRect && (
        <div
          ref={imageEraseOverlayRef}
          style={{
            position: 'absolute',
            left: selectedSingleItemRect.left,
            top: selectedSingleItemRect.top,
            width: selectedSingleItemRect.width,
            height: selectedSingleItemRect.height,
            zIndex: 2147483450,
            pointerEvents: 'auto',
          }}
          onPointerDown={(e) => {
            if (e.button === 1 || e.button === 2) return // allow middle click pan & right click context menu
            e.stopPropagation()
            handleImageErasePointerDown(e)
          }}
          onPointerMove={(e) => {
            if ((e.buttons & 4) || (e.buttons & 2)) return // allow middle/right click drag
            e.stopPropagation()
            handleImageErasePointerMove(e)
          }}
          onPointerUp={(e) => {
            e.stopPropagation()
            handleImageErasePointerUp(e)
          }}
          onPointerLeave={(e) => {
            e.stopPropagation()
            handleImageErasePointerUp(e)
          }}
        >
          <ImageEraseOverlay
            session={imageEraseSession}
            tool={imageEraseSession.tool}
            isDark={isDark}
            onCancel={handleCancelImageErase}
            onConfirm={handleSubmitImageErase}
            onUndo={handleUndoImageErase}
            onRedo={handleRedoImageErase}
            onChangeMode={handleChangeImageEraseMode}
            onChangeBrushSize={handleChangeImageEraseBrushSize}
            canvasRef={imageEraseCanvasRef}
            previewRect={imageErasePreviewRect}
          />
        </div>
      )}

      {/* Spatial Angle Base Rendering */}
      {spatialAngleSession && selectedSingleItemRect && (
        <div
          style={{
            position: 'absolute',
            zIndex: 1000,
            left: selectedSingleItemRect.left + selectedSingleItemRect.width + 16,
            top: selectedSingleItemRect.top,
          }}
        >
          <SpatialAngleOverlay
            session={spatialAngleSession}
            isDark={isDark}
            onCancel={handleCancelSpatialAngle}
            onConfirm={(x, y, scale) => handleSubmitSpatialAngle({ x, y, scale })}
          />
        </div>
      )}

      <ImagePreviewOverlay
        previewImageUrl={previewImageUrl}
        setPreviewImageUrl={setPreviewImageUrl}
      />
      {/* ===== Chat Sidebar ===== */}
      <ChatSidebar
        isOpen={isChatSidebarOpen}
        onClose={() => setIsChatSidebarOpen(false)}
        projectId={Number(id)}
        canvasItems={canvasItems}
        appendMentionRequest={chatAppendMentionRequest}
        deletedAgentMediaKeys={deletedAgentMediaKeys}
        canvasItemsLoaded={canvasItemsLoaded}
        onFocusItem={handleFocusItem}
        marks={marks}
        onRemoveMark={removeMark}
        onUpdateMarkLabel={updateMarkLabel}
        onClearMarks={clearMarks}
        onOpenAttachmentLibrary={() => openGeneratorAssetLibrary({ type: 'chat-attachment' })}
        onOpenReferenceGallery={() => openGeneratorReferenceGallery({ type: 'chat-attachment' })}
        onRequestEcommerceReferenceImages={handleRequestEcommerceReferenceImages}
        onUploadEcommerceReferenceImage={handleUploadEcommerceReferenceImage}
        assetLibrarySelection={chatAttachmentSelection}
        pauseThinkingAnimation={isPanning || isWheeling}
      />
      {isCanvasStale && (
        <CanvasStaleOverlay
          isDark={isDark}
          isRefreshingCanvas={isRefreshingCanvas}
          onRefreshCanvas={refreshCanvasFromServer}
          t={t}
        />
      )}
    </div >
  )
}



