import { toast } from 'sonner'
import type { TFunction } from 'i18next'

import type { CanvasItem } from '@/api/endpoints/projects'

import { planImportedCanvasItems, type ImportedAssetPayload } from '../assetImport'
import { getDefaultMediaSize } from '../mediaDimensions'

interface UseAssetLibraryImportArgs {
  canvasItems: CanvasItem[]
  zoomRef: React.MutableRefObject<number>
  offsetRef: React.MutableRefObject<{ x: number; y: number }>
  updateCanvasItems: (updater: CanvasItem[] | ((previous: CanvasItem[]) => CanvasItem[])) => void
  saveCanvasItems: (items: CanvasItem[]) => void
  setSelectedItems: (itemIds: string[]) => void
  setActiveTool: (tool: string) => void
  handleJumpToItem: (itemId: string, itemOverride?: unknown, fitZoom?: boolean) => void
  t: TFunction
  findPosition: (
    viewportCenterX: number,
    viewportCenterY: number,
    width: number,
    height: number,
    existingItems: CanvasItem[],
  ) => { x: number; y: number }
}

async function resolveMediaSize(asset: ImportedAssetPayload): Promise<{ width: number; height: number }> {
  const fallbackSize = getDefaultMediaSize(asset.type)
  let naturalWidth = fallbackSize.width
  let naturalHeight = fallbackSize.height

  if (asset.type === 'image') {
    const image = new Image()
    image.src = asset.url
    await new Promise((resolve) => {
      image.onload = () => resolve(null)
      image.onerror = () => resolve(null)
    })
    if (image.naturalWidth) naturalWidth = image.naturalWidth
    if (image.naturalHeight) naturalHeight = image.naturalHeight
  } else {
    const video = document.createElement('video')
    video.src = asset.url
    await new Promise((resolve) => {
      video.onloadedmetadata = () => resolve(null)
      video.onerror = () => resolve(null)
    })
    if (video.videoWidth) naturalWidth = video.videoWidth
    if (video.videoHeight) naturalHeight = video.videoHeight
  }

  return {
    width: naturalWidth,
    height: naturalHeight,
  }
}

export function useAssetLibraryImport({
  canvasItems,
  zoomRef,
  offsetRef,
  updateCanvasItems,
  saveCanvasItems,
  setSelectedItems,
  setActiveTool,
  handleJumpToItem,
  t,
  findPosition,
}: UseAssetLibraryImportArgs) {
  return async (assets: ImportedAssetPayload[]) => {
    if (!assets.length) return

    const viewportCenter = {
      x: -offsetRef.current.x / (zoomRef.current / 100),
      y: -offsetRef.current.y / (zoomRef.current / 100),
    }

    const mediaSizes = await Promise.all(assets.map(resolveMediaSize))
    const newItems = planImportedCanvasItems({
      assets,
      mediaSizes,
      viewportCenter,
      existingItems: canvasItems,
      createId: () => Date.now().toString() + Math.random().toString().slice(2, 6),
      findPosition,
    })

    updateCanvasItems((previous) => {
      const nextItems = [...previous, ...newItems]
      saveCanvasItems(nextItems)
      return nextItems
    })

    setActiveTool('select')
    setSelectedItems(newItems.map((item) => item.id))
    handleJumpToItem(newItems[0].id, newItems[0], true)
    toast.success(t('canvas.tools.import_success', '导入成功'))
  }
}
