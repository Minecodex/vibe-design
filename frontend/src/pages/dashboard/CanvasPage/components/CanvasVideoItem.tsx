import { useCallback, useEffect, useRef, useState } from 'react'
import { Maximize, Play } from 'lucide-react'

interface CanvasVideoItemProps {
  url: string
  zoom: number
  autoPreview?: boolean
  onLoadedMetadata: (event: React.SyntheticEvent<HTMLVideoElement>) => void
}

function formatDuration(seconds: number): string {
  if (Number.isNaN(seconds)) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
}

export function CanvasVideoItem({ url, zoom, autoPreview = false, onLoadedMetadata }: CanvasVideoItemProps) {
  const [isHovered, setIsHovered] = useState(false)
  const [duration, setDuration] = useState('')
  const videoRef = useRef<HTMLVideoElement>(null)

  const startPreview = useCallback(() => {
    setIsHovered(true)
    videoRef.current?.play().catch(() => {})
  }, [])

  useEffect(() => {
    if (!autoPreview) return
    startPreview()
  }, [autoPreview, startPreview, url])

  const handleLoadedMetadata = (event: React.SyntheticEvent<HTMLVideoElement>) => {
    if (videoRef.current) {
      setDuration(formatDuration(videoRef.current.duration))
    }
    onLoadedMetadata(event)
  }

  return (
    <div
      data-testid="canvas-video-item"
      style={{ width: '100%', height: '100%', position: 'relative', backgroundColor: 'var(--app-media-overlay)' }}
      onMouseEnter={startPreview}
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
        src={url}
        style={{ width: '100%', height: '100%', objectFit: 'contain' }}
        onLoadedMetadata={handleLoadedMetadata}
        muted
        loop
        playsInline
        preload="metadata"
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
            zIndex: 10,
          }}
        >
          <div
            style={{
              width: 68,
              height: 68,
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
            <Play size={24} fill="currentColor" color="currentColor" style={{ marginLeft: 4 }} />
          </div>
        </div>
      )}
      {isHovered && (
        <>
          <div
            style={{
              position: 'absolute',
              bottom: 8 * 100 / zoom,
              left: 8 * 100 / zoom,
              backgroundColor: 'var(--app-media-control)',
              color: 'var(--app-primary-foreground)',
              padding: '4px 8px',
              borderRadius: 8,
              fontSize: 12,
              backdropFilter: 'blur(8px)',
              zIndex: 10,
              transform: `scale(${100 / zoom})`,
              transformOrigin: 'bottom left',
            }}
          >
            {duration}
          </div>
          <div
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
              bottom: 8 * 100 / zoom,
              right: 8 * 100 / zoom,
              width: 32,
              height: 32,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              backgroundColor: 'var(--app-media-control)',
              color: 'var(--app-primary-foreground)',
              borderRadius: 8,
              cursor: 'pointer',
              backdropFilter: 'blur(8px)',
              zIndex: 10,
              transform: `scale(${100 / zoom})`,
              transformOrigin: 'bottom right',
            }}
          >
            <Maximize size={16} />
          </div>
        </>
      )}
    </div>
  )
}
