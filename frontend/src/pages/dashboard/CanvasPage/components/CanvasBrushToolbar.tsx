import type { CSSProperties, ReactNode } from 'react'
import { useEffect, useMemo, useState } from 'react'

import { X } from 'lucide-react'

import type { CanvasItem } from '@/api/endpoints/projects'
import type { BrushToolbarState } from '../types'

type BrushColor = {
  r: number
  g: number
  b: number
  a: number
}

const TOOLBAR_SCALE = 0.65
const COLOR_SWATCHES = ['transparent', '#000000', '#ffffff', '#00ff00', '#a55cf6', '#d6c2ff']

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function channelToHex(channel: number) {
  return clamp(Math.round(channel), 0, 255).toString(16).padStart(2, '0')
}

function parseBrushColorValue(value?: string | null): BrushColor {
  if (!value || value === 'transparent') {
    return { r: 0, g: 0, b: 0, a: 0 }
  }

  const normalized = value.trim()
  if (/^#([\da-f]{3})$/i.test(normalized)) {
    const [, shortHex] = normalized.match(/^#([\da-f]{3})$/i) || []
    return {
      r: Number.parseInt(shortHex[0] + shortHex[0], 16),
      g: Number.parseInt(shortHex[1] + shortHex[1], 16),
      b: Number.parseInt(shortHex[2] + shortHex[2], 16),
      a: 1,
    }
  }

  if (/^#([\da-f]{6})([\da-f]{2})?$/i.test(normalized)) {
    const [, hex6, alphaHex] = normalized.match(/^#([\da-f]{6})([\da-f]{2})?$/i) || []
    return {
      r: Number.parseInt(hex6.slice(0, 2), 16),
      g: Number.parseInt(hex6.slice(2, 4), 16),
      b: Number.parseInt(hex6.slice(4, 6), 16),
      a: alphaHex ? Number.parseInt(alphaHex, 16) / 255 : 1,
    }
  }

  const rgbaMatch = normalized.match(/^rgba?\(([^)]+)\)$/i)
  if (rgbaMatch) {
    const [r = '0', g = '0', b = '0', a = '1'] = rgbaMatch[1].split(',').map((part) => part.trim())
    return {
      r: clamp(Number(r) || 0, 0, 255),
      g: clamp(Number(g) || 0, 0, 255),
      b: clamp(Number(b) || 0, 0, 255),
      a: clamp(Number(a) || 0, 0, 1),
    }
  }

  return { r: 17, g: 17, b: 17, a: 1 }
}

function serializeBrushColorValue(color: BrushColor) {
  if (color.a <= 0) return 'transparent'
  const hex = `#${channelToHex(color.r)}${channelToHex(color.g)}${channelToHex(color.b)}`
  if (color.a >= 1) return hex
  return `${hex}${channelToHex(color.a * 255)}`
}

function colorToHexInput(color: BrushColor) {
  return `${channelToHex(color.r)}${channelToHex(color.g)}${channelToHex(color.b)}`
}

function rgbToHsv(r: number, g: number, b: number) {
  const red = r / 255
  const green = g / 255
  const blue = b / 255
  const max = Math.max(red, green, blue)
  const min = Math.min(red, green, blue)
  const delta = max - min

  let hue = 0
  if (delta !== 0) {
    if (max === red) hue = ((green - blue) / delta) % 6
    else if (max === green) hue = (blue - red) / delta + 2
    else hue = (red - green) / delta + 4
  }

  return {
    h: Math.round((hue * 60 + 360) % 360),
    s: max === 0 ? 0 : delta / max,
    v: max,
  }
}

function hsvToRgb(h: number, s: number, v: number) {
  const hue = ((h % 360) + 360) % 360
  const chroma = v * s
  const x = chroma * (1 - Math.abs(((hue / 60) % 2) - 1))
  const match = v - chroma

  let red = 0
  let green = 0
  let blue = 0

  if (hue < 60) {
    red = chroma
    green = x
  } else if (hue < 120) {
    red = x
    green = chroma
  } else if (hue < 180) {
    green = chroma
    blue = x
  } else if (hue < 240) {
    green = x
    blue = chroma
  } else if (hue < 300) {
    red = x
    blue = chroma
  } else {
    red = chroma
    blue = x
  }

  return {
    r: Math.round((red + match) * 255),
    g: Math.round((green + match) * 255),
    b: Math.round((blue + match) * 255),
  }
}

function colorToCss(color: BrushColor) {
  return `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${clamp(color.a, 0, 1)})`
}

function getCheckerboardBackground(size = 12) {
  return `linear-gradient(45deg, #d7d7d7 25%, transparent 25%), linear-gradient(-45deg, #d7d7d7 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #d7d7d7 75%), linear-gradient(-45deg, transparent 75%, #d7d7d7 75%) 0 0 / ${size}px ${size}px, #f5f5f5`
}

function ToolbarPopover({ children, minWidth, anchor = 'top-center' }: {
  children: ReactNode
  isDark: boolean
  minWidth?: number
  anchor?: 'top-center' | 'top-left'
}) {
  const positionedStyle = anchor === 'top-left'
    ? {
      bottom: 'calc(100% + 8px)',
      left: 0,
      transform: `translateY(0) scale(${TOOLBAR_SCALE})`,
      transformOrigin: 'left bottom',
    }
    : {
      bottom: 'calc(100% + 12px)',
      left: '50%',
      transform: `translateX(-50%) scale(${TOOLBAR_SCALE})`,
      transformOrigin: 'bottom center',
    }

  return (
    <div
      style={{
        position: 'absolute',
        backgroundColor: 'var(--app-glass)',
        border: '1px solid var(--app-border)',
        borderRadius: 12,
        boxShadow: 'var(--app-shadow-panel)',
        backdropFilter: 'var(--app-blur)',
        WebkitBackdropFilter: 'var(--app-blur)',
        minWidth,
        zIndex: 2147483550,
        overflow: 'hidden',
        ...positionedStyle,
      }}
    >
      {children}
    </div>
  )
}

function ToolbarButton({ label, active, onClick, children, panel }: {
  label: string
  active?: boolean
  onClick: () => void
  children: ReactNode
  panel?: ReactNode
  isDark: boolean
}) {
  return (
    <div style={{ position: 'relative', display: 'flex' }}>
      <button
        type="button"
        title={label}
        aria-label={label}
        onClick={onClick}
        style={{
          border: 'none',
          background: active ? 'var(--app-control-selected)' : 'transparent',
          borderRadius: 8,
          height: 32,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '0 10px',
          cursor: 'pointer',
          color: active ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground)',
          fontSize: 13,
          minWidth: 32,
          justifyContent: 'center',
        }}
      >
        {children}
        <span
          style={{
            position: 'absolute',
            width: 1,
            height: 1,
            padding: 0,
            margin: -1,
            overflow: 'hidden',
            clip: 'rect(0, 0, 0, 0)',
            whiteSpace: 'nowrap',
            border: 0,
          }}
        >
          {label}
        </span>
      </button>
      {panel}
    </div>
  )
}

