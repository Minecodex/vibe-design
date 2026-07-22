import type { TFunction } from 'i18next'
import { toast } from 'sonner'

import { useAppConfigStore } from '@/store/appConfigStore'

type UploadLimitKey =
  | 'avatar_max_bytes'
  | 'canvas_image_max_bytes'
  | 'canvas_video_max_bytes'
  | 'harness_attachment_max_bytes'

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 MB'
  const mb = bytes / (1024 * 1024)
  if (mb >= 1) return `${mb.toFixed(mb >= 10 ? 0 : 1)} MB`
  return `${Math.ceil(bytes / 1024)} KB`
}

export function validateUploadFileSize(
  file: File,
  limitKey: UploadLimitKey,
  t: TFunction,
): boolean {
  const state = (useAppConfigStore as typeof useAppConfigStore & {
    getState?: () => { uploadLimits?: Record<UploadLimitKey, number> | null }
  }).getState?.()
  const limit = state?.uploadLimits?.[limitKey]
  if (!limit || file.size <= limit) {
    return true
  }
  toast.error(t('upload.file_too_large', {
    fileName: file.name,
    maxSize: formatBytes(limit),
  }))
  return false
}
