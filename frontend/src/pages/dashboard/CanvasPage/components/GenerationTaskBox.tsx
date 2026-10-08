import { Download, Loader2, Maximize, Play, XCircle } from 'lucide-react'
import * as React from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useChatStore, type ToolCallInfo } from '@/store/canvasAgentStore'
import { getGenerationTaskId, resolveAsyncGenerationToolStatus } from '@/utils/agentGenerationStatus'
import { getModelDisplayName } from '@/utils/modelDisplayName'
import { hasDeletedAgentMediaKey } from '../agentGeneratedMedia'
import { getGenerationFailureKind } from '../generationFailure'
import { getMediaDimensions } from '../mediaDimensions'
import { ensureFullUrl } from './messageMediaUrl'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'
import { useCanvasHarnessMediaSource } from '../useCanvasHarnessMediaSource'

export interface GenerationTaskBoxProps {
  toolCall: ToolCallInfo
  isDark: boolean
  messageId: string | number
  onPreview: (url: string) => void
  onDownload: (url: string, e: React.MouseEvent) => void
  deletedAgentMediaKeys?: string[]
  canReplayCompletedMedia?: boolean
  isHistoryLoaded?: boolean
}

function formatPreviewDuration(seconds: number): string {
  if (Number.isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

function MessageVideoPreview({
  src,
  onLoadedMetadata,
}: {
  src: string
  onLoadedMetadata: (event: React.SyntheticEvent<HTMLVideoElement>) => void
}) {
  const [isHovered, setIsHovered] = React.useState(false)
  const [duration, setDuration] = React.useState('')
  const videoRef = React.useRef<HTMLVideoElement>(null)

  const handleLoadedMetadata = (event: React.SyntheticEvent<HTMLVideoElement>) => {
    if (videoRef.current) {
      setDuration(formatPreviewDuration(videoRef.current.duration))
    }
    onLoadedMetadata(event)
  }

  return (
    <div
      data-testid="message-video-preview"
      style={{ position: 'absolute', inset: 0, backgroundColor: 'var(--app-media-overlay)' }}
      onMouseEnter={() => {
        setIsHovered(true)
        videoRef.current?.play().catch(() => {})
      }}
      onMouseLeave={() => {
        setIsHovered(false)
        if (videoRef.current) {
          videoRef.current.pause()
          videoRef.current.currentTime = 0
        }
      }}
    >
      <video
        ref={videoRef}
        src={src}
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        onLoadedMetadata={handleLoadedMetadata}
        muted
        loop
        playsInline
        preload="none"
      />
      {!isHovered && (
        <div
          aria-label="Play video preview"
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            pointerEvents: 'none',
            zIndex: 1,
          }}
        >
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              backgroundColor: 'var(--app-media-control)',
              border: '1px solid var(--app-media-border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: 'var(--app-shadow-control)',
              backdropFilter: 'blur(10px)',
            }}
          >
            <Play size={20} fill="currentColor" color="currentColor" style={{ marginLeft: 3 }} />
          </div>
        </div>
      )}
      {isHovered && (
        <>
          <div
            style={{
              position: 'absolute',
              left: 12,
              bottom: 12,
              backgroundColor: 'var(--app-media-control)',
              color: 'var(--app-primary-foreground)',
              padding: '4px 10px',
              borderRadius: 12,
              fontSize: 12,
              fontWeight: 600,
              backdropFilter: 'blur(8px)',
            }}
          >
            {duration}
          </div>
          <button
            type="button"
            aria-label="Fullscreen video preview"
            onClick={(event) => {
              event.stopPropagation()
              if (videoRef.current?.requestFullscreen) {
                videoRef.current.requestFullscreen()
                return
              }
              if ((videoRef.current as HTMLVideoElement & { webkitRequestFullscreen?: () => void })?.webkitRequestFullscreen) {
                (videoRef.current as HTMLVideoElement & { webkitRequestFullscreen?: () => void }).webkitRequestFullscreen?.()
              }
            }}
            style={{
              position: 'absolute',
              right: 12,
              bottom: 12,
              width: 44,
              height: 44,
              border: 'none',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'var(--app-media-control)',
              color: 'var(--app-primary-foreground)',
              borderRadius: 12,
              cursor: 'pointer',
              backdropFilter: 'blur(8px)',
            }}
          >
            <Maximize size={18} />
          </button>
        </>
      )}
    </div>
  )
}

// Memoized: paired with a stable `toolCall` prop (see derivedToolCall in
// MessageListRenderers), an unchanged generation card skips re-rendering during the
// streaming region's high-frequency updates and sibling-block changes.
export const GenerationTaskBox = React.memo(GenerationTaskBoxImpl)

