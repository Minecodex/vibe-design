import type { AssetRead } from '@/api/endpoints/assets'
import type { CanvasItem } from '@/api/endpoints/projects'
import { getNextCanvasStackZIndex } from './imageActions'

export interface ImportedAssetPayload {
  id: number
  url: string
  type: 'image' | 'video'
  origin_kind: AssetRead['origin_kind']
  source_asset_id?: number | null
}

interface PlanImportedCanvasItemsArgs {
  assets: ImportedAssetPayload[]
  mediaSizes: Array<{ width: number; height: number }>
  viewportCenter: { x: number; y: number }
  existingItems: CanvasItem[]
  createId: () => string
  findPosition: (
    viewportCenterX: number,
    viewportCenterY: number,
    width: number,
    height: number,
    existingItems: CanvasItem[],
  ) => { x: number; y: number }
}

export function planImportedCanvasItems({
  assets,
  mediaSizes,
  viewportCenter,
  existingItems,
  createId,
  findPosition,
}: PlanImportedCanvasItemsArgs): CanvasItem[] {
  const nextItems: CanvasItem[] = []
  let allExisting = [...existingItems]

  assets.forEach((asset, index) => {
    const mediaSize = mediaSizes[index]
    const position = findPosition(
      viewportCenter.x,
      viewportCenter.y,
      mediaSize.width,
      mediaSize.height,
      allExisting,
    )

    const newItem: CanvasItem = {
      id: createId(),
      type: asset.type,
      url: asset.url,
      x: position.x,
      y: position.y,
      width: mediaSize.width,
      height: mediaSize.height,
      z_index: getNextCanvasStackZIndex(allExisting),
      asset_origin: asset.origin_kind,
      source_asset_id: asset.id,
      created_at: new Date().toISOString(),
    }

    nextItems.push(newItem)
    allExisting = [...allExisting, newItem]
  })

  return nextItems
}
