import type { CanvasItem } from '@/api/endpoints/projects'
export type GeneratorLibraryAsset = {
  id: number
  url: string
  type: 'image' | 'video'
  origin_kind: string
  source_asset_id?: number | null
}

export type GeneratorLibraryTarget = 'reference' | 'first_frame' | 'tail_frame'

type CanvasItemArgs = {
  item: Partial<CanvasItem>
  target: GeneratorLibraryTarget
  assets: GeneratorLibraryAsset[]
  maxSelection: number
  imageModesConflict: boolean
  allowTailFrame?: boolean
}

type AnchoredImageDraftArgs = {
  draft: {
    reference_images: string[]
  }
  assets: GeneratorLibraryAsset[]
  maxSelection: number
}

type AnchoredVideoDraftArgs = {
  draft: {
    sourcePlacement: 'reference' | 'first_frame' | 'tail_frame'
    reference_images: string[]
    first_frame_image: string
    tail_frame_image: string
  }
  target: GeneratorLibraryTarget
  assets: GeneratorLibraryAsset[]
  maxSelection: number
  imageModesConflict: boolean
  allowTailFrame?: boolean
}

function getAssetUrls(assets: GeneratorLibraryAsset[]) {
  return assets.filter((asset) => asset.type === 'image').map((asset) => asset.url)
}

function clampReferenceImages(existing: string[], incoming: string[], maxSelection: number) {
  const next = [...existing, ...incoming]
  return maxSelection > 0 ? next.slice(0, maxSelection) : next
}

export function applyGeneratorAssetsToCanvasItem({
  item,
  target,
  assets,
  maxSelection,
  imageModesConflict,
  allowTailFrame = true,
}: CanvasItemArgs) {
  const incomingUrls = getAssetUrls(assets)
  if (incomingUrls.length === 0) return item

  if (target === 'reference') {
    const existingReferences = Array.isArray(item.reference_images)
      ? item.reference_images
      : item.reference_image ? [item.reference_image] : []
    const nextReferenceImages = clampReferenceImages(existingReferences, incomingUrls, maxSelection)
    return {
      ...item,
      reference_images: nextReferenceImages,
      reference_image: nextReferenceImages[0] || '',
      ...(imageModesConflict ? { first_frame_image: '', tail_frame_image: '' } : {}),
    }
  }

  const nextUrl = incomingUrls[0]
  if (target === 'tail_frame' && !allowTailFrame) {
    return item
  }
  return {
    ...item,
    [target === 'first_frame' ? 'first_frame_image' : 'tail_frame_image']: nextUrl,
    ...(imageModesConflict ? { reference_images: [], reference_image: '' } : {}),
  }
}

export function applyGeneratorAssetsToAnchoredImageDraft({
  draft,
  assets,
  maxSelection,
}: AnchoredImageDraftArgs) {
  const incomingUrls = getAssetUrls(assets)
  if (incomingUrls.length === 0) return draft

  return {
    ...draft,
    reference_images: clampReferenceImages(draft.reference_images, incomingUrls, maxSelection),
  }
}

export function applyGeneratorAssetsToAnchoredVideoDraft({
  draft,
  target,
  assets,
  maxSelection,
  imageModesConflict,
  allowTailFrame = true,
}: AnchoredVideoDraftArgs) {
  const incomingUrls = getAssetUrls(assets)
  if (incomingUrls.length === 0) return draft

  if (target === 'reference') {
    if (imageModesConflict && draft.sourcePlacement !== 'reference') {
      return draft
    }
    return {
      ...draft,
      reference_images: clampReferenceImages(draft.reference_images, incomingUrls, maxSelection),
      ...(imageModesConflict ? { first_frame_image: '', tail_frame_image: '' } : {}),
    }
  }

  if (draft.sourcePlacement === target) {
    return draft
  }
  if (target === 'tail_frame' && !allowTailFrame) {
    return draft
  }
  if (imageModesConflict && draft.sourcePlacement === 'reference') {
    return draft
  }

  return {
    ...draft,
    [target === 'first_frame' ? 'first_frame_image' : 'tail_frame_image']: incomingUrls[0],
    ...(imageModesConflict ? { reference_images: [] } : {}),
  }
}