function GenerationTaskBoxImpl({
  toolCall,
  messageId,
  onPreview,
  onDownload,
  deletedAgentMediaKeys = [],
  canReplayCompletedMedia = true,
  isHistoryLoaded = false,
}: GenerationTaskBoxProps) {
  const { t } = useTranslation()
  const isImage = toolCall.name === 'generate_image'
  const result = toolCall.result
  const progress = result?.progress || 0
  const taskId = getGenerationTaskId(result, toolCall.args)
  const failedMessage = result?.error_message || result?.error || toolCall.error
  const failureKind = getGenerationFailureKind({
    status: toolCall.status === 'failed' ? 'failed' : result?.status,
    task_id: taskId ?? undefined,
  })
  const isHistoryFailedCard = isHistoryLoaded && (
    toolCall.status === 'failed'
    || result?.status === 'failed'
    || Boolean(failedMessage)
    || result?.canvas_item?.status === 'failed'
  )
  const status = isHistoryFailedCard
    ? 'failed'
    : resolveAsyncGenerationToolStatus({
      currentStatus: toolCall.status,
      result,
      error: toolCall.error,
      args: toolCall.args,
    })

  const onCanvasUpdate = useChatStore(s => s.onCanvasUpdate)
  const conversationId = useChatStore(s => s.conversationId)
  const agentMediaKey = result?.canvas_item?.id || null
  const shouldSkipCanvasReplay = isHistoryLoaded
    || !canReplayCompletedMedia
    || hasDeletedAgentMediaKey(deletedAgentMediaKeys, agentMediaKey)
  const shouldShowFailedErrorTooltip = status === 'failed' && !isHistoryLoaded && Boolean(failedMessage)
  const failureLabel = failureKind === 'internal_failed'
    ? t('canvas.generator.internal_error_label', '内部错误')
    : t('canvas.generator.failed_label')
  const originalResultUrl = ensureFullUrl(result?.result_url, conversationId)
  const previewResultUrl = useCanvasHarnessMediaSource(conversationId, result?.result_url, {
    variant: isHistoryLoaded ? 'thumb-512' : 'original',
    enabled: Boolean(result?.result_url),
  })
  const displayResultUrl = ensureFullUrl(previewResultUrl || result?.result_url, conversationId)
  const modelDisplay = getModelDisplayName(
    result?.model_label || result?.canvas_item?.model_label,
    result?.model_name || result?.canvas_item?.model_name,
  )
  const onCanvasUpdateRef = React.useRef(onCanvasUpdate)
  onCanvasUpdateRef.current = onCanvasUpdate
  const placeholderAddedRef = React.useRef(false)
  const addedToCanvasRef = React.useRef(false)
  const syncCanvasRevision = React.useCallback(() => {
    const revision = Number(result?.canvas_revision ?? result?.canvasRevision)
    if (!Number.isFinite(revision) || revision < 0) {
      return
    }
    onCanvasUpdateRef.current?.('sync_canvas_revision', {}, {
      canvasRevision: Math.trunc(revision),
      canvasItemDeleted: result?.canvas_item_deleted === true || result?.canvasItemDeleted === true,
    })
  }, [result?.canvas_revision, result?.canvasRevision, result?.canvas_item_deleted, result?.canvasItemDeleted])

  React.useEffect(() => {
    if (
      !result?.canvas_item
      || !onCanvasUpdateRef.current
      || placeholderAddedRef.current
      || shouldSkipCanvasReplay
      || status === 'completed'
      || status === 'failed'
    ) {
      return
    }

    placeholderAddedRef.current = true
    syncCanvasRevision()
    onCanvasUpdateRef.current('add', {
      ...result.canvas_item,
      type: isImage ? 'image_generator' : 'video_generator',
      artifact_ref: result?.artifact_ref,
      status: result.canvas_item.status || 'generating',
      canvas_revision: result?.canvas_revision ?? result?.canvasRevision,
      canvas_item_deleted: result?.canvas_item_deleted ?? result?.canvasItemDeleted,
      failure_kind: undefined,
      conversationId,
      messageId,
      agentMediaKey: result.canvas_item.id || null,
      _agentLabel: modelDisplay || t('canvas.chat.agent_added'),
    })
  }, [
    conversationId,
    isImage,
    messageId,
    onCanvasUpdate,
    result?.canvas_item,
    modelDisplay,
    shouldSkipCanvasReplay,
    status,
    syncCanvasRevision,
    t,
  ])

  React.useEffect(() => {
    if (
      !result?.canvas_item
      || !onCanvasUpdateRef.current
      || placeholderAddedRef.current
      || shouldSkipCanvasReplay
      || status !== 'failed'
      || failureKind !== 'internal_failed'
    ) {
      return
    }

    placeholderAddedRef.current = true
    syncCanvasRevision()
    onCanvasUpdateRef.current('add', {
      ...result.canvas_item,
      type: isImage ? 'image_generator' : 'video_generator',
      artifact_ref: result?.artifact_ref,
      status: 'failed',
      task_id: taskId ?? result.canvas_item.task_id,
      error_message: failedMessage,
      failure_kind: failureKind,
      canvas_revision: result?.canvas_revision ?? result?.canvasRevision,
      canvas_item_deleted: result?.canvas_item_deleted ?? result?.canvasItemDeleted,
      conversationId,
      messageId,
      agentMediaKey: result.canvas_item.id || null,
      _agentLabel: modelDisplay || t('canvas.chat.agent_added'),
    })
  }, [
    conversationId,
    failedMessage,
    failureKind,
    isImage,
    messageId,
    result?.canvas_item,
    modelDisplay,
    shouldSkipCanvasReplay,
    status,
    syncCanvasRevision,
    t,
    taskId,
  ])

  React.useEffect(() => {
    if (status === 'completed' && result?.result_url && !addedToCanvasRef.current && onCanvasUpdateRef.current && !shouldSkipCanvasReplay) {
      if (result?.canvas_item) {
        addedToCanvasRef.current = true
        syncCanvasRevision()
        onCanvasUpdateRef.current('add_generated_media', {
          ...result.canvas_item,
          url: originalResultUrl,
          status: 'completed',
          type: isImage ? 'image' : 'video',
          artifact_ref: result?.artifact_ref,
          canvas_revision: result?.canvas_revision ?? result?.canvasRevision,
          canvas_item_deleted: result?.canvas_item_deleted ?? result?.canvasItemDeleted,
          conversationId,
          messageId,
          agentMediaKey: result.canvas_item.id || null,
          _agentLabel: modelDisplay || t('canvas.chat.agent_added'),
        })
      }
    }
  }, [status, result?.result_url, originalResultUrl, conversationId, messageId, isImage, result?.canvas_item, modelDisplay, onCanvasUpdate, t, shouldSkipCanvasReplay, syncCanvasRevision])

  const aspect_ratio = result?.params?.aspect_ratio || result?.canvas_item?.aspect_ratio || toolCall.args.aspect_ratio || (isImage ? '1:1' : '16:9')
  const providerCode = result?.provider_code || result?.canvas_item?.provider_code || toolCall.args.provider_code || ''
  const configuredResolution = result?.params?.resolution || result?.resolution || result?.canvas_item?.resolution || toolCall.args.resolution
  const actualResolution = result?.params?.resolution || result?.resolution || result?.canvas_item?.resolution || ''
  const [actualDims, setActualDims] = React.useState<{ width: number; height: number } | null>(null)
  const dimensions = getMediaDimensions({
    type: isImage ? 'image' : 'video',
    aspect_ratio,
    provider_code: providerCode,
    resolution: configuredResolution,
  }, undefined, actualDims || undefined)
  const ratio = dimensions.display.height / dimensions.display.width
  const resolutionDisplay = actualResolution
    ? (actualDims ? dimensions.display.label : String(actualResolution)).replace(/\s×\s/g, '×')
    : ''
  const shouldShowModelDisplay = Boolean(modelDisplay)
  const shouldShowResolutionDisplay = Boolean(resolutionDisplay)
  const previewBackground = isImage ? 'var(--app-control-hover)' : 'var(--app-media-overlay)'

  return (
    <div style={{
      width: '100%',
      maxWidth: 320,
      borderRadius: 12,
      overflow: 'hidden',
      border: '1px solid var(--app-border)',
      backgroundColor: 'var(--app-surface-muted)',
      display: 'flex',
      flexDirection: 'column',
      marginTop: 8,
    }}>
      <div style={{
        width: '100%',
        paddingTop: `${ratio * 100}%`,
        position: 'relative',
        backgroundColor: previewBackground,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        {status === 'completed' && result?.result_url ? (
          isImage ? (
              <div
                className="group absolute inset-0 cursor-pointer"
              onClick={() => onPreview(originalResultUrl)}
            >
              <AgentLazyMedia
                src={displayResultUrl}
                alt=""
                loadMode={isHistoryLoaded ? 'viewport' : 'immediate'}
                aspectRatio={dimensions.display.width / dimensions.display.height}
                className="absolute inset-0"
                mediaStyle={{ width: '100%', height: '100%', objectFit: 'contain' }}
                mediaClassName="transition-transform group-hover:scale-[1.02] duration-300"
                onImageLoad={(e) => {
                  const img = e.currentTarget
                  if (img.naturalWidth && img.naturalHeight) {
                    setActualDims({ width: img.naturalWidth, height: img.naturalHeight })
                  }
                }}
              />
              <div className="absolute bottom-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <Button
                  size="icon-sm"
                  variant="media"
                  className="rounded-sm"
                  onClick={(e) => onDownload(originalResultUrl, e)}
                  title={t('canvas.chat.download')}
                >
                  <Download size={16} />
                </Button>
              </div>
            </div>
          ) : (
            <MessageVideoPreview
              src={originalResultUrl}
              onLoadedMetadata={(e) => {
                const video = e.currentTarget
                if (video.videoWidth && video.videoHeight) {
                  setActualDims({ width: video.videoWidth, height: video.videoHeight })
                }
              }}
            />
          )
        ) : (
          <div style={{
            position: 'absolute', top: 0, left: 0, width: '100%', height: '100%',
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 12,
          }}>
            {status === 'failed' ? (
              shouldShowFailedErrorTooltip ? (
                <TooltipProvider>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, cursor: 'default' }}>
                        <XCircle size={32} color="var(--app-danger)" strokeWidth={1.5} />
                        <span style={{ fontSize: 13, color: 'var(--app-danger)', fontWeight: 500 }}>
                          {failureLabel}
                        </span>
                      </div>
                    </TooltipTrigger>
                    <TooltipContent side="bottom" className="max-w-xs">
                      <p className="text-xs">{failedMessage}</p>
                    </TooltipContent>
                  </Tooltip>
                </TooltipProvider>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, cursor: 'default' }}>
                  <XCircle size={32} color="var(--app-danger)" strokeWidth={1.5} />
                  <span style={{ fontSize: 13, color: 'var(--app-danger)', fontWeight: 500 }}>
                    {failureLabel}
                  </span>
                </div>
              )
            ) : (
              <>
                <Loader2 size={24} color="var(--app-primary)" style={{ animation: 'spin 1.5s linear infinite' }} />
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--app-foreground)' }}>
                    {progress}%
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--app-foreground-subtle)' }}>
                    {isImage ? t('canvas.generator.generating_image') : t('canvas.generator.generating_video')}
                  </span>
                </div>
                <div style={{
                  width: '60%',
                  height: 4,
                  backgroundColor: 'var(--app-control)',
                  borderRadius: 2,
                  overflow: 'hidden',
                }}>
                  <div style={{
                    width: `${progress}%`,
                    height: '100%',
                    backgroundColor: 'var(--app-primary)',
                    transition: 'width 0.3s ease',
                  }} />
                </div>
              </>
            )}
          </div>
        )}
      </div>

      <div style={{ padding: '8px 12px', borderTop: '1px solid var(--app-border)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {shouldShowModelDisplay && (
            <div style={{
              padding: '2px 8px',
              borderRadius: 4,
              backgroundColor: 'var(--app-control)',
              fontSize: 10,
              color: 'var(--app-foreground-subtle)',
            }}>
              {modelDisplay}
            </div>
          )}
          {shouldShowResolutionDisplay && (
            <div style={{
              padding: '2px 8px',
              borderRadius: 4,
              backgroundColor: 'var(--app-control)',
              fontSize: 10,
              color: 'var(--app-foreground-subtle)',
            }}>
              {resolutionDisplay}
            </div>
          )}
          {status === 'running' && (
            <div style={{ fontSize: 11, color: 'var(--app-primary)', marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 4 }}>
              <Loader2 size={10} style={{ animation: 'spin 1s linear infinite' }} />
              {t('canvas.chat.running')}
            </div>
          )}
          {status === 'failed' && (
            shouldShowFailedErrorTooltip ? (
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <div style={{ fontSize: 11, color: 'var(--app-danger)', marginLeft: 'auto', cursor: 'default' }}>
                      {t('canvas.generator.failed_label') || '生成失败'}
                    </div>
                  </TooltipTrigger>
                  <TooltipContent side="top" className="max-w-xs">
                    <p className="text-xs">{failedMessage}</p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            ) : (
              <div style={{ fontSize: 11, color: 'var(--app-danger)', marginLeft: 'auto', cursor: 'default' }}>
                {t('canvas.generator.failed_label') || '生成失败'}
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}
