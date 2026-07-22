import { resolveHarnessWorkspaceUrl } from '@/api/endpoints/agent'
import { getApiBaseUrl } from '@/config/runtimeConfig'

function normalizeGeneratedPath(path: string): string {
  return path.replace(/^\/+/, '').replace(/^generated\//, '')
}

function getApiOrigin(): string {
  return getApiBaseUrl().replace(/\/api\/v1\/?$/, '')
}

function stripInternalApiOrigin(url: string): string | null {
  try {
    const parsed = new URL(url)
    const apiOrigin = new URL(getApiOrigin())
    const isLocalBackendHost = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '::1'
    const isSameBackendOrigin = parsed.origin === apiOrigin.origin
    if ((isSameBackendOrigin || isLocalBackendHost) && parsed.pathname.startsWith('/api/v1/')) {
      return `${parsed.pathname}${parsed.search}${parsed.hash}`
    }
  } catch {
    return null
  }

  return null
}

export function normalizeCanvasAgentMediaRef(
  url: string | null | undefined,
  conversationId?: string | number | null,
): string {
  const raw = String(url || '').trim()
  if (!raw) return ''

  const strippedInternalUrl = stripInternalApiOrigin(raw)
  if (strippedInternalUrl) {
    return strippedInternalUrl
  }

  if (raw.startsWith('/api/v1/')) {
    return raw
  }

  if (raw.startsWith('generated/')) {
    return `/api/v1/uploads/generated/${normalizeGeneratedPath(raw)}`
  }

  if (raw.startsWith('/generated/')) {
    return `/api/v1/uploads/generated/${normalizeGeneratedPath(raw)}`
  }

  if (
    raw.startsWith('http://')
    || raw.startsWith('https://')
    || raw.startsWith('data:')
    || raw.startsWith('blob:')
  ) {
    return raw
  }

  const harnessUrl = resolveHarnessWorkspaceUrl(conversationId, raw)
  return stripInternalApiOrigin(harnessUrl || '') || harnessUrl || raw
}

export function resolveCanvasAgentMediaUrl(
  url: string | null | undefined,
  conversationId?: string | number | null,
): string {
  const raw = normalizeCanvasAgentMediaRef(url, conversationId)
  if (!raw) return ''

  if (
    raw.startsWith('http://')
    || raw.startsWith('https://')
    || raw.startsWith('data:')
    || raw.startsWith('blob:')
  ) {
    return raw
  }

  if (raw.startsWith('/api/v1/')) {
    return `${getApiOrigin()}${raw}`
  }

  return raw
}
