import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'

export const CANVAS_SCENE_MAX_DETAIL_ZOOM = 60
export const CANVAS_SCENE_MIN_VISIBLE_ITEMS = 12
const CULL_BUFFER = 500

type SceneViewport = {
  width: number
  height: number
}

type CanvasViewportCullBounds = {
  left: number
  right: number
  top: number
  bottom: number
}

type SceneSharedState = {
  selectedItems: string[]
  marks?: CanvasMark[]
  cropState?: { itemId?: string | null } | null
  textRedrawExtractingItemIds?: Set<string> | null
}

type SceneVisibilityArgs = SceneSharedState & {
  canvasItems: CanvasItem[]
  zoom: number
  offset: { x: number; y: number }
  viewport: SceneViewport
  getItemDims: (item: CanvasItem) => { width: number; height: number }
}

type SceneRenderModeArgs = SceneSharedState & {
  useSceneRenderer: boolean
  item: CanvasItem
}

export function shouldUseCanvasSceneRenderer(args: { zoom: number; visibleItemCount: number }) {
  return args.zoom <= CANVAS_SCENE_MAX_DETAIL_ZOOM && args.visibleItemCount >= CANVAS_SCENE_MIN_VISIBLE_ITEMS
}

function hasAttachedMarks(item: CanvasItem, marks: CanvasMark[] = []) {
  return marks.some((mark) => mark.imageItemId === item.id)
}

export function isCanvasSceneRenderableItem(item: CanvasItem, state: SceneSharedState) {
  if (item.is_hidden) return false
  if (state.selectedItems.includes(item.id)) return false
  if (item.groupId) return false
  if (item.type === 'text' || item.type === 'group' || item.type === 'video') return false
  if (state.cropState?.itemId === item.id) return false
  if (state.textRedrawExtractingItemIds?.has(item.id)) return false
  if (hasAttachedMarks(item, state.marks)) return false

  return item.type === 'image' || item.type === 'brush_path'
}

export function getCanvasViewportCullBounds(args: Pick<SceneVisibilityArgs, 'zoom' | 'offset' | 'viewport'>): CanvasViewportCullBounds {
  const scale = args.zoom / 100
  if (scale <= 0) {
    return {
      left: -Infinity,
      right: Infinity,
      top: -Infinity,
      bottom: Infinity,
    }
  }
  const buffer = CULL_BUFFER / scale

  return {
    left: (-args.viewport.width / 2 - args.offset.x) / scale - buffer,
    right: (args.viewport.width / 2 - args.offset.x) / scale + buffer,
    top: (-args.viewport.height / 2 - args.offset.y) / scale - buffer,
    bottom: (args.viewport.height / 2 - args.offset.y) / scale + buffer,
  }
}

export function isCanvasItemVisibleInViewport(
  item: CanvasItem,
  args: { viewportBounds: CanvasViewportCullBounds; getItemDims: (item: CanvasItem) => { width: number; height: number } },
) {
  const dims = args.getItemDims(item)
  const width = item.width || dims.width
  const height = item.height || dims.height

  return !(
    item.x > args.viewportBounds.right ||
    item.x + width < args.viewportBounds.left ||
    item.y > args.viewportBounds.bottom ||
    item.y + height < args.viewportBounds.top
  )
}

export function getVisibleCanvasSceneItems(args: SceneVisibilityArgs) {
  const viewportBounds = getCanvasViewportCullBounds(args)
  return args.canvasItems
    .filter((item) => isCanvasSceneRenderableItem(item, args) && isCanvasItemVisibleInViewport(item, { viewportBounds, getItemDims: args.getItemDims }))
    .sort((a, b) => (a.z_index || 0) - (b.z_index || 0))
}

export function getCanvasSceneItemRenderMode(args: SceneRenderModeArgs) {
  if (!args.useSceneRenderer) return 'full-dom'
  return isCanvasSceneRenderableItem(args.item, args) ? 'interaction-shell' : 'full-dom'
}