export function BrushColorPopover({
  title,
  color,
  isDark,
  onClose,
  onChange,
  anchor,
}: {
  title: string
  color: string
  isDark: boolean
  onClose: () => void
  onChange: (color: string) => void
  anchor?: 'top-center' | 'top-left'
}) {
  const currentColor = useMemo(() => parseBrushColorValue(color), [color])
  const visibleColor = currentColor.a > 0 ? currentColor : { ...currentColor, a: 1 }
  const { h, s, v } = useMemo(
    () => rgbToHsv(visibleColor.r, visibleColor.g, visibleColor.b),
    [visibleColor.b, visibleColor.g, visibleColor.r],
  )
  const opacityPercent = Math.round(currentColor.a * 100)
  const [hexDraft, setHexDraft] = useState(colorToHexInput(visibleColor))

  useEffect(() => {
    setHexDraft(colorToHexInput({ r: visibleColor.r, g: visibleColor.g, b: visibleColor.b, a: 1 }))
  }, [visibleColor.b, visibleColor.g, visibleColor.r])

  const commitColor = (nextColor: BrushColor) => {
    onChange(serializeBrushColorValue(nextColor))
  }

  const commitHsv = (nextHue: number, nextSaturation: number, nextValue: number, nextAlpha = currentColor.a) => {
    const nextRgb = hsvToRgb(nextHue, nextSaturation, nextValue)
    commitColor({ ...nextRgb, a: nextAlpha })
  }

  const huePreview = hsvToRgb(h, 1, 1)
  const alphaPreview = colorToCss({ ...visibleColor, a: 1 })

  return (
    <ToolbarPopover isDark={isDark} minWidth={420} anchor={anchor}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '26px 28px' }}>
        <span style={{ fontSize: 22, fontWeight: 500, color: 'var(--app-foreground)' }}>{title}</span>
        <button
          type="button"
          aria-label={`close-${title}`}
          onClick={onClose}
          style={{
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            width: 40,
            height: 40,
            borderRadius: 12,
            display: 'grid',
            placeItems: 'center',
            color: 'var(--app-foreground)',
          }}
        >
          <X size={28} />
        </button>
      </div>

      <div style={{ height: 1, background: 'var(--app-border)' }} />

      <div style={{ padding: 24, display: 'grid', gap: 18 }}>
        <div
          style={{
            position: 'relative',
            height: 208,
            borderRadius: 18,
            overflow: 'hidden',
            background: `rgb(${huePreview.r}, ${huePreview.g}, ${huePreview.b})`,
          }}
          onPointerDown={(event) => {
            const element = event.currentTarget

            const updateFromPointer = (clientX: number, clientY: number) => {
              const rect = element.getBoundingClientRect()
              const saturation = clamp((clientX - rect.left) / rect.width, 0, 1)
              const value = clamp(1 - (clientY - rect.top) / rect.height, 0, 1)
              commitHsv(h, saturation, value)
            }

            updateFromPointer(event.clientX, event.clientY)

            const handleMove = (moveEvent: PointerEvent) => updateFromPointer(moveEvent.clientX, moveEvent.clientY)
            const handleUp = () => {
              window.removeEventListener('pointermove', handleMove)
              window.removeEventListener('pointerup', handleUp)
            }

            window.addEventListener('pointermove', handleMove)
            window.addEventListener('pointerup', handleUp)
          }}
        >
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(90deg, #ffffff 0%, rgba(255,255,255,0) 100%)' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, #000000 100%)' }} />
          <span
            style={{
              position: 'absolute',
              left: `calc(${s * 100}% - 12px)`,
              top: `calc(${(1 - v) * 100}% - 12px)`,
              width: 24,
              height: 24,
              borderRadius: '50%',
              border: '4px solid var(--app-primary-foreground)',
              boxShadow: '0 2px 8px rgba(0,0,0,0.24)',
              background: colorToCss({ ...visibleColor, a: 1 }),
            }}
          />
        </div>

        <div style={{ display: 'grid', gap: 12 }}>
          <input
            type="range"
            min="0"
            max="360"
            value={h}
            onChange={(event) => commitHsv(Number(event.target.value), s, v)}
            style={{
              width: '100%',
              margin: 0,
              accentColor: 'var(--app-primary)',
              background: 'linear-gradient(90deg, #ff0000 0%, #ffff00 16%, #00ff00 33%, #00ffff 50%, #0000ff 66%, #ff00ff 83%, #ff0000 100%)',
              borderRadius: 999,
              height: 18,
              appearance: 'none',
            }}
          />

          <div style={{ position: 'relative', borderRadius: 999, overflow: 'hidden', background: getCheckerboardBackground(10) }}>
            <input
              type="range"
              min="0"
              max="100"
              value={opacityPercent}
              onChange={(event) => {
                const nextOpacity = clamp(Number(event.target.value) / 100, 0, 1)
                commitColor({ ...visibleColor, a: nextOpacity })
              }}
              style={{
                width: '100%',
                margin: 0,
                accentColor: 'var(--app-primary)',
                background: `linear-gradient(90deg, rgba(${visibleColor.r}, ${visibleColor.g}, ${visibleColor.b}, 0) 0%, ${alphaPreview} 100%)`,
                borderRadius: 999,
                height: 18,
                appearance: 'none',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, minmax(0, 1fr))', gap: 12 }}>
          {COLOR_SWATCHES.map((swatch) => {
            const isTransparent = swatch === 'transparent'
            const swatchColor = parseBrushColorValue(swatch)
            const swatchStyle: CSSProperties = isTransparent
              ? {
                background: getCheckerboardBackground(10),
                border: '1px solid var(--app-border)',
              }
              : {
                background: colorToCss({ ...swatchColor, a: 1 }),
                border: '1px solid var(--app-border)',
              }

            const isActive = isTransparent
              ? color === 'transparent'
              : serializeBrushColorValue({ ...swatchColor, a: 1 }).toLowerCase() === color.toLowerCase()

            return (
              <button
                key={swatch}
                type="button"
                aria-label={`${title}-${swatch}`}
                onClick={() => {
                  if (isTransparent) {
                    onChange('transparent')
                    return
                  }
                  commitColor({ ...swatchColor, a: 1 })
                }}
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: '50%',
                  cursor: 'pointer',
                  position: 'relative',
                  boxShadow: isActive ? '0 0 0 3px var(--app-primary) inset' : 'none',
                  ...swatchStyle,
                }}
              >
                {isTransparent ? (
                  <>
                    <span
                      style={{
                        position: 'absolute',
                        inset: 8,
                        borderRadius: '50%',
                        border: '1px solid var(--app-border-strong)',
                        background: 'transparent',
                      }}
                    />
                    <span
                      style={{
                        position: 'absolute',
                        left: 8,
                        right: 8,
                        top: '50%',
                        height: 2,
                        background: 'var(--app-danger)',
                        transform: 'rotate(-45deg)',
                        transformOrigin: 'center',
                      }}
                    />
                  </>
                ) : null}
              </button>
            )
          })}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 120px', gap: 14 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 12, background: 'var(--app-control)', borderRadius: 14, padding: '14px 16px' }}>
            <span style={{ color: 'var(--app-foreground-muted)', fontSize: 18 }}>#</span>
            <input
              type="text"
              value={hexDraft}
              onChange={(event) => {
                const nextValue = event.target.value.replace(/[^0-9a-f]/gi, '').slice(0, 6).toLowerCase()
                setHexDraft(nextValue)
                if (nextValue.length === 6) {
                  commitColor({
                    r: Number.parseInt(nextValue.slice(0, 2), 16),
                    g: Number.parseInt(nextValue.slice(2, 4), 16),
                    b: Number.parseInt(nextValue.slice(4, 6), 16),
                    a: currentColor.a,
                  })
                }
              }}
              onBlur={() => setHexDraft(colorToHexInput({ r: visibleColor.r, g: visibleColor.g, b: visibleColor.b, a: 1 }))}
              style={{
                width: '100%',
                border: 'none',
                outline: 'none',
                background: 'transparent',
                fontSize: 18,
                color: 'var(--app-foreground)',
                textTransform: 'lowercase',
              }}
            />
          </label>

          <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, background: 'var(--app-control)', borderRadius: 14, padding: '14px 16px' }}>
            <input
              type="number"
              min="0"
              max="100"
              value={opacityPercent}
              onChange={(event) => {
                const nextValue = clamp(Number(event.target.value) || 0, 0, 100)
                commitColor({ ...visibleColor, a: nextValue / 100 })
              }}
              style={{
                width: 52,
                border: 'none',
                outline: 'none',
                background: 'transparent',
                textAlign: 'right',
                fontSize: 18,
                color: 'var(--app-foreground)',
              }}
            />
            <span style={{ color: 'var(--app-foreground-muted)', fontSize: 18 }}>%</span>
          </label>
        </div>
      </div>
    </ToolbarPopover>
  )
}

