import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAppConfigStore } from '@/store/appConfigStore'
import { validateUploadFileSize } from './uploadLimits'

const toastError = vi.hoisted(() => vi.fn())

vi.mock('sonner', () => ({
  toast: {
    error: toastError,
  },
}))

const t = ((key: string, values?: Record<string, string>) => `${key}:${values?.maxSize ?? ''}`) as any

describe('validateUploadFileSize', () => {
  beforeEach(() => {
    toastError.mockReset()
    useAppConfigStore.setState({
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
      uploadLimits: null,
      isLoaded: false,
    })
  })

  it('allows upload when public config limits are unavailable', () => {
    const file = new File(['abcdef'], 'sample.png', { type: 'image/png' })

    expect(validateUploadFileSize(file, 'avatar_max_bytes', t)).toBe(true)
    expect(toastError).not.toHaveBeenCalled()
  })

  it('blocks files larger than the configured limit', () => {
    useAppConfigStore.setState({
      uploadLimits: {
        avatar_max_bytes: 5,
        canvas_image_max_bytes: 5,
        canvas_video_max_bytes: 5,
        harness_attachment_max_bytes: 5,
      },
    })
    const file = new File(['abcdef'], 'sample.png', { type: 'image/png' })

    expect(validateUploadFileSize(file, 'avatar_max_bytes', t)).toBe(false)
    expect(toastError).toHaveBeenCalledWith('upload.file_too_large:1 KB')
  })
})
