// @ts-nocheck

import React, { useMemo } from 'react'
import { getMediaSelectionOverlayMetrics } from '../mediaSelectionResize'

export const CanvasWorkspaceGroupLayer = React.memo(function CanvasWorkspaceGroupLayer(props: any) {
  const {
    canvasItems,
    selectedItems,
    handleItemMouseDown,
    setSelectedItems,
    setContextMenu,
    setActiveContextMenuItem,
    isDark,
    getCanvasSelectionBorder,
    activeTool,
    zoom,
    offset,
    canvasRef,
    editingNameId,
    setEditingNameId,
    updateItem,
    beginTransaction,
    setActiveGuides,
    movingItemIdsRef,
    setResizingGroupId,
    resizingHandle,
    dragItemStart,
    resizingStart,
    getCanvasSelectionHandleAppearance,
    renderSnapshot,
    useWebGLRenderer,
    interactionPreview,
  } = props

  // Viewport culling for groups: memoized to avoid recalculation on unrelated prop changes
  const visibleGroups = useMemo(() => {
    if (useWebGLRenderer && renderSnapshot) {
      const overlayIds = new Set(renderSnapshot.overlayNodes.map((node: any) => node.id))
      return canvasItems.filter((item: any) => item.type === 'group' && overlayIds.has(item.id))
    }
    const _CULL_BUF = 500
    const _el = canvasRef?.current
    const _s = zoom / 100
    let _cL = -Infinity, _cR = Infinity, _cT = -Infinity, _cB = Infinity
    if (_el && _s > 0) {
      const vw = _el.clientWidth
      const vh = _el.clientHeight
      const buf = _CULL_BUF / _s
      _cL = (-vw / 2 - offset.x) / _s - buf
      _cR = (vw / 2 - offset.x) / _s + buf
      _cT = (-vh / 2 - offset.y) / _s - buf
      _cB = (vh / 2 - offset.y) / _s + buf
    }
    return canvasItems.filter((item: any) => {
      if (item.type !== 'group') return false
      if (selectedItems.includes(item.id)) return true
      if (item.is_hidden) return false
      const w = item.width || 0
      const h = item.height || 0
      return !(item.x > _cR || item.x + w < _cL || item.y > _cB || item.y + h < _cT)
    })
  }, [canvasItems, selectedItems, zoom, offset.x, offset.y, canvasRef, renderSnapshot, useWebGLRenderer])

  return (
    <>
      {visibleGroups.map((item: any) => {
        const isItemSelected = selectedItems.includes(item.id)
        const isHidden = item.is_hidden
        const selectionMetrics = getMediaSelectionOverlayMetrics(zoom)

        return (
          <React.Fragment key={item.id}>
            <div
              id={`group-fill-${item.id}`}
              onMouseDown={(e) => handleItemMouseDown(e, item.id)}
              onContextMenu={(e) => {
                e.preventDefault()
                e.stopPropagation()
                if (!selectedItems.includes(item.id)) setSelectedItems([item.id])
                setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
                setActiveContextMenuItem(null)
              }}
              style={{
                display: isHidden ? 'none' : 'block',
                position: 'absolute',
                top: item.y,
                left: item.x,
                width: item.width,
                height: item.height,
                backgroundColor: useWebGLRenderer ? 'transparent' : (item.background_color || 'var(--app-surface-muted)'),
                border: useWebGLRenderer || isItemSelected ? 'none' : '1px dotted var(--app-border-strong)',
                borderRadius: 12,
                zIndex: (item.z_index || 0) - 1,
                cursor: item.is_locked ? 'not-allowed' : (activeTool === 'hand' ? 'grab' : 'default'),
                pointerEvents: useWebGLRenderer ? 'none' : 'auto',
              }}
            />
            <div
              id={`item-${item.id}`}
              style={{
                display: isHidden ? 'none' : 'block',
                position: 'absolute',
                top: item.y,
                left: item.x,
                width: item.width,
                height: item.height,
                backgroundColor: 'transparent',
                border: isItemSelected ? getCanvasSelectionBorder(selectionMetrics.borderWidth) : 'none',
                borderRadius: 12,
                zIndex: isItemSelected ? 2147483639 : (item.z_index || 0),
                pointerEvents: 'none',
              }}
            />
            {!isHidden && (
              <div
                id={`group-label-${item.id}`}
                data-canvas-preview-resize-child="false"
                style={{
                  position: 'absolute',
                  top: item.y,
                  left: item.x,
                  width: item.width,
                  height: item.height,
                  zIndex: isItemSelected ? 2147483640 : (item.z_index || 0),
                  pointerEvents: 'none',
                }}
              >
                <div
                  style={{
                    position: 'absolute',
                    bottom: '100%',
                    left: 0,
                    marginBottom: 4,
                    fontSize: 12,
                    whiteSpace: 'nowrap',
                    padding: '1px 4px',
                    transform: `scale(${100 / zoom})`,
                    transformOrigin: 'left bottom',
                    zIndex: 100,
                    pointerEvents: 'auto',
                  }}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  {editingNameId === item.id ? (
                    <input
                      autoFocus
                      value={item.name || ''}
                      onChange={(e) => updateItem(item.id, { name: e.target.value })}
                      onBlur={() => setEditingNameId(null)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') setEditingNameId(null) }}
                      style={{
                        border: 'none',
                        background: 'transparent',
                        fontSize: 12,
                        color: 'var(--app-foreground-subtle)',
                        outline: 'none',
                        padding: '1px 4px',
                        minWidth: 40,
                      }}
                    />
                  ) : (
                    <span
                      onClick={() => setEditingNameId(item.id)}
                      onMouseDown={(e) => e.stopPropagation()}
                      style={{
                        cursor: 'text',
                        color: 'var(--app-foreground-subtle)',
                        padding: '1px 4px',
                        borderRadius: 3,
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = 'var(--app-control-hover)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'transparent'
                      }}
                    >
                      {item.name || 'group'}
                    </span>
                  )}
                </div>
              </div>
            )}

            {isItemSelected && !item.is_locked && (
              <div
                id={`group-handles-${item.id}`}
                data-canvas-preview-resize-child="false"
                style={{
                  position: 'absolute',
                  top: item.y,
                  left: item.x,
                  width: item.width,
                  height: item.height,
                  zIndex: 2147483400,
                  pointerEvents: 'none',
                }}
              >
                {['nw', 'ne', 'sw', 'se'].map((handle) => (
                  <div
                    key={handle}
                    onMouseDown={(e) => {
                      e.stopPropagation()
                      beginTransaction()
                      interactionPreview?.begin(canvasItems)
                      setActiveGuides([])
                      movingItemIdsRef.current = new Set()
                      setResizingGroupId(item.id)
                      resizingHandle.current = handle
                      dragItemStart.current = { x: e.clientX, y: e.clientY }
                      resizingStart.current = { x: 0, y: 0, w: item.width || 0, h: item.height || 0, top: item.y, left: item.x }
                    }}
                    style={{
                      position: 'absolute',
                      top: handle.includes('n') ? 0 : '100%',
                      left: handle.includes('w') ? 0 : '100%',
                      width: selectionMetrics.handleSize,
                      height: selectionMetrics.handleSize,
                      borderRadius: '50%',
                      cursor: `${handle}-resize`,
                      zIndex: 100,
                      transform: `translate(${-selectionMetrics.handleOffset}px, ${-selectionMetrics.handleOffset}px)`,
                      boxShadow: 'var(--app-shadow-control)',
                      pointerEvents: 'auto',
                      ...getCanvasSelectionHandleAppearance({ borderWidth: selectionMetrics.borderWidth, isDark }),
                    }}
                  />
                ))}
              </div>
            )}
          </React.Fragment>
        )
      })}
    </>
  )
})
