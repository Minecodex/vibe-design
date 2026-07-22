import { useEffect, useRef, useState } from 'react'
import { Video } from 'lucide-react'
import { useVirtualizer } from '@tanstack/react-virtual'

import { getAssetListMediaUrl, type AssetRead } from '@/api/endpoints/assets'
import { cn } from '@/lib/utils'
import { CachedImage } from '@/components/ui/CachedImage'

interface AssetPreviewThumbnailStripProps {
  assets: AssetRead[]
  currentIndex: number
  onSelect: (index: number) => void
}

const THUMBNAIL_SIZE = 64
const THUMBNAIL_GAP = 12
const THUMBNAIL_OVERSCAN = 4
const DEFAULT_VIEWPORT_WIDTH = 640

export function AssetPreviewThumbnailStrip({
  assets,
  currentIndex,
  onSelect,
}: AssetPreviewThumbnailStripProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [previewFailedAssetIds, setPreviewFailedAssetIds] = useState<Set<number>>(() => new Set())
  const [viewportWidth, setViewportWidth] = useState(DEFAULT_VIEWPORT_WIDTH)
  const endSpacerWidth = Math.max(THUMBNAIL_SIZE, Math.floor(viewportWidth / 2 - THUMBNAIL_SIZE / 2))

  const thumbnailVirtualizer = useVirtualizer({
    count: assets.length,
    horizontal: true,
    getScrollElement: () => scrollRef.current,
    observeElementRect: (_instance, callback) => {
      const measure = () => {
        const width = scrollRef.current?.clientWidth || DEFAULT_VIEWPORT_WIDTH
        setViewportWidth(current => current === width ? current : width)
        callback({
          width,
          height: THUMBNAIL_SIZE,
        })
      }

      measure()
      window.addEventListener('resize', measure)

      return () => {
        window.removeEventListener('resize', measure)
      }
    },
    observeElementOffset: (_instance, callback) => {
      const scrollElement = scrollRef.current
      if (!scrollElement) {
        callback(0, false)
        return () => {}
      }

      const handleScroll = () => callback(scrollElement.scrollLeft, false)
      handleScroll()
      scrollElement.addEventListener('scroll', handleScroll, { passive: true })

      return () => {
        scrollElement.removeEventListener('scroll', handleScroll)
      }
    },
    estimateSize: index => THUMBNAIL_SIZE + (index === assets.length - 1 ? 0 : THUMBNAIL_GAP),
    overscan: THUMBNAIL_OVERSCAN,
    initialRect: {
      width: scrollRef.current?.clientWidth || DEFAULT_VIEWPORT_WIDTH,
      height: THUMBNAIL_SIZE,
    },
  })

  useEffect(() => {
    thumbnailVirtualizer.scrollToIndex(currentIndex, {
      align: 'center',
    })
  }, [currentIndex, thumbnailVirtualizer])

  return (
    <div
      ref={scrollRef}
      className="no-scrollbar absolute bottom-12 left-1/2 max-w-[50vw] -translate-x-[calc(50%+192px)] overflow-x-auto overflow-y-hidden rounded-3xl border border-[var(--app-media-border)] bg-[var(--app-media-control)] p-4 shadow-2xl backdrop-blur-3xl"
      data-testid="asset-preview-thumbnails"
    >
      <div
        style={{
          width: thumbnailVirtualizer.getTotalSize() + endSpacerWidth,
          height: THUMBNAIL_SIZE,
          position: 'relative',
        }}
      >
        <div
          aria-hidden="true"
          data-testid="asset-preview-thumbnail-end-spacer"
          className="pointer-events-none absolute top-0 flex h-full items-center pl-3"
          style={{
            left: thumbnailVirtualizer.getTotalSize(),
            width: endSpacerWidth,
            height: THUMBNAIL_SIZE,
          }}
        >
          <div className="h-8 w-px rounded-full bg-[var(--app-media-control-hover)]" />
        </div>
        {thumbnailVirtualizer.getVirtualItems().map(virtualItem => {
          const asset = assets[virtualItem.index]
          if (!asset) {
            return null
          }
          const shouldUseOriginalImage = previewFailedAssetIds.has(asset.id)
          const listMediaUrl = shouldUseOriginalImage ? asset.url : getAssetListMediaUrl(asset)

          return (
            <button
              key={asset.id}
              onClick={() => onSelect(virtualItem.index)}
              className={cn(
                'rounded-2xl overflow-hidden transition-[opacity,box-shadow,border-color] border-2',
                currentIndex === virtualItem.index
                  ? 'z-10 border-[var(--app-primary)] opacity-100 shadow-[0_0_0_2px_var(--app-focus-ring),var(--app-shadow-control)]'
                  : 'border-transparent opacity-40 hover:opacity-100',
              )}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: THUMBNAIL_SIZE,
                height: THUMBNAIL_SIZE,
                transform: `translateX(${virtualItem.start}px)`,
              }}
            >
              {asset.asset_type === 'video' ? (
                <div className="w-full h-full relative">
                  <video src={asset.url} className="w-full h-full object-cover" />
                  <div className="absolute inset-0 flex items-center justify-center bg-[var(--app-media-scrim)]">
                    <Video className="w-4 h-4 text-white" />
                  </div>
                </div>
              ) : (
                <CachedImage
                  src={listMediaUrl}
                  alt=""
                  className="w-full h-full object-cover"
                  onError={() => {
                    if (shouldUseOriginalImage || listMediaUrl === asset.url) {
                      return
                    }
                    setPreviewFailedAssetIds(current => {
                      if (current.has(asset.id)) {
                        return current
                      }
                      const next = new Set(current)
                      next.add(asset.id)
                      return next
                    })
                  }}
                />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
