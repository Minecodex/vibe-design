import type { CanvasItem } from '@/api/endpoints/projects'

export interface ItemBounds {
  left: number
  right: number
  top: number
  bottom: number
  centerX: number
  centerY: number
}

type XAnchor = 'left' | 'centerX' | 'right'
type YAnchor = 'top' | 'centerY' | 'bottom'

export interface GuideCandidate {
  axis: 'x' | 'y'
  value: number
  spanStart: number
  spanEnd: number
  sourceItemId: string
  sourceKind: 'item' | 'group'
  anchor: XAnchor | YAnchor
}

export interface GuideCandidateBuckets {
  x: GuideCandidate[]
  y: GuideCandidate[]
}

export interface ActiveGuide {
  axis: 'x' | 'y'
  value: number
  lineStart: number
  lineEnd: number
  matchedAnchor: XAnchor | YAnchor
  sourceItemId: string
}

export interface ProjectedGuide {
  axis: 'x' | 'y'
  left: number
  top: number
  width: number
  height: number
  sourceItemId: string
  matchedAnchor: XAnchor | YAnchor
}

const GUIDE_LINE_PADDING = 12

type GetItemDims = (item: CanvasItem) => { width: number; height: number }

export function getCanvasBounds(item: CanvasItem, getItemDims: GetItemDims): ItemBounds {
  const dims = getItemDims(item)
  const width = item.width || dims.width
  const height = item.height || dims.height
  const left = item.x
  const top = item.y
  const right = left + width
  const bottom = top + height

  return {
    left,
    right,
    top,
    bottom,
    centerX: left + width / 2,
    centerY: top + height / 2,
  }
}

export function collectGuideCandidates(
  items: CanvasItem[],
  excludedIds: Set<string>,
  getItemDims: GetItemDims,
): GuideCandidate[] {
  const candidates: GuideCandidate[] = []

  items.forEach((item) => {
    if (item.is_hidden || item.type === 'group' || excludedIds.has(item.id)) return

    const bounds = getCanvasBounds(item, getItemDims)
    candidates.push(
      {
        axis: 'x',
        value: bounds.left,
        spanStart: bounds.top,
        spanEnd: bounds.bottom,
        sourceItemId: item.id,
        sourceKind: 'item',
        anchor: 'left',
      },
      {
        axis: 'x',
        value: bounds.centerX,
        spanStart: bounds.top,
        spanEnd: bounds.bottom,
        sourceItemId: item.id,
        sourceKind: 'item',
        anchor: 'centerX',
      },
      {
        axis: 'x',
        value: bounds.right,
        spanStart: bounds.top,
        spanEnd: bounds.bottom,
        sourceItemId: item.id,
        sourceKind: 'item',
        anchor: 'right',
      },
      {
        axis: 'y',
        value: bounds.top,
        spanStart: bounds.left,
        spanEnd: bounds.right,
        sourceItemId: item.id,
        sourceKind: 'item',
        anchor: 'top',
      },
      {
        axis: 'y',
        value: bounds.centerY,
        spanStart: bounds.left,
        spanEnd: bounds.right,
        sourceItemId: item.id,
        sourceKind: 'item',
        anchor: 'centerY',
      },
      {
        axis: 'y',
        value: bounds.bottom,
        spanStart: bounds.left,
        spanEnd: bounds.right,
        sourceItemId: item.id,
        sourceKind: 'item',
        anchor: 'bottom',
      },
    )
  })

  return candidates
}

export function filterGuideCandidates(
  candidates: GuideCandidate[],
  excludedIds: Set<string>,
): GuideCandidate[] {
  if (excludedIds.size === 0) return candidates
  return candidates.filter((candidate) => !excludedIds.has(candidate.sourceItemId))
}

export function buildGuideCandidateBuckets(candidates: GuideCandidate[]): GuideCandidateBuckets {
  const compareByValue = (left: GuideCandidate, right: GuideCandidate) => left.value - right.value

  return {
    x: candidates.filter((candidate) => candidate.axis === 'x').sort(compareByValue),
    y: candidates.filter((candidate) => candidate.axis === 'y').sort(compareByValue),
  }
}

export function filterGuideCandidateBuckets(
  candidateBuckets: GuideCandidateBuckets,
  excludedIds: Set<string>,
): GuideCandidateBuckets {
  if (excludedIds.size === 0) return candidateBuckets

  return {
    x: candidateBuckets.x.filter((candidate) => !excludedIds.has(candidate.sourceItemId)),
    y: candidateBuckets.y.filter((candidate) => !excludedIds.has(candidate.sourceItemId)),
  }
}

export function getDraggedBounds(
  movingIds: Set<string>,
  items: CanvasItem[],
  getItemDims: GetItemDims,
): ItemBounds | null {
  let combined: ItemBounds | undefined

  for (const item of items) {
    if (!movingIds.has(item.id)) continue
    const bounds = getCanvasBounds(item, getItemDims)
    if (!combined) {
      combined = bounds
      continue
    }

    combined = {
      left: Math.min(combined.left, bounds.left),
      right: Math.max(combined.right, bounds.right),
      top: Math.min(combined.top, bounds.top),
      bottom: Math.max(combined.bottom, bounds.bottom),
      centerX: 0,
      centerY: 0,
    }
  }

  if (!combined) return null

  return {
    left: combined.left,
    right: combined.right,
    top: combined.top,
    bottom: combined.bottom,
    centerX: combined.left + (combined.right - combined.left) / 2,
    centerY: combined.top + (combined.bottom - combined.top) / 2,
  }
}

