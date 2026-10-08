import React, { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Loader2 } from 'lucide-react'
import type { SpatialAngleSession } from '../types'

interface SpatialAngleOverlayProps {
  session: SpatialAngleSession
  isDark: boolean
  onCancel: () => void
  onConfirm: (x: number, y: number, scale: string) => void
}

export function SpatialAngleOverlay({ session, onCancel, onConfirm }: SpatialAngleOverlayProps) {
  const { t } = useTranslation()

  const [x, setX] = useState(session.x)
  const [y, setY] = useState(session.y)
  const [scale, setScale] = useState(session.scale)

  const dragStartPos = useRef<{ clientX: number, clientY: number, startX: number, startY: number } | null>(null)

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
    if (e.pointerType === 'mouse' && e.button !== 0) return

    e.currentTarget.setPointerCapture(e.pointerId)
    
    dragStartPos.current = {
      clientX: e.clientX,
      clientY: e.clientY,
      startX: x,
      startY: y,
    }
  }

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
    if (!dragStartPos.current) return
    
    // Guard against releasing the mouse cursor outside and returning
    if (e.pointerType === 'mouse' && e.buttons !== 1) {
      dragStartPos.current = null
      return
    }

    const sensitivity = 0.5
    const dx = (e.clientX - dragStartPos.current.clientX) * sensitivity
    const dy = (e.clientY - dragStartPos.current.clientY) * sensitivity

    let nextX = dragStartPos.current.startX + dx
    let nextY = dragStartPos.current.startY - dy

    nextX = Math.max(-90, Math.min(90, nextX))
    nextY = Math.max(-30, Math.min(60, nextY))

    setX(Math.round(nextX))
    setY(Math.round(nextY))
  }

  const handlePointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
    dragStartPos.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }

  const handlePointerCancel = (e: React.PointerEvent<HTMLDivElement>) => {
    e.stopPropagation()
    dragStartPos.current = null
    if (e.currentTarget.hasPointerCapture(e.pointerId)) {
      e.currentTarget.releasePointerCapture(e.pointerId)
    }
  }

  const fillColors = 'var(--app-primary)'
  const emptyColors = 'var(--app-control-track)'
  const borderColor = 'var(--app-border)'

  return (
    <>
      <style>{`
        .custom-angle-slider {
          -webkit-appearance: none;
          appearance: none;
          height: 10px;
          border-radius: 5px;
          border: 1px solid ${borderColor};
          outline: none;
        }
        .custom-angle-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: ${fillColors};
          cursor: pointer;
          border: none;
          transition: none;
        }
        .custom-angle-slider::-moz-range-thumb {
          width: 16px;
          height: 16px;
          border-radius: 50%;
          background: ${fillColors};
          cursor: pointer;
          border: none;
          transition: none;
        }
      `}</style>
      <div
        className="spatial-control-panel nowheel"
      style={{
        width: 320,
        backgroundColor: 'var(--app-glass)',
        borderRadius: 16,
        boxShadow: 'var(--app-shadow-panel)',
        border: '1px solid var(--app-border)',
        backdropFilter: 'var(--app-blur)',
        WebkitBackdropFilter: 'var(--app-blur)',
        padding: '24px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        cursor: 'default',
        pointerEvents: 'auto',
      }}
      onPointerDown={(e) => e.stopPropagation()}
      onPointerMove={(e) => e.stopPropagation()}
      onPointerUp={(e) => e.stopPropagation()}
    >
      <div style={{ fontSize: 16, fontWeight: 600, color: 'var(--app-foreground)' }}>
        {t('canvas.spatial_angle.title', '空间角度调整')}
      </div>

      {/* Interactive Image Preview */}
      <div
        style={{
          width: '100%',
          aspectRatio: '16/9',
          borderRadius: 8,
          overflow: 'hidden',
          backgroundColor: 'var(--app-control)',
          border: '1px solid var(--app-border)',
          position: 'relative',
          cursor: 'grab',
          perspective: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          touchAction: 'none',
          userSelect: 'none',
          WebkitUserSelect: 'none',
          WebkitTapHighlightColor: 'transparent',
          outline: 'none',
        }}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerCancel={handlePointerCancel}
        onPointerLeave={(e) => {
          if (dragStartPos.current && e.pointerType === 'mouse' && e.buttons !== 1) {
            dragStartPos.current = null
          }
        }}
      >
        <div
          style={{
            width: '100%',
            height: '100%',
            transform: `rotateX(${-y}deg) rotateY(${x}deg)`,
            transition: dragStartPos.current ? 'none' : 'transform 0.1s ease-out',
            transformStyle: 'preserve-3d',
            transformOrigin: 'center center',
            userSelect: 'none',
            WebkitUserSelect: 'none',
          }}
        >
          {/* Box effect wireframe */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              border: '1.5px dashed var(--app-border-strong)',
              backgroundColor: 'var(--app-surface-muted)',
              transform: 'translateZ(-10px)',
              pointerEvents: 'none',
            }}
          />
          <div style={{ width: '100%', height: '100%', overflow: 'hidden', borderRadius: 6 }}>
            <img
              src={session.imageUrl}
              alt="Source preview"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                boxShadow: 'var(--app-shadow-control)',
                pointerEvents: 'none',
                userSelect: 'none',
                WebkitUserSelect: 'none',
                WebkitTapHighlightColor: 'transparent',
                backgroundColor: 'var(--app-surface-solid)',
                transform: scale === 'close-up' ? 'scale(1.4)' : scale === 'wide-angle' ? 'scale(0.75)' : 'scale(1)',
                transition: 'transform 0.3s ease-out',
              }}
              draggable={false}
              onDragStart={(event) => event.preventDefault()}
            />
          </div>
        </div>
      </div>

      {/* Sliders */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8, color: 'var(--app-foreground-muted)' }}>
            <span style={{ fontWeight: 500 }}>{t('canvas.spatial_angle.pan_label', '左右倾斜 (X)')}</span>
            <span style={{ fontWeight: 600, color: 'var(--app-foreground)' }}>{x}°</span>
          </div>
          <input
            type="range"
            min="-90"
            max="90"
            value={x}
            title={String(x)}
            onChange={(e) => setX(Number(e.target.value))}
            className="custom-angle-slider"
            style={{ 
              width: '100%', 
              cursor: 'grab',
              background: `linear-gradient(to right, ${fillColors} ${((x + 90) / 180) * 100}%, ${emptyColors} ${((x + 90) / 180) * 100}%)`
            }}
          />
        </div>
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 8, color: 'var(--app-foreground-muted)' }}>
            <span style={{ fontWeight: 500 }}>{t('canvas.spatial_angle.tilt_label', '上下倾斜 (Y)')}</span>
            <span style={{ fontWeight: 600, color: 'var(--app-foreground)' }}>{y}°</span>
          </div>
          <input
            type="range"
            min="-30"
            max="60"
            value={y}
             title={String(y)}
            onChange={(e) => setY(Number(e.target.value))}
            className="custom-angle-slider"
            style={{ 
              width: '100%', 
              cursor: 'grab',
              background: `linear-gradient(to right, ${fillColors} ${((y + 30) / 90) * 100}%, ${emptyColors} ${((y + 30) / 90) * 100}%)`
            }}
          />
        </div>
      </div>

      {/* Scale Buttons */}
      <div>
        <div style={{ fontSize: 13, color: 'var(--app-foreground-muted)', marginBottom: 10, fontWeight: 500 }}>
          {t('canvas.spatial_angle.scale_label', '镜头缩放')}
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {['close-up', 'normal', 'wide-angle'].map((s) => {
            const labels: Record<string, string> = { 'close-up': '特写', 'normal': '正常', 'wide-angle': '广角' }
            const isSelected = scale === s
            return (
              <button
                key={s}
                onClick={() => setScale(s as any)}
                style={{
                  flex: 1,
                  padding: '10px 0',
                  borderRadius: 8,
                  border: '1px solid var(--app-border)',
                  backgroundColor: isSelected ? 'var(--app-control-selected)' : 'var(--app-control)',
                  color: isSelected ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)',
                  cursor: 'pointer',
                  fontSize: 13,
                  fontWeight: 600,
                  transition: 'background-color 0.2s, color 0.2s',
                  boxShadow: isSelected ? 'var(--app-shadow-selected)' : 'none',
                }}
              >
                {t(`canvas.spatial_angle.scale_${s.replace('-', '')}`, labels[s])}
              </button>
            )
          })}
        </div>
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: 12, marginTop: 4 }}>
        <button
          onClick={onCancel}
          disabled={session.isSubmitting}
          style={{
            flex: 1,
            padding: '12px 0',
            borderRadius: 10,
            border: 'none',
            background: 'var(--app-control)',
            color: 'var(--app-foreground-muted)',
            cursor: session.isSubmitting ? 'not-allowed' : 'pointer',
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {t('common.cancel', '取消')}
        </button>
        <button
          onClick={() => onConfirm(x, y, scale)}
          disabled={session.isSubmitting}
          style={{
            flex: 1,
            padding: '12px 0',
            borderRadius: 10,
            border: 'none',
            background: 'var(--app-primary)',
            color: 'var(--app-primary-foreground)',
            cursor: session.isSubmitting ? 'not-allowed' : 'pointer',
            fontSize: 14,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 6,
            boxShadow: 'var(--app-shadow-control)',
          }}
        >
          {session.isSubmitting && <Loader2 size={16} className="animate-spin" />}
          {t('common.confirm', '确认')}
        </button>
      </div>
    </div>
    </>
  )
}
