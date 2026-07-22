import {
  File,
  FileCode,
  FileText,
  Image,
  LayoutTemplate,
  Presentation,
  TableProperties,
  Video,
} from 'lucide-react'
import type { TFunction } from 'i18next'

import { cn } from '@/lib/utils'

import { inferHomeHarnessAttachmentKind } from './homeChatAttachmentKinds'
import { useHarnessMediaSource } from './useHarnessMediaSource'
import type { SessionFileItem } from '../homeHarnessPageUtils'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'

interface HomeChatFileReferenceChipProps {
  file: SessionFileItem
  conversationId?: string | number | null
  isDark: boolean
  t: TFunction
  onOpen: (file: SessionFileItem) => void
}

export function HomeChatFileReferenceChip({
  file,
  conversationId,
  t,
  onOpen,
}: HomeChatFileReferenceChipProps) {
  const kind = inferHomeHarnessAttachmentKind(file)
  const Icon = getFileReferenceIcon(kind)
  const label = file.name || file.path
  const isMedia = kind === 'image' || kind === 'video'
  const mediaUrl = useHarnessMediaSource(conversationId, isMedia ? file.path : null, {
    preferPreviewUrl: true,
    variant: 'thumb-256',
  })
  const visibleLabel = isMedia
    ? (
        kind === 'video'
          ? t('homeHarness.files.videoReference', 'Video')
          : t('homeHarness.files.imageReference', 'Image')
      )
    : label
  const previewLabel = t('homeHarness.files.previewFile', {
    defaultValue: 'Preview file {{name}}',
    name: label,
  })

  return (
    <button
      type="button"
      title={previewLabel}
      aria-label={previewLabel}
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        onOpen(file)
      }}
      className={cn(
        isMedia
          ? 'mx-0.5 inline-flex h-9 max-w-full min-w-[112px] items-center gap-2 rounded-lg border px-2 align-baseline text-[13px] font-medium leading-none transition-colors'
          : 'mx-0.5 inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 align-baseline text-[13px] font-medium leading-none transition-colors',
        'app-chip-primary',
      )}
    >
      {isMedia ? (
        <span
          className={cn(
            'flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md',
            'bg-[var(--app-control)]',
          )}
        >
          {mediaUrl ? (
            <AgentLazyMedia
              src={mediaUrl}
              kind={kind === 'video' ? 'video' : 'image'}
              aspectRatio={1}
              className="h-full w-full"
              mediaClassName="h-full w-full object-cover"
            />
          ) : (
            <Icon className={cn('h-4 w-4', getFileReferenceIconColor(kind))} />
          )}
        </span>
      ) : (
        <Icon className={cn('h-3.5 w-3.5 shrink-0', getFileReferenceIconColor(kind))} />
      )}
      <span className={cn('min-w-0 truncate', isMedia ? 'max-w-[92px]' : '')}>{visibleLabel}</span>
    </button>
  )
}

function getFileReferenceIcon(kind: string) {
  switch (kind) {
    case 'image':
      return Image
    case 'video':
      return Video
    case 'document':
      return FileText
    case 'spreadsheet':
      return TableProperties
    case 'presentation':
      return Presentation
    case 'html':
      return LayoutTemplate
    case 'code':
      return FileCode
    case 'text':
      return FileText
    default:
      return File
  }
}

function getFileReferenceIconColor(kind: string) {
  switch (kind) {
    case 'image':
      return 'text-amber-500'
    case 'video':
      return 'text-sky-500'
    case 'document':
      return 'text-indigo-500'
    case 'spreadsheet':
      return 'text-emerald-500'
    case 'presentation':
      return 'text-rose-500'
    case 'html':
      return 'text-purple-500'
    case 'code':
      return 'text-blue-500'
    default:
      return 'text-zinc-500'
  }
}
