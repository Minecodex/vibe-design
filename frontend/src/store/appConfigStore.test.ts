import { beforeEach, describe, expect, it, vi } from 'vitest'

const publicConfigMocks = vi.hoisted(() => ({
  getPublicConfig: vi.fn(),
}))

vi.mock('@/api/endpoints/publicConfig', () => ({
  publicConfigApi: {
    getPublicConfig: publicConfigMocks.getPublicConfig,
  },
}))

import { useAppConfigStore } from './appConfigStore'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('appConfigStore', () => {
  beforeEach(() => {
    publicConfigMocks.getPublicConfig.mockReset()
    useAppConfigStore.setState({
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
      uploadLimits: null,
      isLoaded: false,
    })
  })

  it('dedupes concurrent public config requests', async () => {
    const configDeferred = deferred<{
      data: {
        app_name: string
        app_name_en: string
        upload_limits?: {
          avatar_max_bytes: number
          canvas_image_max_bytes: number
          canvas_video_max_bytes: number
          harness_attachment_max_bytes: number
        }
      }
    }>()
    publicConfigMocks.getPublicConfig.mockReturnValue(configDeferred.promise)

    const firstRequest = useAppConfigStore.getState().fetchPublicConfig()
    const secondRequest = useAppConfigStore.getState().fetchPublicConfig()

    expect(publicConfigMocks.getPublicConfig).toHaveBeenCalledTimes(1)

    configDeferred.resolve({
      data: {
        app_name: '测试应用',
        app_name_en: 'Test App',
        upload_limits: {
          avatar_max_bytes: 1,
          canvas_image_max_bytes: 2,
          canvas_video_max_bytes: 3,
          harness_attachment_max_bytes: 4,
        },
      },
    })

    await Promise.all([firstRequest, secondRequest])

    expect(useAppConfigStore.getState().isLoaded).toBe(true)
    expect(useAppConfigStore.getState().appName).toBe('测试应用')
    expect(useAppConfigStore.getState().appNameEn).toBe('Test App')
    expect(useAppConfigStore.getState().uploadLimits?.harness_attachment_max_bytes).toBe(4)
  })
})
