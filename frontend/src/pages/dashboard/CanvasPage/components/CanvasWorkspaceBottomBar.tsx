// @ts-nocheck

import { Minus, Plus } from 'lucide-react'

export function CanvasWorkspaceBottomBar(props: any) {
  const {
    isDark: _isDark,
    isLayerPanelOpen,
    setIsLayerPanelOpen,
    zoomOut,
    zoom,
    zoomIn,
  } = props

  return (
    <div
      style={{
        height: 36,
        minHeight: 36,
        display: 'flex',
        alignItems: 'center',
        padding: '0 16px',
        borderTop: '1px solid var(--app-border)',
        backgroundColor: 'var(--app-glass)',
        backdropFilter: 'var(--app-blur)',
        WebkitBackdropFilter: 'var(--app-blur)',
        zIndex: 100,
      }}
    >
      <div
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '3px 10px',
            borderRadius: 999,
            backgroundColor: 'var(--app-control)',
            border: '1px solid var(--app-border)',
            boxShadow: 'var(--app-shadow-control)',
          }}
        >
          {!isLayerPanelOpen && (
            <div
              onClick={() => setIsLayerPanelOpen(true)}
              style={{
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 24,
                height: 24,
                borderRadius: 999,
                color: 'var(--app-foreground-muted)',
                transition: 'background 0.2s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--app-control-hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="12 2 2 7 12 12 22 7 12 2" />
                <polyline points="2 17 12 22 22 17" />
                <polyline points="2 12 12 17 22 12" />
              </svg>
            </div>
          )}

          {!isLayerPanelOpen && (
            <div
              style={{
                width: 1,
                alignSelf: 'stretch',
                backgroundColor: 'var(--app-border)',
                margin: '3px 4px',
              }}
            />
          )}

          <div
            onClick={zoomOut}
            style={{
              width: 24,
              height: 24,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              borderRadius: 999,
              color: 'var(--app-foreground-muted)',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--app-control-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <Minus style={{ width: 14, height: 14 }} />
          </div>

          <span
            style={{
              minWidth: 48,
              textAlign: 'center',
              fontSize: 13,
              fontWeight: 500,
              letterSpacing: '0.01em',
              color: 'var(--app-foreground)',
              userSelect: 'none',
            }}
          >
            {Math.round(zoom)}%
          </span>

          <div
            onClick={zoomIn}
            style={{
              width: 24,
              height: 24,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              borderRadius: 999,
              color: 'var(--app-foreground-muted)',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--app-control-hover)')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          >
            <Plus style={{ width: 14, height: 14 }} />
          </div>
        </div>
      </div>
    </div>
  )
}
