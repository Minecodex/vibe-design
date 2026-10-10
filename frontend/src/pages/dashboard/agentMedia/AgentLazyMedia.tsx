import * as React from 'react'

import { cn } from '@/lib/utils'

import { useAgentViewportReady } from './agentMediaVisibility'

interface AgentLazyMediaProps {
  src?: string | null
  alt?: string
  kind?: 'image' | 'video'
  aspectRatio?: number
  loadMode?: 'viewport' | 'immediate'
  className?: string
  style?: React.CSSProperties
  mediaClassName?: string
  mediaStyle?: React.CSSProperties
  onClick?: React.MouseEventHandler<HTMLDivElement>
  onImageLoad?: React.ReactEventHandler<HTMLImageElement>
  onImageError?: React.ReactEventHandler<HTMLImageElement>
  onVideoLoadedMetadata?: React.ReactEventHandler<HTMLVideoElement>
  children?: React.ReactNode
  as?: 'div' | 'span'
}

export function AgentLazyMedia({
  src,
  alt = '',
  kind = 'image',
  aspectRatio = 1,
  loadMode = 'viewport',
  className,
  style,
  mediaClassName,
  mediaStyle,
  onClick,
  onImageLoad,
  onImageError,
  onVideoLoadedMetadata,
  children,
  as = 'div',
}: AgentLazyMediaProps) {
  const { ref, ready } = useAgentViewportReady(loadMode)
  const ratio = Number.isFinite(aspectRatio) && aspectRatio > 0 ? aspectRatio : 1
  const shouldRenderMedia = ready && Boolean(src)
  const Container = as

  return (
    <Container
      ref={(node: HTMLDivElement | HTMLSpanElement | null) => { ref.current = node }}
      className={cn('relative overflow-hidden', className)}
      style={{ aspectRatio: `${ratio}`, ...style }}
      onClick={onClick}
    >
      {shouldRenderMedia ? (
        kind === 'video' ? (
          <video
            src={src || undefined}
            muted
            playsInline
            preload="none"
            className={mediaClassName}
            style={mediaStyle}
            onLoadedMetadata={onVideoLoadedMetadata}
          />
        ) : (
          <img
            src={src || undefined}
            alt={alt}
            loading="lazy"
            decoding="async"
            className={mediaClassName}
            style={mediaStyle}
            onLoad={onImageLoad}
            onError={onImageError}
          />
        )
      ) : null}
      {children}
    </Container>
  )
}
