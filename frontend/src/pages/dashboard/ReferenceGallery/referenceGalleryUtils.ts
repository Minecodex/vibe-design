import type { ReferenceImageRead } from '@/api/endpoints/referenceGallery'
import { formatApiErrorDetail } from '@/utils/apiErrors'

export function apiErrorMessage(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  return formatApiErrorDetail(detail, fallback)
}

export function imageLabels(image: ReferenceImageRead): string[] {
  return [
    image.category_name,
    image.style_name || '',
    image.classification_name || '',
  ].filter(Boolean)
}
