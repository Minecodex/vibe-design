export interface LayoutItem {
  id?: string
  x: number
  y: number
  width?: number
  height?: number
  type?: string
  is_hidden?: boolean
}

export interface LayoutRect {
  x: number
  y: number
  width: number
  height: number
}

/**
 * Find an empty position near `(centerX, centerY)` for an item of size `w × h`.
 * Uses spiral search outward from center, then falls back to the right edge.
 */
export function findEmptyPosition(
  centerX: number,
  centerY: number,
  w: number,
  h: number,
  existingItems: LayoutItem[],
): { x: number; y: number } {
  const GAP = 50

  const hasOverlap = (x: number, y: number) => {
    for (const it of existingItems) {
      if (it.type === 'group') continue
      const iw = it.width || 1024
      const ih = it.height || 1024
      if (
        x < it.x + iw + GAP &&
        x + w + GAP > it.x &&
        y < it.y + ih + GAP &&
        y + h + GAP > it.y
      ) {
        return true
      }
    }
    return false
  }

  const testX = Math.round(centerX - w / 2)
  const testY = Math.round(centerY - h / 2)
  if (!hasOverlap(testX, testY)) return { x: testX, y: testY }

  for (let radius = 1; radius <= 10; radius++) {
    const step = (w + GAP) * radius
    const positions = [
      { x: testX + step, y: testY },
      { x: testX - step, y: testY },
      { x: testX, y: testY + step },
      { x: testX, y: testY - step },
      { x: testX + step, y: testY + step },
      { x: testX - step, y: testY + step },
      { x: testX + step, y: testY - step },
      { x: testX - step, y: testY - step },
    ]
    for (const pos of positions) {
      if (!hasOverlap(pos.x, pos.y)) return pos
    }
  }

  let maxRight = 0
  for (const it of existingItems) {
    if (it.type === 'group') continue
    maxRight = Math.max(maxRight, it.x + (it.width || 1024))
  }
  return { x: maxRight + GAP, y: testY }
}

export function findEmptyRectPosition(
  preferred: LayoutRect,
  existingItems: LayoutItem[],
  options: {
    gap?: number
    excludeIds?: Iterable<string>
  } = {},
): { x: number; y: number } {
  const gap = options.gap ?? 50
  const excludeIds = new Set(options.excludeIds ?? [])
  const obstacles = existingItems.filter((item) => (
    item.type !== 'group'
    && !item.is_hidden
    && !(item.id && excludeIds.has(item.id))
  ))

  const hasOverlap = (x: number, y: number) => obstacles.some((item) => (
    rectsOverlap(
      { ...preferred, x, y },
      {
        x: item.x,
        y: item.y,
        width: item.width || 1024,
        height: item.height || 1024,
      },
      gap,
    )
  ))

  const preferredX = Math.round(preferred.x)
  const preferredY = Math.round(preferred.y)
  if (!hasOverlap(preferredX, preferredY)) {
    return { x: preferredX, y: preferredY }
  }

  let rightScanX = preferredX
  const y = preferredY
  const horizontallyRelevant = obstacles
    .filter((item) => rangesOverlap(
      y,
      y + preferred.height,
      item.y - gap,
      item.y + (item.height || 1024) + gap,
    ))
    .sort((a, b) => a.x - b.x)

  for (const item of horizontallyRelevant) {
    if (!rectsOverlap(
      { ...preferred, x: rightScanX, y },
      {
        x: item.x,
        y: item.y,
        width: item.width || 1024,
        height: item.height || 1024,
      },
      gap,
    )) {
      continue
    }
    rightScanX = Math.max(rightScanX, Math.round(item.x + (item.width || 1024) + gap))
  }
  if (!hasOverlap(rightScanX, y)) {
    return { x: rightScanX, y }
  }

  const stepX = preferred.width + gap
  const stepY = preferred.height + gap
  for (let radius = 1; radius <= 12; radius++) {
    const positions = [
      { x: preferredX + stepX * radius, y: preferredY },
      { x: preferredX - stepX * radius, y: preferredY },
      { x: preferredX, y: preferredY + stepY * radius },
      { x: preferredX, y: preferredY - stepY * radius },
      { x: preferredX + stepX * radius, y: preferredY + stepY * radius },
      { x: preferredX - stepX * radius, y: preferredY + stepY * radius },
      { x: preferredX + stepX * radius, y: preferredY - stepY * radius },
      { x: preferredX - stepX * radius, y: preferredY - stepY * radius },
    ]

    for (const position of positions) {
      if (!hasOverlap(position.x, position.y)) {
        return position
      }
    }
  }

  const maxRight = obstacles.reduce(
    (right, item) => Math.max(right, item.x + (item.width || 1024)),
    preferredX,
  )
  return { x: Math.round(maxRight + gap), y: preferredY }
}

function rectsOverlap(a: LayoutRect, b: LayoutRect, gap: number): boolean {
  return (
    a.x < b.x + b.width + gap
    && a.x + a.width + gap > b.x
    && a.y < b.y + b.height + gap
    && a.y + a.height + gap > b.y
  )
}

function rangesOverlap(aStart: number, aEnd: number, bStart: number, bEnd: number): boolean {
  return aStart < bEnd && aEnd > bStart
}
