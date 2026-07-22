import type { AxiosError } from 'axios'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { toastError } = vi.hoisted(() => ({
  toastError: vi.fn(),
}))

import { setupInterceptors } from './interceptors'

vi.mock('sonner', () => ({
  toast: {
    error: toastError,
  },
}))

describe('setupInterceptors', () => {
  beforeEach(() => {
    toastError.mockReset()
  })

  it('shows a toast for insufficient-balance API errors', async () => {
    const requestUse = vi.fn()
    const responseUse = vi.fn()
    const client = {
      interceptors: {
        request: { use: requestUse },
        response: { use: responseUse },
      },
    } as any

    setupInterceptors(client)

    const rejectHandler = responseUse.mock.calls[0][1] as (error: AxiosError) => Promise<never>
    const error = {
      config: { headers: {}, url: '/projects/1/generate/hd' },
      response: {
        status: 402,
        data: { detail: { code: 'INSUFFICIENT_BALANCE', message: '余额不足，需要 ¥0.40' } },
      },
    } as AxiosError

    await expect(rejectHandler(error)).rejects.toBe(error)
    expect(toastError).toHaveBeenCalledWith('余额不足，需要 ¥0.40')
  })
})
