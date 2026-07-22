import type { BrushToolState } from '../types'
import { BrushColorPopover } from './CanvasBrushToolbar'

function getCheckerboardBackground(size = 8) {
  return `linear-gradient(45deg, #d7d7d7 25%, transparent 25%), linear-gradient(-45deg, #d7d7d7 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #d7d7d7 75%), linear-gradient(-45deg, transparent 75%, #d7d7d7 75%) 0 0 / ${size}px ${size}px, #f5f5f5`
}

export function CanvasBrushToolPanel({
  isDark,
  activeTool,
  state,
  setState,
  brushToolIndex,
  totalTools,
}: {
  isDark: boolean
  activeTool: string
  state: BrushToolState
  setState: (state: BrushToolState) => void
  brushToolIndex: number
  totalTools: number
}) {
  if (activeTool !== 'brush') return null

  const TOOLBAR_LEFT = 12
  const TOOLBAR_PADDING = 6
  const TOOLBAR_GAP = 2
  const TOOL_BUTTON_SIZE = 36
  const TOOLBAR_WIDTH = TOOLBAR_PADDING * 2 + TOOL_BUTTON_SIZE
  const toolCount = Math.max(totalTools, 1)
  const resolvedBrushIndex = Math.max(brushToolIndex, 0)
  const toolbarHeight = (TOOLBAR_PADDING * 2) + (toolCount * TOOL_BUTTON_SIZE) + ((toolCount - 1) * TOOLBAR_GAP)
  const brushCenterOffset = (-toolbarHeight / 2) + TOOLBAR_PADDING + (resolvedBrushIndex * (TOOL_BUTTON_SIZE + TOOLBAR_GAP)) + (TOOL_BUTTON_SIZE / 2)
  const swatchBackground = state.color === 'transparent' ? getCheckerboardBackground(8) : state.color

  return (
    <div
      style={{
        position: 'absolute',
        left: TOOLBAR_LEFT + TOOLBAR_WIDTH + 8,
        top: `calc(50% + ${brushCenterOffset}px)`,
        transform: 'translateY(-50%)',
        zIndex: 55,
        backgroundColor: 'var(--app-glass)',
        borderRadius: 14,
        boxShadow: 'var(--app-shadow-panel)',
        border: '1px solid var(--app-border)',
        display: 'flex',
        alignItems: 'center',
        padding: '6px 12px',
        gap: 4,
      }}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <div style={{ position: 'relative', display: 'flex' }}>
        <button
          type="button"
          aria-label="Brush Color"
          onClick={() => setState({ ...state, activePanel: state.activePanel === 'color' ? null : 'color' })}
          style={{
            width: 32,
            height: 32,
            border: 'none',
            background: state.activePanel === 'color' ? 'var(--app-control-hover)' : 'transparent',
            borderRadius: 8,
            display: 'grid',
            placeItems: 'center',
            cursor: 'pointer',
            padding: 0,
          }}
        >
          <span
            style={{
              width: 18,
              height: 18,
              borderRadius: '50%',
              border: '1px solid var(--app-border)',
              background: swatchBackground,
              display: 'block',
            }}
          />
        </button>
        {state.activePanel === 'color' && (
          <BrushColorPopover
            title="Color"
            color={state.color}
            isDark={isDark}
            anchor="top-left"
            onClose={() => setState({ ...state, activePanel: null })}
            onChange={(color) => setState({ ...state, color })}
          />
        )}
      </div>

      <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--app-border)' }} />

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 10px', color: 'var(--app-foreground)', fontSize: 14, lineHeight: 1 }}>
        <span style={{ fontWeight: 500 }}>Size</span>
        <input
          type="number"
          min="1"
          max="999"
          value={state.size}
          onChange={(event) => setState({ ...state, size: Math.max(1, Math.min(999, Number(event.target.value) || 1)) })}
          style={{ width: 46, border: 'none', outline: 'none', background: 'transparent', fontSize: 14, color: 'var(--app-foreground)', padding: 0 }}
        />
        <span style={{ color: 'var(--app-foreground-subtle)', fontSize: 14 }}>Px</span>
      </label>
    </div>
  )
}
