import type { TFunction } from 'i18next'
import { Image, Video } from 'lucide-react'

import { cn } from '@/lib/utils'

import { inferCanvasWorkspaceMediaKind } from '../canvasWorkspaceFileReferences'
import { useCanvasHarnessMediaSource } from '../useCanvasHarnessMediaSource'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'

interface CanvasWorkspaceMediaReferenceChipProps {
  filePath: string
  conversationId?: string | number | null
  isDark: boolean
  t: TFunction
  onPreview?: (url: string) => void
}

export function CanvasWorkspaceMediaReferenceChip({
  filePath,
  conversationId,
  t,
  onPreview,
}: CanvasWorkspaceMediaReferenceChipProps) {
  const kind = inferCanvasWorkspaceMediaKind(filePath)
  const resolvedUrl = useCanvasHarnessMediaSource(conversationId, filePath, { variant: 'thumb-256' }) || ''
  const fileName = filePath.split('/').filter(Boolean).pop() || filePath
  const visibleLabel = kind === 'video'
    ? translateWithDefault(t, 'canvas.chat.file_reference.video', 'Video')
    : translateWithDefault(t, 'canvas.chat.file_reference.image', 'Image')
  const previewLabel = translateWithDefault(
    t,
    'canvas.chat.file_reference.preview',
    'Preview file {{name}}',
    { name: fileName },
  )
  const Icon = kind === 'video' ? Video : Image

  return (
    <button
      type="button"
      title={previewLabel}
      aria-label={previewLabel}
      data-testid="canvas-workspace-media-reference"
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        if (!resolvedUrl) {
          return
        }
        if (kind === 'image') {
          onPreview?.(resolvedUrl)
          return
        }
        window.open(resolvedUrl, '_blank', 'noopener,noreferrer')
      }}
      className={cn(
        'mx-0.5 inline-flex h-9 max-w-full min-w-[112px] items-center gap-2 rounded-lg border px-2 align-baseline text-[13px] font-medium leading-none transition-colors',
        kind === 'image' && resolvedUrl ? 'cursor-zoom-in' : resolvedUrl ? 'cursor-pointer' : 'cursor-default',
        'app-chip-primary',
      )}
    >
      <span
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md',
          'bg-[var(--app-control)]',
        )}
      >
        {resolvedUrl ? (
          <AgentLazyMedia
            src={resolvedUrl}
            kind={kind === 'video' ? 'video' : 'image'}
            aspectRatio={1}
            className="h-full w-full"
            mediaClassName="h-full w-full object-cover"
          />
        ) : (
          <Icon className={cn('h-4 w-4', kind === 'video' ? 'text-sky-500' : 'text-amber-500')} />
        )}
      </span>
      <span className="min-w-0 max-w-[92px] truncate">{visibleLabel}</span>
    </button>
  )
}

function translateWithDefault(
  t: TFunction,
  key: string,
  defaultValue: string,
  values?: Record<string, string | number>,
): string {
  const translated = t(key, { defaultValue, ...(values || {}) })
  if (typeof translated === 'string') {
    return translated
  }
  return Object.entries(values || {}).reduce(
    (text, [name, value]) => text.split(`{{${name}}}`).join(String(value)),
    defaultValue,
  )
}
