import { type KeyboardEvent, memo, useEffect, useState } from 'react'
import { X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { agentApi, type AttachmentData } from '@/api/endpoints/agent'
import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'
import {
  getHomeHarnessAttachmentPresentation,
  inferHomeHarnessAttachmentKind,
} from './homeChatAttachmentKinds'
import {
  normalizeWorkspaceAttachmentPath,
  requiresWorkspaceAttachmentFetch,
  resolveAttachmentDisplayUrl,
} from './homeChatAttachmentUrls'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'
import { useAgentViewportReady } from '../../agentMedia/agentMediaVisibility'
import { enqueueAgentMediaRequest } from '../../agentMedia/agentMediaRequestQueue'

interface AttachmentCardStripProps {
  attachments: AttachmentData[]
  isDark: boolean
  onRemove?: (index: number) => void
  onOpenWorkspaceRelativeFile?: (filePath: string, fileName?: string) => void
  className?: string
  conversationId?: string | number | null
}

interface PreviewImageState {
  src: string
  alt: string
  ownedUrl?: string
}

export const AttachmentCardStrip = memo(AttachmentCardStripImpl)

function AttachmentCardStripImpl({
  attachments,
  isDark,
  onRemove,
  onOpenWorkspaceRelativeFile,
  className,
  conversationId,
}: AttachmentCardStripProps) {
  const [previewImage, setPreviewImage] = useState<PreviewImageState | null>(null)

  useEffect(() => {
    return () => {
      if (previewImage?.ownedUrl) {
        URL.revokeObjectURL(previewImage.ownedUrl)
      }
    }
  }, [previewImage?.ownedUrl])

  const openPreview = async (sourceUrl: string, fallbackSrc: string, alt: string) => {
    if (sourceUrl.startsWith('blob:')) {
      setPreviewImage({ src: fallbackSrc, alt, ownedUrl: sourceUrl })
      return
    }

    const workspacePath = normalizeWorkspaceAttachmentPath(sourceUrl)
    if (!requiresWorkspaceAttachmentFetch(sourceUrl, conversationId) || !workspacePath) {
      setPreviewImage({ src: fallbackSrc, alt })
      return
    }

    try {
      const blob = await agentApi.fetchWorkspaceFileBlob(
        String(conversationId),
        workspacePath,
      )
      const objectUrl = URL.createObjectURL(blob)
      setPreviewImage({ src: objectUrl, alt, ownedUrl: objectUrl })
    } catch {
      setPreviewImage({ src: fallbackSrc, alt })
    }
  }

  if (attachments.length === 0) {
    return null
  }

  return (
    <>
      <div className={cn('flex flex-wrap gap-2', className)}>
        {attachments.map((attachment, index) => {
          const label = attachment.name || getAttachmentNameFromUrl(attachment.url)
          const kind = inferHomeHarnessAttachmentKind({
            name: attachment.name,
            path: attachment.url,
            type: attachment.type,
          })
          const presentation = getHomeHarnessAttachmentPresentation(kind)
          const AttachmentIcon = presentation.icon
          const previewSourceUrl = attachment.preview_url || attachment.url
          const resolvedUrl = resolveAttachmentDisplayUrl(previewSourceUrl, conversationId)
          const workspacePath = normalizeWorkspaceAttachmentPath(attachment.url)
          const canOpenFilePreview = kind !== 'image' && Boolean(workspacePath && onOpenWorkspaceRelativeFile)

          const handleOpenFilePreview = () => {
            if (!workspacePath) {
              return
            }
            onOpenWorkspaceRelativeFile?.(workspacePath, label)
          }

          const handleOpenFilePreviewKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
            if (!canOpenFilePreview || (event.key !== 'Enter' && event.key !== ' ')) {
              return
            }
            event.preventDefault()
            handleOpenFilePreview()
          }

          return (
            <div
              key={`${attachment.url}-${index}`}
              role={canOpenFilePreview ? 'button' : undefined}
              tabIndex={canOpenFilePreview ? 0 : undefined}
              onClick={canOpenFilePreview ? handleOpenFilePreview : undefined}
              onKeyDown={canOpenFilePreview ? handleOpenFilePreviewKeyDown : undefined}
              className={cn(
                kind === 'image'
                  ? 'relative h-12 w-12 overflow-hidden rounded-[10px] border'
                  : 'relative flex h-12 min-w-[180px] max-w-[240px] items-center gap-2 overflow-hidden rounded-[10px] border px-2.5 pr-6',
                'app-card-muted',
                canOpenFilePreview && 'app-focus-ring cursor-pointer transition hover:border-[var(--app-primary)] hover:bg-[var(--app-tint-primary)]',
              )}
            >
              {kind === 'image' ? (
                <AttachmentPreviewImage
                  src={resolvedUrl}
                  sourceUrl={attachment.url}
                  previewUrl={previewSourceUrl}
                  localFile={attachment._localFile}
                  conversationId={conversationId}
                  alt={label}
                  onPreview={(sourceUrl, previewSrc) => void openPreview(sourceUrl, previewSrc, label)}
                />
              ) : (
                <div className="flex min-w-0 items-center gap-2">
                  <div className={cn(
                    'flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
                    presentation.bg,
                    presentation.color,
                  )}>
                    <AttachmentIcon className="h-4 w-4" data-testid={`attachment-kind-${kind}`} />
                  </div>
                  <span className={cn(
                    'min-w-0 truncate text-xs font-medium',
                    isDark ? 'text-zinc-200' : 'text-zinc-700',
                  )} title={label}>
                    {label}
                  </span>
                </div>
              )}

              {onRemove ? (
                <button
                  type="button"
                  aria-label={`Remove attachment ${index + 1}`}
                  onClick={(event) => {
                    event.stopPropagation()
                    onRemove(index)
                  }}
                  className="app-media-control absolute right-0.5 top-0.5 flex h-4 w-4 items-center justify-center rounded-full transition"
                >
                  <X className="h-2.5 w-2.5" />
                </button>
              ) : null}
            </div>
          )
        })}
      </div>

      <ImagePreviewDialog
        open={!!previewImage}
        onOpenChange={(open) => !open && setPreviewImage(null)}
        src={previewImage?.src || null}
        alt={previewImage?.alt || 'Attachment preview'}
        title={previewImage?.alt || 'Attachment preview'}
        imageClassName="rounded-2xl"
        downloadUrl={previewImage?.src || null}
      />
    </>
  )
}

