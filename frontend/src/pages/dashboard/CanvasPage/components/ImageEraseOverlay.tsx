import { useEffect } from 'react'
import { Undo, Redo, SquareDashed, Sparkles } from 'lucide-react'

import { useTranslation } from 'react-i18next'

import type { ImageEraseSession } from '../types'

type ImageEraseOverlayProps = {
  session: ImageEraseSession
  tool: 'erase' | 'cutout'
  isDark: boolean
  onCancel: () => void
  onConfirm: () => void
  onUndo: () => void
  onRedo: () => void
  onChangeMode: (mode: ImageEraseSession['mode']) => void
  onChangeBrushSize: (size: number) => void
  canvasRef: { current: HTMLCanvasElement | null }
  previewRect: { x: number; y: number; width: number; height: number } | null
}

export function ImageEraseOverlay({
  session,
  tool,
  onCancel,
  onConfirm,
  onUndo,
  onRedo,
  onChangeMode,
  onChangeBrushSize,
  canvasRef,
  previewRect,
}: ImageEraseOverlayProps) {
  const { t } = useTranslation()
  const isCutout = tool === 'cutout'
  const confirmLabel = session.isSubmitting
    ? isCutout
      ? t('canvas.cutout.generating', '正在生成抠图')
      : t('canvas.generating')
    : isCutout
      ? t('canvas.cutout.confirm', '生成抠图')
      : t('canvas.erase_generate', '生成')

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCancel()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onCancel])

  const brushProgress = ((session.brushSize - 8) / (96 - 8)) * 100

  return (
    <>
      <style>{`
        .custom-brush-slider {
          -webkit-appearance: none;
          appearance: none;
          width: 140px;
          height: 12px;
          border-radius: 6px;
          border: 1px solid var(--app-border);
          outline: none;
        }
        .custom-brush-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: var(--app-foreground-muted);
          cursor: pointer;
          border: none;
          transition: none;
        }
        .custom-brush-slider::-webkit-slider-thumb:hover,
        .custom-brush-slider::-webkit-slider-thumb:active {
          background: var(--app-foreground-muted);
        }
        .custom-brush-slider::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: var(--app-foreground-muted);
          cursor: pointer;
          border: none;
          transition: none;
        }
        .custom-brush-slider::-moz-range-thumb:hover,
        .custom-brush-slider::-moz-range-thumb:active {
          background: #8c8c8c;
        }
      `}</style>
      <canvas
        ref={(node) => {
          canvasRef.current = node
        }}
        width={session.displayWidth}
        height={session.displayHeight}
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', opacity: 0.75 }}
      />
      {session.mode === 'rect' && previewRect && (
        <div
          style={{
            position: 'absolute',
            left: `${(previewRect.x / session.displayWidth) * 100}%`,
            top: `${(previewRect.y / session.displayHeight) * 100}%`,
            width: `${(previewRect.width / session.displayWidth) * 100}%`,
            height: `${(previewRect.height / session.displayHeight) * 100}%`,
            border: '1px dashed rgba(255,255,255,0.95)',
            background: 'rgba(255,255,255,0.2)',
          }}
        />
      )}
      {/* Floating Toolbar */}
      <div
        className="nowheel"
        style={{
          position: 'absolute',
          top: 'calc(100% + 16px)',
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 12,
          pointerEvents: 'auto',
          zIndex: 2147483550,
        }}
        onPointerDown={(e) => e.stopPropagation()}
        onPointerMove={(e) => e.stopPropagation()}
        onPointerUp={(e) => e.stopPropagation()}
        onClick={(e) => e.stopPropagation()}
        onWheel={(e) => {
          if (e.ctrlKey || e.metaKey) {
            return
          }
          e.preventDefault()
          e.stopPropagation()
        }}
        onDoubleClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '6px 6px',
            borderRadius: 14,
            background: 'var(--app-glass)',
            boxShadow: 'var(--app-shadow-panel)',
            border: '1px solid var(--app-border)',
            backdropFilter: 'var(--app-blur)',
            WebkitBackdropFilter: 'var(--app-blur)',
          }}
        >
          <ToolIconButton
            title={t('canvas.tools.brush')}
            active={session.mode === 'brush'}
            icon={isCutout ? <PenToolGlyph /> : <BrushToolGlyph />}
            onClick={() => onChangeMode('brush')}
          />
          <ToolIconButton title={t('canvas.tools.rect')} active={session.mode === 'rect'} icon={<SquareDashed size={18} />} onClick={() => onChangeMode('rect')} />
          
          <div style={{ width: 1, height: 16, background: 'var(--app-border)', margin: '0 4px' }} />
          
          <ToolIconButton icon={<Undo size={18} />} disabled={session.history.length <= 1} onClick={onUndo} />
          <ToolIconButton icon={<Redo size={18} />} disabled={session.future.length === 0} onClick={onRedo} />
          
          <div style={{ width: 1, height: 16, background: 'var(--app-border)', margin: '0 4px' }} />

          <button
            type="button"
            onClick={onConfirm}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              background: 'var(--app-primary)',
              color: 'var(--app-primary-foreground)',
              border: 'none',
              borderRadius: 10,
              padding: '8px 16px',
              fontSize: 14,
              fontWeight: 600,
              cursor: (!session.hasMask || session.isSubmitting) ? 'not-allowed' : 'pointer',
              opacity: (!session.hasMask || session.isSubmitting) ? 0.5 : 1,
              whiteSpace: 'nowrap',
            }}
            disabled={!session.hasMask || session.isSubmitting}
          >
            <Sparkles size={16} />
            {confirmLabel}
          </button>
        </div>

        {session.mode === 'brush' && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              padding: '10px 16px',
              borderRadius: 14,
              background: 'var(--app-glass)',
              boxShadow: 'var(--app-shadow-panel)',
              border: '1px solid var(--app-border)',
              backdropFilter: 'var(--app-blur)',
              WebkitBackdropFilter: 'var(--app-blur)',
            }}
          >
            <input
              type="range"
              min={8}
              max={96}
              step={2}
              value={session.brushSize}
              onChange={(event) => onChangeBrushSize(Number(event.target.value))}
              className="custom-brush-slider"
              style={{
                cursor: 'pointer',
                background: `linear-gradient(to right, #8c8c8c ${brushProgress}%, #fff ${brushProgress}%)`,
              }}
            />
          </div>
        )}
      </div>
    </>
  )
}

