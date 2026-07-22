import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'

import {
  getCanvasViewportCullBounds,
  isCanvasItemVisibleInViewport,
} from './canvasScene'
import {
  createCanvasSpatialIndex,
  rectFromBounds,
} from './canvasSpatialIndex'

export type CanvasRenderKind =
  | 'image'
  | 'video-poster'
  | 'group'
  | 'text'
  | 'brush-path'
  | 'generator-card'
  | 'dom-only'

export type CanvasOverlayKind =
  | 'none'
  | 'interaction-shell'
  | 'full-dom'

export type CanvasRenderNode = {
  id: string
  item: CanvasItem
  type: CanvasItem['type']
  renderKind: CanvasRenderKind
  overlayKind: CanvasOverlayKind
  bounds: { x: number; y: number; width: number; height: number }
  zIndex: number
  hidden: boolean
  locked: boolean
  selected: boolean
  visible: boolean
  webglRenderable: boolean
}

export type CanvasRenderSnapshot = {
  nodes: CanvasRenderNode[]
  visibleNodes: CanvasRenderNode[]
  webglNodes: CanvasRenderNode[]
  overlayNodes: CanvasRenderNode[]
  queryVisibleNodes: (bounds: { left: number; right: number; top: number; bottom: number }) => CanvasRenderNode[]
  hitTest: (point: { x: number; y: number }) => CanvasRenderNode | null
}

export type CanvasRenderModelArgs = {
  canvasItems: CanvasItem[]
  selectedItems: string[]
  marks?: CanvasMark[]
  cropState?: { itemId?: string | null } | null
  textEditingItemId?: string | null
  textRedrawExtractingItemIds?: Set<string> | null
  imageDetailItemId?: string | null
  imageAnchoredImageDraft?: { sourceImageItemId?: string | null } | null
  imageAnchoredVideoDraft?: { sourceImageItemId?: string | null } | null
  hoverDomItemId?: string | null
  zoom: number
  offset: { x: number; y: number }
  viewport: { width: number; height: number }
  getItemDims: (item: CanvasItem) => { width: number; height: number }
}

function hasAttachedMarks(item: CanvasItem, marks: CanvasMark[] = []) {
  return marks.some((mark) => mark.imageItemId === item.id)
}

function hasActiveAnchoredDraft(item: CanvasItem, args: CanvasRenderModelArgs) {
  return args.imageAnchoredImageDraft?.sourceImageItemId === item.id
    || args.imageAnchoredVideoDraft?.sourceImageItemId === item.id
}

function isMediaVisualItem(item: CanvasItem) {
  return item.type === 'image'
    || item.type === 'video'
    || item.type === 'image_generator'
    || item.type === 'video_generator'
}

function getRenderKind(item: CanvasItem): CanvasRenderKind {
  if (item.type === 'image') return 'image'
  if (item.type === 'video') return 'video-poster'
  if (item.type === 'group') return 'group'
  if (item.type === 'text') return 'text'
  if (item.type === 'brush_path') return 'brush-path'
  if (item.type === 'image_generator' || item.type === 'video_generator') {
    return item.url ? (item.type === 'image_generator' ? 'image' : 'video-poster') : 'generator-card'
  }
  return 'dom-only'
}

function getOverlayKind(item: CanvasItem, args: CanvasRenderModelArgs, selected: boolean): CanvasOverlayKind {
  if (item.is_hidden) return 'none'
  const renderKind = getRenderKind(item)
  if (renderKind === 'generator-card') return 'full-dom'
  if (args.hoverDomItemId === item.id) return 'full-dom'
  if (item.is_locked) return 'interaction-shell'
  if (item.type === 'group') return 'full-dom'
  if (item.type === 'text' && args.textEditingItemId === item.id) return 'full-dom'
  if (args.cropState?.itemId === item.id) return 'full-dom'
  if (args.textRedrawExtractingItemIds?.has(item.id)) return 'full-dom'
  if (hasAttachedMarks(item, args.marks)) return 'full-dom'
  if (selected && isMediaVisualItem(item)) return 'interaction-shell'
  if (selected) return 'full-dom'
  if (args.imageDetailItemId === item.id && isMediaVisualItem(item)) return 'interaction-shell'
  if (args.imageDetailItemId === item.id) return 'full-dom'
  if (hasActiveAnchoredDraft(item, args) && isMediaVisualItem(item)) return 'interaction-shell'
  if (hasActiveAnchoredDraft(item, args)) return 'full-dom'
  if (
    item.type === 'image'
    || item.type === 'image_generator'
    || item.type === 'video'
    || item.type === 'video_generator'
    || item.type === 'brush_path'
  ) {
    return 'none'
  }
  return 'full-dom'
}