interface AttachmentPreviewImageProps {
  src: string
  sourceUrl: string
  previewUrl?: string
  localFile?: File
  conversationId?: string | number | null
  alt: string
  onPreview?: (sourceUrl: string, displaySrc: string) => void
}

function AttachmentPreviewImage({
  src,
  sourceUrl,
  previewUrl,
  localFile,
  conversationId,
  alt,
  onPreview,
}: AttachmentPreviewImageProps) {
  const effectivePreviewSource = previewUrl || sourceUrl
  const [displayUrl, setDisplayUrl] = useState(() => (requiresWorkspaceAttachmentFetch(effectivePreviewSource, conversationId) ? '' : src))
  const { ref: viewportRef, ready: shouldLoad } = useAgentViewportReady('viewport')

  useEffect(() => {
    const workspacePath = normalizeWorkspaceAttachmentPath(effectivePreviewSource)
    if (requiresWorkspaceAttachmentFetch(effectivePreviewSource, conversationId) && !shouldLoad) {
      setDisplayUrl('')
      return
    }
    if (!requiresWorkspaceAttachmentFetch(effectivePreviewSource, conversationId) || !workspacePath) {
      setDisplayUrl(src)
      return
    }

    let active = true
    let objectUrl: string | null = null

    const loadProtectedImage = async () => {
      try {
        const blob = await enqueueAgentMediaRequest(() => agentApi.fetchWorkspaceFileBlob(
          String(conversationId),
          workspacePath,
        ))
        if (!active) {
          return
        }

        objectUrl = URL.createObjectURL(blob)
        setDisplayUrl(objectUrl)
      } catch {
        if (active) {
          setDisplayUrl(src)
        }
      }
    }

    setDisplayUrl('')
    void loadProtectedImage()

    return () => {
      active = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [conversationId, effectivePreviewSource, shouldLoad, src])

  return (
    <span ref={viewportRef} className="block h-full w-full">
      <AgentLazyMedia
        src={displayUrl}
        alt={alt}
        aspectRatio={1}
        className="h-full w-full cursor-zoom-in"
        mediaClassName="h-full w-full object-cover"
        onClick={() => {
          if (!displayUrl) {
            return
          }
          if (localFile) {
            const originalUrl = URL.createObjectURL(localFile)
            onPreview?.(originalUrl, originalUrl)
            return
          }
          onPreview?.(sourceUrl, displayUrl)
        }}
      />
    </span>
  )
}

function getAttachmentNameFromUrl(url: string) {
  const path = url.split('?')[0] || url
  const parts = path.split('/')
  return parts[parts.length - 1] || 'attachment'
}

