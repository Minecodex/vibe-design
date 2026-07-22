/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { assetsApi } from '@/api/endpoints/assets'
import { projectsApi } from '@/api/endpoints/projects'

import { buildCanvasSelectionMenuItems } from '../contextMenu'
import { normalizeAgentGeneratedMediaItems, normalizeDeletedAgentMediaKeys } from '../agentGeneratedMedia'
import { buildGuideCandidateBuckets, collectGuideCandidates } from '../alignmentGuides'
import { shouldShowSelectionMeta } from '../imageActions'
import { canPhotoshopEditSelection } from '../photoshopEdit'
import { normalizeReferenceImages } from '../generatorCapabilities'
import { type EditableTextRedrawSegment } from '../textRedraw'
import { type ModifierState } from '../gestureMode'
import { type BrushDraftState, type BrushResizeState, type BrushToolbarState, type BrushToolState, type CropHandle, type CropPanelState, type ImageEraseSession, type MediaResizeState } from '../types'
import { createTextCanvasItem, estimateTextCanvasSize, getVariantForFontFamily, normalizeTextCanvasItem } from '../textTypography'
import { useCanvasControllerMarks } from './useCanvasController.marks'
import { useCanvasControllerMedia } from './useCanvasController.media'
import { useCanvasControllerGenerators } from './useCanvasController.generators'
import { useCanvasControllerCrop } from './useCanvasController.crop'
import { useCanvasControllerArrangement } from './useCanvasController.arrangement'
import { useCanvasControllerViewport } from './useCanvasController.viewport'
import { useCanvasSaver } from './useCanvasSaver'
import { canReadSystemClipboardImages, hasClipboardImageInNavigator } from '../clipboardImage'
import { useCanvasCamera } from './useCanvasCamera'
import { useCanvasViewportActions } from './useCanvasViewportActions'
import {
  CANVAS_REVISION_BROADCAST_CHANNEL,
  applyAgentPatchCanvasRevisionSync,
  broadcastCanvasRevision,
  normalizeCanvasRevision,
} from '../canvasRevision'

function mergeServerCanvasMediaUrls(localItems: any[], serverItems?: any[]) {
  if (!Array.isArray(serverItems) || serverItems.length === 0) return localItems
  const serverUrlById = new Map(
    serverItems
      .filter((item: any) => item?.id && typeof item.url === 'string' && item.url)
      .map((item: any) => [String(item.id), item.url]),
  )
  if (serverUrlById.size === 0) return localItems

  let changed = false
  const nextItems = localItems.map((item: any) => {
    const serverUrl = serverUrlById.get(String(item?.id || ''))
    if (!serverUrl || item.url === serverUrl) return item
    changed = true
    return { ...item, url: serverUrl }
  })
  return changed ? nextItems : localItems
}

