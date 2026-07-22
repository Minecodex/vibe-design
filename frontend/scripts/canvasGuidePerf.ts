import { performance } from 'node:perf_hooks'

import type { CanvasItem } from '../src/api/endpoints/projects'

import {
  buildGuideCandidateBuckets,
  collectGuideCandidates,
  filterGuideCandidateBuckets,
  getCanvasBounds,
  getGuideThresholdInCanvas,
  resolveActiveGuidesFromBuckets,
  type ActiveGuide,
  type GuideCandidate,
  type GuideCandidateBuckets,
  type ItemBounds,
} from '../src/pages/dashboard/CanvasPage/alignmentGuides'
import { applyDraggedCanvasItemsPreview } from '../src/pages/dashboard/CanvasPage/dragMove'

type BenchmarkScenario = {
  totalItems: number
  movingItems: number
  dragFrames: number
}

const SCENARIOS: BenchmarkScenario[] = [
  { totalItems: 500, movingItems: 1, dragFrames: 240 },
  { totalItems: 1000, movingItems: 1, dragFrames: 240 },
  { totalItems: 2000, movingItems: 1, dragFrames: 240 },
]

const GRID_COLUMNS = 20
const ZOOM = 100

function createItems(totalItems: number): CanvasItem[] {
  return Array.from({ length: totalItems }, (_, index) => {
    const row = Math.floor(index / GRID_COLUMNS)
    const column = index % GRID_COLUMNS
    return {
      id: `item-${index}`,
      type: index % 9 === 0 ? 'text' : 'image',
      url: `/asset-${index}.png`,
      x: column * 220,
      y: row * 180,
      width: 160 + (index % 3) * 20,
      height: 110 + (index % 4) * 10,
      z_index: index,
    }
  })
}

function getItemDims(item: CanvasItem) {
  return {
    width: item.width || 1,
    height: item.height || 1,
  }
}

function resolveActiveGuidesFlat(
  draggedBounds: ItemBounds | null,
  candidateBuckets: GuideCandidateBuckets,
  thresholdInCanvas: number,
): ActiveGuide[] {
  if (!draggedBounds) return []

  const allCandidates = [...candidateBuckets.x, ...candidateBuckets.y]
  const guides: ActiveGuide[] = []

  for (const axis of ['x', 'y'] as const) {
    const dragAnchors = axis === 'x'
      ? [
        { anchor: 'left' as const, value: draggedBounds.left },
        { anchor: 'centerX' as const, value: draggedBounds.centerX },
        { anchor: 'right' as const, value: draggedBounds.right },
      ]
      : [
        { anchor: 'top' as const, value: draggedBounds.top },
        { anchor: 'centerY' as const, value: draggedBounds.centerY },
        { anchor: 'bottom' as const, value: draggedBounds.bottom },
      ]

    let bestMatch:
      | (ActiveGuide & {
        distance: number
        matchedPriority: number
        spanLength: number
      })
      | undefined

    for (const candidate of allCandidates) {
      if (candidate.axis !== axis) continue

      for (const dragAnchor of dragAnchors) {
        const distance = Math.abs(dragAnchor.value - candidate.value)
        if (distance > thresholdInCanvas) continue

        const lineStart = Math.min(
          axis === 'x' ? draggedBounds.top : draggedBounds.left,
          candidate.spanStart,
        ) - 12
        const lineEnd = Math.max(
          axis === 'x' ? draggedBounds.bottom : draggedBounds.right,
          candidate.spanEnd,
        ) + 12
        const spanLength = lineEnd - lineStart
        const matchedPriority = dragAnchor.anchor === 'centerX' || dragAnchor.anchor === 'centerY' ? 0 : 1

        const nextMatch = {
          axis,
          value: candidate.value,
          lineStart,
          lineEnd,
          matchedAnchor: dragAnchor.anchor,
          sourceItemId: candidate.sourceItemId,
          distance,
          matchedPriority,
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

    if (bestMatch) {
      guides.push({
        axis: bestMatch.axis,
        value: bestMatch.value,
        lineStart: bestMatch.lineStart,
        lineEnd: bestMatch.lineEnd,
        matchedAnchor: bestMatch.matchedAnchor,
        sourceItemId: bestMatch.sourceItemId,
      })
    }
  }

  return guides
}

function benchmarkScenario(scenario: BenchmarkScenario) {
  const items = createItems(scenario.totalItems)
  const movingIds = new Set(items.slice(0, scenario.movingItems).map((item) => item.id))
  const originals = Object.fromEntries(
    items
      .slice(0, scenario.movingItems)
      .map((item) => [item.id, { x: item.x, y: item.y }]),
  )
  const selectedItems = items.slice(0, scenario.movingItems).map((item) => item.id)
  const groupHitCandidates = items.filter((item) => item.type === 'group')
  const baseCandidates = collectGuideCandidates(items, new Set(), getItemDims)
  const baseBuckets = buildGuideCandidateBuckets(baseCandidates)
  const filteredBuckets = filterGuideCandidateBuckets(baseBuckets, movingIds)
  const thresholdInCanvas = getGuideThresholdInCanvas(ZOOM)

  const previewDurations: number[] = []
  const optimizedGuideDurations: number[] = []
  const flatGuideDurations: number[] = []

  for (let frame = 0; frame < scenario.dragFrames; frame += 1) {
    const deltaX = frame
    const deltaY = Math.floor(frame / 3)

    const previewStart = performance.now()
    const { draggedBounds } = applyDraggedCanvasItemsPreview({
      items,
      draggedItemId: selectedItems[0],
      deltaX,
      deltaY,
      originals,
      selectedItems,
      movingItemIds: movingIds,
      groupHitCandidates,
      getItemDims,
    })
    previewDurations.push(performance.now() - previewStart)

    const optimizedStart = performance.now()
    resolveActiveGuidesFromBuckets(draggedBounds, filteredBuckets, thresholdInCanvas)
    optimizedGuideDurations.push(performance.now() - optimizedStart)

    const flatStart = performance.now()
    resolveActiveGuidesFlat(draggedBounds, filteredBuckets, thresholdInCanvas)
    flatGuideDurations.push(performance.now() - flatStart)
  }

  return {
    scenario,
    previewAvgMs: average(previewDurations),
    optimizedGuideAvgMs: average(optimizedGuideDurations),
    flatGuideAvgMs: average(flatGuideDurations),
    guideSpeedup: average(flatGuideDurations) / Math.max(average(optimizedGuideDurations), 0.0001),
  }
}

function average(values: number[]) {
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

for (const scenario of SCENARIOS) {
  const result = benchmarkScenario(scenario)
  console.log(JSON.stringify(result))
}
