import { ChevronRight, Eye, EyeOff, Loader2, Lock, Unlock } from 'lucide-react'
import type { CanvasItem } from '@/api/endpoints/projects'
import type { TFunction } from 'i18next'

import { canRenameCanvasItem } from '../canvasItemRename'
import { isGenerationTaskPendingStatus } from '../generationTaskBinding'

type CanvasLayerPanelProps = {
  isOpen: boolean
  isDark: boolean
  t: TFunction
  canvasItems: CanvasItem[]
  selectedItems: string[]
  setSelectedItems: React.Dispatch<React.SetStateAction<string[]>>
  layerDragId: string | null
  setLayerDragId: (id: string | null) => void
  layerDropTarget: { id: string; position: 'before' | 'after' | 'inside' } | null
  setLayerDropTarget: React.Dispatch<React.SetStateAction<{ id: string; position: 'before' | 'after' | 'inside' } | null>>
  editingNameId: string | null
  setEditingNameId: (id: string | null) => void
  updateItem: (id: string, updates: Partial<CanvasItem>) => void
  handleLayerDrop: () => void
  handleJumpToItem: (id: string) => void
  handleContextMenuAction: (action: string, itemId?: string) => void
  setContextMenu: (menu: { x: number; y: number; type?: 'item' | 'canvas' } | null) => void
  setActiveContextMenuItem: (value: string | null) => void
  setIsLayerPanelOpen: (open: boolean) => void
}

