export type CanvasSpatialRect = {
  left: number
  right: number
  top: number
  bottom: number
}

export type CanvasSpatialPoint = {
  x: number
  y: number
}

export type CanvasSpatialIndexedItem<T> = {
  id: string
  bounds: CanvasSpatialRect
  value: T
  zIndex?: number
}

type CanvasSpatialIndexEntry<T> = CanvasSpatialIndexedItem<T> & {
  order: number
}

type CanvasSpatialIndexOptions = {
  cellSize?: number
  maxCellsPerItem?: number
  maxQueryCells?: number
}

type CanvasSpatialHitTestOptions<T> = {
  predicate?: (value: T) => boolean
  containsPoint?: (value: T, point: CanvasSpatialPoint) => boolean
}

const DEFAULT_CELL_SIZE = 768
const DEFAULT_MAX_CELLS_PER_ITEM = 256
const DEFAULT_MAX_QUERY_CELLS = 4096

function normalizeRect(rect: CanvasSpatialRect): CanvasSpatialRect {
  return {
    left: Math.min(rect.left, rect.right),
    right: Math.max(rect.left, rect.right),
    top: Math.min(rect.top, rect.bottom),
    bottom: Math.max(rect.top, rect.bottom),
  }
}

function intersects(a: CanvasSpatialRect, b: CanvasSpatialRect) {
  return !(a.left > b.right || a.right < b.left || a.top > b.bottom || a.bottom < b.top)
}

function containsPoint(rect: CanvasSpatialRect, point: CanvasSpatialPoint) {
  return point.x >= rect.left
    && point.x <= rect.right
    && point.y >= rect.top
    && point.y <= rect.bottom
}

function hasFiniteRect(rect: CanvasSpatialRect) {
  return Number.isFinite(rect.left)
    && Number.isFinite(rect.right)
    && Number.isFinite(rect.top)
    && Number.isFinite(rect.bottom)
}

export function rectFromBounds(bounds: { x: number; y: number; width: number; height: number }): CanvasSpatialRect {
  return normalizeRect({
    left: bounds.x,
    right: bounds.x + Math.max(0, bounds.width),
    top: bounds.y,
    bottom: bounds.y + Math.max(0, bounds.height),
  })
}

export class CanvasSpatialIndex<T> {
  private readonly entries: CanvasSpatialIndexEntry<T>[]
  private readonly cells = new Map<string, CanvasSpatialIndexEntry<T>[]>()
  private readonly largeEntries: CanvasSpatialIndexEntry<T>[] = []
  private readonly cellSize: number
  private readonly maxCellsPerItem: number
  private readonly maxQueryCells: number

  constructor(items: CanvasSpatialIndexedItem<T>[], options: CanvasSpatialIndexOptions = {}) {
    this.cellSize = Math.max(1, options.cellSize ?? DEFAULT_CELL_SIZE)
    this.maxCellsPerItem = Math.max(1, options.maxCellsPerItem ?? DEFAULT_MAX_CELLS_PER_ITEM)
    this.maxQueryCells = Math.max(1, options.maxQueryCells ?? DEFAULT_MAX_QUERY_CELLS)
    this.entries = items.map((item, order) => ({
      ...item,
      bounds: normalizeRect(item.bounds),
      zIndex: item.zIndex ?? 0,
      order,
    }))
    this.entries.forEach((entry) => this.insert(entry))
  }

  query(rect: CanvasSpatialRect): T[] {
    return this.queryEntries(rect).map((entry) => entry.value)
  }

  queryEntries(rect: CanvasSpatialRect): CanvasSpatialIndexEntry<T>[] {
    const queryRect = normalizeRect(rect)
    if (!hasFiniteRect(queryRect)) {
      return this.entries.filter((entry) => intersects(entry.bounds, queryRect))
    }

    const range = this.getCellRange(queryRect)
    if (!range || range.cellCount > this.maxQueryCells) {
      return this.entries.filter((entry) => intersects(entry.bounds, queryRect))
    }

    const result = new Map<string, CanvasSpatialIndexEntry<T>>()
    this.largeEntries.forEach((entry) => {
      if (intersects(entry.bounds, queryRect)) {
        result.set(entry.id, entry)
      }
    })

    for (let x = range.minX; x <= range.maxX; x += 1) {
      for (let y = range.minY; y <= range.maxY; y += 1) {
        const entries = this.cells.get(this.getCellKey(x, y))
        if (!entries) continue
        entries.forEach((entry) => {
          if (intersects(entry.bounds, queryRect)) {
            result.set(entry.id, entry)
          }
        })
      }
    }

    return Array.from(result.values()).sort((a, b) => (a.zIndex ?? 0) - (b.zIndex ?? 0) || a.order - b.order)
  }

  hitTest(point: CanvasSpatialPoint, options: CanvasSpatialHitTestOptions<T> = {}): T | null {
    const candidates = this.queryEntries({
      left: point.x,
      right: point.x,
      top: point.y,
      bottom: point.y,
    }).sort((a, b) => (b.zIndex ?? 0) - (a.zIndex ?? 0) || b.order - a.order)

    for (const entry of candidates) {
      if (!containsPoint(entry.bounds, point)) continue
      if (options.predicate && !options.predicate(entry.value)) continue
      if (options.containsPoint && !options.containsPoint(entry.value, point)) continue
      return entry.value
    }

    return null
  }

  private insert(entry: CanvasSpatialIndexEntry<T>) {
    if (!hasFiniteRect(entry.bounds)) {
      this.largeEntries.push(entry)
      return
    }

    const range = this.getCellRange(entry.bounds)
    if (!range || range.cellCount > this.maxCellsPerItem) {
      this.largeEntries.push(entry)
      return
    }

    for (let x = range.minX; x <= range.maxX; x += 1) {
      for (let y = range.minY; y <= range.maxY; y += 1) {
        const key = this.getCellKey(x, y)
        const cell = this.cells.get(key)
        if (cell) {
          cell.push(entry)
        } else {
          this.cells.set(key, [entry])
        }
      }
    }
  }

  private getCellRange(rect: CanvasSpatialRect) {
    if (!hasFiniteRect(rect)) return null

    const minX = Math.floor(rect.left / this.cellSize)
    const maxX = Math.floor(rect.right / this.cellSize)
    const minY = Math.floor(rect.top / this.cellSize)
    const maxY = Math.floor(rect.bottom / this.cellSize)
    const cellCount = Math.max(0, maxX - minX + 1) * Math.max(0, maxY - minY + 1)

    return {
      minX,
      maxX,
      minY,
      maxY,
      cellCount,
    }
  }

  private getCellKey(x: number, y: number) {
    return `${x}:${y}`
  }
}

export function createCanvasSpatialIndex<T>(
  items: CanvasSpatialIndexedItem<T>[],
  options?: CanvasSpatialIndexOptions,
) {
  return new CanvasSpatialIndex(items, options)
}
