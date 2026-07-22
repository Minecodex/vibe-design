import { apiClient } from '../client'
import type { PublicConfigResponse } from '../types/publicConfig'

export const publicConfigApi = {
  getPublicConfig: () =>
    apiClient.get<PublicConfigResponse>('/public-config'),
}
