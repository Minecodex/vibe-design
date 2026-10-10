import type { ValidationError } from '@/api/types/common'

export function errorName(error: unknown): string | undefined {
  if (!error || typeof error !== 'object' || !('name' in error)) return undefined
  return typeof error.name === 'string' ? error.name : undefined
}

export function errorMessage(error: unknown): string | undefined {
  if (!error || typeof error !== 'object' || !('message' in error)) return undefined
  return typeof error.message === 'string' ? error.message : undefined
}

function errorField(value: unknown, field: string): unknown {
  return value && typeof value === 'object' ? (value as Record<string, unknown>)[field] : undefined
}

export function apiErrorDetail(error: unknown): unknown {
  return errorField(errorField(errorField(error, 'response'), 'data'), 'detail')
}

export function apiErrorStatus(error: unknown): number | undefined {
  const status = errorField(errorField(error, 'response'), 'status')
  return typeof status === 'number' ? status : undefined
}

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
