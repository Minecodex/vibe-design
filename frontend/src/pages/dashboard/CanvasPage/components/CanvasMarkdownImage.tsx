import { useCanvasHarnessMediaSource } from '../useCanvasHarnessMediaSource'
import { AgentLazyMedia } from '../../agentMedia/AgentLazyMedia'

interface CanvasMarkdownImageProps {
  src: string
  alt: string
  conversationId?: string | number | null
  onPreview?: (url: string) => void
}

export function CanvasMarkdownImage({
  src,
  alt,
  conversationId,
  onPreview,
}: CanvasMarkdownImageProps) {
  const resolvedUrl = useCanvasHarnessMediaSource(conversationId, src, { variant: 'thumb-1024' }) || ''

  return (
    <AgentLazyMedia
      src={resolvedUrl}
      alt={alt}
      aspectRatio={16 / 9}
      as="span"
      className="my-2.5 rounded-xl"
      mediaStyle={{
        display: 'block',
        width: '100%',
        height: '100%',
        objectFit: 'contain',
      }}
      onClick={() => {
        if (resolvedUrl) {
          onPreview?.(resolvedUrl)
        }
      }}
      style={{
        maxWidth: '100%',
        minHeight: 120,
        background: 'var(--app-surface-muted)',
        cursor: resolvedUrl && onPreview ? 'zoom-in' : 'default',
      }}
    />
  )
}
