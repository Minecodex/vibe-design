import { memo, useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { cn } from '@/lib/utils'
import { Image, Loader2, Download, AlertCircle, Film, ChevronDown, ChevronRight, Paperclip } from 'lucide-react'
import {
    agentApi,
    type AttachmentData,
    isHarnessWorkspaceRelativePath,
    normalizeHarnessWorkspacePath,
} from '@/api/endpoints/agent'
import { ImagePreviewDialog } from '@/components/common/ZoomableImageViewer'
import { getHomeModelDisplayName, getHomeToolDisplayName } from './homeChatMeta'
import { HomeChatVideoItem } from './HomeChatVideoItem'
import { useHarnessMediaSource } from './useHarnessMediaSource'
import {
    applyGenerationProjectionUpdate,
    buildGenerationProjectionUpdateFromTaskSnapshot,
    createGenerationProjectionState,
} from '@/store/generationProjection'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'

interface GenerationCardProps {
    conversationId?: string | number | null
    taskId: string | number
    status: string
    resultUrl?: string | null
    artifact?: {
        absolute_path?: string | null
        absolutePath?: string | null
        relative_path?: string | null
        relativePath?: string | null
        base_dir?: string | null
        baseDir?: string | null
    } | null
    prompt?: string
    mediaType?: string
    modelName?: string
    modelLabel?: string
    aspectRatio?: string
    resolution?: string
    duration?: string | number
    quality?: string
    progress?: number
    toolName?: string
    errorMessage?: string
    onUseAsReference?: (attachment: AttachmentData) => void
    isDark: boolean
}

function resolveAspectRatioClass(aspectRatio?: string) {
    if (aspectRatio === '9:16') return 'aspect-[9/16]'
    if (aspectRatio === '16:9') return 'aspect-video'
    if (aspectRatio === '4:3') return 'aspect-[4/3]'
    if (aspectRatio === '3:4') return 'aspect-[3/4]'
    return 'aspect-square'
}

function inferMediaType(mediaType?: string, toolName?: string) {
    if (mediaType === 'video' || mediaType === 'image') {
        return mediaType
    }

    const normalizedToolName = String(toolName || '').replace(/^lc_/, '')
    if (normalizedToolName === 'generate_video') {
        return 'video'
    }
    if (normalizedToolName === 'generate_image') {
        return 'image'
    }

    return 'image'
}

function formatDurationLabel(duration?: string | number) {
    if (duration == null || duration === '') {
        return null
    }

    const numericDuration = Number(duration)
    if (Number.isFinite(numericDuration) && numericDuration > 0) {
        return `${numericDuration}s`
    }

    return String(duration)
}

function GenerationCardComponent({
    conversationId,
    taskId,
    status: initialStatus,
    resultUrl: initialResultUrl,
    artifact: initialArtifact,
    prompt,
    mediaType,
    modelName,
    modelLabel,
    aspectRatio,
    resolution: initialResolution,
    duration: initialDuration,
    quality: initialQuality,
    progress: initialProgress,
    toolName,
    errorMessage: initialErrorMessage,
    onUseAsReference,
    isDark,
}: GenerationCardProps) {
    const { t, i18n } = useTranslation()
    const currentLanguage = i18n?.resolvedLanguage || i18n?.language || 'en'
    const [status, setStatus] = useState(initialStatus)
    const [rawResultUrl, setRawResultUrl] = useState<string | null | undefined>(
        initialResultUrl || resolveArtifactResultUrl(initialArtifact),
    )
    const [resolution, setResolution] = useState(initialResolution)
    const [duration, setDuration] = useState(initialDuration)
    const [quality, setQuality] = useState(initialQuality)
    const [progress, setProgress] = useState(initialProgress ?? (initialStatus === 'completed' ? 100 : 0))
    const [resolvedModelLabel, setResolvedModelLabel] = useState(modelLabel)
    const [errorMessage, setErrorMessage] = useState(initialErrorMessage)
    const [imageLoaded, setImageLoaded] = useState(false)
    const [imageError, setImageError] = useState(false)
    const [expanded, setExpanded] = useState(false)
    const [previewOpen, setPreviewOpen] = useState(false)
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
    const generationProjectionRef = useRef(createGenerationProjectionState())
    const resultUrl = useHarnessMediaSource(conversationId, rawResultUrl, {
        preferPreviewUrl: true,
        variant: expanded ? 'thumb-1024' : 'thumb-512',
    })
    const originalResultUrl = useHarnessMediaSource(conversationId, rawResultUrl, {
        preferPreviewUrl: true,
        variant: 'original',
        enabled: previewOpen,
    })

    useEffect(() => {
        setImageLoaded(false)
        setImageError(false)
    }, [resultUrl])
    const applyPolledTaskSnapshot = useCallback((snapshot: Record<string, any>) => {
        const update = buildGenerationProjectionUpdateFromTaskSnapshot(snapshot, taskId)
        if (!update) {
            return null
        }
        const projected = applyGenerationProjectionUpdate(generationProjectionRef.current, update)
        generationProjectionRef.current = projected.state
        return projected.state.tasks[String(update.taskId)]
    }, [taskId])

    useEffect(() => {
        if (!taskId || status === 'completed') return

        const poll = async () => {
            try {
                if (conversationId == null || conversationId === '') {
                    return
                }
                const res = await agentApi.getHarnessGenerationTask(String(conversationId), taskId)
                const projectedTask = applyPolledTaskSnapshot(res.data)
                const projectedStatus = projectedTask?.status
                const fallbackProgress = res.data.progress ?? (res.data.status === 'completed' ? 100 : 0)
                setProgress(projectedTask?.progress ?? Math.max(0, Math.min(100, Number(fallbackProgress || 0))))
                if (projectedStatus === 'completed') {
                    setStatus('completed')
                    setRawResultUrl(projectedTask?.resultUrl || res.data.result_url || resolveArtifactResultUrl(res.data.artifact))
                    setResolution(res.data.resolution || initialResolution)
                    setDuration(res.data.duration || initialDuration)
                    setQuality(res.data.quality || initialQuality)
                    setProgress(100)
                    setResolvedModelLabel(res.data.model_label || modelLabel)
                    if (pollRef.current) clearInterval(pollRef.current)
                } else if (projectedStatus === 'failed') {
                    setStatus('failed')
                    setErrorMessage(projectedTask?.errorMessage || res.data.error_message || 'Generation failed')
                    if (pollRef.current) clearInterval(pollRef.current)
                } else {
                    setStatus('running')
                    setRawResultUrl(projectedTask?.resultUrl || res.data.result_url || resolveArtifactResultUrl(res.data.artifact) || null)
                    setResolution(res.data.resolution || initialResolution)
                    setDuration(res.data.duration || initialDuration)
                    setQuality(res.data.quality || initialQuality)
                    setResolvedModelLabel(res.data.model_label || modelLabel)
                    setErrorMessage(undefined)
                }
            } catch {
                // Ignore polling errors and retry next interval.
            }
        }

        pollRef.current = setInterval(poll, 3000)
        poll()

        return () => {
            if (pollRef.current) clearInterval(pollRef.current)
        }
    }, [applyPolledTaskSnapshot, conversationId, taskId, status, initialResolution, initialDuration, initialQuality, modelLabel])

    useEffect(() => {
        const nextInitialResultUrl = initialResultUrl || resolveArtifactResultUrl(initialArtifact)
        generationProjectionRef.current = applyGenerationProjectionUpdate(createGenerationProjectionState(), {
            taskId,
            status: initialStatus,
            progress: initialProgress ?? null,
            resultUrl: nextInitialResultUrl,
            errorMessage: initialErrorMessage,
            source: 'local',
        }).state
        if (initialStatus === 'completed' && nextInitialResultUrl) {
            setStatus('completed')
            setRawResultUrl(nextInitialResultUrl)
            setProgress(100)
        } else if (initialStatus === 'failed') {
            setStatus('failed')
            setErrorMessage(initialErrorMessage || 'Generation failed')
        } else {
            setStatus(initialStatus)
            setRawResultUrl(nextInitialResultUrl)
            setProgress(initialProgress ?? 0)
        }

        setResolution(initialResolution)
        setDuration(initialDuration)
        setQuality(initialQuality)
        setResolvedModelLabel(modelLabel)
    }, [
        initialStatus,
        initialResultUrl,
        initialArtifact,
        initialErrorMessage,
        initialResolution,
        initialDuration,
        initialQuality,
        initialProgress,
        modelLabel,
        conversationId,
        taskId,
    ])

    const resolvedMediaType = inferMediaType(mediaType, toolName)
    const clampedProgress = Math.max(0, Math.min(100, Number(progress || 0)))
    const progressLabel = t('home.chat.generation_progress', {
        defaultValue: currentLanguage.startsWith('zh') ? `进度 ${clampedProgress}%` : `Progress ${clampedProgress}%`,
        progress: clampedProgress,
    })

    const handleDownload = useCallback(async (event?: React.MouseEvent) => {
        event?.stopPropagation()
        if (!rawResultUrl) return
        let downloadUrl = resultUrl || rawResultUrl
        let revokeUrl = false

        if (conversationId && isHarnessWorkspaceRelativePath(rawResultUrl)) {
            const blob = await agentApi.fetchWorkspaceFileBlob(
                String(conversationId),
                normalizeHarnessWorkspacePath(rawResultUrl),
            )
            downloadUrl = URL.createObjectURL(blob)
            revokeUrl = true
        }

        const a = document.createElement('a')
        a.href = downloadUrl
        a.target = '_blank'
        a.download = `generation-${taskId}.${resolvedMediaType === 'video' ? 'mp4' : 'png'}`
        a.click()
        if (revokeUrl) {
            window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0)
        }
    }, [conversationId, rawResultUrl, resolvedMediaType, resultUrl, taskId])

    const handleUseAsReference = useCallback((event: React.MouseEvent) => {
        event.stopPropagation()
        if (!rawResultUrl || resolvedMediaType !== 'image') return
        onUseAsReference?.({
            type: 'image',
            url: rawResultUrl,
            name: getAttachmentNameFromResultUrl(rawResultUrl),
        })
    }, [onUseAsReference, rawResultUrl, resolvedMediaType])

    const isProcessing = status !== 'completed' && status !== 'failed'
    const isFailed = status === 'failed'
    const toolLabel = getHomeToolDisplayName(resolvedMediaType === 'video' ? 'generate_video' : 'generate_image')
    const displayModelName = getHomeModelDisplayName(resolvedModelLabel, modelName)
    const detailLabel = resolvedMediaType === 'video'
        ? [quality, resolution, formatDurationLabel(duration), aspectRatio].filter(Boolean).join(' · ')
        : [resolution, aspectRatio].filter(Boolean).join(' · ')
    const MediaIcon = resolvedMediaType === 'video' ? Film : Image
    const showMedia = expanded && status === 'completed' && !!resultUrl
    const useAsReferenceLabel = t('home.chat.use_generation_as_reference', 'Use as reference')

    return (
        <>
            <div className={cn(
                'app-card overflow-hidden rounded-2xl my-2 max-w-[520px]',
            )}>
                <button
                    type="button"
                    aria-label={`Toggle generation ${taskId}`}
                    onClick={() => setExpanded((current) => !current)}
                    className={cn(
                        'w-full px-4 py-3 flex items-start gap-3 text-left transition-colors hover:bg-[var(--app-control-hover)]',
                    )}
                >
                    {expanded ? (
                        <ChevronDown className="w-4 h-4 mt-0.5 shrink-0 text-zinc-500" />
                    ) : (
                        <ChevronRight className="w-4 h-4 mt-0.5 shrink-0 text-zinc-500" />
                    )}
                    <div className="min-w-0 flex-1">
                        <div className="flex items-start gap-2 min-w-0">
                            <MediaIcon className={cn(
                                'w-3.5 h-3.5 shrink-0',
                                isProcessing ? 'text-blue-500' : isFailed ? 'text-red-400' : 'text-emerald-500',
                            )} />
                            <div className="flex min-w-0 flex-1 items-start justify-between gap-3">
                                <span className={cn(
                                    'text-sm font-medium truncate',
                                    isDark ? 'text-zinc-100' : 'text-zinc-900',
                                )}>
                                    {toolLabel}
                                </span>
                                {isProcessing ? (
                                    <span className={cn(
                                        'shrink-0 text-xs font-medium',
                                        isDark ? 'text-blue-300' : 'text-blue-600',
                                    )}>
                                        {progressLabel}
                                    </span>
                                ) : null}
                            </div>
                        </div>
                        <div className={cn('mt-1 text-sm', isDark ? 'text-zinc-400' : 'text-zinc-600')}>
                            {displayModelName || (mediaType === 'video' ? 'Video' : 'Image')}
                        </div>
                        {detailLabel ? (
                            <div className={cn('mt-1 text-sm', isDark ? 'text-zinc-500' : 'text-zinc-500')}>
                                {detailLabel}
                            </div>
                        ) : null}
                        {isProcessing ? (
                            <>
                                <div className="mt-2 flex items-center gap-2 text-xs text-blue-500">
                                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                    <span>{currentLanguage.startsWith('zh') ? '生成中...' : 'Generating...'}</span>
                                </div>
                                <div
                                    aria-hidden="true"
                                    className={cn(
                                        'mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--app-control)]',
                                    )}
                                >
                                    <div
                                        className="h-full rounded-full bg-[var(--app-primary)] transition-[width] duration-300 ease-out"
                                        style={{ width: `${clampedProgress}%` }}
                                    />
                                </div>
                            </>
                        ) : null}
                        {isFailed ? (
                            <div className="mt-2 flex items-center gap-2 text-xs text-red-400">
                                <AlertCircle className="w-3.5 h-3.5" />
                                <span>{errorMessage || 'Generation failed'}</span>
                            </div>
                        ) : null}
                    </div>
                </button>

                {showMedia ? (
                    <div className="app-divider border-t px-4 pb-4">
                        <div
                            className={cn(
                                'mt-4 relative overflow-hidden rounded-2xl group',
                                resolvedMediaType === 'image' ? 'cursor-zoom-in' : '',
                                resolveAspectRatioClass(aspectRatio),
                            )}
                            onClick={() => {
                                if (resolvedMediaType === 'image') {
                                    setPreviewOpen(true)
                                }
                            }}
                            aria-label={resolvedMediaType === 'image' ? (prompt || 'Generated image preview') : undefined}
                            role={resolvedMediaType === 'image' ? 'button' : undefined}
                            tabIndex={resolvedMediaType === 'image' ? 0 : undefined}
                            onKeyDown={(event) => {
                                if (resolvedMediaType !== 'image') {
                                    return
                                }
                                if (event.key === 'Enter' || event.key === ' ') {
                                    event.preventDefault()
                                    setPreviewOpen(true)
                                }
                            }}
                        >
                            {resolvedMediaType === 'video' ? (
                                <HomeChatVideoItem
                                    url={resultUrl}
                                    zoom={100}
                                    onLoadedMetadata={() => {}}
                                />
                            ) : (
                                <>
                                    {!imageLoaded && !imageError && (
                                        <div className={cn(
                                            'absolute inset-0 flex items-center justify-center bg-[var(--app-control)]',
                                        )}>
                                            <Loader2 className="w-6 h-6 text-zinc-400 animate-spin" />
                                        </div>
                                    )}
                                    {imageError && (
                                        <div className={cn(
                                            'app-muted absolute inset-0 flex items-center justify-center gap-2 bg-[var(--app-control)] text-xs',
                                        )}>
                                            <AlertCircle className="w-4 h-4" />
                                            <span>{t('home.chat.image_load_failed', 'Failed to load image')}</span>
                                        </div>
                                    )}
                                    <AgentLazyMedia
                                        src={resultUrl}
                                        alt={prompt || 'Generated image'}
                                        aspectRatio={1}
                                        loadMode="viewport"
                                        className={cn(
                                            'absolute inset-0',
                                        )}
                                        mediaClassName={cn(
                                            'w-full h-full object-cover transition-opacity duration-300',
                                            imageLoaded && !imageError ? 'opacity-100' : 'opacity-0',
                                        )}
                                        onImageLoad={() => setImageLoaded(true)}
                                        onImageError={() => setImageError(true)}
                                    />
                                    <div className="absolute right-3 top-3 flex gap-2 opacity-0 transition-opacity group-hover:opacity-100">
                                        {onUseAsReference && rawResultUrl ? (
                                            <button
                                                type="button"
                                                aria-label={useAsReferenceLabel}
                                                title={useAsReferenceLabel}
                                                onClick={handleUseAsReference}
                                                className="app-media-control p-2 rounded-full"
                                            >
                                                <Paperclip className="w-4 h-4" />
                                            </button>
                                        ) : null}
                                        <button
                                            type="button"
                                            aria-label={`Download generation ${taskId}`}
                                            onClick={handleDownload}
                                            className="app-media-control p-2 rounded-full"
                                        >
                                            <Download className="w-4 h-4" />
                                        </button>
                                    </div>
                                </>
                            )}
                        </div>
                        {prompt ? (
                            <div className={cn(
                                'mt-3 text-sm leading-6 break-words',
                                isDark ? 'text-zinc-300' : 'text-zinc-700',
                            )}>
                                {prompt}
                            </div>
                        ) : null}
                    </div>
                ) : null}
            </div>

            <ImagePreviewDialog
                open={previewOpen}
                onOpenChange={setPreviewOpen}
                src={originalResultUrl || resultUrl || null}
                alt={prompt || 'Generated image preview'}
                title={prompt || 'Generated image preview'}
                imageClassName="rounded-2xl"
                downloadUrl={originalResultUrl || resultUrl || null}
                onDownload={handleDownload}
            />
        </>
    )
}

