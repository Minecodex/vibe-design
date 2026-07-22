export interface User {
  id: number
  email: string
  username: string
  role: string
  is_active: boolean
  nickname?: string | null
  bio?: string | null
  avatar_url?: string | null
  balance_cents?: number
}

export interface LoginRequest {
  account: string
  password: string
}

export interface RegisterRequest {
  email: string
  username: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface RefreshResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export type LicenseStatus = 'active' | 'expired' | 'invalid' | 'missing'
export type LicenseEdition = 'premium' | 'flagship'

export interface HealthResponse {
  status: string
  env: string
  app: string
  deploy_type: 'saas' | 'private'
  license_status: LicenseStatus
  license_edition: LicenseEdition | null
  license_expired: boolean
  license_expires_at: string | null
  provider_balance_sync_enabled?: boolean
}
