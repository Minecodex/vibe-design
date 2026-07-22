import { normalizeServerBaseUrl } from './config'

export interface LoginRequest {
  serverBaseUrl: string
  account: string
  password: string
}

export interface LoginResult {
  accessToken: string
  refreshToken: string
}

export async function loginWithPassword({
  serverBaseUrl,
  account,
  password,
}: LoginRequest): Promise<LoginResult> {
  const response = await fetch(
    `${normalizeServerBaseUrl(serverBaseUrl)}/api/v1/auth/login`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        account,
        password,
      }),
    },
  )

  if (!response.ok) {
    throw new Error('Login failed')
  }

  const data = await response.json() as {
    access_token: string
    refresh_token: string
  }

  return {
    accessToken: data.access_token,
    refreshToken: data.refresh_token,
  }
}
