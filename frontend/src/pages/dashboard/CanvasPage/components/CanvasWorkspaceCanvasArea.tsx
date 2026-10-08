
import React from 'react'
import { CanvasBrushDraftPreview } from './CanvasBrushDraftPreview'
import { CanvasSceneLayer } from './CanvasSceneLayer'
import { CanvasWorkspaceFloatingPanels } from './CanvasWorkspaceFloatingPanels'
import { CanvasWorkspaceGroupLayer } from './CanvasWorkspaceGroupLayer'
import { CanvasWorkspaceItemLayer } from './CanvasWorkspaceItemLayer'
import { CanvasWorkspaceMultiSelectToolbar } from './CanvasWorkspaceMultiSelectToolbar'
import {
  createCanvasRenderSnapshot,
  getCanvasRendererPreference,
} from '../canvasRenderModel'
import { clipboardDataHasCanvasClipboardMarker } from '../canvasClipboard'
import { getClipboardImageFile } from '../clipboardImage'

import type { ComponentProps, ComponentType, MouseEventHandler, RefObject } from 'react'
import type { CanvasItem } from '@/api/endpoints/projects'
import type { CanvasWebGLStage as CanvasWebGLStageView } from './CanvasWebGLStage'
import type { BrushDraftState } from '../types'

type StageProps = ComponentProps<typeof CanvasWebGLStageView>
export type CanvasWorkspaceCanvasAreaProps = ComponentProps<typeof CanvasWorkspaceItemLayer>
  & Omit<ComponentProps<typeof CanvasWorkspaceGroupLayer>, 'canvasRef'>
  & ComponentProps<typeof CanvasWorkspaceFloatingPanels>
  & Omit<ComponentProps<typeof CanvasWorkspaceMultiSelectToolbar>, 'canvasRef'>
  & {
    canvasContentRef: RefObject<HTMLDivElement>
    handleMouseDown: MouseEventHandler<HTMLDivElement>
    handleMouseMove: MouseEventHandler<HTMLDivElement>
    handleMouseUp: MouseEventHandler<HTMLDivElement>
    handleCanvasClick: MouseEventHandler<HTMLDivElement>
    handleCanvasPaste?: (file: File) => void
    handlePlaceTextAtPoint?: (point: { x: number; y: number }) => void
    isPanning?: boolean
    isWheeling?: boolean
    isCanvasStale?: boolean
    brushDraft: BrushDraftState | null
    clipboardItems?: CanvasItem[]
    clipboardSource?: 'internal' | 'external' | null
    canvasCamera?: StageProps['canvasCamera']
    interactionPreview?: StageProps['interactionPreview']
    webGLStageComponent?: ComponentType<StageProps>
    projectId?: number | null
  }

const CanvasWebGLStage = React.lazy(() => import('./CanvasWebGLStage').then((module) => ({
  default: module.CanvasWebGLStage,
})))

function isEditableElement(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false
  }

  const tagName = target.tagName
  return tagName === 'INPUT' || tagName === 'TEXTAREA' || target.isContentEditable
}

function isProtectedCanvasTextTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false
  }

  return target.closest('[data-canvas-text-selectable="true"]') != null
}

function shouldPreserveCanvasFocusTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false
  }

  if (isProtectedCanvasTextTarget(target)) {
    return true
  }

  if (target.getAttribute('data-canvas-clipboard-catcher') === 'true') {
    return true
  }

  const interactiveAncestor = target.closest('input, textarea, select, button, [contenteditable="true"]')
  return interactiveAncestor != null
}

function isCanvasBackgroundTarget(target: EventTarget | null, canvasElement: HTMLElement | null, contentElement: HTMLElement | null) {
  if (!(target instanceof HTMLElement)) {
    return false
  }
  return target === canvasElement
    || target === contentElement
    || target.getAttribute('data-canvas-bg') === 'true'
    || target.getAttribute('data-testid') === 'canvas-webgl-stage'
}

function getCanvasDomItemId(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return null
  }

  return target.closest('[data-canvas-item-id]')?.getAttribute('data-canvas-item-id') ?? null
}