export function useCanvasController(args: any) {
  const {
    t,
    user,
    id,
    isGuest,
    guestProject,
    title,
    setTitle,
    canvasRef,
    canvasContentRef,
    canvasItems,
    updateCanvasItems,
    updateMarks,
    beginTransaction,
    commitTransaction,
    initializeState,
    canvasItemsLoaded,
    setCanvasItemsLoaded,
    hasInitialJumped,
    setHasInitialJumped,
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
    withReferenceImages,
    getItemReferenceImages,
    getResolvedImageCapability,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    undo,
    redo,
  } = args

  const [activeTool, setActiveTool] = useState('select')
  const [markModifierState, setMarkModifierState] = useState<ModifierState>({ altKey: false, metaKey: false, ctrlKey: false })
  const [hoveredMarkableImageId, setHoveredMarkableImageId] = useState<string | null>(null)
  const [isSelectMenuOpen, setIsSelectMenuOpen] = useState(false)
  const [hoveredSelectTool, setHoveredSelectTool] = useState<string | null>(null)
  const [isAddMenuOpen, setIsAddMenuOpen] = useState(false)
  const [hoveredAddTool, setHoveredAddTool] = useState<string | null>(null)
  const [isLayerPanelOpen, setIsLayerPanelOpen] = useState(false)
  const [selectedItems, setSelectedItems] = useState<string[]>([])
  const [contextMenu, setContextMenu] = useState<{ x: number, y: number, type?: 'item' | 'canvas' } | null>(null)
  const [activeContextMenuItem, setActiveContextMenuItem] = useState<string | null>(null)
  const [isAssetLibraryOpen, setIsAssetLibraryOpen] = useState(false)
  const [projectAssets, setProjectAssets] = useState<Record<number, any>>({})
  const [deletedAgentMediaKeys, setDeletedAgentMediaKeys] = useState<string[]>([])
  const [imageDetailItemId, setImageDetailItemId] = useState<string | null>(null)
  const [imageDetailPanelPosition, setImageDetailPanelPosition] = useState<any>(null)
  const [imageDetailSizeBytes, setImageDetailSizeBytes] = useState<number | null>(null)
  const [textEditingItemId, setTextEditingItemId] = useState<string | null>(null)
  const [textToolbarState, setTextToolbarState] = useState<{ activePanel: string | null }>({ activePanel: null })
  const [brushDraft, setBrushDraft] = useState<BrushDraftState | null>(null)
  const [brushToolState, setBrushToolState] = useState<BrushToolState>({ color: '#111111', size: 12, activePanel: null })
  const [brushToolbarState, setBrushToolbarState] = useState<BrushToolbarState>({ activePanel: null })
  const [brushResizeState, setBrushResizeState] = useState<BrushResizeState | null>(null)
  const [textRedrawState, setTextRedrawState] = useState<{
    itemId: string
    status: 'extracting' | 'editing'
    segments: EditableTextRedrawSegment[]
    isSubmitting: boolean
  } | null>(null)
  const [textRedrawExtractingItemIds, setTextRedrawExtractingItemIds] = useState<Set<string>>(new Set())
  const [textRedrawPanelPosition, setTextRedrawPanelPosition] = useState<any>(null)
  const [imageEraseSession, setImageEraseSession] = useState<ImageEraseSession | null>(null)
  const [imageErasePreviewRect, setImageErasePreviewRect] = useState<any>(null)
  const [cropState, setCropState] = useState<CropPanelState | null>(null)
  const [cropDragState, setCropDragState] = useState<{
    handle: CropHandle
    startClientX: number
    startClientY: number
    startRect: any
  } | null>(null)
  const [cropExpandedGroups, setCropExpandedGroups] = useState<Record<string, boolean>>({ general: true })
  const [activeDropdown, setActiveDropdown] = useState<any>(null)
  const [multiSelectToolsOpen, setMultiSelectToolsOpen] = useState<'align' | 'spacing' | 'bgcolor' | null>(null)
  const [editingNameId, setEditingNameId] = useState<string | null>(null)
  const [layerDragId, setLayerDragId] = useState<string | null>(null)
  const [layerDropTarget, setLayerDropTarget] = useState<any>(null)
  const [clipboardItems, setClipboardItems] = useState<any[]>([])
  const [clipboardSource, setClipboardSource] = useState<'internal' | 'external' | null>(null)
  const [hasExternalClipboardImage, setHasExternalClipboardImage] = useState(false)
  const [zoom, setZoom] = useState(100)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isChatSidebarOpen, setIsChatSidebarOpen] = useState(true)
  const [isPanning, setIsPanning] = useState(false)
  const [isWheeling, setIsWheeling] = useState(false)
  const [selectionBox, setSelectionBox] = useState<any>(null)
  const [draggingItemId, setDraggingItemId] = useState<string | null>(null)
  const [activeGuides, setActiveGuides] = useState<any[]>([])
  const [resizingGroupId, setResizingGroupId] = useState<string | null>(null)
  const [mediaResizeState, setMediaResizeState] = useState<MediaResizeState | null>(null)
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null)
  const [imageAnchoredImageDraft, setImageAnchoredImageDraft] = useState<any>(null)
  const [imageAnchoredVideoDraft, setImageAnchoredVideoDraft] = useState<any>(null)
  const [spatialAngleSession, setSpatialAngleSession] = useState<any>(null)
  const [canvasLoadFailed, setCanvasLoadFailed] = useState(false)
  const [isCanvasStale, setIsCanvasStale] = useState(false)
  const [isRefreshingCanvas, setIsRefreshingCanvas] = useState(false)

  const markIdCounter = useRef(0)
  const zoomRef = useRef(100)
  const offsetRef = useRef({ x: 0, y: 0 })
  const wheelTimeout = useRef<any>(null)
  const panStart = useRef({ x: 0, y: 0 })
  const offsetStart = useRef({ x: 0, y: 0 })
  const resizingHandle = useRef<string | null>(null)
  const resizingStart = useRef({ x: 0, y: 0, w: 0, h: 0, top: 0, left: 0 })
  const dragItemStart = useRef({ x: 0, y: 0 })
  const dragItemOriginals = useRef<Record<string, { x: number, y: number }>>({})
  const movingItemIdsRef = useRef<Set<string>>(new Set())
  const mousePosRef = useRef({ x: 0, y: 0 })
  const rafIdRef = useRef<number>(0)
  const guideCandidatesRef = useRef<any>([])
  const imageInputRef = useRef<HTMLInputElement>(null)
  const videoInputRef = useRef<HTMLInputElement>(null)
  const referenceImageInputRef = useRef<HTMLInputElement>(null)
  const firstFrameImageInputRef = useRef<HTMLInputElement>(null)
  const tailFrameImageInputRef = useRef<HTMLInputElement>(null)
  const anchoredImageReferenceInputRef = useRef<HTMLInputElement>(null)
  const anchoredReferenceImageInputRef = useRef<HTMLInputElement>(null)
  const anchoredFirstFrameImageInputRef = useRef<HTMLInputElement>(null)
  const anchoredTailFrameImageInputRef = useRef<HTMLInputElement>(null)
  const notifiedTasksRef = useRef<Set<string>>(new Set())
  const imageEraseCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageEraseBrushCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageEraseSessionRef = useRef<ImageEraseSession | null>(null)
  const imageErasePointerRef = useRef<any>(null)
  const imageEraseCheckerboardPatternRef = useRef<any>(null)
  const hasHydratedCanvasRef = useRef(false)
  const canvasDirtyEpochRef = useRef(0)
  const persistedCanvasDirtyEpochRef = useRef(0)
  const canvasRevisionRef = useRef(0)
  const isCanvasStaleRef = useRef(false)
  const canvasStaleRevisionRef = useRef<number | null>(null)
  const confirmedCanvasItemsRef = useRef<any[]>([])
  const latestCanvasItemsRef = useRef<any[]>([])
  const saveCanvasItemsRef = useRef<any>(null)
  const visibleSelectableItemsRef = useRef<any[]>([])

  const camera = useCanvasCamera({
    canvasContentRef,
    zoom,
    setZoom,
    zoomRef,
    offset,
    setOffset,
    offsetRef,
  })

  const itemIndex = useMemo(() => new Map(
    canvasItems.map((item: any) => [item.id, item]),
  ), [canvasItems])

  const groupChildrenIndex = useMemo(() => {
    const nextIndex = new Map<string, string[]>()
    canvasItems.forEach((item: any) => {
      if (!item.groupId) return
      const existing = nextIndex.get(item.groupId) || []
      existing.push(item.id)
      nextIndex.set(item.groupId, existing)
    })
    return nextIndex
  }, [canvasItems])

  useEffect(() => {
    latestCanvasItemsRef.current = canvasItems
    visibleSelectableItemsRef.current = canvasItems.filter((item: any) => !item.is_hidden && !item.is_locked)
  }, [canvasItems])

  const baseGuideCandidates = useMemo(() => collectGuideCandidates(
    canvasItems,
    new Set(),
    getItemDims,
  ), [canvasItems, getItemDims])
  const baseGuideCandidateBuckets = useMemo(
    () => buildGuideCandidateBuckets(baseGuideCandidates),
    [baseGuideCandidates],
  )

  const markCanvasAsEdited = useCallback(() => {
    if (!hasHydratedCanvasRef.current) return
    if (isCanvasStaleRef.current) return
    canvasDirtyEpochRef.current += 1
  }, [])

  const trackedUpdateCanvasItems = useCallback((updater: any, options?: any) => {
    if (isCanvasStaleRef.current) return
    markCanvasAsEdited()
    updateCanvasItems(updater, options)
  }, [markCanvasAsEdited, updateCanvasItems])

  // Serialized + coalesced canvas autosave (defects D3/D4) lives in its own hook module.
  const markCanvasRevisionSaved = useCallback((revision: number, savedItems: any[], serverItems?: any[], saveMeta?: { dirtyEpoch?: number }) => {
    const currentRevision = canvasRevisionRef.current
    const savedDirtyEpoch = saveMeta?.dirtyEpoch ?? 0
    if (saveMeta?.dirtyEpoch !== undefined) {
      persistedCanvasDirtyEpochRef.current = Math.max(
        persistedCanvasDirtyEpochRef.current,
        saveMeta.dirtyEpoch,
      )
    }
    const normalizedItems = mergeServerCanvasMediaUrls(savedItems, serverItems)
    if (revision < currentRevision) {
      if (normalizedItems !== savedItems) {
        confirmedCanvasItemsRef.current = mergeServerCanvasMediaUrls(confirmedCanvasItemsRef.current, serverItems)
        updateCanvasItems((current: any[]) => {
          const mergedItems = mergeServerCanvasMediaUrls(current, serverItems)
          latestCanvasItemsRef.current = mergedItems
          return mergedItems
        }, { skipHistory: true })
      }
      return
    }

    canvasRevisionRef.current = revision
    confirmedCanvasItemsRef.current = normalizedItems
    if (savedDirtyEpoch >= canvasDirtyEpochRef.current) {
      latestCanvasItemsRef.current = normalizedItems
    }
    if (normalizedItems !== savedItems) {
      updateCanvasItems((current: any[]) => {
        const mergedItems = mergeServerCanvasMediaUrls(current, serverItems)
        latestCanvasItemsRef.current = mergedItems
        return mergedItems
      }, { skipHistory: true })
    }
    if (id && !isGuest) {
      broadcastCanvasRevision(Number(id), revision)
    }
  }, [id, isGuest, updateCanvasItems])

  const applyAgentCanvasItems = useCallback((updater: any) => {
    if (isCanvasStaleRef.current) return
    updateCanvasItems((current: any[]) => {
      const nextItems = typeof updater === 'function' ? updater(current) : updater
      latestCanvasItemsRef.current = nextItems
      confirmedCanvasItemsRef.current = nextItems
      return nextItems
    }, { skipHistory: true })
  }, [updateCanvasItems])

  const syncCanvasRevisionFromAgentPatch = useCallback((revision: number, options?: { resolveStale?: boolean }) => {
    const next = applyAgentPatchCanvasRevisionSync({
      currentRevision: canvasRevisionRef.current,
      isStale: isCanvasStaleRef.current,
      staleRevision: canvasStaleRevisionRef.current,
    }, revision, options)
    if (!next.revisionChanged && !next.staleCleared) return
    canvasRevisionRef.current = next.currentRevision
    isCanvasStaleRef.current = next.isStale
    canvasStaleRevisionRef.current = next.staleRevision
    if (next.staleCleared) {
      setIsCanvasStale(false)
    }
    if (id && !isGuest) {
      broadcastCanvasRevision(Number(id), next.currentRevision)
    }
  }, [id, isGuest])

  const markCanvasStale = useCallback((revision?: number) => {
    if (revision !== undefined) {
      canvasRevisionRef.current = Math.max(canvasRevisionRef.current, revision)
      canvasStaleRevisionRef.current = normalizeCanvasRevision(revision)
    } else {
      canvasStaleRevisionRef.current = null
    }
    isCanvasStaleRef.current = true
    setIsCanvasStale(true)
    setSelectedItems([])
    setContextMenu(null)
    setActiveDropdown(null)
    setIsAddMenuOpen(false)
    setIsSelectMenuOpen(false)
    setIsAssetLibraryOpen(false)
  }, [])

  const saveCanvasItems = useCanvasSaver({
    id,
    isGuest,
    canvasItemsLoaded,
    canvasLoadFailed,
    buildCanvasMeta,
    deletedAgentMediaKeys,
    canvasRevisionRef,
    isCanvasStaleRef,
    getDirtyEpoch: () => canvasDirtyEpochRef.current,
    onRevisionSaved: markCanvasRevisionSaved,
    onObsoleteRevisionConflict: () => {
      if (isCanvasStaleRef.current) return
      if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return
      void saveCanvasItemsRef.current?.(
        latestCanvasItemsRef.current,
        {},
        { dirtyEpoch: canvasDirtyEpochRef.current },
      )
    },
    onRevisionConflict: (revision) => {
      updateCanvasItems(confirmedCanvasItemsRef.current)
      markCanvasStale(revision)
    },
  })
  saveCanvasItemsRef.current = saveCanvasItems

  const updateItem = useCallback((itemId: string, updates: any) => {
    const isGenerationUpdate = updates.status !== undefined || updates.task_id !== undefined
    const shouldPersistIntrinsicSize =
      updates.media_display_size_source === 'intrinsic'
      && updates.width !== undefined
      && updates.height !== undefined
    trackedUpdateCanvasItems((prev: any[]) => {
      const next = prev.map((item) => item.id === itemId ? { ...item, ...updates } : item)
      if (
        updates.status === 'binding_task'
        || updates.status === 'generating'
        || updates.task_id
        || updates.client_request_id
        || shouldPersistIntrinsicSize
      ) {
        saveCanvasItems(next)
      }
      return next
    }, { skipHistory: isGenerationUpdate })
  }, [saveCanvasItems, trackedUpdateCanvasItems])

  const loadIntrinsicImageSize = useCallback((url: string, fallback: { width: number, height: number }) => {
    return new Promise<{ width: number, height: number }>((resolve) => {
      const image = new Image()
      image.onload = () => resolve({ width: image.naturalWidth || fallback.width, height: image.naturalHeight || fallback.height })
      image.onerror = () => resolve(fallback)
      image.src = url
    })
  }, [])

  const loadProjectAssets = useCallback(async () => {
    if (!id || isGuest) {
      setProjectAssets({})
      return
    }

    try {
      const res = await assetsApi.list(Number(id))
      const nextAssets = res.data.reduce((acc: Record<number, any>, asset: any) => {
        acc[asset.id] = asset
        return acc
      }, {})
      setProjectAssets(nextAssets)
    } catch (error) {
      console.error('Failed to load project assets:', error)
    }
  }, [id, isGuest])

  const {
    handleFocusItem,
    handleJumpToItem,
    selectAndCenterCanvasItem,
    handleFitView,
  } = useCanvasViewportActions({
    camera,
    canvasRef,
    canvasContentRef,
    canvasItems,
    getItemDims,
    isChatSidebarOpen,
    itemIndex,
    setSelectedItems,
    zoom,
    zoomRef,
  })

  const loadCanvasProjectData = useCallback((data: any, options: { clearStale?: boolean } = {}) => {
    hasHydratedCanvasRef.current = false
    canvasDirtyEpochRef.current = 0
    persistedCanvasDirtyEpochRef.current = 0
    setCanvasLoadFailed(false)
    setTitle(data.title)
    const revision = normalizeCanvasRevision(data.canvas_revision)
    canvasRevisionRef.current = revision
    if (options.clearStale) {
      isCanvasStaleRef.current = false
      canvasStaleRevisionRef.current = null
      setIsCanvasStale(false)
    }
    let nextItems: any[] = []
    if (Array.isArray(data.canvas_data) && data.canvas_data.length > 0) {
      const meta = data.canvas_data.find((item: any) => item.id === 'global_state')
      if (meta) {
        loadPersistedGeneratorMeta(meta)
        setDeletedAgentMediaKeys(normalizeDeletedAgentMediaKeys(meta.deletedAgentMediaKeys))
      } else {
        setDeletedAgentMediaKeys([])
      }
      nextItems = normalizeAgentGeneratedMediaItems(
        data.canvas_data
          .filter((item: any) => item.id !== 'global_state'),
      )
        .map((item: any) => ({
          ...(item.type === 'text' ? normalizeTextCanvasItem(item) : item),
          ...withReferenceImages(normalizeReferenceImages(item)),
        }))
      initializeState(nextItems, [])
    } else {
      initializeState([], [])
      setDeletedAgentMediaKeys([])
    }
    confirmedCanvasItemsRef.current = nextItems
    latestCanvasItemsRef.current = nextItems
    hasHydratedCanvasRef.current = true
    setCanvasItemsLoaded(true)
  }, [initializeState, loadPersistedGeneratorMeta, setCanvasItemsLoaded, setTitle, withReferenceImages])

  const refreshCanvasFromServer = useCallback(async () => {
    if (!id || isGuest) return
    setIsRefreshingCanvas(true)
    try {
      const res = await projectsApi.get(Number(id))
      loadCanvasProjectData(res.data, { clearStale: true })
      void loadProjectAssets()
    } catch (error) {
      console.error('Failed to refresh canvas:', error)
    } finally {
      setIsRefreshingCanvas(false)
    }
  }, [id, isGuest, loadCanvasProjectData, loadProjectAssets])

  useEffect(() => {
    if (isGuest && guestProject) {
      loadCanvasProjectData(guestProject, { clearStale: true })
    } else if (id && !isGuest) {
      projectsApi.get(Number(id)).then((res) => {
        loadCanvasProjectData(res.data, { clearStale: true })
        void loadProjectAssets()
      }).catch(() => {
        hasHydratedCanvasRef.current = false
        canvasDirtyEpochRef.current = 0
        persistedCanvasDirtyEpochRef.current = 0
        initializeState([], [])
        setDeletedAgentMediaKeys([])
        setCanvasLoadFailed(true)
        setCanvasItemsLoaded(true)
      })
    }
  }, [guestProject, id, isGuest, loadCanvasProjectData, loadProjectAssets, setCanvasItemsLoaded])

  useEffect(() => {
    if (isGuest || !canvasItemsLoaded || !id || canvasLoadFailed || isCanvasStaleRef.current) return
    if (!hasHydratedCanvasRef.current) {
      hasHydratedCanvasRef.current = true
      return
    }
    if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return
    const timer = setTimeout(() => {
      if (canvasDirtyEpochRef.current <= persistedCanvasDirtyEpochRef.current) return
      void saveCanvasItems(latestCanvasItemsRef.current, {}, { dirtyEpoch: canvasDirtyEpochRef.current })
    }, 1000)
    return () => clearTimeout(timer)
  }, [canvasItems, canvasItemsLoaded, canvasLoadFailed, id, isGuest, saveCanvasItems])

  useEffect(() => {
    isCanvasStaleRef.current = isCanvasStale
  }, [isCanvasStale])

  useEffect(() => {
    if (!id || isGuest || typeof BroadcastChannel === 'undefined') return
    const projectId = Number(id)
    const channel = new BroadcastChannel(CANVAS_REVISION_BROADCAST_CHANNEL)
    channel.onmessage = (event) => {
      const message = event.data || {}
      if (Number(message.projectId) !== projectId) return
      const incomingRevision = normalizeCanvasRevision(message.canvasRevision)
      if (incomingRevision > canvasRevisionRef.current) {
        markCanvasStale(incomingRevision)
      }
    }
    return () => channel.close()
  }, [id, isGuest, markCanvasStale])

  useEffect(() => {
    if (!id || isGuest) return
    let inFlight = false
    const checkRevision = async () => {
      if (inFlight || isCanvasStaleRef.current) return
      inFlight = true
      try {
        const res = await projectsApi.get(Number(id))
        const incomingRevision = normalizeCanvasRevision(res.data.canvas_revision)
        if (incomingRevision > canvasRevisionRef.current) {
          markCanvasStale(incomingRevision)
        }
      } catch {
        // Keep the current editable state on transient revision probe failures.
      } finally {
        inFlight = false
      }
    }
    const handleFocus = () => {
      void checkRevision()
    }
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void checkRevision()
      }
    }
    window.addEventListener('focus', handleFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      window.removeEventListener('focus', handleFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [id, isGuest, markCanvasStale])

  useEffect(() => {
    if (canvasItemsLoaded && !hasInitialJumped && canvasRef.current) {
      const timer = setTimeout(() => {
        handleFitView()
        setHasInitialJumped(true)
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [canvasItemsLoaded, canvasRef, handleFitView, hasInitialJumped, setHasInitialJumped])

  useEffect(() => {
    if (!imageAnchoredImageDraft) return
    const draftItemStillExists = canvasItems.some((item: any) => item.id === imageAnchoredImageDraft.sourceImageItemId)
    const draftItemStillSelected = selectedItems.includes(imageAnchoredImageDraft.sourceImageItemId)
    if (!draftItemStillExists || !draftItemStillSelected) {
      setImageAnchoredImageDraft(null)
    }
  }, [canvasItems, imageAnchoredImageDraft, selectedItems])

  useEffect(() => {
    if (!cropState) return
    const cropItemStillExists = canvasItems.some((item: any) => item.id === cropState.itemId)
    const cropItemStillSelected = selectedItems.includes(cropState.itemId)
    if (!cropItemStillExists || !cropItemStillSelected) {
      setCropState(null)
    }
  }, [canvasItems, cropState, selectedItems])

  useEffect(() => {
    if (!textEditingItemId) return
    const textItemStillExists = canvasItems.some((item: any) => item.id === textEditingItemId && item.type === 'text')
    const textItemStillSelected = selectedItems.includes(textEditingItemId)
    if (!textItemStillExists || !textItemStillSelected) {
      setTextEditingItemId(null)
      setTextToolbarState({ activePanel: null })
    }
  }, [canvasItems, selectedItems, textEditingItemId])

  useEffect(() => {
    if (selectedItems.length !== 1) return
    const selectedBrushItem = canvasItems.find((item: any) => item.id === selectedItems[0] && item.type === 'brush_path')
    if (!selectedBrushItem) return

    setBrushToolState((prev) => ({
      ...prev,
      color: selectedBrushItem.brushColor || prev.color,
      size: selectedBrushItem.brushSize || prev.size,
    }))
  }, [canvasItems, selectedItems])

  const updateTextStyle = useCallback((itemId: string, updates: any) => {
    trackedUpdateCanvasItems((prev: any[]) => prev.map((item) => {
      if (item.id !== itemId || item.type !== 'text') return item

      const nextFontFamily = updates.fontFamily || item.fontFamily
      const mergedItem = {
        ...item,
        ...updates,
        fontFamily: nextFontFamily,
        fontVariant: getVariantForFontFamily(nextFontFamily, updates.fontVariant ?? item.fontVariant),
      }
      const estimatedSize = estimateTextCanvasSize({
        text: mergedItem.text,
        fontSize: mergedItem.fontSize,
        lineHeight: mergedItem.lineHeight,
        writingMode: mergedItem.writingMode,
        width: mergedItem.width,
        height: mergedItem.height,
      })

      return {
        ...mergedItem,
        width: Math.max(mergedItem.width || 0, estimatedSize.width),
        height: Math.max(mergedItem.height || 0, estimatedSize.height),
      }
    }))
  }, [trackedUpdateCanvasItems])

  const handleCommitTextEdit = useCallback((itemId: string, value: string) => {
    trackedUpdateCanvasItems((prev: any[]) => prev.map((item) => {
      if (item.id !== itemId || item.type !== 'text') return item

      const nextText = value?.trim() ? value : item.text || '输入文字'
      const estimatedSize = estimateTextCanvasSize({
        text: nextText,
        fontSize: item.fontSize,
        lineHeight: item.lineHeight,
        writingMode: item.writingMode,
        width: item.width,
        height: item.height,
      })

      return {
        ...item,
        text: nextText,
        width: Math.max(item.width || 0, estimatedSize.width),
        height: Math.max(item.height || 0, estimatedSize.height),
      }
    }))
    setTextEditingItemId(null)
  }, [trackedUpdateCanvasItems])

  const handleCancelTextEdit = useCallback(() => {
    setTextEditingItemId(null)
  }, [])

  const handleStartTextEdit = useCallback((itemId: string) => {
    const targetItem = canvasItems.find((item: any) => item.id === itemId && item.type === 'text')
    if (!targetItem) return
    setSelectedItems([itemId])
    setTextEditingItemId(itemId)
  }, [canvasItems])

  const handlePlaceTextAtPoint = useCallback((position: { x: number, y: number }) => {
    const nextId = `text-${Date.now()}${Math.random().toString().slice(2, 6)}`
    const maxZ = Math.max(0, ...canvasItems.map((item: any) => item.z_index || 0))
    const newItem = createTextCanvasItem({
      id: nextId,
      x: Math.round(position.x),
      y: Math.round(position.y),
      zIndex: maxZ + 1,
    })

    trackedUpdateCanvasItems((prev: any[]) => [...prev, newItem])
    setSelectedItems([nextId])
    setTextEditingItemId(nextId)
    setTextToolbarState({ activePanel: null })
    setActiveTool('select')
  }, [canvasItems, setActiveTool, trackedUpdateCanvasItems])

  const updateBrushItem = useCallback((itemId: string, updates: any) => {
    trackedUpdateCanvasItems((prev: any[]) => prev.map((item) => {
      if (item.id !== itemId || item.type !== 'brush_path') return item

      const nextWidth = updates.width !== undefined ? Math.max(1, Number(updates.width) || 1) : (item.width || item.pathBounds?.width || 1)
      const nextHeight = updates.height !== undefined ? Math.max(1, Number(updates.height) || 1) : (item.height || item.pathBounds?.height || 1)
      const nextBrushSize = updates.brushSize !== undefined ? Math.max(1, Math.min(999, Number(updates.brushSize) || 1)) : (item.brushSize || 1)
      const nextBrushColor = typeof updates.brushColor === 'string' ? updates.brushColor : (item.brushColor || brushToolState.color)

      return {
        ...item,
        ...updates,
        width: nextWidth,
        height: nextHeight,
        brushSize: nextBrushSize,
        brushColor: nextBrushColor,
        pathBounds: item.pathBounds
          ? {
            ...item.pathBounds,
            width: nextWidth,
            height: nextHeight,
          }
          : item.pathBounds,
      }
    }))

    if (updates.brushColor !== undefined || updates.brushSize !== undefined) {
      setBrushToolState((prev) => ({
        ...prev,
        color: typeof updates.brushColor === 'string' ? updates.brushColor : prev.color,
        size: updates.brushSize !== undefined ? Math.max(1, Math.min(999, Number(updates.brushSize) || 1)) : prev.size,
      }))
    }
  }, [brushToolState.color, trackedUpdateCanvasItems])

  const marksController = useCanvasControllerMarks({
    t,
    user,
    updateMarks,
    isChatSidebarOpen,
    setIsChatSidebarOpen,
    markIdCounter,
  })

  const mediaController = useCanvasControllerMedia({
    t,
    user,
    id,
    isGuest,
    canvasRef,
    canvasItems,
    selectedItems,
    setSelectedItems,
    saveCanvasItems,
    updateCanvasItems: trackedUpdateCanvasItems,
    updateItem,
    getItemDims,
    loadIntrinsicImageSize,
    imageDetailItemId,
    setImageDetailItemId,
    setImageDetailPanelPosition,
    imageDetailSizeBytes,
    setImageDetailSizeBytes,
    projectAssets,
    setProjectAssets,
    deletedAgentMediaKeys,
    setDeletedAgentMediaKeys,
    textRedrawState,
    setTextRedrawState,
    textRedrawExtractingItemIds,
    setTextRedrawExtractingItemIds,
    setTextRedrawPanelPosition,
    imageEraseSession,
    setImageEraseSession,
    setImageErasePreviewRect,
    imageEraseCanvasRef,
    imageEraseBrushCanvasRef,
    imageEraseSessionRef,
    imageErasePointerRef,
    imageEraseCheckerboardPatternRef,
    handleJumpToItem,
    setActiveTool,
    selectAndCenterCanvasItem,
    loadProjectAssets,
    zoomRef,
    offsetRef,
    setCamera: camera.setCamera,
    setClipboardSource,
    latestCanvasItemsRef,
  })

  useEffect(() => {
    if (!contextMenu || contextMenu.type !== 'canvas') return

    let cancelled = false
    void hasClipboardImageInNavigator()
      .then((hasImage) => {
        if (!cancelled) setHasExternalClipboardImage(hasImage)
      })
      .catch(() => {
        if (!cancelled) setHasExternalClipboardImage(false)
      })

    return () => {
      cancelled = true
    }
  }, [contextMenu])

  const generatorsController = useCanvasControllerGenerators({
    t,
    id,
    user,
    canvasItems,
    offsetRef,
    zoomRef,
    setCamera: camera.setCamera,
    setSelectedItems,
    updateCanvasItems: trackedUpdateCanvasItems,
    saveCanvasItems,
    isCanvasStale,
    isCanvasStaleRef,
    isRefreshingCanvas,
    refreshCanvasFromServer,
    syncCanvasRevisionFromAgentPatch,
    updateItem,
    getItemDims,
    getItemReferenceImages,
    getResolvedVideoCapability,
    getResolvedVideoDurations,
    getResolvedImageCapability,
    withReferenceImages,
    availableImageModels,
    availableVideoModels,
    imageModel,
    imageProvider,
    videoModel,
    videoProvider,
    imageRes,
    imageRatio,
    videoAspect,
    videoDuration,
    videoQuality,
    setImageAnchoredImageDraft,
    imageAnchoredImageDraft,
    setImageAnchoredVideoDraft,
    imageAnchoredVideoDraft,
    spatialAngleSession,
    setSpatialAngleSession,
    setActiveDropdown,
    selectAndCenterCanvasItem,
    loadIntrinsicImageSize,
    notifiedTasksRef,
  })

  const cropController = useCanvasControllerCrop({
    t,
    canvasItems,
    cropState,
    setCropState,
    cropDragState,
    setCropDragState,
    getItemDims,
    loadImageElement: mediaController.loadImageElement,
    saveCanvasItems,
    updateCanvasItems: trackedUpdateCanvasItems,
    uploadCanvasImageFile: mediaController.uploadCanvasImageFile,
  })

  const arrangementController = useCanvasControllerArrangement({
    t,
    id,
    projectName: title,
    isDark: args.isDark,
    canvasRef,
    canvasItems,
    selectedItems,
    setSelectedItems,
    clipboardItems,
    setClipboardItems,
    clipboardSource,
    setClipboardSource,
    contextMenu,
    zoom,
    offset,
    mousePosRef,
    saveCanvasItems,
    updateCanvasItems: trackedUpdateCanvasItems,
    deletedAgentMediaKeys,
    setDeletedAgentMediaKeys,
    getItemDims,
    layerDragId,
    setLayerDragId,
    layerDropTarget,
    setLayerDropTarget,
    setMultiSelectToolsOpen,
    loadImageElement: mediaController.loadImageElement,
    loadVideoElement: mediaController.loadVideoElement,
    handlePasteClipboardImage: mediaController.handlePasteClipboardImage,
    selectAndCenterCanvasItem,
  })

  const viewportController = useCanvasControllerViewport({
    isDark: args.isDark,
    t,
    canvasRef,
    canvasContentRef,
    canvasItems,
    itemIndex,
    groupChildrenIndex,
    baseGuideCandidates,
    baseGuideCandidateBuckets,
    visibleSelectableItemsRef,
    selectedItems,
    setSelectedItems,
    beginTransaction,
    commitTransaction,
    getItemDims,
    activeTool,
    setActiveTool,
    setMarkModifierState,
    zoom,
    zoomRef,
    offset,
    offsetRef,
    camera,
    isPanning,
    setIsPanning,
    setIsWheeling,
    selectionBox,
    setSelectionBox,
    draggingItemId,
    setDraggingItemId,
    activeGuides,
    setActiveGuides,
    resizingGroupId,
    setResizingGroupId,
    mediaResizeState,
    setMediaResizeState,
    brushResizeState,
    setBrushResizeState,
    movingItemIdsRef,
    resizingHandle,
    dragItemStart,
    resizingStart,
    mousePosRef,
    wheelTimeout,
    panStart,
    offsetStart,
    dragItemOriginals,
    rafIdRef,
    guideCandidatesRef,
    handleCancelImageErase: mediaController.handleCancelImageErase,
    imageEraseSessionRef,
    imageDetailItemId,
    handleCloseImageDetails: mediaController.handleCloseImageDetails,
    textRedrawState,
    handleCancelTextRedraw: mediaController.handleCancelTextRedraw,
    cropState,
    setCropState,
    spatialAngleSession: generatorsController.spatialAngleSession,
    handleCancelSpatialAngle: generatorsController.handleCancelSpatialAngle,
    imageAnchoredImageDraft,
    cancelImageAnchoredImageDraft: generatorsController.cancelImageAnchoredImageDraft,
    imageAnchoredVideoDraft,
    cancelImageAnchoredVideoDraft: generatorsController.cancelImageAnchoredVideoDraft,
    handleContextMenuAction: arrangementController.handleContextMenuAction,
    handlePasteClipboardImage: mediaController.handlePasteClipboardImage,
    clipboardItems,
    clipboardSource,
    undo,
    redo,
    setContextMenu,
    setActiveDropdown,
    handleFitView,
    updateCanvasItems: trackedUpdateCanvasItems,
    handlePlaceTextAtPoint,
    brushDraft,
    setBrushDraft,
    brushToolState,
    textEditingItemId,
    handleCancelTextEdit,
  })

  const currentSelectionItems = canvasItems.filter((item: any) => selectedItems.includes(item.id))
  const firstSelectedItem = currentSelectionItems[0] || null
  const cropCommitMode = cropState ? 'crop' : null
  const MERGEABLE_TYPES = new Set(['image', 'video', 'text', 'brush_path'])
  const selectionContextMenuItems = buildCanvasSelectionMenuItems({
    firstSelectedItemType: firstSelectedItem?.type || null,
    selectedItemIds: selectedItems,
    allSelectedItemsAreMediaWithUrl: selectedItems.every((itemId) => {
      const item = itemIndex.get(itemId)
      return !!item && (item.type === 'image' || item.type === 'video') && !!item.url
    }),
    selectionCanMerge: selectedItems.length > 1 && selectedItems.every((itemId) => {
      const item = itemIndex.get(itemId)
      if (!item) return false
      if (item.type === 'image' || item.type === 'video') return !!item.url
      return MERGEABLE_TYPES.has(item.type)
    }),
    currentSelectionHasImage: currentSelectionItems.some((item: any) => item.type === 'image' || item.type === 'image_generator'),
    currentSelectionSupportsPhotoshopEdit: canPhotoshopEditSelection(selectedItems, firstSelectedItem?.type || null),
    labels: {
      copy: t('canvas.context_menu.copy', '复制'),
      paste: t('canvas.context_menu.paste', '粘贴'),
      restore: t('canvas.context_menu.restore', '尺寸还原'),
      bringForward: t('canvas.context_menu.bring_forward', '上移一层'),
      sendBackward: t('canvas.context_menu.send_backward', '下移一层'),
      bringFront: t('canvas.context_menu.bring_front', '移动至顶层'),
      sendBack: t('canvas.context_menu.send_back', '移动至底层'),
      createGroup: t('canvas.context_menu.group', '创建编组'),
      mergeLayers: t('canvas.context_menu.merge_layers', '合并图层'),
      ungroup: t('canvas.context_menu.ungroup', '解除编组'),
      toggleVisible: t('canvas.context_menu.toggle_visible', '显示/隐藏'),
      lock: t('canvas.context_menu.lock', '锁定/解锁'),
      export: t('canvas.context_menu.export', '导出'),
      delete: t('canvas.context_menu.delete', '删除'),
      photoshopEdit: t('canvas.context_menu.ps_edit', 'PS 编辑'),
    },
  })
  const effectiveSelectionContextMenuItems = firstSelectedItem?.generation_kind === 'text_redraw' && firstSelectedItem?.status === 'failed'
    ? [{ key: 'delete', label: t('canvas.context_menu.delete', '删除') }]
    : selectionContextMenuItems

  const selectedSingleItem = selectedItems.length === 1
    ? itemIndex.get(selectedItems[0]) || null
    : null
  const selectedSingleItemDims = selectedSingleItem ? getItemDims(selectedSingleItem) : null
  const selectedSingleItemRect = (() => {
    if (!selectedSingleItem) return null
    const canvasRect = canvasRef.current?.getBoundingClientRect()
    if (!canvasRect) return null
    const w = selectedSingleItem.width || selectedSingleItemDims?.width || 0
    const h = selectedSingleItem.height || selectedSingleItemDims?.height || 0
    const scale = zoom / 100
    return {
      left: (selectedSingleItem.x * scale) + canvasRect.width / 2 + offset.x + canvasRect.left,
      top: (selectedSingleItem.y * scale) + canvasRect.height / 2 + offset.y + canvasRect.top,
      width: w * scale,
      height: h * scale,
    }
  })()
  const selectedSingleItemCanvasRect = (() => {
    if (!selectedSingleItem || !canvasRef.current) return null
    const w = selectedSingleItem.width || selectedSingleItemDims?.width || 0
    const h = selectedSingleItem.height || selectedSingleItemDims?.height || 0
    const scale = zoom / 100
    return {
      left: (selectedSingleItem.x * scale) + canvasRef.current.clientWidth / 2 + offset.x,
      top: (selectedSingleItem.y * scale) + canvasRef.current.clientHeight / 2 + offset.y,
      width: w * scale,
      height: h * scale,
    }
  })()
  const selectedSingleItemViewportWidth = selectedSingleItemRect?.width || 0
  const selectedSingleItemWidth = selectedSingleItem ? (selectedSingleItem.width || selectedSingleItemDims?.width || 0) : 0
  const selectedSingleItemHeight = selectedSingleItem ? (selectedSingleItem.height || selectedSingleItemDims?.height || 0) : 0
  const selectedIsImageGroup = selectedSingleItem ? ['image', 'image_generator'].includes(selectedSingleItem.type) : false
  const selectedIsGenerator = selectedSingleItem ? ['image_generator', 'video_generator'].includes(selectedSingleItem.type) : false
  const shouldRenderSelectedMeta = selectedSingleItemRect ? shouldShowSelectionMeta(selectedSingleItemViewportWidth, 280) : false

  return {
    activeTool,
    setActiveTool,
    markModifierState,
    setMarkModifierState,
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
    projectAssets,
    setProjectAssets,
    deletedAgentMediaKeys,
    imageDetailItemId,
    imageDetailPanelPosition,
    imageDetailSizeBytes,
    textEditingItemId,
    textToolbarState,
    setTextToolbarState,
    brushDraft,
    setBrushDraft,
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
    hasExternalClipboardImage,
    canPasteExternalClipboard: hasExternalClipboardImage || canReadSystemClipboardImages(),
    setClipboardItems,
    zoom,
    setZoom,
    offset,
    setOffset,
    canvasCamera: camera,
    isChatSidebarOpen,
    setIsChatSidebarOpen,
    zoomRef,
    offsetRef,
    isPanning,
    isWheeling,
    setIsWheeling,
    selectionBox,
    draggingItemId,
    activeGuides,
    setActiveGuides,
    resizingGroupId,
    setResizingGroupId,
    mediaResizeState,
    setMediaResizeState,
    brushResizeState,
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
    mousePosRef,
    movingItemIdsRef,
    resizingHandle,
    dragItemStart,
    resizingStart,
    updateCanvasItems: trackedUpdateCanvasItems,
    saveCanvasItems,
    isCanvasStale,
    isCanvasStaleRef,
    isRefreshingCanvas,
    refreshCanvasFromServer,
    syncCanvasRevisionFromAgentPatch,
    updateItem,
    currentSelectionItems,
    selectionContextMenuItems: effectiveSelectionContextMenuItems,
    firstSelectedItem,
    cropCommitMode,
    handleFocusItem,
    handlePlaceTextAtPoint,
    handleStartTextEdit,
    handleCancelTextEdit,
    handleCommitTextEdit,
    updateTextStyle,
    updateBrushItem,
    applyAgentCanvasItems,
    ...marksController,
    ...viewportController,
    ...mediaController,
    ...cropController,
    ...generatorsController,
    ...arrangementController,
    handleFitView,
    handleJumpToItem,
    selectAndCenterCanvasItem,
    loadProjectAssets,
    imageEraseCanvasRef,
    imageAnchoredImageDraft,
    imageAnchoredVideoDraft,
    selectedSingleItem,
    selectedSingleItemRect,
    selectedSingleItemCanvasRect,
    selectedSingleItemViewportWidth,
    selectedSingleItemWidth,
    selectedSingleItemHeight,
    selectedIsImageGroup,
    selectedIsGenerator,
    shouldRenderSelectedMeta,
  }
}

