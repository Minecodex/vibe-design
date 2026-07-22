import * as React from 'react'
import { Download, X } from 'lucide-react'

import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Dialog, DialogClose, DialogContent, DialogTitle } from '@/components/ui/dialog'

const MIN_ZOOM = 1
const MAX_ZOOM = 6
const WHEEL_STEP = 0.2
const IMAGE_PREVIEW_DIALOG_Z_INDEX = 'z-[2147483647]'

interface ZoomableImageViewerProps {
  src: string
  alt: string
  className?: string
  imageClassName?: string
  closeAction?: React.ReactNode
  downloadAction?: React.ReactNode
}

interface ImagePreviewDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  src: string | null
  alt: string
  title?: string
  imageClassName?: string
  downloadUrl?: string | null
  onDownload?: (event?: React.MouseEvent) => void | Promise<void>
}

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function clampOffset(nextOffset: { x: number; y: number }, maxOffset: { x: number; y: number }) {
  return {
    x: clamp(nextOffset.x, -maxOffset.x, maxOffset.x),
    y: clamp(nextOffset.y, -maxOffset.y, maxOffset.y),
  }
}

function buildDownloadAction(downloadUrl?: string | null, onDownload?: (event?: React.MouseEvent) => void | Promise<void>) {
  if (!downloadUrl && !onDownload) {
    return null
  }

  const handleClick = async (event: React.MouseEvent) => {
    event.stopPropagation()
    if (onDownload) {
      await onDownload(event)
      return
    }

    if (!downloadUrl) {
      return
    }

    const response = await fetch(downloadUrl)
    const blob = await response.blob()
    const blobUrl = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = blobUrl
    const filename = downloadUrl.split('/').pop()?.split('?')[0] || 'image'
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(blobUrl)
  }

  return (
    <Button
      size="icon"
      variant="secondary"
      className="rounded-full bg-[var(--app-control-selected)] text-[var(--app-control-selected-foreground)] shadow-lg hover:bg-[var(--app-control-selected)]"
      onClick={(event) => { void handleClick(event) }}
    >
      <Download size={18} />
    </Button>
  )
}

function buildCloseAction() {
  return (
    <DialogClose asChild>
      <Button
        size="icon"
        variant="secondary"
        className="rounded-full border border-[var(--app-media-border)] bg-[var(--app-media-control)] text-white shadow-lg hover:bg-[var(--app-media-control-hover)]"
      >
        <X size={18} />
        <span className="sr-only">Close</span>
      </Button>
    </DialogClose>
  )
}