function ToolIconButton({ active, disabled, icon, onClick, title }: { active?: boolean, disabled?: boolean, icon: React.ReactNode, onClick: () => void, title?: string }) {
  return (
    <button
      type="button"
      title={title}
      onClick={disabled ? undefined : onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 36,
        height: 36,
        borderRadius: 10,
        border: 'none',
        background: active ? 'var(--app-control-selected)' : 'transparent',
        color: disabled ? 'var(--app-foreground-subtle)' : (active ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)'),
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.2s',
      }}
      onMouseEnter={(e) => {
        if (!disabled && !active) e.currentTarget.style.background = 'var(--app-control-hover)'
      }}
      onMouseLeave={(e) => {
        if (!disabled && !active) e.currentTarget.style.background = 'transparent'
      }}
    >
      {icon}
    </button>
  )
}


function BrushToolGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 18c1.5-2.5 3.5-4 6-4 2.2 0 4 1.8 4 4" />
      <path d="M14.5 14.5 19 10a3 3 0 0 0-4.2-4.2l-4.6 4.6" />
      <path d="M5 20c1.2 0 2.3-.2 3.3-.7.9-.4 1.7-1.1 2.3-1.9" />
    </svg>
  )
}

function PenToolGlyph() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 20h4l10-10-4-4L4 16v4z" />
      <path d="M13 7l4 4" />
    </svg>
  )
}
