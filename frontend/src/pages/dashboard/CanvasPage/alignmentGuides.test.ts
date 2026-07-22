import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  buildGuideCandidateBuckets,
  collectGuideCandidates,
  filterGuideCandidates,
  filterGuideCandidateBuckets,
  resolveActiveGuides,
  resolveActiveGuidesFromBuckets,
} from './alignmentGuides'

function createItem(overrides: Partial<CanvasItem> = {}): CanvasItem {
  return {
    id: overrides.id || 'item-1',
    type: overrides.type || 'image',
    url: overrides.url || '',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 100,
    height: overrides.height ?? 80,
    z_index: overrides.z_index ?? 0,
    ...overrides,
  }
}

describe('alignmentGuides', () => {
  it('filters precomputed guide candidates by excluded ids without rebuilding the candidate list', () => {
    const items = [
      createItem({ id: 'item-a', x: 10, y: 20 }),
      createItem({ id: 'item-b', x: 200, y: 220 }),
      createItem({ id: 'item-c', x: 400, y: 420 }),
    ]

    const candidates = collectGuideCandidates(items, new Set(), (item) => ({
      width: item.width || 1,
      height: item.height || 1,
    }))

    const filtered = filterGuideCandidates(candidates, new Set(['item-b']))

    expect(candidates).toHaveLength(18)
    expect(filtered).toHaveLength(12)
    expect(filtered.every((candidate) => candidate.sourceItemId !== 'item-b')).toBe(true)
  })

  it('resolves the same guide matches from axis buckets without re-scanning candidates for the other axis', () => {
    const items = [
      createItem({ id: 'item-a', x: 10, y: 20, width: 100, height: 80 }),
      createItem({ id: 'item-b', x: 200, y: 220, width: 120, height: 90 }),
      createItem({ id: 'item-c', x: 420, y: 200, width: 140, height: 100 }),
    ]

    const candidates = collectGuideCandidates(items, new Set(), (item) => ({
      width: item.width || 1,
      height: item.height || 1,
    }))
    const candidateBuckets = buildGuideCandidateBuckets(candidates)
    const filteredCandidates = filterGuideCandidates(candidates, new Set(['item-c']))
    const filteredBuckets = filterGuideCandidateBuckets(candidateBuckets, new Set(['item-c']))
    const draggedBounds = {
      left: 202,
      right: 322,
      top: 219,
      bottom: 309,
      centerX: 262,
      centerY: 264,
    }

    const fromFlatCandidates = resolveActiveGuides(draggedBounds, filteredCandidates, 4)
    const fromBuckets = resolveActiveGuidesFromBuckets(draggedBounds, filteredBuckets, 4)

    expect(fromBuckets).toEqual(fromFlatCandidates)
    expect(filteredBuckets.x.every((candidate) => candidate.axis === 'x')).toBe(true)
    expect(filteredBuckets.y.every((candidate) => candidate.axis === 'y')).toBe(true)
  })

  it('builds guide candidate buckets sorted by value so neighborhood lookups can binary-search the active threshold window', () => {
    const candidates = [
      { axis: 'x', value: 300, spanStart: 0, spanEnd: 10, sourceItemId: 'x-3', sourceKind: 'item', anchor: 'left' },
      { axis: 'y', value: 120, spanStart: 0, spanEnd: 10, sourceItemId: 'y-2', sourceKind: 'item', anchor: 'top' },
      { axis: 'x', value: 100, spanStart: 0, spanEnd: 10, sourceItemId: 'x-1', sourceKind: 'item', anchor: 'left' },
      { axis: 'y', value: 20, spanStart: 0, spanEnd: 10, sourceItemId: 'y-1', sourceKind: 'item', anchor: 'top' },
      { axis: 'x', value: 200, spanStart: 0, spanEnd: 10, sourceItemId: 'x-2', sourceKind: 'item', anchor: 'left' },
    ] as const

    const buckets = buildGuideCandidateBuckets([...candidates])

    expect(buckets.x.map((candidate) => candidate.value)).toEqual([100, 200, 300])
    expect(buckets.y.map((candidate) => candidate.value)).toEqual([20, 120])
  })
})
