import type { AssetRead } from '@/api/endpoints/assets'
import type { CanvasItem } from '@/api/endpoints/projects'

export const IMAGE_DETAIL_PANEL_WIDTH = 360
export const IMAGE_DETAIL_PANEL_HEIGHT = 220
const IMAGE_DETAIL_PANEL_GAP = 16
const IMAGE_DETAIL_PANEL_MARGIN = 32

export interface ImageDetailState {
  detailItemId: string | null
  selectedItems: string[]
}

export interface RemoveCanvasImageParams {
  canvasItems: CanvasItem[]
  selectedItems: string[]
  itemId: string
  projectAssets: Record<number, AssetRead>
}

export interface RemoveCanvasImageResult {
  canvasItems: CanvasItem[]
  selectedItems: string[]
  assetIdsToDelete: number[]
}

export interface ImageDetailViewModel {
  creatorName: string
  creatorAvatar: string | null
  fileFormat: string
  imageSize: string
  updatedAt: string
  generationMeta: {
    model: string
    resolution: string
    dimensions: string
    prompt: string
  } | null
}

export interface ImageDetailFallbacks {
  creatorName?: string | null
  creatorAvatar?: string | null
}

export function getImageDetailAsset(
  item: CanvasItem,
  projectAssets: Record<number, AssetRead>,
): AssetRead | null {
  const assets = Object.values(projectAssets)

  const byCanvasItemId = assets.find((asset) => asset.canvas_item_id === item.id)
  if (byCanvasItemId) {
    return byCanvasItemId
  }

  if (item.source_asset_id) {
    const byDirectId = projectAssets[item.source_asset_id]
    if (byDirectId) {
      return byDirectId
    }

    const bySourceAssetId = assets.find((asset) => asset.source_asset_id === item.source_asset_id)
    if (bySourceAssetId) {
      return bySourceAssetId
    }
  }

  return null
}

export function removeCanvasImage({
  canvasItems,
  itemId,
  projectAssets,
}: RemoveCanvasImageParams): RemoveCanvasImageResult {
  const item = canvasItems.find((canvasItem) => canvasItem.id === itemId)
  const canvasItemsAfterDelete = canvasItems.filter((canvasItem) => canvasItem.id !== itemId)
  const syncedAsset = item ? getImageDetailAsset(item, projectAssets) : null

  return {
    canvasItems: canvasItemsAfterDelete,
    selectedItems: [],
    assetIdsToDelete: syncedAsset?.id ? [syncedAsset.id] : (item?.source_asset_id ? [item.source_asset_id] : []),
  }
}

export function openImageDetails({
  itemId,
}: {
  itemId: string
  selectedItems: string[]
}): ImageDetailState {
  return {
    detailItemId: itemId,
    selectedItems: [],
  }
}

export function closeImageDetails(itemId: string): ImageDetailState {
  return {
    detailItemId: null,
    selectedItems: [itemId],
  }
}

export function formatImageDetails(
  item: CanvasItem,
  asset?: AssetRead | null,
  sizeBytes?: number | null,
  fallbacks?: ImageDetailFallbacks,
): ImageDetailViewModel {
  return {
    creatorName: asset?.adder_nickname || item.creator_name || fallbacks?.creatorName || 'Unknown',
    creatorAvatar: asset?.adder_avatar || item.creator_avatar || fallbacks?.creatorAvatar || null,
    fileFormat: inferFileFormat(item.url, asset?.asset_type),
    imageSize: formatImageSizeLabel(item, sizeBytes ?? null),
    updatedAt: formatUpdatedAt(asset?.created_at || item.created_at || asset?.updated_at),
    generationMeta: formatImageGenerationMeta(item),
  }
}

export function getImageDetailPanelPosition({
  item,
  zoom,
  offset,
  viewport,
}: {
  item: CanvasItem
  zoom: number
  offset: { x: number; y: number }
  viewport: { width: number; height: number }
}) {
  const scaledWidth = (item.width || 0) * zoom / 100
  const scaledX = offset.x + item.x * zoom / 100
  const scaledY = offset.y + item.y * zoom / 100

  const unclampedLeft = scaledX + scaledWidth + IMAGE_DETAIL_PANEL_GAP
  const maxLeft = viewport.width - IMAGE_DETAIL_PANEL_WIDTH - IMAGE_DETAIL_PANEL_MARGIN
  const maxTop = viewport.height - IMAGE_DETAIL_PANEL_HEIGHT - IMAGE_DETAIL_PANEL_MARGIN

  return {
    left: Math.max(IMAGE_DETAIL_PANEL_MARGIN, Math.min(unclampedLeft, maxLeft)),
    top: Math.max(IMAGE_DETAIL_PANEL_MARGIN, Math.min(scaledY, maxTop)),
    width: IMAGE_DETAIL_PANEL_WIDTH,
    height: IMAGE_DETAIL_PANEL_HEIGHT,
  }
}

