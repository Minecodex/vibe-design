import { toast } from 'sonner'

const GLOBAL_ERROR_TOAST_SHOWN_KEY = '__global_error_toast_shown__'

type ValidationDetail = {
  msg?: string
}

type ErrorDetailObject = {
  code?: string
  message?: string
}

type ToastTrackedError = {
  [GLOBAL_ERROR_TOAST_SHOWN_KEY]?: boolean
}

function extractDetailMessage(detail: unknown): string | null {
  if (typeof detail === 'string') {
    const trimmed = detail.trim()
    return trimmed || null
  }

  if (Array.isArray(detail)) {
    const combined = detail
      .map((entry) => (entry && typeof entry === 'object' ? (entry as ValidationDetail).msg : ''))
      .filter(Boolean)
      .join('; ')

    return combined || null
  }

  if (detail && typeof detail === 'object') {
    const message = typeof (detail as ErrorDetailObject).message === 'string'
      ? (detail as ErrorDetailObject).message?.trim()
      : ''
    return message || null
  }

  return null
}

export function extractApiErrorMessage(error: unknown, fallback = '操作失败'): string {
  if (error && typeof error === 'object') {
    const detail = extractDetailMessage((error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail)
    if (detail) return detail

    const message = typeof (error as { message?: unknown }).message === 'string'
      ? (error as { message: string }).message.trim()
      : ''
    if (message) return message
  }

  return fallback
}

export function extractApiErrorMessageFromText(text: string, fallback = '操作失败'): string {
  const trimmed = text.trim()
  if (!trimmed) return fallback

  try {
    const parsed = JSON.parse(trimmed) as { detail?: unknown }
    const detail = extractDetailMessage(parsed?.detail)
    if (detail) return detail
  } catch {
    // Fall through to raw text.
  }

  return trimmed || fallback
}

export function isBillingInsufficientError(error: unknown): boolean {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (detail && typeof detail === 'object') {
    return (detail as ErrorDetailObject).code === 'INSUFFICIENT_BALANCE'
  }
  const message = extractDetailMessage(detail) || ''
  return /余额不足|积分不足|insufficient\s+balance/i.test(message)
}

export function isBillingInsufficientMessage(message: string): boolean {
  return /余额不足|积分不足|insufficient\s+balance/i.test(String(message || ''))
}

export function markApiErrorToastShown(error: unknown): void {
  if (!error || typeof error !== 'object') return
  ;(error as ToastTrackedError)[GLOBAL_ERROR_TOAST_SHOWN_KEY] = true
}

export function hasApiErrorToastShown(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  return Boolean((error as ToastTrackedError)[GLOBAL_ERROR_TOAST_SHOWN_KEY])
}

export function toastApiError(error: unknown, fallback: string): string {
  const message = extractApiErrorMessage(error, fallback)
  if (!hasApiErrorToastShown(error)) {
    toast.error(message)
    markApiErrorToastShown(error)
  }
  return message
}

export function toastBillingErrorIfNeeded(error: unknown): string | null {
  const message = extractApiErrorMessage(error, '')
  if (!message || !isBillingInsufficientError(error) || hasApiErrorToastShown(error)) {
    return null
  }

  toast.error(message)
  markApiErrorToastShown(error)
  return message
}

