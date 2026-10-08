
import React from 'react'
import { ChevronDown, Copy, Layers } from 'lucide-react'

import type { Dispatch, RefObject, SetStateAction } from 'react'
import type { TFunction } from 'i18next'
import type { CanvasItem } from '@/api/endpoints/projects'
import type { CanvasSelectionProps } from './canvasSelectionContracts'

type MultiSelectPanel = 'align' | 'spacing' | 'bgcolor' | null
interface CanvasWorkspaceMultiSelectToolbarProps extends CanvasSelectionProps {
  getItemDims: (item: CanvasItem) => { width: number; height: number }
  canvasRef: RefObject<{ getBoundingClientRect: () => { left: number; top: number; width: number; height: number } }>
  handleUngroup: (id: string) => void
  setMultiSelectToolsOpen: Dispatch<SetStateAction<MultiSelectPanel>>
  multiSelectToolsOpen: MultiSelectPanel
  t: TFunction
  setGroupBackgroundColor: (id: string, color: string) => void
  handleCreateGroup: () => void
  handleMergeLayers: () => void
  handleAlign: (key: string) => void
  handleAutoArrange: () => void
  handleSpacing: (key: string) => void
  handleContextMenuAction: (action: string) => void
  handleBulkExport?: () => void
}

export const CanvasWorkspaceMultiSelectToolbar = React.memo(function CanvasWorkspaceMultiSelectToolbar(props: CanvasWorkspaceMultiSelectToolbarProps) {
  const { selectedItems, canvasItems, getItemDims, canvasRef, zoom, offset, handleItemMouseDown, setContextMenu, setActiveContextMenuItem, getCanvasSelectionBorder, activeTool, getCanvasSelectionHandleAppearance, isDark, handleUngroup, setMultiSelectToolsOpen, multiSelectToolsOpen, t, setGroupBackgroundColor, handleCreateGroup, handleMergeLayers, handleAlign, handleAutoArrange, handleSpacing, handleContextMenuAction } = props

  if (selectedItems.length === 0) return null

  const isSingleGroup = selectedItems.length === 1 && canvasItems.find((i) => i.id === selectedItems[0])?.type === 'group'
  if (selectedItems.length === 1 && !isSingleGroup) return null

  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  let hasItems = false

  selectedItems.forEach((id: string) => {
    const item = canvasItems.find((candidate) => candidate.id === id)
    if (item && !item.is_hidden) {
      const dims = getItemDims(item)
      const w = item.width || dims.width
      const h = item.height || dims.height
      minX = Math.min(minX, item.x)
      minY = Math.min(minY, item.y)
      maxX = Math.max(maxX, item.x + w)
      maxY = Math.max(maxY, item.y + h)
      hasItems = true
    }
  })

  if (!hasItems) return null

  const rect = canvasRef.current?.getBoundingClientRect()
  if (!rect) return null

  const scale = zoom / 100
  const screenX = (minX * scale) + rect.width / 2 + offset.x
  const screenY = (minY * scale) + rect.height / 2 + offset.y
  const screenWidth = (maxX - minX) * scale
  const screenHeight = (maxY - minY) * scale
  const isMulti = selectedItems.length > 1
  const previewItemId = selectedItems.length === 1 ? selectedItems[0] : null

  return (
    <div
      id={isMulti ? 'canvas-screen-preview-selection' : (previewItemId ? `canvas-screen-preview-${previewItemId}` : undefined)}
      data-canvas-preview-scale={isMulti || previewItemId ? scale : undefined}
      onMouseDown={(e) => {
        if (isMulti) {
          handleItemMouseDown(e, selectedItems[0])
        }
      }}
      onContextMenu={(e) => {
        if (isMulti) {
          e.preventDefault()
          e.stopPropagation()
          setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
          setActiveContextMenuItem(null)
        }
      }}
      style={{
        position: 'absolute',
        left: screenX,
        top: screenY,
        width: screenWidth,
        height: screenHeight,
        border: isMulti ? getCanvasSelectionBorder(1.5) : 'none',
        pointerEvents: isMulti ? 'auto' : 'none',
        zIndex: 1000,
        cursor: isMulti ? (activeTool === 'hand' ? 'grab' : 'move') : 'inherit',
      }}
    >
      {isMulti && (
        <>
          <div style={{ position: 'absolute', top: 0, left: 0, width: 10, height: 10, borderRadius: '50%', transform: 'translate(-50%, -50%)', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
          <div style={{ position: 'absolute', top: 0, right: 0, width: 10, height: 10, borderRadius: '50%', transform: 'translate(50%, -50%)', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
          <div style={{ position: 'absolute', bottom: 0, left: 0, width: 10, height: 10, borderRadius: '50%', transform: 'translate(-50%, 50%)', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
          <div style={{ position: 'absolute', bottom: 0, right: 0, width: 10, height: 10, borderRadius: '50%', transform: 'translate(50%, 50%)', boxShadow: 'var(--app-shadow-control)', ...getCanvasSelectionHandleAppearance({ borderWidth: 1.5, isDark }) }} />
        </>
      )}

      <div
        style={{
          position: 'absolute',
          bottom: '100%',
          left: '50%',
          transform: 'translateX(-50%)',
          marginBottom: 16,
          backgroundColor: 'var(--app-glass)',
          borderRadius: 12,
          padding: '6px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          boxShadow: 'var(--app-shadow-panel)',
          border: '1px solid var(--app-border)',
          pointerEvents: 'auto',
          whiteSpace: 'nowrap',
          zIndex: 1001,
        }}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {selectedItems.length === 1 && canvasItems.find((i) => i.id === selectedItems[0])?.type === 'group' ? (
          <>
            <div onClick={() => handleUngroup(selectedItems[0])} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', transition: 'background 0.2s' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 3"><rect x="3" y="3" width="18" height="18" rx="2" /></svg>
              <span style={{ fontSize: 13, color: 'var(--app-foreground)', fontWeight: 500 }}>{t('canvas.context_menu.ungroup')}</span>
            </div>
            <div style={{ position: 'relative' }}>
              <div onClick={(e) => { e.stopPropagation(); setMultiSelectToolsOpen((o) => o === 'bgcolor' ? null : 'bgcolor') }} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', transition: 'background 0.2s', backgroundColor: multiSelectToolsOpen === 'bgcolor' ? 'var(--app-control-hover)' : 'transparent' }}>
                <div style={{ width: 14, height: 14, borderRadius: 3, border: '1px solid var(--app-border)', backgroundColor: canvasItems.find((i) => i.id === selectedItems[0])?.background_color || 'var(--app-surface-muted)' }} />
                <span style={{ fontSize: 13, color: 'var(--app-foreground)', fontWeight: 500 }}>{t('canvas.generator.background_color')}</span>
                <ChevronDown size={12} color="var(--app-foreground-subtle)" />
              </div>
              {multiSelectToolsOpen === 'bgcolor' && (
                <div style={{ position: 'absolute', bottom: '100%', left: 0, marginBottom: 8, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: '12px', display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 8, zIndex: 1002 }}>
                  {['transparent', '#f0f2f5', '#fff', '#000', '#ff4d4f', '#faad14', '#52c41a', '#1890ff', '#722ed1', '#eb2f96', '#1677ff11', '#1677ff33', '#1677ff', '#00000000', '#262626'].map((color) => (
                    <div key={color} onClick={() => { setGroupBackgroundColor(selectedItems[0], color); setMultiSelectToolsOpen(null) }} style={{ width: 24, height: 24, borderRadius: 4, cursor: 'pointer', backgroundColor: color, border: '1px solid var(--app-border)', boxSizing: 'border-box', position: 'relative', overflow: 'hidden' }}>
                      {color === 'transparent' && <div style={{ position: 'absolute', top: '50%', left: '-20%', width: '140%', height: 1, backgroundColor: 'red', transform: 'rotate(45deg)' }} />}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : (
          <>
            <div onClick={() => handleCreateGroup()} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', transition: 'background 0.2s' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="3 3"><rect x="3" y="3" width="18" height="18" rx="2" /><circle cx="12" cy="12" r="3" fill="currentColor" /></svg>
              <span style={{ fontSize: 13, color: 'var(--app-foreground)', fontWeight: 500 }}>{t('canvas.context_menu.group')}</span>
            </div>
            <div onClick={() => handleMergeLayers()} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 10px', borderRadius: 8, cursor: 'pointer', transition: 'background 0.2s' }}>
              <Layers size={14} color="var(--app-foreground)" />
              <span style={{ fontSize: 13, color: 'var(--app-foreground)', fontWeight: 500 }}>{t('canvas.context_menu.merge_layers')}</span>
            </div>
          </>
        )}
        <div style={{ width: 1, height: 20, backgroundColor: 'var(--app-border)', margin: '0 4px' }} />
        <div style={{ position: 'relative' }}>
          <div onClick={(e) => { e.stopPropagation(); setMultiSelectToolsOpen((o) => o === 'align' ? null : 'align') }} style={{ padding: 6, borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 2, transition: 'background 0.2s', backgroundColor: multiSelectToolsOpen === 'align' ? 'var(--app-control-hover)' : 'transparent' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="4" width="2" height="16" /><rect x="8" y="7" width="12" height="3" rx="1" /><rect x="8" y="14" width="8" height="3" rx="1" /></svg>
            <ChevronDown size={12} color="var(--app-foreground-subtle)" style={{ transform: multiSelectToolsOpen === 'align' ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          </div>
          {multiSelectToolsOpen === 'align' && (
            <div style={{ position: 'absolute', bottom: '100%', left: 0, marginBottom: 8, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: '6px 0', minWidth: 180, zIndex: 1002 }}>
              {['left', 'center', 'right', 'top', 'middle', 'bottom'].map((key) => (
                <div key={key} onClick={() => { handleAlign(key); setMultiSelectToolsOpen(null) }} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px', cursor: 'pointer', transition: 'background 0.2s', color: 'var(--app-foreground)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>{t(`canvas.align.${key}`)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ position: 'relative' }}>
          <div onClick={(e) => { e.stopPropagation(); setMultiSelectToolsOpen((o) => o === 'spacing' ? null : 'spacing') }} style={{ padding: 6, borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 2, transition: 'background 0.2s', backgroundColor: multiSelectToolsOpen === 'spacing' ? 'var(--app-control-hover)' : 'transparent' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="2" /><rect x="3" y="21" width="18" height="2" /><rect x="7" y="8" width="10" height="8" rx="1" /></svg>
            <ChevronDown size={12} color="var(--app-foreground-subtle)" style={{ transform: multiSelectToolsOpen === 'spacing' ? 'rotate(180deg)' : 'none', transition: 'transform 0.2s' }} />
          </div>
          {multiSelectToolsOpen === 'spacing' && (
            <div style={{ position: 'absolute', bottom: '100%', left: 0, marginBottom: 8, backgroundColor: 'var(--app-glass)', borderRadius: 12, boxShadow: 'var(--app-shadow-panel)', border: '1px solid var(--app-border)', padding: '6px 0', minWidth: 180, zIndex: 1002 }}>
              {['horizontal', 'vertical', 'auto'].map((key) => (
                <div key={key} onClick={() => { if (key === 'auto') handleAutoArrange(); else handleSpacing(key); setMultiSelectToolsOpen(null) }} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px', cursor: 'pointer', transition: 'background 0.2s', color: 'var(--app-foreground)' }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>{t(key === 'auto' ? 'canvas.align.auto_arrange' : `canvas.align.${key}_spacing`)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ width: 1, height: 20, backgroundColor: 'var(--app-border)', margin: '0 4px' }} />
        <div
          aria-label="Copy selection"
          title={t('canvas.context_menu.copy')}
          onClick={() => { handleContextMenuAction('copy') }}
          style={{ padding: 6, borderRadius: 8, cursor: 'pointer', transition: 'background 0.2s' }}
        >
          <Copy size={18} color="var(--app-foreground)" />
        </div>
      </div>
    </div>
  )
})
