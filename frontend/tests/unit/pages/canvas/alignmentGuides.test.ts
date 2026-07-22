import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'
import {
  collectGuideCandidates,
  getCanvasBounds,
  getDraggedBounds,
  getGuideThresholdInCanvas,
  resolveActiveGuides,
} from '@/pages/dashboard/CanvasPage/alignmentGuides'

const defaultDimsByType: Record<CanvasItem['type'], { width: number; height: number }> = {
  text: { width: 160, height: 96 },
  image: { width: 100, height: 80 },
  video: { width: 120, height: 90 },
  image_generator: { width: 100, height: 80 },
  video_generator: { width: 120, height: 90 },
  group: { width: 240, height: 180 },
  brush_path: { width: 120, height: 120 },
}

const getItemDims = (item: CanvasItem) => ({
  width: item.width ?? defaultDimsByType[item.type].width,
  height: item.height ?? defaultDimsByType[item.type].height,
})

function makeItem(overrides: Partial<CanvasItem> & Pick<CanvasItem, 'id' | 'type' | 'x' | 'y'>): CanvasItem {
  return {
    url: '',
    ...overrides,
  }
}

describe('alignment guide geometry', () => {
  it('builds bounds using rendered dimensions', () => {
    const bounds = getCanvasBounds(
      makeItem({ id: 'image-1', type: 'image', x: 40, y: 60, width: 90, height: 50 }),
      getItemDims,
    )

    expect(bounds).toEqual({
      left: 40,
      right: 130,
      top: 60,
      bottom: 110,
      centerX: 85,
      centerY: 85,
    })
  })

  it('collects candidate guides from visible non-group items only', () => {
    const items: CanvasItem[] = [
      makeItem({ id: 'group-1', type: 'group', x: 0, y: 0, width: 300, height: 200 }),
      makeItem({ id: 'child-1', type: 'image', x: 20, y: 30, groupId: 'group-1' }),
      makeItem({ id: 'child-2', type: 'video', x: 180, y: 40, groupId: 'group-1' }),
      makeItem({ id: 'external', type: 'image', x: 400, y: 80 }),
      makeItem({ id: 'hidden', type: 'image', x: 600, y: 120, is_hidden: true }),
    ]

    const candidates = collectGuideCandidates(items, new Set(['group-1', 'child-1', 'child-2']), getItemDims)

    expect(candidates).toHaveLength(6)
    expect(new Set(candidates.map((candidate) => candidate.sourceItemId))).toEqual(new Set(['external']))
    expect(candidates.every((candidate) => candidate.sourceKind !== 'group')).toBe(true)
  })

  it('returns a combined dragged bounds box for multi-selection drags', () => {
    const items: CanvasItem[] = [
      makeItem({ id: 'a', type: 'image', x: 10, y: 20, width: 80, height: 40 }),
      makeItem({ id: 'b', type: 'video', x: 160, y: 100, width: 120, height: 90 }),
      makeItem({ id: 'c', type: 'image', x: 320, y: 40 }),
    ]

    const bounds = getDraggedBounds(new Set(['a', 'b']), items, getItemDims)

    expect(bounds).toEqual({
      left: 10,
      right: 280,
      top: 20,
      bottom: 190,
      centerX: 145,
      centerY: 105,
    })
  })

  it('resolves a vertical guide when dragged item left edge aligns with another item', () => {
    const dragged = getCanvasBounds(
      makeItem({ id: 'dragged', type: 'image', x: 102, y: 50, width: 80, height: 40 }),
      getItemDims,
    )
    const candidates = collectGuideCandidates(
      [makeItem({ id: 'target', type: 'image', x: 100, y: 200, width: 90, height: 50 })],
      new Set(),
      getItemDims,
    )

    const guides = resolveActiveGuides(dragged, candidates, 3)

    expect(guides).toHaveLength(1)
    expect(guides[0]).toMatchObject({
      axis: 'x',
      value: 100,
      matchedAnchor: 'left',
      sourceItemId: 'target',
      lineStart: 38,
      lineEnd: 262,
    })
  })

  it('prefers center-line matches when edge and center candidates are equally close', () => {
    const dragged = getCanvasBounds(
      makeItem({ id: 'dragged', type: 'image', x: 101, y: 50, width: 100, height: 40 }),
      getItemDims,
    )
    const candidates = collectGuideCandidates(
      [makeItem({ id: 'target', type: 'image', x: 100, y: 120, width: 100, height: 50 })],
      new Set(),
      getItemDims,
    )

    const guides = resolveActiveGuides(dragged, candidates, 2)

    expect(guides).toHaveLength(1)
    expect(guides[0]).toMatchObject({
      axis: 'x',
      value: 150,
      matchedAnchor: 'centerX',
      sourceItemId: 'target',
    })
  })

  it('returns no guides when all candidates fall outside the threshold', () => {
    const dragged = getCanvasBounds(
      makeItem({ id: 'dragged', type: 'image', x: 10, y: 20, width: 80, height: 40 }),
      getItemDims,
    )
    const candidates = collectGuideCandidates(
      [makeItem({ id: 'target', type: 'image', x: 70, y: 200, width: 90, height: 50 })],
      new Set(),
      getItemDims,
    )

    expect(resolveActiveGuides(dragged, candidates, 5)).toEqual([])
  })

  it('converts screen thresholds into canvas space based on zoom', () => {
    expect(getGuideThresholdInCanvas(50)).toBe(12)
    expect(getGuideThresholdInCanvas(100)).toBe(6)
    expect(getGuideThresholdInCanvas(200)).toBe(3)
  })
})
