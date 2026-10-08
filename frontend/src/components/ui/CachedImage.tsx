import { loadedImageUrls, retainImage, touchRetainedImage } from './cachedImageState'
import { useEffect, useState, type ImgHTMLAttributes, type SyntheticEvent } from 'react'

import { cn } from '@/lib/utils'











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
