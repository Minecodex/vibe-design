import { apiClient } from '../client'
import type { LicenseActivateRequest, LicenseActivateResponse } from '../types/license'

export const licenseApi = {
  activate: (data: LicenseActivateRequest) =>
    apiClient.post<LicenseActivateResponse>('/license/activate', data),
}
