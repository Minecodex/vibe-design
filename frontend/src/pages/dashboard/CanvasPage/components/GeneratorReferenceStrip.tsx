import React, { useCallback } from 'react'
import { X } from 'lucide-react'
import type { GeneratorReferenceChip } from './useGeneratorReferenceChips'

type GeneratorReferenceStripProps = {
  chips: GeneratorReferenceChip[]
  isDark: boolean
  onPreviewImage: (url: string) => void
  onRemove?: (id: string) => void
}

const chipStyleBase: React.CSSProperties = {
  position: 'relative',
  width: 32,
  height: 32,
  borderRadius: 6,
  overflow: 'hidden',
  flexShrink: 0,
  cursor: 'zoom-in',
}

const imageStyle: React.CSSProperties = {
  width: '100%',
  height: '100%',
  objectFit: 'cover',
}

const removeButtonStyle: React.CSSProperties = {
  position: 'absolute',
  top: -2,
  right: -2,
  width: 14,
  height: 14,
  backgroundColor: 'var(--app-danger)',
  borderRadius: '50%',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  cursor: 'pointer',
  border: '1.5px solid var(--app-surface-solid)',
  color: 'var(--app-primary-foreground)',
  zIndex: 10,
  padding: 0,
}

function areChipsEqual(previous: GeneratorReferenceChip[], next: GeneratorReferenceChip[]) {
  if (previous === next) return true
  if (previous.length !== next.length) return false

  return previous.every((previousChip, index) => {
    const nextChip = next[index]
    return previousChip.id === nextChip.id
      && previousChip.imageUrl === nextChip.imageUrl
      && previousChip.alt === nextChip.alt
      && previousChip.removeLabel === nextChip.removeLabel
      && previousChip.draggable === nextChip.draggable
      && previousChip.onDragStart === nextChip.onDragStart
  })
}

function areReferenceStripPropsEqual(
  previous: GeneratorReferenceStripProps,
  next: GeneratorReferenceStripProps,
) {
  return previous.isDark === next.isDark
    && previous.onPreviewImage === next.onPreviewImage
    && previous.onRemove === next.onRemove
    && areChipsEqual(previous.chips, next.chips)
}

export const GeneratorReferenceStrip = React.memo(function GeneratorReferenceStrip({
  chips,
  onPreviewImage,
  onRemove,
}: GeneratorReferenceStripProps) {
  const handlePreview = useCallback((event: React.MouseEvent<HTMLDivElement>, imageUrl: string) => {
    event.stopPropagation()
    onPreviewImage(imageUrl)
  }, [onPreviewImage])

  const handleRemove = useCallback((event: React.MouseEvent<HTMLButtonElement>, id: string) => {
    event.stopPropagation()
    onRemove?.(id)
  }, [onRemove])

  if (chips.length === 0) return null

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {chips.map((chip) => (
        <div
          key={chip.id}
          draggable={chip.draggable}
          onDragStart={chip.onDragStart}
          onClick={(event) => handlePreview(event, chip.imageUrl)}
          style={{
            ...chipStyleBase,
            border: '1px solid var(--app-border)',
            cursor: chip.draggable ? 'grab' : 'zoom-in',
          }}
        >
          <img
            src={chip.imageUrl}
            alt={chip.alt}
            loading="lazy"
            decoding="async"
            draggable={false}
            style={imageStyle}
          />
          {onRemove && chip.removeLabel && (
            <button
              type="button"
              aria-label={chip.removeLabel}
              onClick={(event) => handleRemove(event, chip.id)}
              style={removeButtonStyle}
            >
              <X size={8} color="currentColor" strokeWidth={3} />
            </button>
          )}
        </div>
      ))}
    </div>
  )
}, areReferenceStripPropsEqual)
