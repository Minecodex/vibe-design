import { AlertCircle, Film, Image, Loader2 } from 'lucide-react'
import type { TFunction } from 'i18next'
import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { agentApi } from '@/api/endpoints/agent'
import { cn } from '@/lib/utils'

import { useHarnessMediaSource } from './useHarnessMediaSource'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'

interface GenerationArtifactReferenceChipProps {
  artifactRef: string
  conversationId?: string | number | null
  isDark: boolean
  onPreviewImage?: (url: string, alt: string) => void
}

type GenerationArtifactSnapshot = {
  task_id?: string | number | null
  artifact_ref?: string | null
  status?: string | null
  kind?: string | null
  progress?: number | null
  result_url?: string | null
  result_urls?: string[] | null
  artifact?: Record<string, unknown> | null
  error_message?: string | null
  prompt?: string | null
  params?: Record<string, unknown> | null
  canvas_item?: Record<string, unknown> | null
}

const POLL_INTERVAL_MS = 3000
const MAX_MEDIA_LOAD_RETRIES = 12
const artifactSnapshotCache = new Map<string, GenerationArtifactSnapshot>()
const artifactSnapshotRequests = new Map<string, Promise<GenerationArtifactSnapshot>>()
const artifactMediaReadyCache = new Set<string>()

