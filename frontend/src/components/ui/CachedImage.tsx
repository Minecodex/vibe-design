import { useEffect, useState, type ImgHTMLAttributes, type SyntheticEvent } from 'react'

import { cn } from '@/lib/utils'

const loadedImageUrls = new Set<string>()
const retainedImages = new Map<string, HTMLImageElement>()
const MAX_RETAINED_IMAGES = 256

function touchRetainedImage(src: string) {
  const image = retainedImages.get(src)
  if (!image) {
    return
  }
  retainedImages.delete(src)
  retainedImages.set(src, image)
}

function retainImage(src: string): HTMLImageElement | null {
  if (typeof Image === 'undefined') {
    return null
  }

  const existing = retainedImages.get(src)
  if (existing) {
    touchRetainedImage(src)
    return existing
  }

  const image = new Image()
  image.decoding = 'async'
  image.src = src
  retainedImages.set(src, image)

  while (retainedImages.size > MAX_RETAINED_IMAGES) {
    const oldestKey = retainedImages.keys().next().value
    if (!oldestKey) {
      break
    }
    retainedImages.delete(oldestKey)
  }

  return image
}

export function resetCachedImageStateForTests() {
  loadedImageUrls.clear()
  retainedImages.clear()
}

type CachedImageProps = ImgHTMLAttributes<HTMLImageElement>

export function CachedImage({
  src,
  className,
  onLoad,
  ...props
}: CachedImageProps) {
  const normalizedSrc = src ?? ''
  const [isLoaded, setIsLoaded] = useState(() => loadedImageUrls.has(normalizedSrc))

  useEffect(() => {
    if (!normalizedSrc) {
      setIsLoaded(false)
      return
    }

    if (loadedImageUrls.has(normalizedSrc)) {
      touchRetainedImage(normalizedSrc)
      setIsLoaded(true)
      return
    }

    setIsLoaded(false)
    const retained = retainImage(normalizedSrc)
    if (!retained) {
      return
    }

    if (retained.complete && retained.naturalWidth > 0) {
      loadedImageUrls.add(normalizedSrc)
      setIsLoaded(true)
      return
    }

    const handleLoad = () => {
      loadedImageUrls.add(normalizedSrc)
      touchRetainedImage(normalizedSrc)
      setIsLoaded(true)
    }

    retained.addEventListener('load', handleLoad)
    return () => {
      retained.removeEventListener('load', handleLoad)
    }
  }, [normalizedSrc])

  const handleLoad = (event: SyntheticEvent<HTMLImageElement>) => {
    if (normalizedSrc) {
      loadedImageUrls.add(normalizedSrc)
      retainImage(event.currentTarget.currentSrc || normalizedSrc)
      setIsLoaded(true)
    }
    onLoad?.(event)
  }

  return (
    <img
      {...props}
      src={src}
      onLoad={handleLoad}
      decoding="async"
      data-loaded={isLoaded ? 'true' : 'false'}
      className={cn(
        'transition-opacity duration-150',
        isLoaded ? 'opacity-100' : 'opacity-0',
        className,
      )}
    />
  )
}
