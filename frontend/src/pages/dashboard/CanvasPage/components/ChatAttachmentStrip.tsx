import { Download, FileText, Globe, Image as ImageIcon, TableProperties } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { agentApi, type AttachmentData } from '@/api/endpoints/agent'
import { cn } from '@/lib/utils'
import { normalizeWorkspaceAttachmentPathByPolicy } from '@/utils/harnessWorkspacePathPolicy'

import { resolveCanvasAgentMediaUrl } from '../canvasMediaUrl'
import { useCanvasHarnessMediaSource } from '../useCanvasHarnessMediaSource'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'
import {
  inferCanvasChatAttachmentKind,
  type CanvasChatAttachmentKind,
} from '../chatAttachmentKinds'

interface ChatAttachmentStripProps {
  attachments: AttachmentData[]
  isDark: boolean
  conversationId?: string | number | null
  onRemove?: (index: number) => void
  onPreview?: (url: string) => void
  className?: string
}

interface AttachmentPresentation {
  icon: typeof FileText
  iconClassName: string
  badgeClassName: string
}

const PRESENTATIONS: Record<Exclude<CanvasChatAttachmentKind, 'image'>, AttachmentPresentation> = {
  text: {
    icon: FileText,
    iconClassName: 'text-zinc-500',
    badgeClassName: 'bg-zinc-500/10',
  },
  document: {
    icon: FileText,
    iconClassName: 'text-indigo-500',
    badgeClassName: 'bg-indigo-500/10',
  },
  spreadsheet: {
    icon: TableProperties,
    iconClassName: 'text-emerald-500',
    badgeClassName: 'bg-emerald-500/10',
  },
  html: {
    icon: Globe,
    iconClassName: 'text-sky-500',
    badgeClassName: 'bg-sky-500/10',
  },
  other: {
    icon: FileText,
    iconClassName: 'text-zinc-400',
    badgeClassName: 'bg-zinc-400/10',
  },
}

