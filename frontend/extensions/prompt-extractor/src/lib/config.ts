export const DEFAULT_SERVER_BASE_URL =
  (globalThis as { __PROMPT_EXTRACTOR_DEFAULT_SERVER__?: string }).__PROMPT_EXTRACTOR_DEFAULT_SERVER__
  || 'http://localhost:8000'

export function normalizeServerBaseUrl(serverBaseUrl: string): string {
  const normalized = serverBaseUrl.trim().replace(/\/+$/, '')
  return normalized.replace(/\/api\/v1$/i, '')
}