function artifactField(artifact: GenerationCardProps['artifact'], key: keyof NonNullable<GenerationCardProps['artifact']>) {
    return artifact ? artifact[key] : undefined
}

export const GenerationCard = memo(GenerationCardComponent, (previous, next) => (
    (previous.status === 'completed' || previous.status === 'failed')
    && (next.status === 'completed' || next.status === 'failed')
    && previous.conversationId === next.conversationId
    && previous.taskId === next.taskId
    && previous.status === next.status
    && previous.resultUrl === next.resultUrl
    && previous.prompt === next.prompt
    && previous.mediaType === next.mediaType
    && previous.modelName === next.modelName
    && previous.modelLabel === next.modelLabel
    && previous.aspectRatio === next.aspectRatio
    && previous.resolution === next.resolution
    && previous.duration === next.duration
    && previous.quality === next.quality
    && previous.progress === next.progress
    && previous.toolName === next.toolName
    && previous.errorMessage === next.errorMessage
    && previous.onUseAsReference === next.onUseAsReference
    && previous.isDark === next.isDark
    && artifactField(previous.artifact, 'absolute_path') === artifactField(next.artifact, 'absolute_path')
    && artifactField(previous.artifact, 'absolutePath') === artifactField(next.artifact, 'absolutePath')
    && artifactField(previous.artifact, 'relative_path') === artifactField(next.artifact, 'relative_path')
    && artifactField(previous.artifact, 'relativePath') === artifactField(next.artifact, 'relativePath')
    && artifactField(previous.artifact, 'base_dir') === artifactField(next.artifact, 'base_dir')
    && artifactField(previous.artifact, 'baseDir') === artifactField(next.artifact, 'baseDir')
))

function resolveArtifactResultUrl(artifact?: GenerationCardProps['artifact']) {
    if (!artifact) return undefined
    const baseDir = String(artifact.base_dir || artifact.baseDir || '').trim()
    const relativePath = String(artifact.relative_path || artifact.relativePath || '').trim()
    if (relativePath && (!baseDir || baseDir === 'FILES_DIR')) {
        return relativePath
    }
    return String(artifact.absolute_path || artifact.absolutePath || '').trim() || undefined
}

function getAttachmentNameFromResultUrl(url: string) {
    const cleaned = String(url || '').split(/[?#]/)[0]
    const fileName = cleaned.split('/').filter(Boolean).pop()
    return fileName || 'image'
}
