import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'

import { Check, ChevronDown, SlidersHorizontal, X } from 'lucide-react'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  DEFAULT_TEXT_STROKE,
  getSupportedFontVariants,
  normalizeTextCanvasItem,
  textFontRegistry,
} from '../textTypography'

type CanvasTextToolbarProps = {
  item: CanvasItem
  rect: { left: number; top: number; width: number; height: number }
  isDark: boolean
  labels: {
    fill: string
    stroke: string
    font: string
    variant: string
    size: string
    align: string
    more: string
    vertical: string
  }
  state: { activePanel: string | null }
  setState: (state: { activePanel: string | null }) => void
  updateTextStyle: (itemId: string, updates: Record<string, unknown>) => void
}

type ColorField = 'fillColor' | 'strokeColor'

type RgbaColor = {
  r: number
  g: number
  b: number
  a: number
}

const PANEL_SIZE_OPTIONS = [16, 32, 48, 64, 80, 96, 112, 128, 144, 160, 176, 192, 208, 224, 256, 288, 320, 384, 448, 512]
const COLOR_SWATCHES = ['transparent', '#000000', '#ffffff', '#00ff00', '#a55cf6', '#d6c2ff']
const TOOLBAR_SCALE = 0.65
const POPOVER_SCALE = Number((TOOLBAR_SCALE * 1.3).toFixed(3))
const MAX_TEXT_FONT_SIZE = 9999

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function channelToHex(channel: number) {
  return clamp(Math.round(channel), 0, 255).toString(16).padStart(2, '0')
}

function parseColorValue(value?: string | null): RgbaColor {
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

  return { r: 0, g: 0, b: 0, a: 1 }
}

function serializeColorValue(color: RgbaColor) {
  if (color.a <= 0) return 'transparent'
  const hex = `#${channelToHex(color.r)}${channelToHex(color.g)}${channelToHex(color.b)}`
  if (color.a >= 1) return hex
  return `${hex}${channelToHex(color.a * 255)}`
}

function colorToHexInput(color: RgbaColor) {
  return `${channelToHex(color.r)}${channelToHex(color.g)}${channelToHex(color.b)}`
}

function colorToCss(color: RgbaColor) {
  return `rgba(${Math.round(color.r)}, ${Math.round(color.g)}, ${Math.round(color.b)}, ${clamp(color.a, 0, 1)})`
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

function getCheckerboardBackground(size = 12) {
  return `linear-gradient(45deg, #d7d7d7 25%, transparent 25%), linear-gradient(-45deg, #d7d7d7 25%, transparent 25%), linear-gradient(45deg, transparent 75%, #d7d7d7 75%), linear-gradient(-45deg, transparent 75%, #d7d7d7 75%) 0 0 / ${size}px ${size}px, #f5f5f5`
}

function ToolbarPopover({ children, minWidth }: {
  children: ReactNode
  isDark: boolean
  minWidth?: number
}) {
  return (
    <div
      style={{
        position: 'absolute',
        bottom: 'calc(100% + 12px)',
        left: '50%',
        transform: `translateX(-50%) scale(${POPOVER_SCALE})`,
        transformOrigin: 'bottom center',
        backgroundColor: 'var(--app-glass)',
        border: '1px solid var(--app-border)',
        borderRadius: 12,
        boxShadow: 'var(--app-shadow-panel)',
        backdropFilter: 'var(--app-blur)',
        WebkitBackdropFilter: 'var(--app-blur)',
        minWidth,
        zIndex: 2147483550,
        overflow: 'hidden',
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
  isDark?: boolean
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
          whiteSpace: 'nowrap',
          transition: 'background 0.2s',
        }}
        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--app-control-hover)'}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = active ? 'var(--app-control-selected)' : 'transparent'}
      >
        {children}
      </button>
      {panel}
    </div>
  )
}

function SegmentedButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        border: 'none',
        borderRadius: 12,
        padding: '10px 12px',
        background: active ? 'var(--app-control-selected)' : 'var(--app-surface-muted)',
        color: active ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground-muted)',
        cursor: 'pointer',
        minHeight: 44,
      }}
    >
      {label}
    </button>
  )
}

