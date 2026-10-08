import { type CSSProperties, type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import { type LucideIcon, Image as ImageIcon } from 'lucide-react'

type GeneratorImageSourcePickerProps = {
  isDark: boolean
  label: string
  countLabel?: string
  active?: boolean
  disabled?: boolean
  localDisabled?: boolean
  libraryDisabled?: boolean
  referenceLibraryDisabled?: boolean
  accentColor?: string
  textColor?: string
  inactiveIconColor?: string
  testId?: string
  localLabel?: string
  libraryLabel?: string
  referenceLibraryLabel?: string
  triggerVariant?: 'button' | 'icon'
  icon?: LucideIcon
  iconSize?: number
  triggerStyle?: CSSProperties
  triggerContent?: ReactNode
  onPickLocal: () => void
  onPickFromLibrary: () => void
  onPickFromReferenceLibrary?: () => void
}

export function GeneratorImageSourcePicker({
  isDark,
  label,
  countLabel,
  active = false,
  disabled = false,
  localDisabled = false,
  libraryDisabled = false,
  referenceLibraryDisabled = libraryDisabled,
  accentColor = 'var(--app-primary)',
  textColor,
  inactiveIconColor,
  testId,
  localLabel = '本地图片',
  libraryLabel = '素材库',
  referenceLibraryLabel = '参考图库',
  triggerVariant = 'button',
  icon: TriggerIcon = ImageIcon,
  iconSize = 14,
  triggerStyle,
  triggerContent,
  onPickLocal,
  onPickFromLibrary,
  onPickFromReferenceLibrary,
}: GeneratorImageSourcePickerProps) {
  const rootRef = useRef<HTMLDivElement | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [supportsHover, setSupportsHover] = useState(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
    return window.matchMedia('(hover: hover)').matches
  })

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const query = window.matchMedia('(hover: hover)')
    const update = () => setSupportsHover(query.matches)
    update()
    query.addEventListener?.('change', update)
    return () => query.removeEventListener?.('change', update)
  }, [])

  useEffect(() => {
    if (!menuOpen) return
    const handleDocumentClick = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', handleDocumentClick)
    return () => document.removeEventListener('mousedown', handleDocumentClick)
  }, [menuOpen])

  const resolvedTextColor = useMemo(() => {
    if (disabled) return 'var(--app-foreground-subtle)'
    if (active || menuOpen) return accentColor
    return textColor || 'var(--app-foreground-muted)'
  }, [accentColor, active, disabled, menuOpen, textColor])

  const resolvedIconColor = useMemo(() => {
    if (disabled) return 'var(--app-foreground-subtle)'
    if (active || menuOpen) return accentColor
    return inactiveIconColor || 'var(--app-foreground-muted)'
  }, [accentColor, active, disabled, inactiveIconColor, menuOpen])

  const closeAndRun = (callback: () => void) => {
    setMenuOpen(false)
    callback()
  }

  return (
    <div
      ref={rootRef}
      data-testid={testId}
      style={{ position: 'relative', display: 'inline-flex' }}
      onMouseEnter={() => {
        if (supportsHover && !disabled) setMenuOpen(true)
      }}
      onMouseLeave={() => {
        if (supportsHover) setMenuOpen(false)
      }}
    >
      <button
        type="button"
        aria-label={label}
        disabled={disabled}
        onClick={(event) => {
          event.stopPropagation()
          if (!supportsHover && !disabled) {
            setMenuOpen((previous) => !previous)
          }
        }}
        style={{
          ...(triggerVariant === 'icon'
            ? {
                height: 20,
                width: 20,
                padding: 0,
                borderRadius: 999,
                border: 'none',
                backgroundColor: 'transparent',
                justifyContent: 'center',
              }
            : {
                height: 32,
                padding: '0 12px',
                borderRadius: 8,
                border: '1px solid var(--app-border)',
                backgroundColor: 'var(--app-control)',
                boxShadow: 'var(--app-shadow-control)',
              }),
          display: 'flex',
          alignItems: 'center',
          gap: triggerVariant === 'icon' ? 0 : 6,
          cursor: disabled ? 'not-allowed' : 'pointer',
          fontSize: 13,
          fontWeight: 500,
          color: resolvedTextColor,
          opacity: disabled ? 0.6 : 1,
          ...triggerStyle,
        }}
      >
        {triggerContent || (
          <>
            <TriggerIcon size={iconSize} color={resolvedIconColor} />
            {triggerVariant !== 'icon' && <span>{countLabel || label}</span>}
          </>
        )}
      </button>

      {menuOpen && !disabled && (
        <div
          style={{
            position: 'absolute',
            bottom: 'calc(100% - 4px)',
            left: 0,
            minWidth: 128,
            padding: 6,
            display: 'flex',
            flexDirection: 'column',
            gap: 4,
            borderRadius: 10,
            backgroundColor: 'var(--app-glass)',
            border: '1px solid var(--app-border)',
            boxShadow: 'var(--app-shadow-panel)',
            backdropFilter: 'var(--app-blur)',
            WebkitBackdropFilter: 'var(--app-blur)',
            zIndex: 1003,
          }}
        >
          <button
            type="button"
            aria-label={localLabel}
            disabled={localDisabled}
            onClick={(event) => {
              event.stopPropagation()
              if (!localDisabled) closeAndRun(onPickLocal)
            }}
            style={menuItemStyle(isDark, localDisabled)}
          >
            {localLabel}
          </button>
          <button
            type="button"
            aria-label={libraryLabel}
            disabled={libraryDisabled}
            onClick={(event) => {
              event.stopPropagation()
              if (!libraryDisabled) closeAndRun(onPickFromLibrary)
            }}
            style={menuItemStyle(isDark, libraryDisabled)}
          >
            {libraryLabel}
          </button>
          {onPickFromReferenceLibrary && (
            <button
              type="button"
              aria-label={referenceLibraryLabel}
              disabled={referenceLibraryDisabled}
              onClick={(event) => {
                event.stopPropagation()
                if (!referenceLibraryDisabled) closeAndRun(onPickFromReferenceLibrary)
              }}
              style={menuItemStyle(isDark, referenceLibraryDisabled)}
            >
              {referenceLibraryLabel}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function menuItemStyle(_isDark: boolean, disabled: boolean) {
  return {
    height: 32,
    padding: '0 10px',
    borderRadius: 8,
    border: 'none',
    backgroundColor: 'transparent',
          color: disabled ? 'var(--app-foreground-subtle)' : 'var(--app-foreground)',
    cursor: disabled ? 'not-allowed' : 'pointer',
    textAlign: 'left' as const,
    fontSize: 13,
    fontWeight: 500,
  }
}