export const CanvasWorkspaceCanvasArea = React.memo(function CanvasWorkspaceCanvasArea(props: CanvasWorkspaceCanvasAreaProps) {
  const [isSceneReady, setIsSceneReady] = React.useState(false)
  const [webglFallback, setWebglFallback] = React.useState(false)
  const [hoverDomItemId, setHoverDomItemId] = React.useState<string | null>(null)
  const [viewportSize, setViewportSize] = React.useState({ width: 0, height: 0 })
  const { canvasRef, handleMouseDown, handleMouseMove, handleMouseUp, setContextMenu, setSelectedItems, setActiveContextMenuItem, handleCanvasClick, isPanning, activeTool, MARK_CURSOR, canvasContentRef, brushDraft } = props
  const isCanvasStale = Boolean(props.isCanvasStale)
  const clipboardCatcherRef = React.useRef<HTMLDivElement | null>(null)
  const hasInternalClipboardPasteIntent = Boolean(
    props.clipboardSource === 'internal'
    && Array.isArray(props.clipboardItems)
    && props.clipboardItems.length > 0,
  )
  React.useEffect(() => {
    const element = canvasRef?.current
    if (!element) return undefined

    const measure = () => {
      const rect = element.getBoundingClientRect()
      const width = Math.max(0, Math.round(element.clientWidth || rect.width || 0))
      const height = Math.max(0, Math.round(element.clientHeight || rect.height || 0))
      setViewportSize((current) => (
        current.width === width && current.height === height
          ? current
          : { width, height }
      ))
    }

    measure()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    observer?.observe(element)
    window.addEventListener('resize', measure)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [canvasRef])

  const rendererPreference = getCanvasRendererPreference()
  const useWebGLRenderer = rendererPreference === 'webgl' && !webglFallback
  const CanvasWebGLStageComponent = props.webGLStageComponent || CanvasWebGLStage
  const renderSnapshot = React.useMemo(() => createCanvasRenderSnapshot({
    canvasItems: props.canvasItems,
    selectedItems: props.selectedItems,
    marks: props.marks,
    cropState: props.cropState,
    textEditingItemId: props.textEditingItemId,
    textRedrawExtractingItemIds: props.textRedrawExtractingItemIds,
    imageDetailItemId: props.imageDetailItemId,
    imageAnchoredImageDraft: props.imageAnchoredImageDraft,
    imageAnchoredVideoDraft: props.imageAnchoredVideoDraft,
    hoverDomItemId,
    zoom: props.zoom,
    offset: props.offset,
    viewport: viewportSize,
    getItemDims: props.getItemDims,
  }), [
    props.canvasItems,
    props.selectedItems,
    props.marks,
    props.cropState,
    props.textEditingItemId,
    props.textRedrawExtractingItemIds,
    props.imageDetailItemId,
    props.imageAnchoredImageDraft,
    props.imageAnchoredVideoDraft,
    hoverDomItemId,
    props.zoom,
    props.offset,
    viewportSize,
    props.getItemDims,
  ])
  const getCanvasPointFromClient = React.useCallback((clientX: number, clientY: number) => {
    const element = props.canvasRef?.current
    if (!element) return null
    const rect = element.getBoundingClientRect()
    const camera = props.canvasCamera?.getCamera?.() ?? {
      zoom: props.zoom,
      offset: props.offset,
    }
    const scale = camera.zoom / 100
    if (scale <= 0) return null
    return {
      x: (clientX - rect.left - rect.width / 2 - camera.offset.x) / scale,
      y: (clientY - rect.top - rect.height / 2 - camera.offset.y) / scale,
    }
  }, [props.canvasCamera, props.canvasRef, props.offset, props.zoom])
  const getWebGLHitNode = React.useCallback((event: { clientX: number; clientY: number; target: EventTarget | null }) => {
    if (!useWebGLRenderer) return null
    if (!isCanvasBackgroundTarget(event.target, props.canvasRef?.current ?? null, canvasContentRef?.current ?? null)) return null
    const point = getCanvasPointFromClient(event.clientX, event.clientY)
    if (!point) return null
    const node = renderSnapshot.hitTest(point)
    if (!node) return null
    if (node.overlayKind !== 'none' && node.type !== 'group') return null
    return node
  }, [canvasContentRef, getCanvasPointFromClient, props.canvasRef, renderSnapshot, useWebGLRenderer])
  const routeWebGLItemClick = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const node = getWebGLHitNode(event)
    if (!node) return false
    const item = node.item
    props.setContextMenu(null)
    props.setActiveContextMenuItem(null)
    if (item.is_locked) return true
    const isImageItem = item.type === 'image' || item.type === 'image_generator'
    if ((props.activeTool === 'mark' || (props.activeTool === 'select' && props.isMarkModifierPressed?.({
      altKey: event.altKey,
      metaKey: event.metaKey,
      ctrlKey: event.ctrlKey,
    }))) && isImageItem && item.url) {
      props.addMark?.(item, event)
      return true
    }
    if (props.activeTool === 'select') {
      props.setSelectedItems([item.id])
      return true
    }
    return false
  }, [getWebGLHitNode, props])
  const routeWebGLItemMouseDown = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const node = getWebGLHitNode(event)
    if (!node) return false
    if (props.activeTool === 'hand') return false
    if (props.activeTool === 'mark') return true
    if (props.activeTool === 'select' && (node.type === 'image' || node.type === 'image_generator') && props.isMarkModifierPressed?.({
      altKey: event.altKey,
      metaKey: event.metaKey,
      ctrlKey: event.ctrlKey,
    })) {
      return true
    }
    if (!node.item.is_locked) {
      props.handleItemMouseDown(event, node.id)
    }
    return true
  }, [getWebGLHitNode, props])
  const routeWebGLItemContextMenu = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const node = getWebGLHitNode(event)
    if (!node) return false
    event.preventDefault()
    event.stopPropagation()
    if (!props.selectedItems.includes(node.id)) {
      props.setSelectedItems([node.id])
    }
    props.setContextMenu({ x: event.clientX, y: event.clientY, type: 'item' })
    props.setActiveContextMenuItem(null)
    return true
  }, [getWebGLHitNode, props])
  const routeWebGLItemDoubleClick = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const node = getWebGLHitNode(event)
    if (!node) return false
    if (node.type !== 'image' || !node.item.url) return false
    event.stopPropagation()
    props.handleAppendImageMentionToChat?.(node.id)
    return true
  }, [getWebGLHitNode, props])
  const handleCanvasMouseMove = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    const hoveredDomItemId = getCanvasDomItemId(event.target)
    if (hoverDomItemId && hoveredDomItemId === hoverDomItemId) {
      handleMouseMove(event)
      return
    }

    const node = getWebGLHitNode(event)
    const nextHoverDomItemId = node && (node.type === 'video' || node.type === 'video_generator')
      ? node.id
      : null
    setHoverDomItemId((current) => current === nextHoverDomItemId ? current : nextHoverDomItemId)
    handleMouseMove(event)
  }, [getWebGLHitNode, handleMouseMove, hoverDomItemId])
  const handleCanvasMouseLeave = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    setHoverDomItemId(null)
    handleMouseUp(event)
  }, [handleMouseUp])

  // Single source of truth for "what does this paste actually contain?".
  // Order matters: the live clipboard wins over any in-memory copy intent, so a
  // stale internal canvas copy can never permanently block pasting an OS / web image.
  const { handleCanvasPaste, handleContextMenuAction } = props
  const runNativePasteFromClipboardData = React.useCallback((clipboardData: DataTransfer | null | undefined) => {
    if (isCanvasStale) return true
    // 1) Our own canvas marker travels through the system clipboard → internal duplicate paste.
    if (clipboardDataHasCanvasClipboardMarker(clipboardData)) {
      handleContextMenuAction?.('paste')
      return true
    }
    // 2) A real image on the clipboard (copied from the OS or a web page) → external import.
    //    This MUST be checked before any in-memory internal fallback below.
    const imageFile = getClipboardImageFile(clipboardData)
    if (imageFile) {
      handleCanvasPaste?.(imageFile)
      return true
    }
    // 3) Nothing recognizable on the clipboard, but we still hold an in-memory canvas
    //    copy (e.g. the system clipboard write was blocked) → internal fallback.
    if (hasInternalClipboardPasteIntent) {
      handleContextMenuAction?.('paste')
      return true
    }
    return false
  }, [hasInternalClipboardPasteIntent, isCanvasStale, handleCanvasPaste, handleContextMenuAction])

  React.useEffect(() => {
    const handleWindowPaste = (event: ClipboardEvent) => {
      if (event.defaultPrevented) {
        return
      }
      if (isEditableElement(event.target) || isEditableElement(document.activeElement)) {
        return
      }
      if (runNativePasteFromClipboardData(event.clipboardData)) {
        event.preventDefault()
      }
    }

    window.addEventListener('paste', handleWindowPaste)
    return () => {
      window.removeEventListener('paste', handleWindowPaste)
    }
  }, [runNativePasteFromClipboardData])

  return (
    <div
      ref={canvasRef}
      tabIndex={0}
      onMouseDownCapture={(event) => {
        if (isCanvasStale) {
          event.preventDefault()
          event.stopPropagation()
          return
        }
        if (shouldPreserveCanvasFocusTarget(event.target)) {
          return
        }

        if (clipboardCatcherRef.current) {
          clipboardCatcherRef.current.focus({ preventScroll: true })
        }
      }}
      onMouseDown={(event) => {
        if (isCanvasStale) {
          event.preventDefault()
          event.stopPropagation()
          return
        }
        if (shouldPreserveCanvasFocusTarget(event.target)) {
          handleMouseDown(event)
          return
        }

        if (clipboardCatcherRef.current) {
          clipboardCatcherRef.current.focus({ preventScroll: true })
        } else {
          event.currentTarget.focus()
        }
        if (routeWebGLItemMouseDown(event)) {
          return
        }
        handleMouseDown(event)
      }}
      onMouseMove={isCanvasStale ? undefined : handleCanvasMouseMove}
      onMouseUp={isCanvasStale ? undefined : handleMouseUp}
      onMouseLeave={isCanvasStale ? undefined : handleCanvasMouseLeave}
      onContextMenu={(e) => {
        e.preventDefault()
        if (isCanvasStale) {
          e.stopPropagation()
          return
        }
        if (routeWebGLItemContextMenu(e)) {
          return
        }
        setContextMenu({ x: e.clientX, y: e.clientY, type: 'canvas' })
        setSelectedItems([])
        setActiveContextMenuItem(null)
      }}
      onClick={(event) => {
        if (isCanvasStale) {
          event.preventDefault()
          event.stopPropagation()
          return
        }
        if (routeWebGLItemClick(event)) {
          return
        }
        handleCanvasClick(event)
      }}
      onDoubleClick={(event) => {
        if (isCanvasStale) {
          event.preventDefault()
          event.stopPropagation()
          return
        }
        routeWebGLItemDoubleClick(event)
      }}
      onPaste={(event) => {
        if (event.isDefaultPrevented()) return
        if (isEditableElement(event.target) || isEditableElement(document.activeElement)) return
        if (runNativePasteFromClipboardData(event.clipboardData)) {
          event.preventDefault()
        }
      }}
      style={{
        flex: 1,
        outline: 'none',
        cursor: isPanning
          ? 'grabbing'
          : activeTool === 'hand'
            ? 'grab'
            : activeTool === 'brush'
              ? 'crosshair'
              : activeTool === 'mark'
                ? MARK_CURSOR
                : 'default',
        position: 'relative',
        overflow: 'hidden',
        backgroundColor: 'var(--app-bg-soft)',
        userSelect: 'none',
        WebkitUserSelect: 'none',
      }}
    >
      <div
        ref={clipboardCatcherRef}
        contentEditable
        suppressContentEditableWarning
        tabIndex={-1}
        aria-hidden="true"
        data-canvas-clipboard-catcher="true"
        onPaste={(event) => {
          event.preventDefault()
          if (clipboardCatcherRef.current) {
            clipboardCatcherRef.current.textContent = ''
          }
          // Decide from the live clipboard. If nothing matched, still attempt an
          // internal paste so the context-menu / system-clipboard path can resolve it.
          if (!runNativePasteFromClipboardData(event.clipboardData)) {
            handleContextMenuAction?.('paste')
          }
        }}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && !['v', 'V', 'c', 'C', 'x', 'X', 'a', 'A'].includes(event.key)) {
            return
          }
          if (!(event.ctrlKey || event.metaKey) && event.key.length === 1) {
            event.preventDefault()
          }
        }}
        onInput={(event) => {
          (event.currentTarget as HTMLDivElement).textContent = ''
        }}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: 1,
          height: 1,
          opacity: 0,
          pointerEvents: 'none',
          outline: 'none',
          overflow: 'hidden',
          whiteSpace: 'nowrap',
          zIndex: -1,
        }}
      />
      {useWebGLRenderer ? (
        <React.Suspense fallback={null}>
          {React.createElement(CanvasWebGLStageComponent, {
            canvasRef: props.canvasRef,
            canvasCamera: props.canvasCamera,
            projectId: props.projectId,
            nodes: renderSnapshot.webglNodes,
            zoom: props.zoom,
            offset: props.offset,
            isDark: props.isDark,
            isInteracting: props.isPanning || props.isWheeling,
            interactionPreview: props.interactionPreview,
            onReadyChange: setIsSceneReady,
            onFallback: () => setWebglFallback(true),
          })}
        </React.Suspense>
      ) : (
        <CanvasSceneLayer
          canvasRef={props.canvasRef}
          canvasItems={props.canvasItems}
          selectedItems={props.selectedItems}
          marks={props.marks}
          cropState={props.cropState}
          textRedrawExtractingItemIds={props.textRedrawExtractingItemIds}
          zoom={props.zoom}
          offset={props.offset}
          isDark={props.isDark}
          getItemDims={props.getItemDims}
          canvasCamera={props.canvasCamera}
          onReadyChange={setIsSceneReady}
        />
      )}

      <div
        ref={canvasContentRef}
        style={{
          position: 'absolute',
          left: '50%',
          top: '50%',
          transformOrigin: 'center center',
          transition: 'none',
        }}
      >
        <div data-canvas-bg="true" style={{ display: 'flex', gap: 80, alignItems: 'flex-start' }}>
          <CanvasWorkspaceGroupLayer
            canvasItems={props.canvasItems}
            renderSnapshot={renderSnapshot}
            useWebGLRenderer={useWebGLRenderer}
            selectedItems={props.selectedItems}
            handleItemMouseDown={props.handleItemMouseDown}
            setSelectedItems={props.setSelectedItems}
            setContextMenu={props.setContextMenu}
            setActiveContextMenuItem={props.setActiveContextMenuItem}
            isDark={props.isDark}
            getCanvasSelectionBorder={props.getCanvasSelectionBorder}
            activeTool={props.activeTool}
            zoom={props.zoom}
            offset={props.offset}
            canvasRef={props.canvasRef}
            editingNameId={props.editingNameId}
            setEditingNameId={props.setEditingNameId}
            updateItem={props.updateItem}
            beginTransaction={props.beginTransaction}
            setActiveGuides={props.setActiveGuides}
            movingItemIdsRef={props.movingItemIdsRef}
            setResizingGroupId={props.setResizingGroupId}
            resizingHandle={props.resizingHandle}
            dragItemStart={props.dragItemStart}
            resizingStart={props.resizingStart}
            getCanvasSelectionHandleAppearance={props.getCanvasSelectionHandleAppearance}
          />
          <CanvasWorkspaceItemLayer
            {...props}
            isSceneReady={isSceneReady}
            renderSnapshot={renderSnapshot}
            useWebGLRenderer={useWebGLRenderer}
            activeVideoPreviewItemId={hoverDomItemId}
          />
        </div>

        {brushDraft?.points?.length && (
          <div style={{ position: 'absolute', inset: 0, zIndex: 2147483500, pointerEvents: 'none', opacity: 0.92, overflow: 'visible' }}>
            <CanvasBrushDraftPreview points={brushDraft.points} brushColor={brushDraft.brushColor} brushSize={brushDraft.brushSize} />
          </div>
        )}
      </div>

      <CanvasWorkspaceFloatingPanels
        {...props}
      />
      {!props.isPanning && (
        <CanvasWorkspaceMultiSelectToolbar
          selectedItems={props.selectedItems}
          canvasItems={props.canvasItems}
          getItemDims={props.getItemDims}
          canvasRef={props.canvasRef}
          zoom={props.zoom}
          offset={props.offset}
          handleItemMouseDown={props.handleItemMouseDown}
          setContextMenu={props.setContextMenu}
          setActiveContextMenuItem={props.setActiveContextMenuItem}
          getCanvasSelectionBorder={props.getCanvasSelectionBorder}
          activeTool={props.activeTool}
          getCanvasSelectionHandleAppearance={props.getCanvasSelectionHandleAppearance}
          isDark={props.isDark}
          handleUngroup={props.handleUngroup}
          setMultiSelectToolsOpen={props.setMultiSelectToolsOpen}
          multiSelectToolsOpen={props.multiSelectToolsOpen}
          t={props.t}
          setGroupBackgroundColor={props.setGroupBackgroundColor}
          handleCreateGroup={props.handleCreateGroup}
          handleMergeLayers={props.handleMergeLayers}
          handleAlign={props.handleAlign}
          handleAutoArrange={props.handleAutoArrange}
          handleSpacing={props.handleSpacing}
          handleBulkExport={props.handleBulkExport}
          handleContextMenuAction={props.handleContextMenuAction}
        />
      )}
    </div>
  )
})
