import type { CanvasItem } from '@/api/endpoints/projects'

type CanvasPreviewRect = {
  x: number
  y: number
  width?: number
  height?: number
}

type CanvasPreviewItem = CanvasItem & CanvasPreviewRect

export type CanvasInteractionPreviewSnapshot = {
  items: CanvasItem[]
  guideBounds?: unknown
}

export type CanvasInteractionPreviewListener = (
  items: CanvasItem[] | null,
  options?: { restore?: boolean },
) => void

type StyleSnapshot = {
  transform: string
  willChange: string
  width: string
  height: string
}

type ScreenPreviewSnapshot = StyleSnapshot & {
  transformBase: string
}

function getItemElement(id: string) {
  if (typeof document === 'undefined') return null
  return document.getElementById(`item-${id}`) as HTMLElement | null
}

function getGroupFillElement(id: string) {
  if (typeof document === 'undefined') return null
  return document.getElementById(`group-fill-${id}`) as HTMLElement | null
}

function getGroupHandlesElement(id: string) {
  if (typeof document === 'undefined') return null
  return document.getElementById(`group-handles-${id}`) as HTMLElement | null
}

function getGroupLabelElement(id: string) {
  if (typeof document === 'undefined') return null
  return document.getElementById(`group-label-${id}`) as HTMLElement | null
}

function getScreenPreviewElement(id: string) {
  if (typeof document === 'undefined') return null
  return document.getElementById(`canvas-screen-preview-${id}`) as HTMLElement | null
}

function getMultiSelectionPreviewElement() {
  if (typeof document === 'undefined') return null
  return document.getElementById('canvas-screen-preview-selection') as HTMLElement | null
}

function getPreviewSizeElement(element: HTMLElement) {
  if (element.dataset.canvasPreviewResizeChild === 'false') return null
  return element.firstElementChild instanceof HTMLElement
    ? element.firstElementChild
    : null
}

function captureStyleSnapshot(
  snapshots: Map<HTMLElement, StyleSnapshot>,
  element: HTMLElement | null,
) {
  if (!element || snapshots.has(element)) return
  snapshots.set(element, {
    transform: element.style.transform,
    willChange: element.style.willChange,
    width: element.style.width,
    height: element.style.height,
  })
}

function applyElementRect(
  snapshots: Map<HTMLElement, StyleSnapshot>,
  element: HTMLElement | null,
  item: CanvasPreviewItem,
  original: CanvasItem | null,
) {
  if (!element) return
  const originalX = original?.x ?? item.x
  const originalY = original?.y ?? item.y
  const translateX = item.x - originalX
  const translateY = item.y - originalY
  const hasSizeChange = item.width !== undefined || item.height !== undefined

  captureStyleSnapshot(snapshots, element)
  element.style.transform = translateX || translateY
    ? `translate3d(${translateX}px, ${translateY}px, 0)`
    : ''
  element.style.willChange = translateX || translateY || hasSizeChange ? 'transform, width, height' : ''

  if (item.width !== undefined) {
    element.style.width = `${Math.max(1, item.width)}px`
  }
  if (item.height !== undefined) {
    element.style.height = `${Math.max(1, item.height)}px`
  }

  if (hasSizeChange) {
    const sizeElement = getPreviewSizeElement(element)
    captureStyleSnapshot(snapshots, sizeElement)
    if (sizeElement && item.width !== undefined) {
      sizeElement.style.width = `${Math.max(1, item.width)}px`
    }
    if (sizeElement && item.height !== undefined) {
      sizeElement.style.height = `${Math.max(1, item.height)}px`
    }
  }
}

function resetElement(
  snapshots: Map<HTMLElement, StyleSnapshot>,
  element: HTMLElement | null,
) {
  if (!element) return
  const snapshot = snapshots.get(element)
  if (!snapshot) return
  element.style.transform = snapshot.transform
  element.style.willChange = snapshot.willChange
  element.style.width = snapshot.width
  element.style.height = snapshot.height
  snapshots.delete(element)
}

function captureScreenSnapshot(
  snapshots: Map<HTMLElement, ScreenPreviewSnapshot>,
  element: HTMLElement | null,
) {
  if (!element || snapshots.has(element)) return
  snapshots.set(element, {
    transform: element.style.transform,
    transformBase: element.style.transform,
    willChange: element.style.willChange,
    width: element.style.width,
    height: element.style.height,
  })
}

function applyScreenElementTranslation(
  snapshots: Map<HTMLElement, ScreenPreviewSnapshot>,
  element: HTMLElement | null,
  item: CanvasPreviewItem,
  original: CanvasItem | null,
) {
  if (!element) return
  const originalX = original?.x ?? item.x
  const originalY = original?.y ?? item.y
  const scale = Number(element.dataset.canvasPreviewScale || 1) || 1
  const translateX = (item.x - originalX) * scale
  const translateY = (item.y - originalY) * scale

  captureScreenSnapshot(snapshots, element)
  const snapshot = snapshots.get(element)
  const baseTransform = snapshot?.transformBase || ''
  element.style.transform = translateX || translateY
    ? `${baseTransform} translate3d(${translateX}px, ${translateY}px, 0)`.trim()
    : baseTransform
  element.style.willChange = translateX || translateY ? 'transform' : ''
}

function resetScreenElement(
  snapshots: Map<HTMLElement, ScreenPreviewSnapshot>,
  element: HTMLElement | null,
) {
  if (!element) return
  const snapshot = snapshots.get(element)
  if (!snapshot) return
  element.style.transform = snapshot.transform
  element.style.willChange = snapshot.willChange
  element.style.width = snapshot.width
  element.style.height = snapshot.height
  snapshots.delete(element)
}

