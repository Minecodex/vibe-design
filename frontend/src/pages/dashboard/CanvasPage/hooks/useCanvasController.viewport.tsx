/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment, react-hooks/exhaustive-deps */
// @ts-nocheck
import { useCallback, useEffect, useRef } from 'react'

import { filterGuideCandidateBuckets, getDraggedBounds, getGuideThresholdInCanvas, projectGuidesToViewport, resolveActiveGuidesFromBuckets } from '../alignmentGuides';
import {
  clampCanvasZoom,
  MAX_CANVAS_ZOOM,
} from '../canvasZoom'
import { createCanvasWheelCameraScheduler } from '../canvasWheelCamera'
import { getCanvasSelectionHandleAppearance } from '../selectionStyles'
import '../imageAnchoredVideo';
import { createBrushPathCanvasItem } from '../brushPaths'
import { collectCanvasClipboardItems } from './useCanvasController.arrangement'
import { writeCanvasClipboardMarkerToClipboardData } from '../canvasClipboard'
import { createCanvasInteractionPreviewController } from '../canvasInteractionPreview'
import {
  applyBrushResizePreview,
  applyDragPreview,
  applyGroupResizePreview,
  applyMediaResizePreview,
} from '../canvasInteractionTransforms'

export function useCanvasControllerViewport(args: any) {
  const { isDark, canvasRef, canvasContentRef, canvasItems, itemIndex, groupChildrenIndex, baseGuideCandidateBuckets, visibleSelectableItemsRef, updateCanvasItems, selectedItems, setSelectedItems, beginTransaction, commitTransaction, getItemDims, activeTool, setActiveTool, setMarkModifierState, zoom, zoomRef, offset, offsetRef, camera, isPanning, setIsPanning, setIsWheeling, selectionBox, setSelectionBox, draggingItemId, setDraggingItemId, activeGuides, setActiveGuides, resizingGroupId, setResizingGroupId, mediaResizeState, setMediaResizeState, brushResizeState, setBrushResizeState, movingItemIdsRef, resizingHandle, dragItemStart, resizingStart, mousePosRef, panStart, offsetStart, dragItemOriginals, rafIdRef, guideCandidatesRef, handleCancelImageErase, imageEraseSessionRef, imageDetailItemId, handleCloseImageDetails, textRedrawState, handleCancelTextRedraw, cropState, setCropState, imageAnchoredImageDraft, cancelImageAnchoredImageDraft, imageAnchoredVideoDraft, cancelImageAnchoredVideoDraft, spatialAngleSession, handleCancelSpatialAngle, handleContextMenuAction, handlePasteClipboardImage, clipboardItems, undo, redo, setContextMenu, setActiveDropdown, handleFitView, handlePlaceTextAtPoint, brushDraft, setBrushDraft, brushToolState, textEditingItemId, handleCancelTextEdit } = args

  // Shadow frequently-changing state values with refs to stabilize handleMouseMove callback
  const brushDraftRef = useRef(brushDraft)
  brushDraftRef.current = brushDraft
  const brushResizeStateRef = useRef(brushResizeState)
  brushResizeStateRef.current = brushResizeState
  const mediaResizeStateRef = useRef(mediaResizeState)
  mediaResizeStateRef.current = mediaResizeState
  const resizingGroupIdRef = useRef(resizingGroupId)
  resizingGroupIdRef.current = resizingGroupId
  const draggingItemIdRef = useRef(draggingItemId)
  draggingItemIdRef.current = draggingItemId
  const groupHitCandidatesRef = useRef<any[]>([])
  const isPanningRef = useRef(isPanning)
  isPanningRef.current = isPanning
  const selectionBoxRef = useRef(selectionBox)
  selectionBoxRef.current = selectionBox
  const activeToolRef = useRef(activeTool)
  activeToolRef.current = activeTool
  const temporaryHandToolRef = useRef(false)
  const temporaryHandToolRestoreRef = useRef<string | null>(null)
  const selectedItemsRef = useRef(selectedItems)
  selectedItemsRef.current = selectedItems
  const canvasItemsRef = useRef(canvasItems)
  canvasItemsRef.current = canvasItems
  const interactionPreviewRef = useRef(createCanvasInteractionPreviewController())

  const getCanvasPointFromClient = useCallback((clientX: number, clientY: number) => {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return null

    const scale = zoomRef.current / 100
    return {
      x: (clientX - rect.left - rect.width / 2 - offsetRef.current.x) / scale,
      y: (clientY - rect.top - rect.height / 2 - offsetRef.current.y) / scale,
    }
  }, [canvasRef, offsetRef, zoomRef])

  const getMovingItemIds = useCallback((itemIds: string[]) => {
    const ids = new Set<string>()
    itemIds.forEach((itemId) => {
      ids.add(itemId)
      const item = itemIndex.get(itemId)
      if (item?.type === 'group') {
        const childIds = groupChildrenIndex.get(item.id) || []
        childIds.forEach((childId) => ids.add(childId))
      }
    })
    return ids
  }, [groupChildrenIndex, itemIndex])

  const zoomIn = useCallback(() => {
    const currentZoom = zoomRef.current
    const nextZoom = clampCanvasZoom(Math.min(currentZoom + 10, MAX_CANVAS_ZOOM))
    if (nextZoom !== currentZoom) {
      const ratio = nextZoom / currentZoom
      const newOffset = { x: offsetRef.current.x * ratio, y: offsetRef.current.y * ratio }
      camera.setCamera({ zoom: nextZoom, offset: newOffset }, { commit: true, reason: 'zoom-button' })
    }
  }, [camera, offsetRef, zoomRef])

  const zoomOut = useCallback(() => {
    const currentZoom = zoomRef.current
    const nextZoom = clampCanvasZoom(currentZoom - 10)
    if (nextZoom !== currentZoom) {
      const ratio = nextZoom / currentZoom
      const newOffset = { x: offsetRef.current.x * ratio, y: offsetRef.current.y * ratio }
      camera.setCamera({ zoom: nextZoom, offset: newOffset }, { commit: true, reason: 'zoom-button' })
    }
  }, [camera, offsetRef, zoomRef])

  const resetZoom = useCallback(() => {
    camera.setCamera({ zoom: 100, offset: { x: 0, y: 0 } }, { commit: true, reason: 'reset-zoom' })
  }, [camera])

  const handleMouseDown = useCallback((event: React.MouseEvent) => {
    if (spatialAngleSession && event.button === 0) {
      handleCancelSpatialAngle()
      return
    }
    if (imageEraseSessionRef.current && event.button === 0) {
      handleCancelImageErase()
      return
    }
    if (event.button === 0 && activeTool === 'brush') {
      const point = getCanvasPointFromClient(event.clientX, event.clientY)
      if (!point) return
      setActiveGuides([])
      movingItemIdsRef.current = new Set()
      setSelectedItems([])
      setBrushDraft({
        points: [{ x: Math.round(point.x), y: Math.round(point.y) }],
        brushColor: brushToolState.color,
        brushSize: brushToolState.size,
      })
      return
    }
    const isHandMode = activeTool === 'hand'
    if (event.button === 1 || (event.button === 0 && isHandMode)) {
      setActiveGuides([])
      movingItemIdsRef.current = new Set()
      setSelectionBox(null)
      setIsPanning(true)
      panStart.current = { x: event.clientX, y: event.clientY }
      offsetStart.current = { ...offsetRef.current }
    } else if (event.button === 0 && activeTool === 'select') {
      const isCanvasBackground = event.target === canvasRef.current
        || event.target === canvasContentRef.current
        || (event.target as HTMLElement).getAttribute('data-canvas-bg') === 'true'
      if (isCanvasBackground) {
        setActiveGuides([])
        movingItemIdsRef.current = new Set()
        setSelectionBox({ x1: event.clientX, y1: event.clientY, x2: event.clientX, y2: event.clientY })
      }
    }
  }, [activeTool, brushToolState.color, brushToolState.size, canvasContentRef, canvasRef, getCanvasPointFromClient, handleCancelImageErase, handleCancelSpatialAngle, spatialAngleSession, imageEraseSessionRef, movingItemIdsRef, offsetRef, offsetStart, panStart, setActiveGuides, setBrushDraft, setIsPanning, setSelectedItems, setSelectionBox])

  const handleItemMouseDown = useCallback((event: React.MouseEvent, itemId: string) => {
    if (activeTool !== 'select' || event.button !== 0) return
    event.stopPropagation()

    if (spatialAngleSession) {
      handleCancelSpatialAngle()
      return
    }

    if (imageEraseSessionRef.current) {
      handleCancelImageErase()
      return
    }

    const item = itemIndex.get(itemId)
    if (!item || item.is_locked) return

    if (imageAnchoredVideoDraft && itemId !== imageAnchoredVideoDraft.sourceImageItemId) {
      cancelImageAnchoredVideoDraft(true)
      return
    }

    const isMulti = event.ctrlKey || event.metaKey
    let targetSelection: string[] = []
    if (isMulti) {
      targetSelection = selectedItems.includes(itemId)
        ? selectedItems.filter((selectedId) => selectedId !== itemId)
        : [...selectedItems, itemId]
      setSelectedItems(targetSelection)
    } else {
      if (!selectedItems.includes(itemId)) {
        targetSelection = [itemId]
        setSelectedItems(targetSelection)
      } else {
        targetSelection = selectedItems
      }
    }

    setDraggingItemId(itemId)
    beginTransaction()
    const currentItems = canvasItemsRef.current
    interactionPreviewRef.current.begin(currentItems)
    dragItemStart.current = { x: event.clientX, y: event.clientY }

    const originals: Record<string, any> = {}
    targetSelection.forEach((selectedId) => {
      const selectedItem = itemIndex.get(selectedId)
      if (selectedItem) {
        originals[selectedId] = { x: selectedItem.x, y: selectedItem.y }
        if (selectedItem.type === 'group') {
          const childIds = groupChildrenIndex.get(selectedItem.id) || []
          childIds.forEach((childId) => {
            const childItem = itemIndex.get(childId)
            if (childItem) {
              originals[childItem.id] = { x: childItem.x, y: childItem.y }
            }
          })
        }
      }
    })
    dragItemOriginals.current = originals
    movingItemIdsRef.current = getMovingItemIds(targetSelection)

    const movingIds = movingItemIdsRef.current
    groupHitCandidatesRef.current = currentItems.filter((canvasItem: any) => (
      canvasItem.type === 'group' && !movingIds.has(canvasItem.id)
    ))
    const candidates = filterGuideCandidateBuckets(baseGuideCandidateBuckets, movingIds)
    guideCandidatesRef.current = candidates
    const draggedBounds = getDraggedBounds(movingIds, currentItems, getItemDims)
    const initialGuides = resolveActiveGuidesFromBuckets(draggedBounds, candidates, getGuideThresholdInCanvas(zoom))
    setActiveGuides(initialGuides)
  }, [activeTool, baseGuideCandidateBuckets, beginTransaction, cancelImageAnchoredVideoDraft, dragItemOriginals, dragItemStart, getItemDims, getMovingItemIds, groupChildrenIndex, guideCandidatesRef, handleCancelImageErase, handleCancelSpatialAngle, spatialAngleSession, imageAnchoredVideoDraft, imageEraseSessionRef, itemIndex, movingItemIdsRef, selectedItems, setActiveGuides, setDraggingItemId, setSelectedItems, zoom])

  const handleMouseMove = useCallback((event: React.MouseEvent) => {
    mousePosRef.current = { x: event.clientX, y: event.clientY }

    // Capture event data synchronously (React synthetic events are pooled)
    const clientX = event.clientX
    const clientY = event.clientY

    // Cancel any pending rAF to ensure only the latest event is processed per frame
    if (rafIdRef.current) {
      cancelAnimationFrame(rafIdRef.current)
    }

    rafIdRef.current = requestAnimationFrame(() => {
      rafIdRef.current = 0

      // Read current state from refs to avoid stale closures and reduce callback dependencies
      const _brushDraft = brushDraftRef.current
      const _brushResizeState = brushResizeStateRef.current
      const _mediaResizeState = mediaResizeStateRef.current
      const _resizingGroupId = resizingGroupIdRef.current
      const _draggingItemId = draggingItemIdRef.current
      const _isPanning = isPanningRef.current
      const _selectionBox = selectionBoxRef.current
      const _activeTool = activeToolRef.current
      const _selectedItems = selectedItemsRef.current
      const _zoom = zoomRef.current
      const currentItems = canvasItemsRef.current

      if (_brushDraft) {
        const point = getCanvasPointFromClient(clientX, clientY)
        if (!point) return

        setBrushDraft((prev: any) => {
          if (!prev) return prev
          const roundedPoint = { x: Math.round(point.x), y: Math.round(point.y) }
          const lastPoint = prev.points[prev.points.length - 1]
          if (lastPoint && lastPoint.x === roundedPoint.x && lastPoint.y === roundedPoint.y) {
            return prev
          }
          const newPoints = prev.points.slice()
          newPoints.push(roundedPoint)
          return {
            ...prev,
            points: newPoints,
          }
        })
        return
      }
      if (_brushResizeState) {
        setActiveGuides([])
        const scale = _zoom / 100
        const dx = (clientX - dragItemStart.current.x) / scale
        const dy = (clientY - dragItemStart.current.y) / scale
        const nextItems = applyBrushResizePreview({
          items: currentItems,
          itemId: _brushResizeState.itemId,
          handle: _brushResizeState.handle,
          startRect: _brushResizeState.startRect,
          deltaX: dx,
          deltaY: dy,
        })
        interactionPreviewRef.current.apply(
          nextItems.filter((item) => item.id === _brushResizeState.itemId),
          currentItems,
        )
        return
      }
      if (_mediaResizeState) {
        setActiveGuides([])
        const scale = _zoom / 100
        const dx = (clientX - dragItemStart.current.x) / scale
        const dy = (clientY - dragItemStart.current.y) / scale
        const nextItems = applyMediaResizePreview({
          items: currentItems,
          itemId: _mediaResizeState.itemId,
          handle: _mediaResizeState.handle,
          startRect: _mediaResizeState.startRect,
          deltaX: dx,
          deltaY: dy,
        })
        interactionPreviewRef.current.apply(
          nextItems.filter((item) => item.id === _mediaResizeState.itemId),
          currentItems,
        )
        return
      }
      if (_resizingGroupId) {
        setActiveGuides([])
        const scale = _zoom / 100
        const dx = (clientX - dragItemStart.current.x) / scale
        const dy = (clientY - dragItemStart.current.y) / scale
        const handle = resizingHandle.current
        const start = resizingStart.current
        const nextItems = applyGroupResizePreview({
          items: currentItems,
          groupId: _resizingGroupId,
          handle,
          start,
          deltaX: dx,
          deltaY: dy,
        })
        interactionPreviewRef.current.apply(
          nextItems.filter((item) => item.id === _resizingGroupId),
          currentItems,
        )
        return
      }
      if (_draggingItemId) {
        const scale = _zoom / 100
        const dx = (clientX - dragItemStart.current.x) / scale
        const dy = (clientY - dragItemStart.current.y) / scale
        let nextGuides: any[] = []

        const { items: nextItems, draggedBounds } = applyDragPreview({
          items: currentItems,
          draggedItemId: _draggingItemId,
          deltaX: dx,
          deltaY: dy,
          originals: dragItemOriginals.current,
          selectedItems: _selectedItems,
          movingItemIds: movingItemIdsRef.current,
          groupHitCandidates: groupHitCandidatesRef.current,
          getItemDims,
        })
        const candidates = guideCandidatesRef.current
        nextGuides = resolveActiveGuidesFromBuckets(draggedBounds, candidates, getGuideThresholdInCanvas(_zoom))
        interactionPreviewRef.current.apply(
          nextItems.filter((item) => movingItemIdsRef.current.has(item.id) || item.id === _draggingItemId),
          currentItems,
        )
        setActiveGuides(nextGuides)
        return
      }
      if (_selectionBox) {
        if (_activeTool !== 'select') {
          setSelectionBox(null)
          return
        }
        setActiveGuides([])
        setSelectionBox((prev: any) => prev ? { ...prev, x2: clientX, y2: clientY } : null)
        return
      }
      if (!_isPanning) return
      setActiveGuides([])
      const dx = clientX - panStart.current.x
      const dy = clientY - panStart.current.y
      const newOffset = { x: offsetStart.current.x + dx, y: offsetStart.current.y + dy }
      camera.panToOffset(newOffset)
    })
  }, [camera, dragItemOriginals, dragItemStart, getCanvasPointFromClient, getItemDims, guideCandidatesRef, mousePosRef, movingItemIdsRef, offsetStart, panStart, rafIdRef, resizingHandle, resizingStart, setActiveGuides, setBrushDraft, setSelectionBox, brushDraftRef, brushResizeStateRef, mediaResizeStateRef, resizingGroupIdRef, draggingItemIdRef, isPanningRef, selectionBoxRef, activeToolRef, selectedItemsRef, zoomRef])

  const handleMouseUp = useCallback((event: React.MouseEvent) => {
    // Cancel any pending rAF to avoid stale updates after interaction ends
    if (rafIdRef.current) {
      cancelAnimationFrame(rafIdRef.current)
      rafIdRef.current = 0
    }
    guideCandidatesRef.current = []
    groupHitCandidatesRef.current = []
    const previewItems = interactionPreviewRef.current.getLatestItems()
    if (previewItems?.length) {
      const previewById = new Map(previewItems.map((item: any) => [item.id, item]))
      updateCanvasItems((prev: any[]) => prev.map((item) => previewById.get(item.id) || item))
    }
    interactionPreviewRef.current.clear({ restore: !previewItems?.length })
    commitTransaction()
    setMediaResizeState(null)
    setBrushResizeState(null)
    setResizingGroupId(null)
    resizingHandle.current = null
    if (brushDraft) {
      if (brushDraft.points.length > 0) {
        const nextId = `brush-${Date.now()}${Math.random().toString().slice(2, 6)}`
        const maxZ = Math.max(0, ...canvasItems.map((item: any) => item.z_index || 0))
        const brushItem = createBrushPathCanvasItem({
          id: nextId,
          points: brushDraft.points,
          brushColor: brushDraft.brushColor,
          brushSize: brushDraft.brushSize,
          zIndex: maxZ + 1,
        })
        updateCanvasItems((prev: any[]) => [...prev, brushItem])
        setSelectedItems([nextId])
      }
      setBrushDraft(null)
      setActiveTool('select')
    }
    if (selectionBox) {
      const xMin = Math.min(selectionBox.x1, selectionBox.x2)
      const xMax = Math.max(selectionBox.x1, selectionBox.x2)
      const yMin = Math.min(selectionBox.y1, selectionBox.y2)
      const yMax = Math.max(selectionBox.y1, selectionBox.y2)
      const isTiny = (xMax - xMin < 2) && (yMax - yMin < 2)

      if (isTiny) {
        if (!(event.ctrlKey || event.metaKey)) {
          if (imageAnchoredVideoDraft) {
            cancelImageAnchoredVideoDraft(false)
          }
          setSelectedItems([])
        }
      } else {
        const rect = canvasRef.current?.getBoundingClientRect()
        if (rect) {
          const scale = zoom / 100
          const cx1 = (selectionBox.x1 - rect.left - rect.width / 2 - offset.x) / scale
          const cy1 = (selectionBox.y1 - rect.top - rect.height / 2 - offset.y) / scale
          const cx2 = (selectionBox.x2 - rect.left - rect.width / 2 - offset.x) / scale
          const cy2 = (selectionBox.y2 - rect.top - rect.height / 2 - offset.y) / scale
          const selXMin = Math.min(cx1, cx2)
          const selXMax = Math.max(cx1, cx2)
          const selYMin = Math.min(cy1, cy2)
          const selYMax = Math.max(cy1, cy2)
          const selectionCandidateItems = visibleSelectableItemsRef.current
          const overlaps = selectionCandidateItems.filter((item: any) => {
            if (item.is_hidden || item.is_locked) return false
            const dims = getItemDims(item)
            const w = item.width || dims.width
            const h = item.height || dims.height
            return !(item.x > selXMax || item.x + w < selXMin || item.y > selYMax || item.y + h < selYMin)
          })
          if (overlaps.length > 0) {
            const overlapIds = overlaps.map((item: any) => item.id)
            if (event.ctrlKey || event.metaKey) {
              setSelectedItems((prev: string[]) => Array.from(new Set([...prev, ...overlapIds])))
            } else {
              setSelectedItems(overlapIds)
            }
          } else if (!(event.ctrlKey || event.metaKey)) {
            if (imageAnchoredVideoDraft) {
              cancelImageAnchoredVideoDraft(false)
            }
            setSelectedItems([])
          }
        }
      }
      setSelectionBox(null)
    }
    setActiveGuides([])
    if (isPanningRef.current) {
      camera.commitCamera('pan-end')
    }
    setIsPanning(false)
    setDraggingItemId(null)
    dragItemOriginals.current = {}
    movingItemIdsRef.current = new Set()
  }, [brushDraft, camera, cancelImageAnchoredVideoDraft, commitTransaction, getItemDims, imageAnchoredVideoDraft, movingItemIdsRef, offset.x, offset.y, resizingHandle, selectionBox, setActiveGuides, setActiveTool, setBrushDraft, setBrushResizeState, setDraggingItemId, setIsPanning, setMediaResizeState, setResizingGroupId, setSelectedItems, setSelectionBox, updateCanvasItems, visibleSelectableItemsRef, zoom])

  useEffect(() => {
    if (isPanningRef.current) {
      camera.commitCamera('pan-end')
    }
    setActiveGuides([])
    movingItemIdsRef.current = new Set()
    setSelectionBox(null)
    setIsPanning(false)
    interactionPreviewRef.current.clear()
  }, [activeTool, camera, movingItemIdsRef, setActiveGuides, setSelectionBox, setIsPanning])

  useEffect(() => {
    if (activeTool === 'brush') return
    if (brushDraft) setBrushDraft(null)
  }, [activeTool, brushDraft, setBrushDraft])

  useEffect(() => {
    const element = canvasRef.current
    if (!element) return
    const scheduler = createCanvasWheelCameraScheduler({
      camera,
      zoomRef,
      offsetRef,
      getViewportElement: () => canvasRef.current,
      setIsWheeling,
    })
    const handler = (event: WheelEvent) => {
      const isNoWheel = (event.target as HTMLElement).closest('.nowheel')
      if (event.ctrlKey || event.metaKey) {
        event.preventDefault()
      } else if (!isNoWheel) {
        event.preventDefault()
      }
      if (isNoWheel && !(event.ctrlKey || event.metaKey)) return
      scheduler.handleWheel(event)
    }
    element.addEventListener('wheel', handler, { passive: false })
    return () => {
      scheduler.cancel()
      element.removeEventListener('wheel', handler)
    }
  }, [camera, canvasRef, offsetRef, setIsWheeling, zoomRef])

  useEffect(() => {
    const handleClick = () => {
      setContextMenu(null)
      setActiveDropdown(null)
    }
    window.addEventListener('click', handleClick)
    return () => window.removeEventListener('click', handleClick)
  }, [setActiveDropdown, setContextMenu])

  const handleCanvasClick = useCallback((event: React.MouseEvent) => {
    if (activeTool !== 'text') return

    const target = event.target as HTMLElement
    const isCanvasBackground = target === canvasRef.current
      || target === canvasContentRef.current
      || target.getAttribute('data-canvas-bg') === 'true'

    if (!isCanvasBackground) return

    const position = getCanvasPointFromClient(event.clientX, event.clientY)
    if (!position) return

    handlePlaceTextAtPoint(position)
  }, [activeTool, canvasContentRef, canvasRef, getCanvasPointFromClient, handlePlaceTextAtPoint])

  useEffect(() => {
    const getModifierState = (event: KeyboardEvent) => ({
      altKey: event.altKey,
      metaKey: event.metaKey,
      ctrlKey: event.ctrlKey,
    })
    const getProtectedTextSelectionOwner = () => {
      const selection = window.getSelection()
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null

      const range = selection.getRangeAt(0)
      const commonAncestor = range.commonAncestorContainer
      const ancestorElement = commonAncestor instanceof HTMLElement
        ? commonAncestor
        : commonAncestor.parentElement

      return ancestorElement?.closest?.('[data-canvas-text-selectable="true"]') ?? null
    }

    const getCanvasShortcutContext = (target: HTMLElement | null) => {
      const isClipboardCatcher = target?.getAttribute?.('data-canvas-clipboard-catcher') === 'true'
      const isEditableTarget = !isClipboardCatcher && (
        target?.tagName === 'INPUT'
        || target?.tagName === 'TEXTAREA'
        || target?.isContentEditable
      )

      const protectedSelectionOwner = getProtectedTextSelectionOwner()
      const isProtectedSelectionShortcutContext = Boolean(protectedSelectionOwner)

      return {
        isEditableTarget,
        isProtectedSelectionShortcutContext,
      }
    }

    const resetTemporaryHandTool = () => {
      if (!temporaryHandToolRef.current) return

      temporaryHandToolRef.current = false
      const restoreTool = temporaryHandToolRestoreRef.current
      temporaryHandToolRestoreRef.current = null

      if (restoreTool) {
        setActiveTool(restoreTool)
      }
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement

      if (textEditingItemId && event.key === 'Escape') {
        event.preventDefault()
        handleCancelTextEdit()
        return
      }

      if (imageDetailItemId && event.key === 'Escape') {
        event.preventDefault()
        handleCloseImageDetails()
        return
      }

      if (textRedrawState && event.key === 'Escape') {
        event.preventDefault()
        handleCancelTextRedraw()
        return
      }

      if (cropState && event.key === 'Escape') {
        event.preventDefault()
        setCropState(null)
        return
      }

      if (spatialAngleSession && event.key === 'Escape') {
        event.preventDefault()
        handleCancelSpatialAngle(false)
        return
      }

      if (imageAnchoredImageDraft && event.key === 'Escape') {
        event.preventDefault()
        cancelImageAnchoredImageDraft(false)
        return
      }

      if (imageAnchoredVideoDraft && event.key === 'Escape') {
        event.preventDefault()
        cancelImageAnchoredVideoDraft(false)
        return
      }

      const { isEditableTarget, isProtectedSelectionShortcutContext } = getCanvasShortcutContext(target)
      if (isEditableTarget) return

      if (isProtectedSelectionShortcutContext && (
        event.ctrlKey
        || event.metaKey
        || event.key === 'Control'
        || event.key === 'Meta'
      )) {
        return
      }

      setMarkModifierState(getModifierState(event))

      if (event.code === 'Space' && !event.repeat) {
        event.preventDefault()
        if (activeToolRef.current !== 'hand' && !temporaryHandToolRef.current) {
          temporaryHandToolRestoreRef.current = activeToolRef.current
          temporaryHandToolRef.current = true
          setActiveTool('hand')
        }
        return
      }

      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        if (event.shiftKey) redo()
        else undo()
        return
      }
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'y') {
        event.preventDefault()
        redo()
        return
      }

      if (event.key === 'v' || event.key === 'V') setActiveTool('select')
      if (event.key === 'h' || event.key === 'H') setActiveTool('hand')
      if (event.key === 'm' || event.key === 'M') setActiveTool('mark')
      if (event.key === 'p' || event.key === 'P') setActiveTool('brush')
      if (event.key === 't' || event.key === 'T') setActiveTool('text')

      if ((event.ctrlKey || event.metaKey) && (event.key === '=' || event.key === '+')) {
        event.preventDefault()
        zoomIn()
      }
      if ((event.ctrlKey || event.metaKey) && event.key === '-') {
        event.preventDefault()
        zoomOut()
      }
      if ((event.ctrlKey || event.metaKey) && event.key === '0') {
        event.preventDefault()
        resetZoom()
      }
      if (event.shiftKey && event.key === '1') {
        event.preventDefault()
        handleFitView()
      }

      if ((event.key === 'Delete' || event.key === 'Backspace') && selectedItems.length > 0) {
        handleContextMenuAction('delete')
      }
      // Intentionally do NOT handle Ctrl/Cmd+V here. Letting the keydown fall
      // through lets the browser dispatch a real `paste` event, whose live
      // clipboardData is the single source of truth for internal-vs-external
      // paste (see runNativePasteFromClipboardData in CanvasWorkspaceCanvasArea).
      // Preempting it from a sticky in-memory flag is exactly what permanently
      // blocked pasting an OS / web image after a canvas copy.
      if (selectedItems.length > 0 || clipboardItems.length > 0) {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c') {
          event.preventDefault()
          if (typeof document !== 'undefined' && typeof document.execCommand === 'function') {
            const didDispatchNativeCopy = document.execCommand('copy')
            if (didDispatchNativeCopy) {
              return
            }
          }

          handleContextMenuAction('copy')
          return
        }
        if ((event.ctrlKey || event.metaKey) && event.key === ']') {
          event.preventDefault()
          if (event.altKey) handleContextMenuAction('bring_front')
          else handleContextMenuAction('bring_forward')
        }
        if ((event.ctrlKey || event.metaKey) && event.key === '[') {
          event.preventDefault()
          if (event.altKey) handleContextMenuAction('send_back')
          else handleContextMenuAction('send_backward')
        }
        if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'y') {
          event.preventDefault()
          handleContextMenuAction('toggle_visible')
        }
        if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'l') {
          event.preventDefault()
          handleContextMenuAction('lock')
        }
      }
    }

    const handleCopy = (event: ClipboardEvent) => {
      const target = event.target as HTMLElement | null
      if (selectedItems.length === 0) {
        return
      }

      const { isEditableTarget, isProtectedSelectionShortcutContext } = getCanvasShortcutContext(target)
      if (isEditableTarget || isProtectedSelectionShortcutContext) {
        return
      }

      const items = collectCanvasClipboardItems(canvasItems, selectedItems)
      if (items.length === 0) {
        return
      }

      event.preventDefault()
      writeCanvasClipboardMarkerToClipboardData(event.clipboardData, items)
      handleContextMenuAction('copy')
    }

    const handleKeyUp = (event: KeyboardEvent) => {
      setMarkModifierState(getModifierState(event))
      if (event.code === 'Space' && temporaryHandToolRef.current) {
        event.preventDefault()
        resetTemporaryHandTool()
      }
    }
    const resetModifierState = () => {
      if (isPanningRef.current) {
        camera.commitCamera('blur')
      }
      setMarkModifierState({ altKey: false, metaKey: false, ctrlKey: false })
      setIsPanning(false)
      resetTemporaryHandTool()
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('copy', handleCopy)
    window.addEventListener('keyup', handleKeyUp)
    window.addEventListener('blur', resetModifierState)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('copy', handleCopy)
      window.removeEventListener('keyup', handleKeyUp)
      window.removeEventListener('blur', resetModifierState)
    }
  }, [camera, cancelImageAnchoredImageDraft, cancelImageAnchoredVideoDraft, clipboardItems.length, cropState, handleCancelSpatialAngle, handleCancelTextEdit, handleCancelTextRedraw, handleCloseImageDetails, handleContextMenuAction, handleFitView, handlePasteClipboardImage, imageAnchoredImageDraft, imageAnchoredVideoDraft, imageDetailItemId, redo, resetZoom, selectedItems.length, setActiveTool, setCropState, setIsPanning, setMarkModifierState, spatialAngleSession, textEditingItemId, textRedrawState, undo, zoomIn, zoomOut])

  const projectedGuides = canvasRef.current
    ? projectGuidesToViewport(activeGuides, zoom, offset, {
      width: canvasRef.current.clientWidth,
      height: canvasRef.current.clientHeight,
    })
    : []

  const renderSelectionHandles = () => (
    <>
      <div style={{ position: 'absolute', top: -4, left: -4, width: 8, height: 8, borderRadius: '50%', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
      <div style={{ position: 'absolute', top: -4, right: -4, width: 8, height: 8, borderRadius: '50%', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
      <div style={{ position: 'absolute', bottom: -4, left: -4, width: 8, height: 8, borderRadius: '50%', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
      <div style={{ position: 'absolute', bottom: -4, right: -4, width: 8, height: 8, borderRadius: '50%', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
    </>
  )

  return {
    zoomIn,
    zoomOut,
    resetZoom,
    handleMouseDown,
    handleItemMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleCanvasClick,
    projectedGuides,
    renderSelectionHandles,
    interactionPreview: interactionPreviewRef.current,
  }
}