function canRenderInWebGL(node: Pick<CanvasRenderNode, 'renderKind' | 'overlayKind' | 'item'>) {
  if (node.item.is_hidden) return false
  if (node.renderKind === 'generator-card') return false
  if (node.overlayKind === 'full-dom') {
    return node.renderKind === 'image'
      || node.renderKind === 'video-poster'
      || node.renderKind === 'group'
  }
  return node.renderKind === 'image'
    || node.renderKind === 'video-poster'
    || node.renderKind === 'brush-path'
    || node.renderKind === 'group'
    || node.renderKind === 'text'
}

function containsPoint(node: CanvasRenderNode, point: { x: number; y: number }) {
  return point.x >= node.bounds.x
    && point.x <= node.bounds.x + node.bounds.width
    && point.y >= node.bounds.y
    && point.y <= node.bounds.y + node.bounds.height
}

function sortByZIndex(a: CanvasRenderNode, b: CanvasRenderNode) {
  return a.zIndex - b.zIndex
}

function getRenderZIndex(item: CanvasItem, groupChildZIndex: Map<string, number>) {
  if (item.type !== 'group') return item.z_index || 0
  const childBaseline = groupChildZIndex.get(item.id)
  const ownZIndex = item.z_index || 0
  if (childBaseline == null) return ownZIndex
  return Math.min(ownZIndex, childBaseline - 1)
}

function compareHitNodes(a: CanvasRenderNode, b: CanvasRenderNode) {
  if (a.type === 'group' && b.type !== 'group') return 1
  if (a.type !== 'group' && b.type === 'group') return -1
  return b.zIndex - a.zIndex
}

export function createCanvasRenderSnapshot(args: CanvasRenderModelArgs): CanvasRenderSnapshot {
  const selectedItemSet = new Set(args.selectedItems)
  const groupChildZIndex = new Map<string, number>()
  args.canvasItems.forEach((item) => {
    if (!item.groupId) return
    const current = groupChildZIndex.get(item.groupId)
    const zIndex = item.z_index || 0
    groupChildZIndex.set(item.groupId, current == null ? zIndex : Math.min(current, zIndex))
  })
  const viewportBounds = getCanvasViewportCullBounds({
    zoom: args.zoom,
    offset: args.offset,
    viewport: args.viewport,
  })

  const nodes = args.canvasItems.map((item) => {
    const dims = args.getItemDims(item)
    const width = item.width || dims.width
    const height = item.height || dims.height
    const selected = selectedItemSet.has(item.id)
    const renderKind = getRenderKind(item)
    const overlayKind = getOverlayKind(item, args, selected)
    const baseNode: CanvasRenderNode = {
      id: item.id,
      item,
      type: item.type,
      renderKind,
      overlayKind,
      bounds: {
        x: item.x,
        y: item.y,
        width,
        height,
      },
      zIndex: getRenderZIndex(item, groupChildZIndex),
      hidden: Boolean(item.is_hidden),
      locked: Boolean(item.is_locked),
      selected,
      visible: selected || isCanvasItemVisibleInViewport(item, {
        viewportBounds,
        getItemDims: args.getItemDims,
      }),
      webglRenderable: false,
    }
    return {
      ...baseNode,
      webglRenderable: canRenderInWebGL(baseNode),
    }
  }).sort(sortByZIndex)

  const index = createCanvasSpatialIndex(nodes.map((node) => ({
    id: node.id,
    bounds: rectFromBounds(node.bounds),
    value: node,
    zIndex: node.zIndex,
  })))

  const visibleNodeMap = new Map<string, CanvasRenderNode>()
  index.query({
    left: viewportBounds.left,
    right: viewportBounds.right,
    top: viewportBounds.top,
    bottom: viewportBounds.bottom,
  }).forEach((node) => {
    if (!node.hidden) {
      visibleNodeMap.set(node.id, node)
    }
  })
  nodes.forEach((node) => {
    if (node.selected && !node.hidden) {
      visibleNodeMap.set(node.id, node)
    }
  })
  const visibleNodes = Array.from(visibleNodeMap.values()).sort(sortByZIndex)

  const webglNodes = visibleNodes.filter((node) => node.webglRenderable)
  const overlayNodes = visibleNodes.filter((node) => node.overlayKind !== 'none')

  return {
    nodes,
    visibleNodes,
    webglNodes,
    overlayNodes,
    queryVisibleNodes(bounds) {
      return index.query(bounds).filter((node) => !node.hidden)
    },
    hitTest(point) {
      const candidates = index.query({
        left: point.x,
        right: point.x,
        top: point.y,
        bottom: point.y,
      }).filter((node) => (
        node.visible
        && !node.hidden
        && !node.locked
        && containsPoint(node, point)
      )).sort(compareHitNodes)
      return candidates[0] ?? null
    },
  }
}

export function getCanvasRendererPreference() {
  const value = import.meta.env.VITE_CANVAS_RENDERER
  return value === 'dom' ? 'dom' : 'webgl'
}
