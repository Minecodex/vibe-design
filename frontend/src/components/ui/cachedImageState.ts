

export const loadedImageUrls = new Set<string>()

const retainedImages = new Map<string, HTMLImageElement>()

const MAX_RETAINED_IMAGES = 256

export function touchRetainedImage(src: string) {
  const image = retainedImages.get(src)
  if (!image) {
    return
  }
  retainedImages.delete(src)
  retainedImages.set(src, image)
}

export function retainImage(src: string): HTMLImageElement | null {
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