function ColorPopover({
  field,
  item,
  isDark,
  labels,
  closePanel,
  updateTextStyle,
}: {
  field: ColorField
  item: ReturnType<typeof normalizeTextCanvasItem>
  isDark: boolean
  labels: CanvasTextToolbarProps['labels']
  closePanel: () => void
  updateTextStyle: (itemId: string, updates: Record<string, unknown>) => void
}) {
  const currentColor = useMemo(() => parseColorValue(item[field]), [field, item])
  const visibleColor = currentColor.a > 0 ? currentColor : { ...currentColor, a: 1 }
  const { h, s, v } = useMemo(
    () => rgbToHsv(visibleColor.r, visibleColor.g, visibleColor.b),
    [visibleColor.b, visibleColor.g, visibleColor.r]
  )
  const opacityPercent = Math.round(currentColor.a * 100)
  const [hexDraft, setHexDraft] = useState(colorToHexInput(visibleColor))

  useEffect(() => {
    setHexDraft(colorToHexInput({ r: visibleColor.r, g: visibleColor.g, b: visibleColor.b, a: 1 }))
  }, [visibleColor.b, visibleColor.g, visibleColor.r])

  const commitColor = (nextColor: RgbaColor) => {
    const serialized = serializeColorValue(nextColor)
    updateTextStyle(item.id, {
      [field]: serialized,
      ...(field === 'strokeColor'
        ? { strokeWidth: serialized === 'transparent' ? 0 : Math.max(item.strokeWidth || 0, 1) }
        : {}),
    })
  }

  const commitHsv = (nextHue: number, nextSaturation: number, nextValue: number, nextAlpha = currentColor.a) => {
    const nextRgb = hsvToRgb(nextHue, nextSaturation, nextValue)
    commitColor({ ...nextRgb, a: nextAlpha })
  }

  const startAreaDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
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
  }

  const panelTitle = field === 'fillColor' ? labels.fill : labels.stroke
  const huePreview = hsvToRgb(h, 1, 1)
  const alphaPreview = colorToCss({ ...visibleColor, a: 1 })

  return (
    <ToolbarPopover isDark={isDark} minWidth={420}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '26px 28px' }}>
        <span style={{ fontSize: 22, fontWeight: 500, color: 'var(--app-foreground)' }}>{panelTitle}</span>
        <button
          type="button"
          aria-label={`close-${field}`}
          onClick={closePanel}
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
          onPointerDown={startAreaDrag}
          style={{
            position: 'relative',
            height: 208,
            borderRadius: 18,
            overflow: 'hidden',
            cursor: 'crosshair',
            background: `rgb(${huePreview.r}, ${huePreview.g}, ${huePreview.b})`,
          }}
        >
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(90deg, #ffffff 0%, rgba(255,255,255,0) 100%)',
            }}
          />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(180deg, rgba(0,0,0,0) 0%, #000000 100%)',
            }}
          />
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
              background:
                'linear-gradient(90deg, #ff0000 0%, #ffff00 16%, #00ff00 33%, #00ffff 50%, #0000ff 66%, #ff00ff 83%, #ff0000 100%)',
              borderRadius: 999,
              height: 18,
              appearance: 'none',
            }}
          />

          <div
            style={{
              position: 'relative',
              borderRadius: 999,
              overflow: 'hidden',
              background: getCheckerboardBackground(10),
            }}
          >
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
          {COLOR_SWATCHES.map((color) => {
            const isTransparent = color === 'transparent'
            const swatchColor = parseColorValue(color)
            const swatchStyle: CSSProperties = isTransparent
              ? {
                  background: getCheckerboardBackground(10),
                  border: '1px solid var(--app-border)',
                }
              : {
                  background: colorToCss({ ...swatchColor, a: 1 }),
                  border: '1px solid var(--app-border)',
                }

            return (
              <button
                key={`${field}-${color}`}
                type="button"
                aria-label={`${field}-${color}`}
                onClick={() => {
                  if (isTransparent) {
                    commitColor({ ...visibleColor, a: 0 })
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
                  boxShadow:
                    item[field] === color ||
                    (!isTransparent && serializeColorValue({ ...swatchColor, a: 1 }).toLowerCase() === item[field]?.toLowerCase())
                      ? '0 0 0 3px var(--app-primary) inset'
                      : 'none',
                  ...swatchStyle,
                }}
              >
                {isTransparent ? (
                  <span
                    style={{
                      position: 'absolute',
                      inset: 8,
                      borderRadius: '50%',
                      border: '1px solid var(--app-border-strong)',
                      background: 'transparent',
                    }}
                  />
                ) : null}
                {isTransparent ? (
                  <span
                    style={{
                      position: 'absolute',
                      left: 8,
                      right: 8,
                      top: '50%',
                      height: 2,
                      transform: 'rotate(-45deg)',
                      background: 'var(--app-danger)',
                    }}
                  />
                ) : null}
              </button>
            )
          })}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 112px', gap: 14 }}>
          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              background: 'var(--app-control)',
              borderRadius: 16,
              padding: '0 18px',
              minHeight: 56,
            }}
          >
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

          <label
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              background: 'var(--app-control)',
              borderRadius: 16,
              minHeight: 56,
              padding: '0 12px',
            }}
          >
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

