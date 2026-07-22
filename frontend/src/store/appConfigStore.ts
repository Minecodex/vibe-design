import { create } from 'zustand'

import { publicConfigApi } from '@/api/endpoints/publicConfig'
import type { UploadLimits } from '@/api/types/publicConfig'

interface AppConfigState {
  appName: string
  appNameEn: string
  uploadLimits: UploadLimits | null
  isLoaded: boolean
  fetchPublicConfig: () => Promise<void>
}

const DEFAULT_APP_NAME = '像素重组'
const DEFAULT_APP_NAME_EN = 'Pixel Reorganization'
let publicConfigRequest: Promise<void> | null = null

export const useAppConfigStore = create<AppConfigState>()((set) => ({
  appName: DEFAULT_APP_NAME,
  appNameEn: DEFAULT_APP_NAME_EN,
  uploadLimits: null,
  isLoaded: false,
  fetchPublicConfig: async () => {
    if (useAppConfigStore.getState().isLoaded) {
      return
    }
    if (publicConfigRequest) {
      return publicConfigRequest
    }

    publicConfigRequest = (async () => {
      try {
        const { data } = await publicConfigApi.getPublicConfig()
        set({
          appName: data.app_name || DEFAULT_APP_NAME,
          appNameEn: data.app_name_en || DEFAULT_APP_NAME_EN,
          uploadLimits: data.upload_limits ?? null,
          isLoaded: true,
        })
      } catch {
        set({ isLoaded: true })
      } finally {
        publicConfigRequest = null
      }
    })()

    return publicConfigRequest
  },
}))