function getGuideThresholdPriority(anchor: XAnchor | YAnchor) {
  if (anchor === 'centerX' || anchor === 'centerY') return 0
  return 1
}

function getAxisAnchors(bounds: ItemBounds, axis: 'x' | 'y'): Array<{ anchor: XAnchor | YAnchor; value: number }> {
  if (axis === 'x') {
    return [
      { anchor: 'left', value: bounds.left },
      { anchor: 'centerX', value: bounds.centerX },
      { anchor: 'right', value: bounds.right },
    ]
  }

  return [
    { anchor: 'top', value: bounds.top },
    { anchor: 'centerY', value: bounds.centerY },
    { anchor: 'bottom', value: bounds.bottom },
  ]
}

function findFirstCandidateIndex(candidates: GuideCandidate[], minValue: number) {
  let low = 0
  let high = candidates.length

  while (low < high) {
    const mid = Math.floor((low + high) / 2)
    if (candidates[mid].value < minValue) low = mid + 1
    else high = mid
  }

  return low
}

export function resolveActiveGuides(
  draggedBounds: ItemBounds | null,
  candidates: GuideCandidate[],
  thresholdInCanvas: number,
): ActiveGuide[] {
  return resolveActiveGuidesFromBuckets(
    draggedBounds,
    buildGuideCandidateBuckets(candidates),
    thresholdInCanvas,
  )
}

export function resolveActiveGuidesFromBuckets(
  draggedBounds: ItemBounds | null,
  candidateBuckets: GuideCandidateBuckets,
  thresholdInCanvas: number,
): ActiveGuide[] {
  if (!draggedBounds) return []

  type Match = ActiveGuide & {
    distance: number
    matchedPriority: number
    spanLength: number
  }

  const guides: ActiveGuide[] = []

  for (const axis of ['x', 'y'] as const) {
    const dragAnchors = getAxisAnchors(draggedBounds, axis)
    let bestMatch: Match | undefined
    const axisCandidates = axis === 'x' ? candidateBuckets.x : candidateBuckets.y
    const minAnchorValue = Math.min(...dragAnchors.map((anchor) => anchor.value))
    const maxAnchorValue = Math.max(...dragAnchors.map((anchor) => anchor.value))
    const startIndex = findFirstCandidateIndex(axisCandidates, minAnchorValue - thresholdInCanvas)
    const maxCandidateValue = maxAnchorValue + thresholdInCanvas

    for (let candidateIndex = startIndex; candidateIndex < axisCandidates.length; candidateIndex += 1) {
      const candidate = axisCandidates[candidateIndex]
      if (candidate.value > maxCandidateValue) break

      for (const dragAnchor of dragAnchors) {
        const distance = Math.abs(dragAnchor.value - candidate.value)
        if (distance > thresholdInCanvas) continue

        const lineStart = Math.min(
          axis === 'x' ? draggedBounds.top : draggedBounds.left,
          candidate.spanStart,
        ) - GUIDE_LINE_PADDING
        const lineEnd = Math.max(
          axis === 'x' ? draggedBounds.bottom : draggedBounds.right,
          candidate.spanEnd,
        ) + GUIDE_LINE_PADDING
        const spanLength = lineEnd - lineStart

        const nextMatch: Match = {
          axis,
          value: candidate.value,
          lineStart,
          lineEnd,
          matchedAnchor: dragAnchor.anchor,
          sourceItemId: candidate.sourceItemId,
          distance,
          matchedPriority: getGuideThresholdPriority(dragAnchor.anchor),
          spanLength,
        }

        if (
          !bestMatch ||
          nextMatch.distance < bestMatch.distance ||
          (nextMatch.distance === bestMatch.distance && nextMatch.matchedPriority < bestMatch.matchedPriority) ||
          (
            nextMatch.distance === bestMatch.distance &&
            nextMatch.matchedPriority === bestMatch.matchedPriority &&
            nextMatch.spanLength > bestMatch.spanLength
          )
        ) {
          bestMatch = nextMatch
        }
      }
    }

    if (!bestMatch) continue

    guides.push({
      axis: bestMatch.axis,
      value: bestMatch.value,
      lineStart: bestMatch.lineStart,
      lineEnd: bestMatch.lineEnd,
      matchedAnchor: bestMatch.matchedAnchor,
      sourceItemId: bestMatch.sourceItemId,
    })
  }

  return guides
}

export function getGuideThresholdInCanvas(zoom: number, screenThreshold = 6) {
  if (zoom <= 0) return screenThreshold
  return screenThreshold / (zoom / 100)
}

export function projectGuidesToViewport(
  guides: ActiveGuide[],
  zoom: number,
  offset: { x: number; y: number },
  viewport: { width: number; height: number },
): ProjectedGuide[] {
  const scale = zoom / 100
  const centerX = viewport.width / 2 + offset.x
  const centerY = viewport.height / 2 + offset.y

  return guides.map((guide) => {
    if (guide.axis === 'x') {
      return {
        axis: guide.axis,
        left: centerX + guide.value * scale,
        top: centerY + guide.lineStart * scale,
        width: 1,
        height: Math.max(0, (guide.lineEnd - guide.lineStart) * scale),
        sourceItemId: guide.sourceItemId,
        matchedAnchor: guide.matchedAnchor,
      }
    }

    return {
      axis: guide.axis,
      left: centerX + guide.lineStart * scale,
      top: centerY + guide.value * scale,
      width: Math.max(0, (guide.lineEnd - guide.lineStart) * scale),
      height: 1,
      sourceItemId: guide.sourceItemId,
      matchedAnchor: guide.matchedAnchor,
    }
  })
}
