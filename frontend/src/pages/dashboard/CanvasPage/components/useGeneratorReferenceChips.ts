import React from 'react'

export type GeneratorReferenceChip = {
  id: string
  imageUrl: string
  alt: string
  removeLabel?: string
  draggable?: boolean
  onDragStart?: (event: React.DragEvent<HTMLDivElement>) => void
}

type UseGeneratorReferenceChipsArgs = {
  imageUrls: string[]
  alt: string
  removeLabel?: string
  idPrefix?: string
}

function areImageUrlsEqual(previous: string[], next: string[]) {
  if (previous === next) return true
  if (previous.length !== next.length) return false
  return previous.every((imageUrl, index) => imageUrl === next[index])
}

export function useGeneratorReferenceChips({
  imageUrls,
  alt,
  removeLabel,
  idPrefix = '',
}: UseGeneratorReferenceChipsArgs) {
  const cacheRef = React.useRef<{
    imageUrls: string[]
    alt: string
    removeLabel?: string
    idPrefix: string
    chips: GeneratorReferenceChip[]
  } | null>(null)
  const cached = cacheRef.current

  if (
    cached
    && cached.alt === alt
    && cached.removeLabel === removeLabel
    && cached.idPrefix === idPrefix
    && areImageUrlsEqual(cached.imageUrls, imageUrls)
  ) {
    return cached.chips
  }

  const chips = imageUrls.map((imageUrl, index) => ({
    id: `${idPrefix}${index}:${imageUrl}`,
    imageUrl,
    alt,
    removeLabel,
  }))
  cacheRef.current = {
    imageUrls: imageUrls.slice(),
    alt,
    removeLabel,
    idPrefix,
    chips,
  }
  return chips
}

