import type { CanvasItem } from '@/api/endpoints/projects'
import { isGenerationTaskPendingStatus } from './generationTaskBinding'

function isMediaItem(item: CanvasItem) {
  return item.type === 'image'
    || item.type === 'video'
    || item.type === 'image_generator'
    || item.type === 'video_generator'
}

export function canRenameCanvasItem(item: CanvasItem | null | undefined) {
  if (!item) return false
  if (isGenerationTaskPendingStatus(item.status) && isMediaItem(item)) return false
  return true
}
