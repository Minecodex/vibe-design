import type { CanvasItem } from '@/api/endpoints/projects'

import { findEmptyPosition } from './canvasLayout'
import { getNextCanvasStackZIndex } from './imageActions'
import { getDefaultMediaSize } from './mediaDimensions'

export interface UploadedCanvasImage {
  url: string
  width: number
  height: number
}

export interface CanvasImageUploadBatchResult {
  successful: UploadedCanvasImage[]
  failedCount: number
}

const DEFAULT_UPLOAD_CONCURRENCY = 3

function loadImageSize(url: string): Promise<{ width: number; height: number }> {
  const fallbackSize = getDefaultMediaSize('image')

  return new Promise((resolve) => {
    const image = new Image()
    image.onload = () => resolve({
      width: image.naturalWidth || fallbackSize.width,
      height: image.naturalHeight || fallbackSize.height,
    })
    image.onerror = () => resolve(fallbackSize)
    image.src = url
  })
}

export async function uploadCanvasImageFiles(
  files: File[],
  uploadFile: (file: File) => Promise<string>,
  concurrency = DEFAULT_UPLOAD_CONCURRENCY,
): Promise<CanvasImageUploadBatchResult> {
  if (files.length === 0) {
    return { successful: [], failedCount: 0 }
  }

  const successfulByIndex: Array<UploadedCanvasImage | undefined> = new Array(files.length)
  let nextIndex = 0
  let failedCount = 0
  const workerCount = Math.min(files.length, Math.max(1, Math.floor(concurrency)))

  const worker = async () => {
    while (nextIndex < files.length) {
      const currentIndex = nextIndex
      nextIndex += 1

      try {
        const url = await uploadFile(files[currentIndex])
        const size = await loadImageSize(url)
        successfulByIndex[currentIndex] = { url, ...size }
      } catch {
        failedCount += 1
      }
    }
  }

  await Promise.all(Array.from({ length: workerCount }, worker))

  return {
    successful: successfulByIndex.filter((image): image is UploadedCanvasImage => Boolean(image)),
    failedCount,
  }
}

function createCanvasImageId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

export function planUploadedCanvasImages(
  images: UploadedCanvasImage[],
  existingItems: CanvasItem[],
  viewportCenter: { x: number; y: number },
  createId: () => string = createCanvasImageId,
): CanvasItem[] {
  const newItems: CanvasItem[] = []
  let occupiedItems = [...existingItems]

  for (const image of images) {
    const position = findEmptyPosition(
      viewportCenter.x,
      viewportCenter.y,
      image.width,
      image.height,
      occupiedItems,
    )
    const newItem: CanvasItem = {
      id: createId(),
      type: 'image',
      url: image.url,
      x: position.x,
      y: position.y,
      width: image.width,
      height: image.height,
      z_index: getNextCanvasStackZIndex(occupiedItems),
      asset_origin: 'local_upload',
      created_at: new Date().toISOString(),
    }

    newItems.push(newItem)
    occupiedItems = [...occupiedItems, newItem]
  }

  return newItems
}