type CanvasBrushToolbarProps = {
  item: CanvasItem
  rect: { left: number; top: number; width: number; height: number }
  isDark: boolean
  colorLabel: string
  sizeLabel: string
  widthLabel: string
  heightLabel: string
  state: BrushToolbarState
  setState: (state: BrushToolbarState) => void
  updateBrushItem: (itemId: string, updates: Record<string, number | string>) => void
}

export function CanvasBrushToolbar({
  item,
  rect,
  isDark,
  colorLabel,
  sizeLabel,
  widthLabel,
  heightLabel,
  state,
  setState,
  updateBrushItem,
}: CanvasBrushToolbarProps) {
  const toolbarTop = Math.max(20, rect.top - 88)
  const toolbarLeft = Math.max(96, rect.left + rect.width / 2)
  const itemColor = item.brushColor || '#111111'
  const swatchBackground = itemColor === 'transparent' ? getCheckerboardBackground(8) : itemColor

  return (
    <div
      style={{
        position: 'fixed',
        left: toolbarLeft,
        top: toolbarTop,
        transform: 'translateX(-50%)',
        zIndex: 2147483450,
        backgroundColor: 'var(--app-glass)',
        border: '1px solid var(--app-border)',
        borderRadius: 12,
        boxShadow: 'var(--app-shadow-panel)',
        backdropFilter: 'var(--app-blur)',
        WebkitBackdropFilter: 'var(--app-blur)',
        padding: '6px 12px',
        display: 'flex',
        alignItems: 'center',
        gap: 4,
      }}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <ToolbarButton
        label={colorLabel}
        active={state.activePanel === 'color'}
        onClick={() => setState({ activePanel: state.activePanel === 'color' ? null : 'color' })}
        panel={state.activePanel === 'color'
          ? (
            <BrushColorPopover
              title={colorLabel}
              color={itemColor}
              isDark={isDark}
              onClose={() => setState({ activePanel: null })}
              onChange={(nextColor) => updateBrushItem(item.id, { brushColor: nextColor })}
            />
          )
          : null}
        isDark={isDark}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            background: swatchBackground,
            border: '1px solid var(--app-border)',
          }}
        />
      </ToolbarButton>

      <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--app-border)' }} />

      <label style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '0 10px', color: 'var(--app-foreground)' }}>
        <span>{sizeLabel}</span>
        <input
          type="number"
          min="1"
          max="999"
          value={item.brushSize || 1}
          onChange={(event) => updateBrushItem(item.id, { brushSize: clamp(Number(event.target.value) || 1, 1, 999) })}
          style={{ width: 62, border: 'none', outline: 'none', background: 'transparent', fontSize: 16, color: 'var(--app-foreground)' }}
        />
        <span style={{ color: 'var(--app-foreground-subtle)' }}>Px</span>
      </label>

      <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--app-border)' }} />

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 10px', color: 'var(--app-foreground)' }}>
        <span>{widthLabel}</span>
        <input
          type="number"
          min="1"
          value={Math.round(item.width || 1)}
          onChange={(event) => updateBrushItem(item.id, { width: Math.max(1, Number(event.target.value) || 1) })}
          style={{ width: 60, border: 'none', outline: 'none', background: 'transparent', fontSize: 16, color: 'var(--app-foreground)' }}
        />
      </label>

      <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '0 10px', color: 'var(--app-foreground)' }}>
        <span>{heightLabel}</span>
        <input
          type="number"
          min="1"
          value={Math.round(item.height || 1)}
          onChange={(event) => updateBrushItem(item.id, { height: Math.max(1, Number(event.target.value) || 1) })}
          style={{ width: 60, border: 'none', outline: 'none', background: 'transparent', fontSize: 16, color: 'var(--app-foreground)' }}
        />
      </label>
    </div>
  )
}
