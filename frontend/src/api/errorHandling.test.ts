import { describe, expect, it, vi, beforeEach } from 'vitest'

const { toastError } = vi.hoisted(() => ({
  toastError: vi.fn(),
}))

import {
  extractApiErrorMessage,
  extractApiErrorMessageFromText,
  hasApiErrorToastShown,
  toastApiError,
  toastBillingErrorIfNeeded,
} from './errorHandling'

vi.mock('sonner', () => ({
  toast: {
    error: toastError,
  },
}))

describe('errorHandling', () => {
  beforeEach(() => {
    toastError.mockReset()
  })

  it('extracts string details from axios-style errors', () => {
    expect(
      extractApiErrorMessage({
        response: { data: { detail: '余额不足，需要 40 分' } },
      }),
    ).toBe('余额不足，需要 40 分')
  })

  it('parses detail from JSON response text', () => {
    expect(extractApiErrorMessageFromText('{"detail":"余额不足，需要 40 分"}')).toBe('余额不足，需要 40 分')
  })

  it('shows a global toast once for insufficient-balance errors', () => {
    const error = {
      response: { data: { detail: { code: 'INSUFFICIENT_BALANCE', message: '余额不足，需要 40 分' } } },
    }

    expect(toastBillingErrorIfNeeded(error)).toBe('余额不足，需要 40 分')
    expect(hasApiErrorToastShown(error)).toBe(true)
    expect(toastError).toHaveBeenCalledTimes(1)
    expect(toastError).toHaveBeenCalledWith('余额不足，需要 40 分')
  })

  it('does not duplicate toasts after a global toast has already been shown', () => {
    const error = {
      response: { data: { detail: { code: 'INSUFFICIENT_BALANCE', message: '余额不足，需要 40 分' } } },
    }

    toastBillingErrorIfNeeded(error)
    const message = toastApiError(error, '操作失败')

    expect(message).toBe('余额不足，需要 40 分')
    expect(toastError).toHaveBeenCalledTimes(1)
  })
})
