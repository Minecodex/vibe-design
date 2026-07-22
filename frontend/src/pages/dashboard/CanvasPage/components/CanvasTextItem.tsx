import type { CSSProperties } from 'react'
import { useEffect, useMemo, useRef, useState } from 'react'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  DEFAULT_TEXT_FILL,
  DEFAULT_TEXT_VALUE,
  formatTextContentForDisplay,
  getTextItemVariantStyle,
  normalizeTextCanvasItem,
} from '../textTypography'

type CanvasTextItemProps = {
  item: CanvasItem
  isEditing: boolean
  onStartEdit: (itemId: string) => void
  onCommitEdit: (itemId: string, value: string) => void
  onCancelEdit: () => void
}

export function CanvasTextItem({
  item,
  isEditing,
  onStartEdit,
  onCommitEdit,
  onCancelEdit,
}: CanvasTextItemProps) {
  const normalizedItem = useMemo(() => normalizeTextCanvasItem(item), [item])
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const [draft, setDraft] = useState(normalizedItem.text || DEFAULT_TEXT_VALUE)
  const variantStyle = getTextItemVariantStyle(normalizedItem)
  const displayLines = formatTextContentForDisplay(normalizedItem)
  const textDecoration = `${normalizedItem.underline ? 'underline' : ''} ${normalizedItem.strikeThrough ? 'line-through' : ''}`.trim() || 'none'

  useEffect(() => {
    setDraft(normalizedItem.text || DEFAULT_TEXT_VALUE)
  }, [normalizedItem.text, isEditing])

  useEffect(() => {
    if (isEditing) {
      requestAnimationFrame(() => {
        textareaRef.current?.focus()
        textareaRef.current?.select()
      })
    }
  }, [isEditing])

  const sharedTextStyle: CSSProperties = {
    width: '100%',
    height: '100%',
    fontFamily: normalizedItem.fontFamily,
    fontSize: normalizedItem.fontSize,
    fontWeight: variantStyle.fontWeight,
    fontStyle: variantStyle.fontStyle,
    color: normalizedItem.fillColor || DEFAULT_TEXT_FILL,
    WebkitTextStroke: normalizedItem.strokeColor && normalizedItem.strokeColor !== 'transparent'
      ? `${Math.max(normalizedItem.strokeWidth || 0, 1)}px ${normalizedItem.strokeColor}`
      : undefined,
    lineHeight: normalizedItem.lineHeight,
    letterSpacing: `${normalizedItem.letterSpacing || 0}px`,
    textAlign: normalizedItem.textAlign,
    textDecoration,
    textTransform: normalizedItem.textTransform,
    writingMode: normalizedItem.writingMode === 'vertical' ? 'vertical-rl' : 'horizontal-tb',
    textOrientation: normalizedItem.writingMode === 'vertical' ? 'upright' : 'mixed',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word' as const,
    overflowWrap: 'anywhere' as const,
    overflow: 'hidden',
    background: 'transparent',
    border: 'none',
    outline: 'none',
  }

  if (isEditing) {
    return (
      <textarea
        ref={textareaRef}
        title={normalizedItem.text}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onBlur={() => onCommitEdit(normalizedItem.id, draft)}
        onKeyDown={(event) => {
          event.stopPropagation()
          if (event.key === 'Escape') {
            event.preventDefault()
            setDraft(normalizedItem.text || DEFAULT_TEXT_VALUE)
            onCancelEdit()
          }
          if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
            event.preventDefault()
            onCommitEdit(normalizedItem.id, draft)
          }
        }}
        onMouseDown={(event) => event.stopPropagation()}
        style={{
          ...sharedTextStyle,
          resize: 'none',
          padding: 0,
        }}
      />
    )
  }

  return (
    <div
      title={normalizedItem.text}
      onDoubleClick={(event) => {
        event.stopPropagation()
        onStartEdit(normalizedItem.id)
      }}
      style={{
        ...sharedTextStyle,
        cursor: 'text',
        minWidth: 1,
        minHeight: 1,
      }}
    >
      {displayLines.map((line, index) => (
        <div key={`${normalizedItem.id}-line-${index}`}>{line || '\u00A0'}</div>
      ))}
    </div>
  )
}
