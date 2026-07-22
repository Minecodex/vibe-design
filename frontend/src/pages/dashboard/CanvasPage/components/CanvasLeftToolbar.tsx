import type { RefObject } from 'react'
import type { ToolItem } from '../types'

type CanvasLeftToolbarProps = {
  isGuest: boolean
  isDark: boolean
  tools: ToolItem[]
  selectTools: Array<ToolItem & { shortcut?: string }>
  addTools: ToolItem[]
  activeTool: string
  setActiveTool: (tool: string) => void
  isSelectMenuOpen: boolean
  setIsSelectMenuOpen: (open: boolean) => void
  hoveredSelectTool: string | null
  setHoveredSelectTool: (tool: string | null) => void
  isAddMenuOpen: boolean
  setIsAddMenuOpen: (open: boolean) => void
  hoveredAddTool: string | null
  setHoveredAddTool: (tool: string | null) => void
  addNewGenerator: (type: 'image_generator' | 'video_generator') => void
  imageInputRef: RefObject<HTMLInputElement>
  videoInputRef: RefObject<HTMLInputElement>
  setIsAssetLibraryOpen: (open: boolean) => void
}

export function CanvasLeftToolbar({
  isGuest,
  tools,
  selectTools,
  addTools,
  activeTool,
  setActiveTool,
  isSelectMenuOpen,
  setIsSelectMenuOpen,
  hoveredSelectTool,
  setHoveredSelectTool,
  isAddMenuOpen,
  setIsAddMenuOpen,
  hoveredAddTool,
  setHoveredAddTool,
  addNewGenerator,
  imageInputRef,
  videoInputRef,
  setIsAssetLibraryOpen,
}: CanvasLeftToolbarProps) {
  if (isGuest) return null

  return (
    <div
      style={{
        position: 'absolute',
        left: 12,
        top: '50%',
        transform: 'translateY(-50%)',
        zIndex: 50,
        backgroundColor: 'var(--app-glass)',
        borderRadius: 14,
        boxShadow: 'var(--app-shadow-panel)',
        border: '1px solid var(--app-border)',
        backdropFilter: 'var(--app-blur)',
        WebkitBackdropFilter: 'var(--app-blur)',
        padding: '6px',
        display: 'flex',
        flexDirection: 'column',
        gap: 2,
      }}
    >
      {tools.map((tool) => {
        const isSelectGroup = tool.key === 'select'
        const isAddGroup = tool.key === 'add'
        const isSelectCategoryActive = ['select', 'hand', 'mark'].includes(activeTool)
        const isActive = isSelectGroup ? isSelectCategoryActive : activeTool === tool.key
        const currentMainIcon = isSelectGroup
          ? (selectTools.find(st => st.key === activeTool)?.svgPath || tool.svgPath)
          : tool.svgPath

        return (
          <div
            key={tool.key}
            style={{ position: 'relative' }}
            onMouseEnter={() => {
              if (isSelectGroup) setIsSelectMenuOpen(true)
              if (isAddGroup) setIsAddMenuOpen(true)
            }}
            onMouseLeave={() => {
              if (isSelectGroup) setIsSelectMenuOpen(false)
              if (isAddGroup) setIsAddMenuOpen(false)
            }}
          >
            <div
              title={tool.label}
              onClick={() => {
                const shouldSelectGenerator = tool.key === 'image_gen' || tool.key === 'video_gen'
                setActiveTool(isSelectGroup || shouldSelectGenerator ? 'select' : tool.key)
                if (tool.key === 'image_gen') addNewGenerator('image_generator')
                if (tool.key === 'video_gen') addNewGenerator('video_generator')
              }}
              style={{
                width: 36,
                height: 36,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: 10,
                cursor: 'pointer',
                backgroundColor: isActive ? 'var(--app-control-selected)' : 'transparent',
                color: isActive ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = 'var(--app-control-hover)'
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = 'transparent'
              }}
            >
              {currentMainIcon}
            </div>

            {isSelectGroup && isSelectMenuOpen && (
              <div style={{ position: 'absolute', left: '100%', top: 0, paddingLeft: 8 }}>
                <div
                  style={{
                    backgroundColor: 'var(--app-glass)',
                    borderRadius: 12,
                    boxShadow: 'var(--app-shadow-panel)',
                    border: '1px solid var(--app-border)',
                    backdropFilter: 'var(--app-blur)',
                    WebkitBackdropFilter: 'var(--app-blur)',
                    padding: 8,
                    minWidth: 160,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                  }}
                >
                  {selectTools.map((st) => {
                    const isSubActive = activeTool === st.key
                    const isSubHovered = hoveredSelectTool === st.key
                    return (
                      <div
                        key={st.key}
                        onClick={() => {
                          setActiveTool(st.key)
                          setIsSelectMenuOpen(false)
                        }}
                        onMouseEnter={() => setHoveredSelectTool(st.key)}
                        onMouseLeave={() => setHoveredSelectTool(null)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '8px 12px',
                          borderRadius: 8,
                          cursor: 'pointer',
                          backgroundColor: isSubActive
                            ? 'var(--app-control-selected)'
                            : (isSubHovered ? 'var(--app-control-hover)' : 'transparent'),
                          transition: 'all 0.1s',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--app-foreground)' }}>
                          {st.svgPath}
                          <span style={{ fontSize: 14, fontWeight: 500 }}>{st.label}</span>
                        </div>
                        <span style={{ fontSize: 12, color: 'var(--app-foreground-subtle)', fontWeight: 600 }}>{st.shortcut}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {isAddGroup && isAddMenuOpen && (
              <div style={{ position: 'absolute', left: '100%', top: 0, paddingLeft: 8 }}>
                <div
                  style={{
                    backgroundColor: 'var(--app-glass)',
                    borderRadius: 12,
                    boxShadow: 'var(--app-shadow-panel)',
                    border: '1px solid var(--app-border)',
                    backdropFilter: 'var(--app-blur)',
                    WebkitBackdropFilter: 'var(--app-blur)',
                    padding: '12px',
                    minWidth: 160,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                  }}
                >
                  <span style={{ fontSize: 13, color: 'var(--app-foreground-muted)', marginBottom: 8, paddingLeft: 4 }}>新增</span>
                  {addTools.map((at) => {
                    const isSubHovered = hoveredAddTool === at.key
                    return (
                      <div
                        key={at.key}
                        onClick={() => {
                          setIsAddMenuOpen(false)
                          if (at.key === 'upload_image') {
                            imageInputRef.current?.click()
                          } else if (at.key === 'upload_video') {
                            videoInputRef.current?.click()
                          } else if (at.key === 'asset_library') {
                            setIsAssetLibraryOpen(true)
                          }
                        }}
                        onMouseEnter={() => setHoveredAddTool(at.key)}
                        onMouseLeave={() => setHoveredAddTool(null)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          padding: '8px 4px',
                          borderRadius: 8,
                          cursor: 'pointer',
                          backgroundColor: isSubHovered ? 'var(--app-control-hover)' : 'transparent',
                          transition: 'all 0.1s',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: 'var(--app-foreground)' }}>
                          {at.svgPath}
                          <span style={{ fontSize: 15, fontWeight: 400 }}>{at.label}</span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}