export function ChatAttachmentStrip({
  attachments,
  isDark,
  conversationId,
  onRemove,
  onPreview,
  className,
}: ChatAttachmentStripProps) {
  const { t } = useTranslation()

  if (attachments.length === 0) {
    return null
  }

  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {attachments.map((attachment, index) => {
        const kind = inferCanvasChatAttachmentKind({
          name: attachment.name,
          path: attachment.url,
          type: attachment.type,
        })
        const label = attachment.name || getAttachmentNameFromUrl(attachment.url)
        const previewSourceUrl = attachment.preview_url || attachment.url
        const resolvedUrl = attachment.url
          ? resolveCanvasAgentMediaUrl(attachment.url, conversationId)
          : ''

        return (
          <div
            key={`${attachment.url || attachment.name || 'attachment'}-${index}`}
            className={cn(
              'app-card-muted relative overflow-hidden',
              kind === 'image'
                ? 'h-12 w-12 rounded-[10px]'
                : 'flex h-12 min-w-[180px] max-w-[240px] items-center gap-2 rounded-[10px] px-2.5 pr-6',
            )}
          >
            {kind === 'image' ? (
              <AttachmentPreviewImage
                sourceUrl={previewSourceUrl}
                originalUrl={attachment.url}
                alt={label}
                conversationId={conversationId}
                isDark={isDark}
                onPreview={onPreview}
              />
            ) : (
              <AttachmentFileCard
                label={label}
                kind={kind}
                sourceUrl={attachment.url}
                resolvedUrl={resolvedUrl}
                conversationId={conversationId}
                isDark={isDark}
                downloadLabel={t('common.download', 'Download')}
              />
            )}

            {onRemove ? (
              <button
                type="button"
                aria-label={`Remove attachment ${index + 1}`}
                onClick={() => onRemove(index)}
                className="app-media-control absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full transition"
              >
                ×
              </button>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function AttachmentPreviewImage({
  sourceUrl,
  originalUrl,
  alt,
  conversationId,
  isDark,
  onPreview,
}: {
  sourceUrl: string
  originalUrl?: string
  alt: string
  conversationId?: string | number | null
  isDark: boolean
  onPreview?: (url: string) => void
}) {
  const workspacePath = normalizeWorkspaceAttachmentPath(sourceUrl)
  const canResolveSource = !workspacePath || Boolean(conversationId)
  const displayUrl = useCanvasHarnessMediaSource(conversationId, sourceUrl, {
    variant: 'thumb-256',
    enabled: canResolveSource,
  }) || ''

  return (
    <button
      type="button"
      className="h-full w-full"
      onClick={() => {
        if (!onPreview) {
          return
        }
        if (originalUrl) {
          onPreview(originalUrl)
          return
        }
        if (displayUrl) {
          onPreview(displayUrl)
        }
      }}
    >
      {displayUrl ? (
        <AgentLazyMedia
          src={displayUrl}
          alt={alt}
          aspectRatio={1}
          className="h-full w-full"
          mediaClassName="h-full w-full object-cover"
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <ImageIcon className={cn('h-4 w-4', isDark ? 'text-zinc-300' : 'text-zinc-500')} />
        </div>
      )}
    </button>
  )
}

function AttachmentFileCard({
  label,
  kind,
  sourceUrl,
  resolvedUrl,
  conversationId,
  isDark,
  downloadLabel,
}: {
  label: string
  kind: Exclude<CanvasChatAttachmentKind, 'image'>
  sourceUrl: string
  resolvedUrl: string
  conversationId?: string | number | null
  isDark: boolean
  downloadLabel: string
}) {
  const presentation = PRESENTATIONS[kind] || PRESENTATIONS.other
  const Icon = presentation.icon
  const workspacePath = normalizeWorkspaceAttachmentPath(sourceUrl)
  const isTextAttachment = kind === 'text'

  const handleDownload = async () => {
    if (workspacePath && conversationId) {
      const blob = await agentApi.fetchWorkspaceFileBlob(String(conversationId), workspacePath)
      downloadAttachmentBlob(blob, label)
      return
    }

    if (!resolvedUrl) {
      return
    }

    triggerBrowserDownload(resolvedUrl, label)
  }

  const content = (
    <>
      <div
        className={cn(
          'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
          presentation.badgeClassName,
        )}
      >
        <Icon className={cn('h-4 w-4', presentation.iconClassName)} />
      </div>
      <span
        className={cn(
          'min-w-0 truncate text-xs font-medium',
          isDark ? 'text-zinc-200' : 'text-zinc-700',
        )}
        title={label}
      >
        {label}
      </span>
    </>
  )

  if (!resolvedUrl) {
    return <div className="flex min-w-0 items-center gap-2">{content}</div>
  }

  if (isTextAttachment) {
    return (
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">{content}</div>
        <button
          type="button"
          aria-label={`${downloadLabel} ${label}`}
          title={downloadLabel}
          onClick={() => void handleDownload()}
          className={cn(
            'app-muted flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition hover:bg-[var(--app-control-hover)]',
          )}
        >
          <Download className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <a
      href={resolvedUrl}
      target="_blank"
      rel="noreferrer"
      className="flex min-w-0 items-center gap-2"
    >
      {content}
    </a>
  )
}

function getAttachmentNameFromUrl(url: string | undefined): string {
  const path = String(url || '').split('?')[0]
  const parts = path.split('/')
  return parts[parts.length - 1] || 'attachment'
}

function normalizeWorkspaceAttachmentPath(url: string | undefined): string | null {
  return normalizeWorkspaceAttachmentPathByPolicy(url)
}

function downloadAttachmentBlob(blob: Blob, fileName: string) {
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = fileName
  link.target = '_blank'
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}

function triggerBrowserDownload(url: string, fileName: string) {
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.target = '_blank'
  link.click()
}