export function CanvasLayerPanel({
  isOpen,
  t,
  canvasItems,
  selectedItems,
  setSelectedItems,
  layerDragId,
  setLayerDragId,
  layerDropTarget,
  setLayerDropTarget,
  editingNameId,
  setEditingNameId,
  updateItem,
  handleLayerDrop,
  handleJumpToItem,
  handleContextMenuAction,
  setContextMenu,
  setActiveContextMenuItem,
  setIsLayerPanelOpen,
}: CanvasLayerPanelProps) {
  if (!isOpen) return null

  const groups = canvasItems.filter(i => i.type === 'group').sort((a, b) => (b.z_index || 0) - (a.z_index || 0))
  const standalone = canvasItems.filter(i => !i.groupId && i.type !== 'group').sort((a, b) => (b.z_index || 0) - (a.z_index || 0))

  const renderItemRow = (item: CanvasItem, isChild = false) => {
    const isItemSelected = selectedItems.includes(item.id)
    const isGenerator = item.type === 'image_generator' || item.type === 'video_generator'
    const isText = item.type === 'text'
    const itemLabel = isText
      ? (item.name || item.text || t('canvas.tools.text', 'Text'))
      : isGenerator
      ? (item.type === 'image_generator' ? t('canvas.generator.image_title') : t('canvas.generator.video_title'))
      : (item.name || item.id)
    const iconBg = 'color-mix(in srgb, var(--app-primary) 12%, var(--app-surface-muted))'
    const iconColor = 'var(--app-primary)'
    const canDrag = item.type !== 'group'
    const canRename = canRenameCanvasItem(item)
    const isBeingDragged = layerDragId === item.id
    const isDragOverThis = layerDropTarget?.id === item.id

    return (
      <div
        key={item.id}
        draggable={canDrag}
        onDragStart={(e) => {
          if (!canDrag) {
            e.preventDefault()
            return
          }
          setLayerDragId(item.id)
          e.dataTransfer.effectAllowed = 'move'
        }}
        onDragOver={(e) => {
          e.preventDefault()
          e.dataTransfer.dropEffect = 'move'
          if (!layerDragId || layerDragId === item.id) return
          const rect = e.currentTarget.getBoundingClientRect()
          const y = e.clientY - rect.top
          const h = rect.height
          if (item.type === 'group') {
            setLayerDropTarget({ id: item.id, position: y < h * 0.3 ? 'before' : 'inside' })
          } else {
            setLayerDropTarget({ id: item.id, position: y < h / 2 ? 'before' : 'after' })
          }
        }}
        onDragLeave={() => setLayerDropTarget(prev => prev?.id === item.id ? null : prev)}
        onDrop={(e) => {
          e.preventDefault()
          handleLayerDrop()
        }}
        onDragEnd={() => {
          setLayerDragId(null)
          setLayerDropTarget(null)
        }}
        onContextMenu={(e) => {
          e.preventDefault()
          e.stopPropagation()
          if (!selectedItems.includes(item.id)) setSelectedItems([item.id])
          setContextMenu({ x: e.clientX, y: e.clientY, type: 'item' })
          setActiveContextMenuItem(null)
        }}
        onClick={(e) => {
          if (e.ctrlKey || e.metaKey) {
            setSelectedItems(prev => prev.includes(item.id) ? prev.filter(id => id !== item.id) : [...prev, item.id])
          } else {
            setSelectedItems([item.id])
            handleJumpToItem(item.id)
          }
        }}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 4,
          padding: '6px 16px',
          paddingLeft: isChild ? 36 : 8,
          cursor: canDrag ? 'grab' : 'pointer',
          transition: 'background 0.2s, opacity 0.2s',
          backgroundColor: isItemSelected ? 'color-mix(in srgb, var(--app-primary) 12%, transparent)' : 'transparent',
          borderRight: isItemSelected ? '2px solid var(--app-primary)' : '2px solid transparent',
          opacity: isBeingDragged ? 0.4 : 1,
          position: 'relative',
        }}
        onMouseEnter={(e) => {
          if (!isItemSelected) e.currentTarget.style.backgroundColor = 'var(--app-control-hover)'
        }}
        onMouseLeave={(e) => {
          if (!isItemSelected) e.currentTarget.style.backgroundColor = 'transparent'
        }}
      >
        {isDragOverThis && layerDropTarget?.position === 'before' && (
          <div style={{ position: 'absolute', top: -1, left: 8, right: 8, height: 2, backgroundColor: 'var(--app-primary)', borderRadius: 1, zIndex: 10, pointerEvents: 'none' }} />
        )}
        {isDragOverThis && layerDropTarget?.position === 'after' && (
          <div style={{ position: 'absolute', bottom: -1, left: 8, right: 8, height: 2, backgroundColor: 'var(--app-primary)', borderRadius: 1, zIndex: 10, pointerEvents: 'none' }} />
        )}
        {isDragOverThis && layerDropTarget?.position === 'inside' && (
          <div style={{ position: 'absolute', inset: 0, border: '2px solid var(--app-primary)', borderRadius: 6, pointerEvents: 'none', zIndex: 10 }} />
        )}

        {item.type === 'group' ? (
          <div style={{ width: 14, height: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, transform: 'rotate(90deg)' }}>
            <ChevronRight size={12} color="var(--app-foreground-subtle)" />
          </div>
        ) : null}

        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 6,
            backgroundColor: iconBg,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            overflow: 'hidden',
            border: '1px solid var(--app-border)',
          }}
        >
          {isGenerationTaskPendingStatus(item.status) ? (
            <Loader2 size={12} className="animate-spin" color={iconColor} />
          ) : item.url ? (
            (item.type === 'image' || item.type === 'image_generator') ? (
              <img src={item.url} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            ) : (
              item.type === 'video' || item.type === 'video_generator' ? (
                item.first_frame_image ? (
                  <img src={item.first_frame_image} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <video src={item.url} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                )
              ) : (
                item.type === 'group' ? (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={iconColor} strokeWidth="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></svg>
                ) : null
              )
            )
          ) : isText ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={iconColor} strokeWidth="1.8" strokeLinecap="round">
              <path d="M6 5h12" />
              <path d="M12 5v14" />
              <path d="M8 19h8" />
            </svg>
          ) : (
            item.type === 'group' ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={iconColor} strokeWidth="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" /></svg>
            ) : (item.type === 'image' || item.type === 'image_generator' ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={iconColor} strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2" /><circle cx="8.5" cy="8.5" r="1.5" /><polyline points="21 15 16 10 5 21" /></svg>
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill={iconColor}><polygon points="5 3 19 12 5 21 5 3" /></svg>
            ))
          )}
        </div>

        {editingNameId === item.id && canRename ? (
          <input
            autoFocus
            value={item.name || ''}
            onChange={(e) => updateItem(item.id, { name: e.target.value })}
            onBlur={() => setEditingNameId(null)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === 'Escape') setEditingNameId(null)
            }}
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
            style={{
              flex: 1,
              border: 'none',
              background: 'transparent',
              fontSize: 13,
              color: isItemSelected ? 'var(--app-primary)' : 'var(--app-foreground-muted)',
              outline: 'none',
              padding: 0,
              fontWeight: item.type === 'group' ? 500 : 400,
              minWidth: 0,
            }}
          />
        ) : (
          <span
            onDoubleClick={(e) => {
              e.stopPropagation()
              if (!canRename) return
              setEditingNameId(item.id)
            }}
            onMouseDown={(e) => e.stopPropagation()}
            style={{
              flex: 1,
              fontSize: 13,
              color: isItemSelected ? 'var(--app-primary)' : 'var(--app-foreground-muted)',
              fontWeight: item.type === 'group' ? 500 : (isItemSelected ? 500 : 400),
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              minWidth: 0,
              cursor: 'pointer',
            }}
          >
            {itemLabel}
          </span>
        )}

        <div style={{ display: 'flex', alignItems: 'center', gap: 4, flexShrink: 0 }}>
          <div
            onClick={(e) => {
              e.stopPropagation()
              handleContextMenuAction('lock', item.id)
            }}
            style={{ padding: 4, cursor: 'pointer', opacity: item.is_locked ? 1 : 0.5 }}
            title={item.is_locked ? '解锁' : '锁定'}
          >
            {item.is_locked ? <Lock size={12} color="var(--app-primary)" /> : <Unlock size={12} color="var(--app-foreground-subtle)" />}
          </div>
          <div
            onClick={(e) => {
              e.stopPropagation()
              handleContextMenuAction('toggle_visible', item.id)
            }}
            style={{ padding: 4, cursor: 'pointer', opacity: item.is_hidden ? 0.5 : 1 }}
            title={item.is_hidden ? '显示' : '隐藏'}
          >
            {item.is_hidden ? <EyeOff size={12} color="var(--app-foreground-subtle)" /> : <Eye size={12} color="var(--app-foreground-subtle)" />}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      style={{
        width: 260,
        backgroundColor: 'var(--app-surface)',
        borderRight: '1px solid var(--app-border)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 10,
      }}
    >
      <div style={{ height: 48, minHeight: 48, padding: '0 16px', display: 'flex', alignItems: 'center', borderBottom: '1px solid var(--app-border)', fontSize: 14, fontWeight: 500, color: 'var(--app-foreground)' }}>
        {t('canvas.layers')}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
        {groups.map(group => {
          const members = canvasItems.filter(i => i.groupId === group.id).sort((a, b) => (b.z_index || 0) - (a.z_index || 0))
          return (
            <div key={group.id}>
              {renderItemRow(group)}
              {members.length > 0 && (
                <div style={{ backgroundColor: 'var(--app-surface-muted)' }}>
                  {members.map(child => renderItemRow(child, true))}
                </div>
              )}
            </div>
          )
        })}
        {standalone.map(item => renderItemRow(item))}
      </div>

      <div style={{ height: 36, minHeight: 36, display: 'flex', alignItems: 'center', padding: '0 16px', borderTop: '1px solid var(--app-border)' }}>
        <div
          onClick={() => setIsLayerPanelOpen(false)}
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 4, borderRadius: 4, transition: 'background 0.2s' }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--app-control-hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--app-foreground-muted)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </div>
      </div>
    </div>
  )
}
