export type MediaSelectionHandle = 'nw' | 'ne' | 'sw' | 'se'

export type MediaSelectionRect = {
  x: number
  y: number
  width: number
  height: number
}

type MediaDisplayInitItem = {
  type?: 'image' | 'video' | 'image_generator' | 'video_generator' | 'group' | 'text' | 'brush_path'
  x: number
  y: number
  width?: number
  height?: number
  url?: string
  asset_origin?: string
  status?: string
  media_display_size_source?: 'placeholder' | 'intrinsic' | 'user'
}

const FIXED_HANDLE_SIZE_PX = 12
const FIXED_BORDER_WIDTH_PX = 2

export function getMediaSelectionOverlayMetrics(zoom: number) {
  const safeZoom = zoom > 0 ? zoom : 100
  const zoomScale = safeZoom / 100

  return {
    handleSize: FIXED_HANDLE_SIZE_PX / zoomScale,
    handleOffset: (FIXED_HANDLE_SIZE_PX / 2) / zoomScale,
    borderWidth: FIXED_BORDER_WIDTH_PX / zoomScale,
    screenHandleSize: FIXED_HANDLE_SIZE_PX,
    screenBorderWidth: FIXED_BORDER_WIDTH_PX,
  }
}

export function getMediaDisplayInitializationUpdate(args: {
  item: MediaDisplayInitItem
  intrinsicWidth: number
  intrinsicHeight: number
}) {
  const { item, intrinsicWidth, intrinsicHeight } = args

  if (!intrinsicWidth || !intrinsicHeight) return null

  if (
    item.width
    && item.height
    && !shouldReplacePlaceholderMediaSize(item, { intrinsicWidth, intrinsicHeight })
  ) return null

  return {
    width: intrinsicWidth,
    height: intrinsicHeight,
    x: item.x,
    y: item.y,
    media_display_size_source: 'intrinsic' as const,
  }
}

export function shouldReplacePlaceholderMediaSize(
  item: MediaDisplayInitItem,
  intrinsicSize?: { intrinsicWidth: number; intrinsicHeight: number },
) {
  if (item.media_display_size_source === 'user') return false
  if (item.media_display_size_source === 'placeholder') return true

  const isAgentGenerated = item.asset_origin === 'ai_generated'
  const isGeneratorPlaceholder = item.type === 'image_generator' || item.type === 'video_generator'
  if (
    isAgentGenerated
    && item.media_display_size_source === 'intrinsic'
    && intrinsicSize
    && item.width
    && item.height
  ) {
    return (
      Math.round(item.width) !== Math.round(intrinsicSize.intrinsicWidth)
      || Math.round(item.height) !== Math.round(intrinsicSize.intrinsicHeight)
    )
  }
  return isAgentGenerated && isGeneratorPlaceholder && !item.url
}

export function resizeMediaSelectionFromCorner(args: {
  handle: MediaSelectionHandle
  startRect: MediaSelectionRect
  deltaX: number
  deltaY: number
  minSize?: number
}): MediaSelectionRect {
  const { handle, startRect, deltaX, deltaY } = args
  const minSize = Math.max(args.minSize ?? 40, 1)
  const startWidth = Math.max(startRect.width, 1)
  const startHeight = Math.max(startRect.height, 1)
  const aspectRatio = startWidth / startHeight

  const minScale = Math.max(minSize / startWidth, minSize / startHeight)

  const horizontalScale = (() => {
    if (handle === 'nw' || handle === 'sw') {
      return (startWidth - deltaX) / startWidth
    }
    return (startWidth + deltaX) / startWidth
  })()

  const verticalScale = (() => {
    if (handle === 'nw' || handle === 'ne') {
      return (startHeight - deltaY) / startHeight
    }
    return (startHeight + deltaY) / startHeight
  })()

  const horizontalDelta = Math.abs(horizontalScale - 1)
  const verticalDelta = Math.abs(verticalScale - 1)
  const rawScale = horizontalDelta >= verticalDelta ? horizontalScale : verticalScale
  const scale = Math.max(rawScale, minScale)

  const nextWidth = Math.round(startWidth * scale)
  const nextHeight = Math.round(nextWidth / aspectRatio)
  const anchorX = startRect.x + startRect.width
  const anchorY = startRect.y + startRect.height

  switch (handle) {
    case 'nw':
      return {
        x: anchorX - nextWidth,
        y: anchorY - nextHeight,
        width: nextWidth,
        height: nextHeight,
      }
    case 'ne':
      return {
        x: startRect.x,
        y: anchorY - nextHeight,
        width: nextWidth,
        height: nextHeight,
      }
    case 'sw':
      return {
        x: anchorX - nextWidth,
        y: startRect.y,
        width: nextWidth,
        height: nextHeight,
      }
    case 'se':
    default:
      return {
        x: startRect.x,
        y: startRect.y,
        width: nextWidth,
        height: nextHeight,
      }
  }
}
