import React from 'react'
import type { ComponentProps, CSSProperties, MouseEvent, MutableRefObject } from 'react'
import type { CanvasItem } from '@/api/endpoints/projects'
import type { MediaResizeState } from '../types'
import type { getMediaSelectionOverlayMetrics } from '../mediaSelectionResize'
import type { getCanvasSelectionBorder, getCanvasSelectionHandleAppearance } from '../selectionStyles'
import { CanvasTextItem } from './CanvasTextItem'

type TextItemProps = ComponentProps<typeof CanvasTextItem>
interface CanvasWorkspaceTextRenderItemProps {
  item: CanvasItem
  normalizedTextItem: CanvasItem | null
  isHidden: boolean
  isItemSelected: boolean
  actualWidth: number
  actualHeight: number
  selectedItems: string[]
  clampCanvasStackZIndex: (value?: number) => number
  activeTool: string
  textEditingItemId: string | null
  handleStartTextEdit: TextItemProps['onStartEdit']
  handleCommitTextEdit: TextItemProps['onCommitEdit']
  handleCancelTextEdit: TextItemProps['onCancelEdit']
  handleItemMouseDown: (event: MouseEvent<HTMLDivElement>, itemId: string) => void
  setSelectedItems: (items: string[]) => void
  setContextMenu: (menu: { x: number; y: number; type: 'item' }) => void
  setActiveContextMenuItem: (id: string | null) => void
  getCanvasSelectionBorder: typeof getCanvasSelectionBorder
  getCanvasSelectionHandleAppearance: (options: Parameters<typeof getCanvasSelectionHandleAppearance>[0]) => CSSProperties
  beginTransaction: () => void
  setActiveGuides: (guides: []) => void
  movingItemIdsRef: MutableRefObject<Set<string>>
  setMediaResizeState: (state: MediaResizeState) => void
  resizingHandle: MutableRefObject<string | null>
  dragItemStart: MutableRefObject<{ x: number; y: number } | null>
  resizingStart: MutableRefObject<{ x: number; y: number; w: number; h: number; top: number; left: number } | null>
  mediaSelectionMetrics: Pick<ReturnType<typeof getMediaSelectionOverlayMetrics>, 'handleSize' | 'handleOffset' | 'borderWidth'>
  isDark: boolean
  interactionPreview?: { begin: (items: CanvasItem[]) => void }
  canvasItems: CanvasItem[]
}

function areTextItemPropsEqual(prev: CanvasWorkspaceTextRenderItemProps, next: CanvasWorkspaceTextRenderItemProps) {
  if (prev.item !== next.item) return false
  if (prev.normalizedTextItem !== next.normalizedTextItem) return false
  if (prev.isHidden !== next.isHidden) return false
  if (prev.isItemSelected !== next.isItemSelected) return false
  if (prev.actualWidth !== next.actualWidth) return false
  if (prev.actualHeight !== next.actualHeight) return false

  // Selected text items need zoom-dependent UI (handles)
  if (prev.isItemSelected || next.isItemSelected) return false

  // Non-selected: only visual props
  if (prev.isDark !== next.isDark) return false
  if (prev.activeTool !== next.activeTool) return false
  if (prev.textEditingItemId !== next.textEditingItemId) return false

  return true
}

const CanvasWorkspaceTextRenderItemInner = React.memo(function CanvasWorkspaceTextRenderItemInner(props: CanvasWorkspaceTextRenderItemProps) {
  const {
    item,
    normalizedTextItem,
    isHidden,
    isItemSelected,
    actualWidth,
    actualHeight,
    selectedItems,
    clampCanvasStackZIndex,
    activeTool,
    textEditingItemId,
    handleStartTextEdit,
    handleCommitTextEdit,
    handleCancelTextEdit,
    handleItemMouseDown,
    setSelectedItems,
    setContextMenu,
    setActiveContextMenuItem,
    getCanvasSelectionBorder,
    beginTransaction,
    setActiveGuides,
    movingItemIdsRef,
    setMediaResizeState,
    resizingHandle,
    dragItemStart,
    resizingStart,
    mediaSelectionMetrics,
    getCanvasSelectionHandleAppearance,
    isDark,
    interactionPreview,
    canvasItems,
  } = props

  if (item.type !== 'text' || !normalizedTextItem) {
    return null
  }

  const showTextSelectionOverlay = isItemSelected && selectedItems.length === 1 && !item.is_locked

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
          cursor: item.is_locked ? 'default' : (activeTool === 'hand' ? 'inherit' : (activeTool === 'brush' ? 'crosshair' : 'text')),
        }}
        onClick={(e) => {
          e.stopPropagation()
          if (item.is_locked) return
          if (isItemSelected) {
            handleStartTextEdit(item.id)
          } else if (!selectedItems.includes(item.id)) {
            setSelectedItems([item.id])
          }
        }}
        onMouseDown={(e) => handleItemMouseDown(e, item.id)}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (!selectedItems.includes(item.id)) setSelectedItems([item.id])
          setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
          setActiveContextMenuItem(null)
        }}
      >
        <div
          style={{
            width: actualWidth,
            height: actualHeight,
            padding: 12,
            outline: showTextSelectionOverlay ? getCanvasSelectionBorder(mediaSelectionMetrics.borderWidth) : 'none',
            borderRadius: 8,
            boxSizing: 'border-box',
            backgroundColor: textEditingItemId === item.id ? 'var(--app-surface-muted)' : 'transparent',
          }}
        >
          <CanvasTextItem
            item={normalizedTextItem}
            isEditing={textEditingItemId === item.id}
            onStartEdit={handleStartTextEdit}
            onCommitEdit={handleCommitTextEdit}
            onCancelEdit={handleCancelTextEdit}
          />
        </div>

        {showTextSelectionOverlay && (
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
}, areTextItemPropsEqual)

export { CanvasWorkspaceTextRenderItemInner as CanvasWorkspaceTextRenderItem }
