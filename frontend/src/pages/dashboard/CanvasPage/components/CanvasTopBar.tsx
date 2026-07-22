import { ChevronDown, Target } from 'lucide-react'
import type { TFunction } from 'i18next'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { BrandMark } from '@/components/common/BrandMark'

type CanvasTopBarProps = {
  isDark: boolean
  navigate: (path: string) => void
  isEditingTitle: boolean
  titleInputRef: React.RefObject<HTMLInputElement>
  editingTitleValue: string
  setEditingTitleValue: (value: string) => void
  title: string
  setIsEditingTitle: (value: boolean) => void
  isChatSidebarOpen: boolean
  setIsChatSidebarOpen: React.Dispatch<React.SetStateAction<boolean>>
  t: TFunction
  onStartEditingTitle: () => void
  onCommitTitle: () => void
}

export function CanvasTopBar({
  isDark,
  navigate,
  isEditingTitle,
  titleInputRef,
  editingTitleValue,
  setEditingTitleValue,
  title,
  setIsEditingTitle,
  isChatSidebarOpen,
  setIsChatSidebarOpen,
  t,
  onStartEditingTitle,
  onCommitTitle,
}: CanvasTopBarProps) {
  return (
    <div
      style={{
        position: 'absolute',
        top: 16,
        left: 16,
        right: 16,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        zIndex: 1000,
        pointerEvents: 'none',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          backgroundColor: 'transparent',
          padding: '4px 8px',
          borderRadius: 0,
          boxShadow: 'none',
          border: 'none',
          pointerEvents: 'auto',
          height: 40,
        }}
      >
        <div onClick={() => navigate('/dashboard/projects')} style={{ cursor: 'pointer' }}>
          <BrandMark isDark={isDark} className="w-7 h-7" />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
          <ChevronDown style={{ width: 10, height: 10, color: 'var(--app-foreground-subtle)' }} />
          {isEditingTitle ? (
            <input
              ref={titleInputRef}
              value={editingTitleValue}
              onChange={(e) => setEditingTitleValue(e.target.value)}
              onBlur={onCommitTitle}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.currentTarget.blur()
                }
                if (e.key === 'Escape') {
                  setIsEditingTitle(false)
                }
              }}
              autoFocus
              style={{
                fontSize: 14,
                fontWeight: 500,
                color: 'var(--app-foreground)',
                border: 'none',
                outline: 'none',
                width: 180,
                background: 'transparent',
              }}
            />
          ) : (
            <span
              onClick={onStartEditingTitle}
              style={{ fontSize: 14, fontWeight: 500, color: 'var(--app-foreground)' }}
            >
              {title}
            </span>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 8, pointerEvents: 'auto' }}>
        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              <div
                onClick={() => setIsChatSidebarOpen(!isChatSidebarOpen)}
                style={{
                  width: 40,
                  height: 40,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: isChatSidebarOpen ? 'var(--app-control-selected)' : 'var(--app-glass)',
                  borderRadius: 12,
                  border: '1px solid var(--app-border)',
                  boxShadow: 'var(--app-shadow-control)',
                  backdropFilter: 'var(--app-blur)',
                  WebkitBackdropFilter: 'var(--app-blur)',
                  cursor: 'pointer',
                  transition: 'all 0.15s',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--app-control-hover)')}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = isChatSidebarOpen
                    ? 'var(--app-control-selected)'
                    : 'var(--app-glass)'
                }}
              >
                <Target
                  style={{
                    width: 18,
                    height: 18,
                    color: isChatSidebarOpen ? 'var(--app-primary)' : 'var(--app-foreground)',
                  }}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom" sideOffset={8}>
              {t('canvas.smart_designer')}
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </div>
    </div>
  )
}
