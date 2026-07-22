// @ts-nocheck

import React from 'react'
import { CanvasTextItem } from './CanvasTextItem'

function areTextItemPropsEqual(prev: any, next: any) {
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

const CanvasWorkspaceTextRenderItemInner = React.memo(function CanvasWorkspaceTextRenderItemInner(props: any) {
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