export function CanvasTextToolbar({
  item,
  rect,
  isDark,
  labels,
  state,
  setState,
  updateTextStyle,
}: CanvasTextToolbarProps) {
  const textItem = normalizeTextCanvasItem(item)
  const toolbarRef = useRef<HTMLDivElement | null>(null)
  const supportedVariants = getSupportedFontVariants(textItem.fontFamily)
  const toolbarTop = Math.max(20, rect.top - 88)
  const toolbarLeft = Math.max(96, rect.left + rect.width / 2)
  const togglePanel = (panelKey: string) => setState({ activePanel: state.activePanel === panelKey ? null : panelKey })

  useEffect(() => {
    if (!state.activePanel) return

    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target
      if (!(target instanceof Node)) return
      if (toolbarRef.current?.contains(target)) return
      setState({ activePanel: null })
    }

    document.addEventListener('pointerdown', handlePointerDown)
    return () => document.removeEventListener('pointerdown', handlePointerDown)
  }, [setState, state.activePanel])

  const textTransformOptions = [
    { key: 'none', label: '-', value: textItem.textTransform === 'none' },
    { key: 'capitalize', label: 'Aa', value: textItem.textTransform === 'capitalize' },
    { key: 'uppercase', label: 'AA', value: textItem.textTransform === 'uppercase' },
    { key: 'lowercase', label: 'aa', value: textItem.textTransform === 'lowercase' },
  ]

  const listStyleOptions = [
    { key: 'none', label: '-', value: textItem.listStyle === 'none' },
    { key: 'ordered', label: '1 2', value: textItem.listStyle === 'ordered' },
    { key: 'unordered', label: '• •', value: textItem.listStyle === 'unordered' },
  ]

  const colorPanel = (field: ColorField) => (
    <ColorPopover
      field={field}
      item={textItem}
      isDark={isDark}
      labels={labels}
      closePanel={() => setState({ activePanel: null })}
      updateTextStyle={updateTextStyle}
    />
  )

  const alignPanel = (
    <ToolbarPopover isDark={isDark} minWidth={180}>
      <div style={{ display: 'flex', gap: 10, padding: 18 }}>
        {[
          { key: 'left', label: 'Left' },
          { key: 'center', label: 'Center' },
          { key: 'right', label: 'Right' },
        ].map((option) => (
          <SegmentedButton
            key={option.key}
            active={textItem.textAlign === option.key}
            label={option.label}
            onClick={() => updateTextStyle(textItem.id, { textAlign: option.key })}
          />
        ))}
      </div>
    </ToolbarPopover>
  )

  const fontPanel = (
    <ToolbarPopover isDark={isDark} minWidth={220}>
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 300, overflowY: 'auto', padding: 14 }}>
        {textFontRegistry.map((font) => (
          <button
            key={font.family}
            type="button"
            onClick={() => updateTextStyle(textItem.id, { fontFamily: font.family })}
            style={{
              border: 'none',
              background: font.family === textItem.fontFamily ? 'var(--app-control-selected)' : 'transparent',
              color: font.family === textItem.fontFamily ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground)',
              textAlign: 'left',
              padding: '8px 10px',
              borderRadius: 12,
              fontFamily: font.family,
              fontSize: 22,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <span>{font.label}</span>
            {font.family === textItem.fontFamily ? <Check size={16} /> : null}
          </button>
        ))}
      </div>
    </ToolbarPopover>
  )

  const variantPanel = (
    <ToolbarPopover isDark={isDark} minWidth={200}>
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 300, overflowY: 'auto', padding: 14 }}>
        {supportedVariants.map((variant) => (
          <button
            key={variant}
            type="button"
            onClick={() => updateTextStyle(textItem.id, { fontVariant: variant })}
            style={{
              border: 'none',
              background: variant === textItem.fontVariant ? 'var(--app-control-selected)' : 'transparent',
              color: variant === textItem.fontVariant ? 'var(--app-control-selected-foreground)' : 'var(--app-foreground)',
              textAlign: 'left',
              padding: '10px 12px',
              borderRadius: 12,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <span>{variant}</span>
            {variant === textItem.fontVariant ? <Check size={16} /> : null}
          </button>
        ))}
      </div>
    </ToolbarPopover>
  )

  const sizePanel = (
    <ToolbarPopover isDark={isDark} minWidth={176}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 420, overflowY: 'auto', padding: 18 }}>
        <label
          style={{
            position: 'sticky',
            top: 0,
            zIndex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '8px 10px',
            borderRadius: 12,
            background: 'var(--app-surface-muted)',
            boxShadow: 'inset 0 0 0 1px var(--app-border)',
          }}
        >
          <input
            type="number"
            min="16"
            max={String(MAX_TEXT_FONT_SIZE)}
            autoFocus
            value={textItem.fontSize}
            onFocus={(event) => event.currentTarget.select()}
            onChange={(event) => {
              const parsedValue = Number(event.target.value)
              if (!Number.isFinite(parsedValue)) return
              updateTextStyle(textItem.id, { fontSize: Math.min(MAX_TEXT_FONT_SIZE, Math.max(16, parsedValue)) })
            }}
            style={{
              width: '100%',
              border: 'none',
              outline: 'none',
              background: 'transparent',
              fontSize: 18,
              fontWeight: 600,
              color: 'var(--app-foreground)',
            }}
          />
          <span style={{ color: 'var(--app-foreground-muted)', fontSize: 14, fontWeight: 600 }}>
            px
          </span>
        </label>
        {PANEL_SIZE_OPTIONS.map((size) => (
          <button
            key={size}
            type="button"
            onClick={() => updateTextStyle(textItem.id, { fontSize: size })}
            style={{
              border: 'none',
              background: size === textItem.fontSize ? 'var(--app-control-hover)' : 'transparent',
              textAlign: 'left',
              padding: '8px 10px',
              borderRadius: 10,
              cursor: 'pointer',
            }}
          >
            {size}
          </button>
        ))}
      </div>
    </ToolbarPopover>
  )

  const morePanel = (
    <ToolbarPopover isDark={isDark} minWidth={320}>
      <div style={{ display: 'grid', gap: 12, padding: 18 }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--app-control)', borderRadius: 14, padding: '10px 12px' }}>
            <span style={{ minWidth: 42 }}>A</span>
            <input
              type="number"
              min="0.8"
              max="3"
              step="0.1"
              value={textItem.lineHeight}
              onChange={(event) => updateTextStyle(textItem.id, { lineHeight: Number(event.target.value) || 1.2 })}
              style={{ width: '100%', border: 'none', background: 'transparent', outline: 'none' }}
            />
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: 10, background: 'var(--app-control)', borderRadius: 14, padding: '10px 12px' }}>
            <span style={{ minWidth: 42 }}>|A|</span>
            <input
              type="number"
              min="-10"
              max="40"
              step="1"
              value={textItem.letterSpacing}
              onChange={(event) => updateTextStyle(textItem.id, { letterSpacing: Number(event.target.value) || 0 })}
              style={{ width: '100%', border: 'none', background: 'transparent', outline: 'none' }}
            />
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
          <SegmentedButton
            active={!textItem.underline && !textItem.strikeThrough}
            label="-"
            onClick={() => updateTextStyle(textItem.id, { underline: false, strikeThrough: false })}
          />
          <SegmentedButton
            active={textItem.underline}
            label={<span style={{ textDecoration: 'underline' }}>U</span>}
            onClick={() => updateTextStyle(textItem.id, { underline: !textItem.underline })}
          />
          <SegmentedButton
            active={textItem.strikeThrough}
            label={<span style={{ textDecoration: 'line-through' }}>S</span>}
            onClick={() => updateTextStyle(textItem.id, { strikeThrough: !textItem.strikeThrough })}
          />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 10 }}>
          {listStyleOptions.map((option) => (
            <SegmentedButton
              key={option.key}
              active={option.value}
              label={option.label}
              onClick={() => updateTextStyle(textItem.id, { listStyle: option.key })}
            />
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
          {textTransformOptions.map((option) => (
            <SegmentedButton
              key={option.key}
              active={option.value}
              label={option.label}
              onClick={() => updateTextStyle(textItem.id, { textTransform: option.key })}
            />
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10 }}>
          <SegmentedButton
            active={textItem.writingMode === 'horizontal'}
            label="水平"
            onClick={() => updateTextStyle(textItem.id, { writingMode: 'horizontal' })}
          />
          <SegmentedButton
            active={textItem.writingMode === 'vertical'}
            label={labels.vertical}
            onClick={() => updateTextStyle(textItem.id, { writingMode: 'vertical' })}
          />
        </div>
      </div>
    </ToolbarPopover>
  )

  return (
    <div
      ref={toolbarRef}
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
        label={labels.fill}
        active={state.activePanel === 'fill'}
        onClick={() => togglePanel('fill')}
        panel={state.activePanel === 'fill' ? colorPanel('fillColor') : null}
        isDark={isDark}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            background: textItem.fillColor === 'transparent' ? getCheckerboardBackground(8) : textItem.fillColor,
            border: '1px solid var(--app-border)',
          }}
        />
      </ToolbarButton>

      <ToolbarButton
        label={labels.stroke}
        active={state.activePanel === 'stroke'}
        onClick={() => togglePanel('stroke')}
        panel={state.activePanel === 'stroke' ? colorPanel('strokeColor') : null}
        isDark={isDark}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: '50%',
            border: textItem.strokeColor === 'transparent' ? '1px solid var(--app-border)' : `2px solid ${textItem.strokeColor || DEFAULT_TEXT_STROKE}`,
            background: textItem.strokeColor === 'transparent' ? getCheckerboardBackground(8) : '#ffffff',
          }}
        />
      </ToolbarButton>

      <div style={{ width: 1, alignSelf: 'stretch', background: 'var(--app-border)' }} />

      <ToolbarButton
        label={labels.font}
        active={state.activePanel === 'font'}
        onClick={() => togglePanel('font')}
        panel={state.activePanel === 'font' ? fontPanel : null}
        isDark={isDark}
      >
        <span style={{ fontFamily: textItem.fontFamily }}>{textItem.fontFamily.split(',')[0].replace(/['"]/g, '')}</span>
        <ChevronDown size={12} color="var(--app-foreground-subtle)" />
      </ToolbarButton>

      {supportedVariants.length > 1 && (
        <ToolbarButton
          label={labels.variant}
          active={state.activePanel === 'variant'}
          onClick={() => togglePanel('variant')}
          panel={state.activePanel === 'variant' ? variantPanel : null}
          isDark={isDark}
        >
          <span>{textItem.fontVariant}</span>
          <ChevronDown size={12} color="var(--app-foreground-subtle)" />
        </ToolbarButton>
      )}

      <div style={{ width: 1, height: 20, backgroundColor: 'var(--app-border)', margin: '0 4px' }} />

      <ToolbarButton
        label={labels.size}
        active={state.activePanel === 'size'}
        onClick={() => togglePanel('size')}
        panel={state.activePanel === 'size' ? sizePanel : null}
        isDark={isDark}
      >
        <span>{textItem.fontSize}</span>
        <ChevronDown size={12} color="var(--app-foreground-subtle)" />
      </ToolbarButton>

      <div style={{ width: 1, height: 20, backgroundColor: 'var(--app-border)', margin: '0 4px' }} />

      <ToolbarButton
        label={labels.align}
        active={state.activePanel === 'align'}
        onClick={() => togglePanel('align')}
        panel={state.activePanel === 'align' ? alignPanel : null}
        isDark={isDark}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <rect x="3" y="4" width="2" height="16" />
          <rect x="8" y="7" width="12" height="3" rx="1" />
          <rect x="8" y="14" width="8" height="3" rx="1" />
        </svg>
      </ToolbarButton>

      <ToolbarButton
        label={labels.more}
        active={state.activePanel === 'more'}
        onClick={() => togglePanel('more')}
        panel={state.activePanel === 'more' ? morePanel : null}
        isDark={isDark}
      >
        <SlidersHorizontal size={16} />
      </ToolbarButton>
    </div>
  )
}
