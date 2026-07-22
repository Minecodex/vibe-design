import { getViewportMenuPosition } from '../floatingPanelPosition'
import type { CanvasItem } from '@/api/endpoints/projects'
import type { TFunction } from 'i18next'

type CanvasContextMenuProps = {
  contextMenu: { x: number; y: number; type?: 'item' | 'canvas' } | null
  isDark: boolean
  setContextMenu: (value: { x: number; y: number; type?: 'item' | 'canvas' } | null) => void
  setActiveContextMenuItem: (value: string | null) => void
  activeContextMenuItem: string | null
  selectionContextMenuItems: Array<{ key?: string; label?: string; shortcut?: string; type?: string }>
  firstSelectedItem: CanvasItem | null
  clipboardItems: CanvasItem[]
  canPasteExternalClipboard: boolean
  currentSelectionItems: CanvasItem[]
  selectedItems: string[]
  handleCreateGroup: () => void
  handleMergeLayers: () => void
  handleUngroup: (id: string) => void
  handleBulkExport: (ids: string[], format?: string) => void
  handleContextMenuAction: (action: string) => void
  zoomIn: () => void
  zoomOut: () => void
  resetZoom: () => void
  handleFitView: () => void
  t: TFunction
}

export function CanvasContextMenu({
  contextMenu,
  setContextMenu,
  setActiveContextMenuItem,
  activeContextMenuItem,
  selectionContextMenuItems,
  firstSelectedItem,
  clipboardItems,
  canPasteExternalClipboard,
  currentSelectionItems,
  selectedItems,
  handleCreateGroup,
  handleMergeLayers,
  handleUngroup,
  handleBulkExport,
  handleContextMenuAction,
  zoomIn,
  zoomOut,
  resetZoom,
  handleFitView,
  t,
}: CanvasContextMenuProps) {
  if (!contextMenu) return null

  const canvasMenuItems = [
    { key: 'paste', label: t('canvas.context_menu.paste'), shortcut: 'Ctrl + V' },
    { type: 'divider' },
    { key: 'zoom_in', label: t('canvas.context_menu.zoom_in'), shortcut: 'Ctrl + +' },
    { key: 'zoom_out', label: t('canvas.context_menu.zoom_out'), shortcut: 'Ctrl + -' },
    { key: 'fit_view', label: t('canvas.context_menu.fit_view'), shortcut: 'Shift + 1' },
    { key: 'reset_zoom', label: t('canvas.context_menu.reset_zoom'), shortcut: 'Ctrl + 0' },
  ]
  const menuItems = contextMenu.type === 'canvas' ? canvasMenuItems : selectionContextMenuItems
  const dividerCount = menuItems.filter(item => item.type === 'divider').length
  const actionableCount = menuItems.length - dividerCount
  const estimatedMenuHeight = (actionableCount * 40) + (dividerCount * 13) + 16
  const estimatedMenuWidth = 240
  const isGroupSelected = firstSelectedItem?.type === 'group'
  const viewportMenuPosition = typeof window === 'undefined'
    ? { left: contextMenu.x, top: contextMenu.y }
    : getViewportMenuPosition({
      anchorX: contextMenu.x,
      anchorY: contextMenu.y,
      panelWidth: estimatedMenuWidth,
      panelHeight: estimatedMenuHeight,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    })

  return (
    <div
      style={{
        position: 'fixed',
        left: viewportMenuPosition.left,
        top: viewportMenuPosition.top,
        backgroundColor: 'var(--app-glass)',
        borderRadius: 12,
        boxShadow: 'var(--app-shadow-panel)',
        border: '1px solid var(--app-border)',
        padding: '8px 0',
        minWidth: 200,
        zIndex: 2147483600,
        display: 'flex',
        flexDirection: 'column',
        fontSize: 14,
        color: 'var(--app-foreground)',
      }}
      onClick={(e) => {
        e.stopPropagation()
        setContextMenu(null)
        setActiveContextMenuItem(null)
      }}
      onContextMenu={(e) => e.preventDefault()}
    >
      {menuItems.map((item, idx) => {
        if (item.type === 'divider') {
          return (
            <div
              key={`div-${idx}`}
              style={{ height: 1, backgroundColor: 'var(--app-border)', margin: '6px 0' }}
            />
          )
        }

        const isDisabled = (item.key === 'paste' && contextMenu.type === 'canvas' && clipboardItems.length === 0 && !canPasteExternalClipboard)
        const isHovered = !isDisabled && activeContextMenuItem === item.key
        const hasImage = currentSelectionItems.some((it) => it.type === 'image' || it.type === 'image_generator')
        const isImageExport = item.key === 'export' && (hasImage || isGroupSelected)

        return (
          <div
            key={item.key}
            style={{
              position: 'relative',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              padding: '10px 20px',
              cursor: isDisabled ? 'not-allowed' : 'pointer',
              transition: 'background 0.1s',
              backgroundColor: isHovered ? 'var(--app-control-hover)' : 'transparent',
            }}
            onMouseEnter={() => !isDisabled && setActiveContextMenuItem(item.key || null)}
            onMouseLeave={() => setActiveContextMenuItem(null)}
            onClick={(e) => {
              e.stopPropagation()
              if (isDisabled || !item.key) return

              if (item.key === 'create_group') {
                handleCreateGroup()
                setContextMenu(null)
                return
              }

              if (item.key === 'merge_layers') {
                handleMergeLayers()
                setContextMenu(null)
                return
              }

              if (item.key === 'ungroup') {
                if (firstSelectedItem?.type === 'group') {
                  handleUngroup(firstSelectedItem.id)
                }
                setContextMenu(null)
                return
              }

              if (item.key === 'export') {
                const hasVideo = currentSelectionItems.some((it) => it.type === 'video' || it.type === 'video_generator')
                const hasOnlyVideo = hasVideo && !hasImage

                if (hasOnlyVideo) {
                  handleBulkExport(selectedItems)
                  setContextMenu(null)
                }
                return
              }

              if (contextMenu.type === 'canvas') {
                if (item.key === 'paste') handleContextMenuAction('paste')
                if (item.key === 'zoom_in') zoomIn()
                if (item.key === 'zoom_out') zoomOut()
                if (item.key === 'reset_zoom') resetZoom()
                if (item.key === 'fit_view') handleFitView()
              } else {
                handleContextMenuAction(item.key)
              }

              setContextMenu(null)
            }}
          >
            <span style={{ color: isDisabled ? 'var(--app-foreground-subtle)' : 'var(--app-foreground)', display: 'flex', alignItems: 'center', gap: 6 }}>
              {item.label}
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {item.shortcut && (
                <span style={{ color: 'var(--app-foreground-subtle)', fontSize: 13, fontFamily: 'system-ui, -apple-system, sans-serif' }}>
                  {item.shortcut}
                </span>
              )}
              {isImageExport && (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--app-foreground-subtle)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              )}
            </span>

            {isImageExport && isHovered && (
              <div
                style={{
                  position: 'absolute',
                  bottom: -15,
                  left: '100%',
                  backgroundColor: 'var(--app-glass)',
                  borderRadius: 12,
                  boxShadow: 'var(--app-shadow-panel)',
                  border: '1px solid var(--app-border)',
                  padding: '8px 0',
                  minWidth: 100,
                  zIndex: 2147483601,
                }}
              >
                {['PNG', 'JPG', 'SVG'].map(format => (
                  <div
                    key={format}
                    style={{
                      padding: '10px 20px',
                      cursor: 'pointer',
                      color: 'var(--app-foreground)',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--app-control-hover)')}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleBulkExport(selectedItems, format)
                      setContextMenu(null)
                    }}
                  >
                    {format}
                  </div>
                ))}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