export function ZoomableImageViewer({
  src,
  alt,
  className,
  imageClassName,
  closeAction,
  downloadAction,
}: ZoomableImageViewerProps) {
  const viewportRef = React.useRef<HTMLDivElement | null>(null)
  const [viewportSize, setViewportSize] = React.useState({ width: 0, height: 0 })
  const [naturalSize, setNaturalSize] = React.useState({ width: 0, height: 0 })
  const [zoom, setZoom] = React.useState(MIN_ZOOM)
  const [offset, setOffset] = React.useState({ x: 0, y: 0 })
  const [isDragging, setIsDragging] = React.useState(false)
  const hasInitializedZoomRef = React.useRef(false)
  const dragPointerIdRef = React.useRef<number | null>(null)
  const dragStartPointerRef = React.useRef({ x: 0, y: 0 })
  const dragStartOffsetRef = React.useRef({ x: 0, y: 0 })

  React.useEffect(() => {
    setZoom(MIN_ZOOM)
    setOffset({ x: 0, y: 0 })
    setIsDragging(false)
    hasInitializedZoomRef.current = false
    dragPointerIdRef.current = null
    setNaturalSize({ width: 0, height: 0 })
  }, [src])

  React.useEffect(() => {
    const element = viewportRef.current
    if (!element || typeof ResizeObserver === 'undefined') {
      return
    }

    const syncViewportSize = () => {
      setViewportSize({
        width: element.clientWidth,
        height: element.clientHeight,
      })
    }

    syncViewportSize()

    const observer = new ResizeObserver(() => syncViewportSize())
    observer.observe(element)

    return () => observer.disconnect()
  }, [])

  const fitScale = React.useMemo(() => {
    if (!naturalSize.width || !naturalSize.height || !viewportSize.width || !viewportSize.height) {
      return 1
    }

    return Math.min(
      viewportSize.width / naturalSize.width,
      viewportSize.height / naturalSize.height,
    )
  }, [naturalSize.height, naturalSize.width, viewportSize.height, viewportSize.width])

  const naturalZoom = React.useMemo(() => {
    if (fitScale <= 0) {
      return 1
    }

    return Math.max(1, Number((1 / fitScale).toFixed(2)))
  }, [fitScale])

  const initialZoom = React.useMemo(() => {
    if (!naturalSize.width || !naturalSize.height || !viewportSize.width || !viewportSize.height) {
      return MIN_ZOOM
    }

    // Open in fit-to-viewport mode so the whole image is visible initially.
    return MIN_ZOOM
  }, [naturalSize.height, naturalSize.width, viewportSize.height, viewportSize.width])

  const renderedWidth = React.useMemo(() => naturalSize.width * fitScale * zoom, [fitScale, naturalSize.width, zoom])
  const renderedHeight = React.useMemo(() => naturalSize.height * fitScale * zoom, [fitScale, naturalSize.height, zoom])

  const maxOffset = React.useMemo(() => ({
    x: Math.max(0, (renderedWidth - viewportSize.width) / 2),
    y: Math.max(0, (renderedHeight - viewportSize.height) / 2),
  }), [renderedHeight, renderedWidth, viewportSize.height, viewportSize.width])

  React.useEffect(() => {
    setOffset((currentOffset) => clampOffset(currentOffset, maxOffset))
  }, [maxOffset.x, maxOffset.y])

  React.useEffect(() => {
    if (!naturalSize.width || !naturalSize.height || !viewportSize.width || !viewportSize.height) {
      return
    }

    if (hasInitializedZoomRef.current) {
      return
    }

    hasInitializedZoomRef.current = true
    setZoom(initialZoom)
    setOffset({ x: 0, y: 0 })
  }, [initialZoom, naturalSize.height, naturalSize.width, viewportSize.height, viewportSize.width])

  const handleWheel = React.useCallback((event: React.WheelEvent<HTMLDivElement>) => {
    event.stopPropagation()

    if (event.ctrlKey || event.metaKey) {
      return
    }

    event.preventDefault()

    setZoom((currentZoom) => {
      const direction = event.deltaY < 0 ? 1 : -1
      const nextZoom = clamp(Number((currentZoom + direction * WHEEL_STEP).toFixed(2)), MIN_ZOOM, MAX_ZOOM)
      if (nextZoom === MIN_ZOOM) {
        setOffset({ x: 0, y: 0 })
      }
      return nextZoom
    })
  }, [])

  const handlePointerDown = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (maxOffset.x === 0 && maxOffset.y === 0) {
      return
    }

    dragPointerIdRef.current = event.pointerId
    dragStartPointerRef.current = { x: event.clientX, y: event.clientY }
    dragStartOffsetRef.current = offset
    setIsDragging(true)
    event.currentTarget.setPointerCapture(event.pointerId)
  }, [maxOffset.x, maxOffset.y, offset])

  const handlePointerMove = React.useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    if (!isDragging || dragPointerIdRef.current !== event.pointerId) {
      return
    }

    const deltaX = event.clientX - dragStartPointerRef.current.x
    const deltaY = event.clientY - dragStartPointerRef.current.y
    setOffset(clampOffset({
      x: dragStartOffsetRef.current.x + deltaX,
      y: dragStartOffsetRef.current.y + deltaY,
    }, maxOffset))
  }, [isDragging, maxOffset])

  const stopDragging = React.useCallback((event?: React.PointerEvent<HTMLDivElement>) => {
    if (event && dragPointerIdRef.current === event.pointerId && event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId)
    }
    dragPointerIdRef.current = null
    setIsDragging(false)
  }, [])

  const handleDoubleClick = React.useCallback((event: React.MouseEvent<HTMLDivElement>) => {
    event.stopPropagation()

    const targetZoom = zoom > MIN_ZOOM + 0.01
      ? MIN_ZOOM
      : (naturalZoom > 1.05 ? naturalZoom : 2)

    setZoom(clamp(targetZoom, MIN_ZOOM, MAX_ZOOM))
    setOffset({ x: 0, y: 0 })
  }, [naturalZoom, zoom])

  const canDrag = maxOffset.x > 0 || maxOffset.y > 0

  return (
    <div
      ref={viewportRef}
      className={cn('relative flex h-full w-full items-center justify-center overflow-hidden', className)}
      onClick={(event) => event.stopPropagation()}
      onWheel={handleWheel}
    >
      <div
        className={cn(
          'relative flex items-center justify-center select-none',
          canDrag ? (isDragging ? 'cursor-grabbing' : 'cursor-grab') : 'cursor-zoom-in',
        )}
        style={{
          width: renderedWidth || undefined,
          height: renderedHeight || undefined,
          transform: `translate(${offset.x}px, ${offset.y}px)`,
        }}
        onDoubleClick={handleDoubleClick}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
      >
        <img
          src={src}
          alt={alt}
          draggable={false}
          className={cn('block max-w-none select-none shadow-2xl', imageClassName)}
          style={{
            width: renderedWidth || undefined,
            height: renderedHeight || undefined,
          }}
          onLoad={(event) => {
            setNaturalSize({
              width: event.currentTarget.naturalWidth,
              height: event.currentTarget.naturalHeight,
            })
          }}
        />
      </div>

      {closeAction ? <div className="absolute right-5 top-5 z-10">{closeAction}</div> : null}
      {downloadAction ? <div className="absolute bottom-5 right-5 z-10">{downloadAction}</div> : null}
    </div>
  )
}

export function ImagePreviewDialog({
  open,
  onOpenChange,
  src,
  alt,
  title,
  imageClassName,
  downloadUrl,
  onDownload,
}: ImagePreviewDialogProps) {
  const downloadAction = React.useMemo(
    () => buildDownloadAction(downloadUrl, onDownload),
    [downloadUrl, onDownload],
  )
  const closeAction = React.useMemo(() => buildCloseAction(), [])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className={cn(
          IMAGE_PREVIEW_DIALOG_Z_INDEX,
          "w-[calc(100vw-2rem)] h-[calc(100vh-2rem)] max-w-[calc(100vw-2rem)] sm:w-[calc(100vw-3rem)] sm:h-[calc(100vh-3rem)] sm:max-w-[calc(100vw-3rem)] lg:w-[min(96vw,1680px)] lg:h-[min(94vh,1040px)] lg:max-w-[min(96vw,1680px)] overflow-hidden rounded-[28px] border border-[var(--app-media-border)] bg-[var(--app-media-overlay)] p-0 shadow-2xl backdrop-blur-xl",
        )}
        overlayClassName={IMAGE_PREVIEW_DIALOG_Z_INDEX}
      >
        <DialogTitle className="sr-only">{title || alt}</DialogTitle>
        {src ? (
          <ZoomableImageViewer
            src={src}
            alt={alt}
            imageClassName={imageClassName}
            closeAction={closeAction}
            downloadAction={downloadAction}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