export function GenerationArtifactReferenceChip({
  artifactRef,
  conversationId,
  isDark,
  onPreviewImage,
}: GenerationArtifactReferenceChipProps) {
  const { t } = useTranslation()
  const initialSnapshot = getCachedArtifactSnapshot(conversationId, artifactRef)
  const initialResultUrl = resolveArtifactResultUrl(initialSnapshot)
  const [snapshot, setSnapshot] = useState<GenerationArtifactSnapshot | null>(initialSnapshot)
  const [requestFailed, setRequestFailed] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [mediaLoaded, setMediaLoaded] = useState(() => (
    !!initialResultUrl && artifactMediaReadyCache.has(initialResultUrl)
  ))
  const [mediaErrored, setMediaErrored] = useState(false)
  const status = String(snapshot?.status || '').toLowerCase()
  const mediaType = inferArtifactMediaType(snapshot)
  const resultUrl = resolveArtifactResultUrl(snapshot)
  const displayUrl = useHarnessMediaSource(conversationId, resultUrl, {
    preferPreviewUrl: true,
    reloadToken,
    variant: 'thumb-256',
  })
  const isFailed = isFailedStatus(status) || requestFailed
  const completedWithResult = isCompletedStatus(status) && !!resultUrl
  const hasDisplayMedia = completedWithResult && !!displayUrl
  const hasRenderableMedia = isCompletedStatus(status) && !!displayUrl && (mediaType === 'video' || (mediaType === 'image' && mediaLoaded && !mediaErrored))
  const isGenerating = !isFailed && !hasDisplayMedia
  const progress = Math.max(0, Math.min(100, Number(snapshot?.progress || 0)))
  const label = useMemo(() => {
    if (isFailed) {
      return t('homeHarness.artifactReference.generationFailed', 'Generation failed')
    }
    if (isGenerating) {
      return mediaType === 'video'
        ? t('homeHarness.artifactReference.generatingVideo', 'Generating video...')
        : t('homeHarness.artifactReference.generatingImage', 'Generating image...')
    }
    return mediaType === 'video'
      ? t('homeHarness.artifactReference.generatedVideo', 'Generated video')
      : t('homeHarness.artifactReference.generatedImage', 'Generated image')
  }, [isFailed, isGenerating, mediaType, t])
  const title = t('homeHarness.artifactReference.previewArtifact', {
    defaultValue: 'Preview generated media {{name}}',
    name: artifactRef,
  })
  const previewTitle = typeof title === 'string'
    ? title
    : formatDefaultTranslation('Preview generated media {{name}}', { name: artifactRef })

  useEffect(() => {
    if (resultUrl && artifactMediaReadyCache.has(resultUrl)) {
      setMediaLoaded(true)
      setMediaErrored(false)
      return
    }
    setMediaLoaded(false)
    setMediaErrored(false)
  }, [displayUrl, resultUrl])

  useEffect(() => {
    if (!conversationId || !artifactRef) {
      return
    }
    const cacheKey = getArtifactCacheKey(conversationId, artifactRef)
    const cachedSnapshot = artifactSnapshotCache.get(cacheKey)
    if (cachedSnapshot) {
      setSnapshot(cachedSnapshot)
      setRequestFailed(false)
      if (isCompletedSnapshotReady(cachedSnapshot) || isFailedStatus(cachedSnapshot.status)) {
        return
      }
    }

    let active = true
    let timer: number | null = null

    const poll = async () => {
      try {
        const response = await fetchArtifactSnapshot(String(conversationId), artifactRef)
        if (!active) {
          return
        }
        setSnapshot(response)
        setRequestFailed(false)
        if (!isFailedStatus(response.status) && !isCompletedSnapshotReady(response)) {
          timer = window.setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        if (!active) {
          return
        }
        setRequestFailed(false)
        timer = window.setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    void poll()

    return () => {
      active = false
      if (timer) {
        window.clearTimeout(timer)
      }
    }
  }, [artifactRef, conversationId])

  useEffect(() => {
    if (!mediaErrored || reloadToken >= MAX_MEDIA_LOAD_RETRIES) {
      return
    }
    const timer = window.setTimeout(() => {
      setMediaErrored(false)
      setReloadToken((current) => current + 1)
    }, POLL_INTERVAL_MS)
    return () => window.clearTimeout(timer)
  }, [mediaErrored, reloadToken])

  const Icon = mediaType === 'video' ? Film : Image
  const prompt = String(snapshot?.prompt || snapshot?.params?.prompt || '').trim()
  const previewAlt = prompt || label

  return (
    <button
      type="button"
      title={previewTitle}
      aria-label={previewTitle}
      data-testid="generation-artifact-reference"
      onClick={(event) => {
        event.preventDefault()
        event.stopPropagation()
        if (mediaType === 'image' && hasRenderableMedia && displayUrl) {
          onPreviewImage?.(displayUrl, previewAlt)
        }
      }}
      className={cn(
        'mx-0.5 inline-flex h-9 max-w-full items-center gap-2 rounded-lg border px-2 align-baseline text-[13px] font-medium leading-none transition-colors',
        'min-w-[136px]',
        hasRenderableMedia && mediaType === 'image' ? 'cursor-zoom-in' : 'cursor-default',
        'app-chip-primary',
      )}
    >
      <span
        className={cn(
          'relative flex h-7 w-7 shrink-0 items-center justify-center overflow-hidden rounded-md',
          'bg-[var(--app-control)]',
        )}
      >
        {hasRenderableMedia && displayUrl ? (
          <AgentLazyMedia
            src={displayUrl}
            kind={mediaType === 'video' ? 'video' : 'image'}
            aspectRatio={1}
            className="h-full w-full"
            mediaClassName="h-full w-full object-cover"
          />
        ) : completedWithResult ? (
          <Icon className={cn('h-4 w-4', mediaType === 'video' ? 'text-sky-500' : 'text-emerald-500')} />
        ) : isFailed ? (
          <AlertCircle className="h-4 w-4 text-red-400" />
        ) : (
          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
        )}
      </span>
      <span className="inline-flex min-w-0 flex-col gap-0.5">
        <span className="truncate">{label}</span>
        {isGenerating && progress > 0 ? (
          <span className={cn('text-[11px] font-normal', isDark ? 'text-zinc-400' : 'text-zinc-500')}>
            {translateWithDefault(t, 'home.chat.generation_progress', 'Progress {{progress}}%', { progress })}
          </span>
        ) : null}
      </span>
      {displayUrl && mediaType === 'image' ? (
        <img
          src={displayUrl}
          alt=""
          loading="lazy"
          decoding="async"
          className="sr-only"
          onLoad={() => {
            if (resultUrl) {
              artifactMediaReadyCache.add(resultUrl)
            }
            setMediaLoaded(true)
            setMediaErrored(false)
          }}
          onError={() => {
            setMediaLoaded(false)
            setMediaErrored(true)
          }}
        />
      ) : null}
      {!displayUrl && !isFailed ? <Icon className="h-3.5 w-3.5 shrink-0 text-zinc-400" /> : null}
    </button>
  )
}

async function fetchArtifactSnapshot(
  conversationId: string,
  artifactRef: string,
): Promise<GenerationArtifactSnapshot> {
  const cacheKey = getArtifactCacheKey(conversationId, artifactRef)
  const cachedSnapshot = artifactSnapshotCache.get(cacheKey)
  if (cachedSnapshot && (isCompletedSnapshotReady(cachedSnapshot) || isFailedStatus(cachedSnapshot.status))) {
    return cachedSnapshot
  }

  const existingRequest = artifactSnapshotRequests.get(cacheKey)
  if (existingRequest) {
    return existingRequest
  }

  const request = agentApi.getHarnessGenerationArtifactTask(conversationId, artifactRef)
    .then((response) => {
      artifactSnapshotCache.set(cacheKey, response.data)
      return response.data
    })
    .finally(() => {
      artifactSnapshotRequests.delete(cacheKey)
    })
  artifactSnapshotRequests.set(cacheKey, request)
  return request
}

function getArtifactCacheKey(conversationId: string | number, artifactRef: string): string {
  return `${String(conversationId)}::${artifactRef}`
}

function getCachedArtifactSnapshot(
  conversationId: string | number | null | undefined,
  artifactRef: string,
): GenerationArtifactSnapshot | null {
  if (!conversationId || !artifactRef) {
    return null
  }
  return artifactSnapshotCache.get(getArtifactCacheKey(conversationId, artifactRef)) || null
}

function isCompletedSnapshotReady(snapshot: GenerationArtifactSnapshot): boolean {
  return isCompletedStatus(snapshot.status) && !!resolveArtifactResultUrl(snapshot)
}

function isCompletedStatus(status: unknown): boolean {
  return ['completed', 'succeeded', 'success', 'done'].includes(String(status || '').toLowerCase())
}

function isFailedStatus(status: unknown): boolean {
  return ['failed', 'error', 'cancelled', 'canceled'].includes(String(status || '').toLowerCase())
}

function translateWithDefault(
  t: TFunction,
  key: string,
  defaultValue: string,
  values?: Record<string, string | number>,
): string {
  const translated = t(key, { defaultValue, ...(values || {}) })
  return typeof translated === 'string'
    ? translated
    : formatDefaultTranslation(defaultValue, values)
}

function formatDefaultTranslation(defaultValue: string, values?: Record<string, string | number>): string {
  return Object.entries(values || {}).reduce(
    (text, [key, value]) => text.split(`{{${key}}}`).join(String(value)),
    defaultValue,
  )
}

function inferArtifactMediaType(snapshot: GenerationArtifactSnapshot | null): 'image' | 'video' {
  const kind = String(snapshot?.kind || '').toLowerCase()
  const taskType = String(snapshot?.params?.task_type || snapshot?.params?.type || '').toLowerCase()
  const canvasType = String(snapshot?.canvas_item?.type || '').toLowerCase()
  const resultUrl = String(resolveArtifactResultUrl(snapshot) || '').toLowerCase().split(/[?#]/)[0]
  if (
    kind === 'video'
    || taskType.includes('video')
    || canvasType.includes('video')
    || /\.(mp4|webm|mov|m4v|avi)$/.test(resultUrl)
  ) {
    return 'video'
  }
  return 'image'
}

function resolveArtifactResultUrl(snapshot: GenerationArtifactSnapshot | null): string | null {
  if (!snapshot) {
    return null
  }
  const directUrl = String(snapshot.result_url || '').trim()
  if (directUrl) {
    return directUrl
  }
  const resultUrls = Array.isArray(snapshot.result_urls) ? snapshot.result_urls : []
  const firstResultUrl = String(resultUrls[0] || '').trim()
  if (firstResultUrl) {
    return firstResultUrl
  }
  const artifact = snapshot.artifact || {}
  const baseDir = String(artifact.base_dir || artifact.baseDir || '').trim()
  const relativePath = String(artifact.relative_path || artifact.relativePath || '').trim()
  if (relativePath && (!baseDir || baseDir === 'FILES_DIR')) {
    return relativePath
  }
  return String(artifact.absolute_path || artifact.absolutePath || '').trim() || null
}
