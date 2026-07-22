import { Pencil, Sparkles, X } from 'lucide-react'

import { handleScrollableWheel } from '../scrollableWheel'
import type { EditableTextRedrawSegment } from '../textRedraw'
import { TEXT_REDRAW_PANEL_TOKENS } from '../textRedrawUi'

type TextRedrawPanelProps = {
  isDark: boolean
  title: string
  segmentLabelPrefix?: string
  submitLabel?: string
  segments: EditableTextRedrawSegment[]
  isSubmitting: boolean
  onChangeSegment: (segmentId: string, text: string) => void
  onCancel: () => void
  onSubmit: () => void
}

export function TextRedrawPanel({
  isDark: _isDark,
  title,
  segmentLabelPrefix = '文字',
  submitLabel = '确认重绘',
  segments,
  isSubmitting,
  onChangeSegment,
  onCancel,
  onSubmit,
}: TextRedrawPanelProps) {
  return (
    <div
      style={{
        width: '100%',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: `0 0 ${TEXT_REDRAW_PANEL_TOKENS.titlePaddingBottom}px`,
          borderBottom: '1px solid var(--app-border)',
        }}
      >
        <div
          style={{
            fontSize: TEXT_REDRAW_PANEL_TOKENS.titleFontSize,
            fontWeight: 600,
            color: 'var(--app-foreground)',
          }}
        >
          {title}
        </div>
        <button
          type="button"
          onClick={onCancel}
          style={{
            width: TEXT_REDRAW_PANEL_TOKENS.closeButtonSize,
            height: TEXT_REDRAW_PANEL_TOKENS.closeButtonSize,
            borderRadius: 999,
            border: 'none',
            background: 'var(--app-control)',
            color: 'var(--app-foreground-muted)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
          }}
        >
          <X size={15} />
        </button>
      </div>

      <div
        data-testid="text-redraw-scroll-area"
        onWheel={handleScrollableWheel}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: `${TEXT_REDRAW_PANEL_TOKENS.scrollPaddingTop}px 2px 0`,
          display: 'flex',
          flexDirection: 'column',
          gap: TEXT_REDRAW_PANEL_TOKENS.scrollGap,
        }}
      >
        {segments.map((segment, index) => (
          <div key={segment.id} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div
              style={{
                fontSize: TEXT_REDRAW_PANEL_TOKENS.segmentLabelFontSize,
                fontWeight: 600,
                color: 'var(--app-foreground-muted)',
              }}
            >
              {`${segmentLabelPrefix} ${index + 1}`}
            </div>
            <div style={{ position: 'relative' }}>
              <input
                value={segment.text}
                onChange={(event) => onChangeSegment(segment.id, event.target.value)}
                style={{
                  width: '100%',
                  height: TEXT_REDRAW_PANEL_TOKENS.inputHeight,
                  borderRadius: TEXT_REDRAW_PANEL_TOKENS.inputRadius,
                  border: '1px solid var(--app-border)',
                  background: 'var(--app-control)',
                  color: 'var(--app-foreground)',
                  fontSize: TEXT_REDRAW_PANEL_TOKENS.inputFontSize,
                  fontWeight: 500,
                  padding: `0 ${TEXT_REDRAW_PANEL_TOKENS.inputPaddingX + 24}px 0 ${TEXT_REDRAW_PANEL_TOKENS.inputPaddingX}px`,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  right: TEXT_REDRAW_PANEL_TOKENS.inputIconOffset,
                  top: '50%',
                  transform: 'translateY(-50%)',
                  color: 'var(--app-foreground-subtle)',
                  pointerEvents: 'none',
                }}
              >
                <Pencil size={14} />
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={onSubmit}
        disabled={isSubmitting || segments.length === 0}
        style={{
          marginTop: 16,
          height: TEXT_REDRAW_PANEL_TOKENS.submitButtonHeight,
          borderRadius: TEXT_REDRAW_PANEL_TOKENS.submitButtonRadius,
          border: 'none',
          background: 'var(--app-primary)',
          color: 'var(--app-primary-foreground)',
          fontSize: TEXT_REDRAW_PANEL_TOKENS.submitButtonFontSize,
          fontWeight: 600,
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 10,
          cursor: isSubmitting || segments.length === 0 ? 'not-allowed' : 'pointer',
          opacity: isSubmitting || segments.length === 0 ? 0.6 : 1,
          boxShadow: 'var(--app-shadow-control)',
        }}
      >
        <Sparkles size={TEXT_REDRAW_PANEL_TOKENS.submitButtonIconSize} />
        <span>{submitLabel}</span>
      </button>
    </div>
  )
}
