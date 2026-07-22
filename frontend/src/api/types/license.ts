export interface LicenseActivateRequest {
  code: string
}

export interface LicenseActivateResponse {
  expires_at: string
  expired: boolean
}