function inferFileFormat(url: string, assetType?: AssetRead['asset_type']) {
  const cleanUrl = url.split('?')[0]
  const segments = cleanUrl.split('.')
  const extension = segments.length > 1 ? segments[segments.length - 1] : ''

  if (extension) {
    return extension.toUpperCase()
  }

  if (assetType === 'video') {
    return 'MP4'
  }

  return 'IMAGE'
}

export function formatImageSizeLabel(_item: CanvasItem, sizeBytes?: number | null) {
  if (typeof sizeBytes === 'number' && Number.isFinite(sizeBytes) && sizeBytes > 0) {
    if (sizeBytes >= 1024 * 1024) {
      return `${(sizeBytes / (1024 * 1024)).toFixed(2)} MB`
    }

    return `${(sizeBytes / 1024).toFixed(2)} KB`
  }

  return '--'
}

export function shouldShowSelectionMeta(width: number, minWidth = 320) {
  return Number.isFinite(width) && width >= minWidth
}

export function shouldShowImageToolbar(itemType: CanvasItem['type']) {
  return itemType === 'image'
}

export function shouldShowGeneratorControlPanel(
  item: Pick<CanvasItem, 'type' | 'status'>,
  options: { isHoverOnlyFailedVideo?: boolean } = {},
) {
  const isGenerator = item.type === 'image_generator' || item.type === 'video_generator'
  if (!isGenerator) {
    return false
  }

  if ((item.status === 'binding_task' || item.status === 'generating') || item.status === 'failed') {
    return false
  }

  return !options.isHoverOnlyFailedVideo
}

export function getImageExportDimensions(
  item: Pick<CanvasItem, 'width' | 'height'>,
  intrinsicSize?: { width: number; height: number } | null,
) {
  const intrinsicWidth = intrinsicSize?.width
  const intrinsicHeight = intrinsicSize?.height

  if (intrinsicWidth && intrinsicHeight) {
    return {
      width: intrinsicWidth,
      height: intrinsicHeight,
    }
  }

  return {
    width: item.width || 0,
    height: item.height || 0,
  }
}

export function getMediaRestoreRect(
  item: Pick<CanvasItem, 'x' | 'y' | 'width' | 'height'>,
  intrinsicSize: { width: number; height: number },
) {
  const currentWidth = item.width || 0
  const currentHeight = item.height || 0
  const centerX = item.x + currentWidth / 2
  const centerY = item.y + currentHeight / 2

  return {
    x: Math.round(centerX - intrinsicSize.width / 2),
    y: Math.round(centerY - intrinsicSize.height / 2),
    width: intrinsicSize.width,
    height: intrinsicSize.height,
  }
}

export function clampCanvasStackZIndex(
  zIndex: number | undefined,
  {
    min = -2147483000,
    max = 2147483000,
  }: { min?: number; max?: number } = {},
) {
  if (typeof zIndex !== 'number' || !Number.isFinite(zIndex)) {
    return 0
  }

  return Math.max(min, Math.min(Math.trunc(zIndex), max))
}

export function getNextCanvasStackZIndex(items: Array<{ z_index?: number | null }>) {
  const maxZIndex = items.reduce((max, item) => {
    const normalized = clampCanvasStackZIndex(item.z_index ?? undefined)
    return Math.max(max, normalized)
  }, 0)

  return clampCanvasStackZIndex(maxZIndex + 1)
}

function formatUpdatedAt(updatedAt?: string) {
  if (!updatedAt) {
    return '--'
  }

  const normalized = updatedAt.includes('T') ? updatedAt : updatedAt.replace(' ', 'T')
  const date = new Date(normalized)
  if (Number.isNaN(date.getTime())) {
    return '--'
  }

  return date.toLocaleString()
}

function formatImageGenerationMeta(item: CanvasItem) {
  if (item.asset_origin !== 'ai_generated' || item.source_asset_id) {
    return null
  }

  return {
    model: item.model_label || item.model_name || '--',
    resolution: item.resolution || '--',
    dimensions: item.width && item.height
      ? `${Math.round(item.width)} x ${Math.round(item.height)} px`
      : '--',
    prompt: item.prompt || '--',
  }
}
