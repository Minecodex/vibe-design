import type { ValidationError } from '@/api/types/common'

export function formatApiErrorDetail(detail: unknown, fallback: string) {
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    const message = (detail as { message?: unknown }).message
    if (typeof message === 'string' && message.trim()) return message
  }
  if (typeof detail === 'string' && detail.trim()) {
    return detail
  }

  if (Array.isArray(detail)) {
    const message = detail
      .map((item) => {
        const validationItem = item as Partial<ValidationError>
        return typeof validationItem.msg === 'string' ? validationItem.msg : ''
      })
      .filter(Boolean)
      .join('; ')

    if (message) {
      return message
    }
  }

  return fallback
}
