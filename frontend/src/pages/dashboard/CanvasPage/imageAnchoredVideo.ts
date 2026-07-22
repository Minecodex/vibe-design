import type { CanvasItem } from '@/api/endpoints/projects'

export type AnchoredVideoSourcePlacement = 'reference' | 'first_frame' | 'tail_frame'

export interface AnchoredVideoInputsDraft {
  sourceImageUrl: string
  sourcePlacement: AnchoredVideoSourcePlacement
  referenceImages: string[]
  firstFrameImage: string
  tailFrameImage: string
}

export interface HoverOnlyFailedVideoTaskLike {
  type?: CanvasItem['type']
  status?: CanvasItem['status']
  generator_origin?: 'image_action' | 'standalone'
}

function sanitizeImageList(imageUrls: string[], excludedUrl: string) {
  return imageUrls.filter((url) => Boolean(url) && url !== excludedUrl)
}

export function buildAnchoredVideoInputs(draft: AnchoredVideoInputsDraft) {
  const referenceImages = sanitizeImageList(draft.referenceImages, draft.sourceImageUrl)
  const firstFrameImage = draft.firstFrameImage === draft.sourceImageUrl ? '' : draft.firstFrameImage
  const tailFrameImage = draft.tailFrameImage === draft.sourceImageUrl ? '' : draft.tailFrameImage

  if (draft.sourcePlacement === 'reference') {
    return {
      referenceImages: [draft.sourceImageUrl, ...referenceImages],
      firstFrameImage,
      tailFrameImage,
    }
  }

  if (draft.sourcePlacement === 'first_frame') {
    return {
      referenceImages,
      firstFrameImage: draft.sourceImageUrl,
      tailFrameImage,
    }
  }

  return {
    referenceImages,
    firstFrameImage,
    tailFrameImage: draft.sourceImageUrl,
  }
}

function overlapsRect(
  left: number,
  top: number,
  width: number,
  height: number,
  item: CanvasItem,
) {
  const itemWidth = item.width || 0
  const itemHeight = item.height || 0

  return !(
    left + width <= item.x ||
    item.x + itemWidth <= left ||
    top + height <= item.y ||
    item.y + itemHeight <= top
  )
}

export function findNearbyVideoTaskPosition({
  sourceItem,
  canvasItems,
  taskSize,
  gap = 24,
}: {
  sourceItem: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>
  canvasItems: CanvasItem[]
  taskSize: { width: number; height: number }
  gap?: number
}) {
  const sourceWidth = sourceItem.width || 0
  const sourceHeight = sourceItem.height || 0

  const candidates = [
    {
      x: sourceItem.x + sourceWidth + gap,
      y: sourceItem.y + (sourceHeight - taskSize.height) / 2,
    },
    {
      x: sourceItem.x + (sourceWidth - taskSize.width) / 2,
      y: sourceItem.y + sourceHeight + gap,
    },
    {
      x: sourceItem.x - taskSize.width - gap,
      y: sourceItem.y + (sourceHeight - taskSize.height) / 2,
    },
    {
      x: sourceItem.x + (sourceWidth - taskSize.width) / 2,
      y: sourceItem.y - taskSize.height - gap,
    },
  ]

  const availableCandidate = candidates.find((candidate) => {
    return !canvasItems.some((item) =>
      overlapsRect(candidate.x, candidate.y, taskSize.width, taskSize.height, item),
    )
  })

  return availableCandidate || candidates[0]
}

export function isHoverOnlyFailedVideoTask(item: HoverOnlyFailedVideoTaskLike) {
  return (
    item.type === 'video_generator' &&
    item.status === 'failed' &&
    item.generator_origin === 'image_action'
  )
}