function getPreviewBounds(
  items: CanvasPreviewItem[],
  resolveItem: (item: CanvasPreviewItem) => CanvasPreviewItem | CanvasItem | null,
): CanvasPreviewRect | null {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  let hasItems = false

  items.forEach((item) => {
    const resolved = resolveItem(item)
    if (!resolved) return
    const width = resolved.width ?? item.width ?? 0
    const height = resolved.height ?? item.height ?? 0
    minX = Math.min(minX, resolved.x)
    minY = Math.min(minY, resolved.y)
    maxX = Math.max(maxX, resolved.x + width)
    maxY = Math.max(maxY, resolved.y + height)
    hasItems = true
  })

  if (!hasItems) return null

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  }
}

function applyMultiSelectionElementTranslation(
  snapshots: Map<HTMLElement, ScreenPreviewSnapshot>,
  element: HTMLElement | null,
  items: CanvasPreviewItem[],
  originalItems: Map<string, CanvasItem>,
) {
  if (!element || items.length <= 1) {
    resetScreenElement(snapshots, element)
    return
  }

  const nextBounds = getPreviewBounds(items, (item) => item)
  const originalBounds = getPreviewBounds(items, (item) => originalItems.get(item.id) ?? item)
  if (!nextBounds || !originalBounds) {
    resetScreenElement(snapshots, element)
    return
  }

  applyScreenElementTranslation(snapshots, element, nextBounds as CanvasPreviewItem, originalBounds as CanvasItem)
}

export class CanvasInteractionPreviewController {
  private originalItems = new Map<string, CanvasItem>()
  private previewIds = new Set<string>()
  private latestItems: CanvasItem[] | null = null
  private styleSnapshots = new Map<HTMLElement, StyleSnapshot>()
  private screenStyleSnapshots = new Map<HTMLElement, ScreenPreviewSnapshot>()
  private listeners = new Set<CanvasInteractionPreviewListener>()

  begin(originalItems: CanvasItem[]) {
    this.originalItems = new Map(originalItems.map((item) => [item.id, item]))
    this.latestItems = null
  }

  apply(items: CanvasItem[], originalItems?: CanvasItem[]) {
    if (originalItems) {
      this.originalItems = new Map(originalItems.map((item) => [item.id, item]))
    }

    const nextIds = new Set(items.map((item) => item.id))
    this.previewIds.forEach((id) => {
      if (nextIds.has(id)) return
      this.resetPreviewElement(getItemElement(id))
      this.resetPreviewElement(getGroupFillElement(id))
      this.resetPreviewElement(getGroupHandlesElement(id))
      this.resetPreviewElement(getGroupLabelElement(id))
      resetScreenElement(this.screenStyleSnapshots, getScreenPreviewElement(id))
    })

    items.forEach((item) => {
      const original = this.originalItems.get(item.id) ?? null
      applyElementRect(this.styleSnapshots, getItemElement(item.id), item, original)
      if (item.type === 'group') {
        applyElementRect(this.styleSnapshots, getGroupFillElement(item.id), item, original)
        applyElementRect(this.styleSnapshots, getGroupHandlesElement(item.id), item, original)
        applyElementRect(this.styleSnapshots, getGroupLabelElement(item.id), item, original)
      }
      applyScreenElementTranslation(this.screenStyleSnapshots, getScreenPreviewElement(item.id), item, original)
    })
    applyMultiSelectionElementTranslation(
      this.screenStyleSnapshots,
      getMultiSelectionPreviewElement(),
      items,
      this.originalItems,
    )

    this.previewIds = nextIds
    this.latestItems = items
    this.notify(items)
  }

  getLatestItems() {
    return this.latestItems
  }

  subscribe(listener: CanvasInteractionPreviewListener) {
    this.listeners.add(listener)
    if (this.latestItems) {
      listener(this.latestItems)
    }
    return () => {
      this.listeners.delete(listener)
    }
  }

  clear(options: { notify?: boolean; restore?: boolean } = {}) {
    const notify = options.notify ?? true
    const restore = options.restore ?? true
    this.previewIds.forEach((id) => {
      this.resetPreviewElement(getItemElement(id))
      this.resetPreviewElement(getGroupFillElement(id))
      this.resetPreviewElement(getGroupHandlesElement(id))
      this.resetPreviewElement(getGroupLabelElement(id))
      resetScreenElement(this.screenStyleSnapshots, getScreenPreviewElement(id))
    })
    resetScreenElement(this.screenStyleSnapshots, getMultiSelectionPreviewElement())
    Array.from(this.styleSnapshots.keys()).forEach((element) => resetElement(this.styleSnapshots, element))
    Array.from(this.screenStyleSnapshots.keys()).forEach((element) => resetScreenElement(this.screenStyleSnapshots, element))
    this.previewIds.clear()
    this.originalItems.clear()
    this.latestItems = null
    if (notify) {
      this.notify(null, { restore })
    }
  }

  private resetPreviewElement(element: HTMLElement | null) {
    resetElement(this.styleSnapshots, element)
    resetElement(this.styleSnapshots, element ? getPreviewSizeElement(element) : null)
  }

  private notify(items: CanvasItem[] | null, options?: { restore?: boolean }) {
    this.listeners.forEach((listener) => listener(items, options))
  }
}

export function createCanvasInteractionPreviewController() {
  return new CanvasInteractionPreviewController()
}
