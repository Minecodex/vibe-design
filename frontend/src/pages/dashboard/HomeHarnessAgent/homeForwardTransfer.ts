import type { MediaReferenceData } from '@/api/endpoints/agent'

export type HomeForwardTransferMode = 'document' | 'ppt' | 'spreadsheet' | 'web' | 'slides' | 'image' | 'video'

export interface HomeForwardTransferAttachment {
  id: number
  url: string
  type: 'image'
  origin_kind: string
  source_asset_id?: number | null
  reference?: MediaReferenceData
}

export interface HomeForwardTransferPayload {
  key: string
  createdAt: string
  source: 'canvas-agent'
  projectId: number
  mode: HomeForwardTransferMode
  text: string
  attachments: HomeForwardTransferAttachment[]
}

function isAttachment(value: unknown): value is HomeForwardTransferAttachment {
  if (!value || typeof value !== 'object') {
    return false
  }

  const candidate = value as Record<string, unknown>
  return typeof candidate.id === 'number'
    && typeof candidate.url === 'string'
    && candidate.type === 'image'
    && typeof candidate.origin_kind === 'string'
}

function isPayload(value: unknown): value is HomeForwardTransferPayload {
  if (!value || typeof value !== 'object') {
    return false
  }

  const candidate = value as Record<string, unknown>
  return typeof candidate.key === 'string'
    && typeof candidate.createdAt === 'string'
    && candidate.source === 'canvas-agent'
    && typeof candidate.projectId === 'number'
    && ['document', 'ppt', 'spreadsheet', 'web', 'slides', 'image', 'video'].includes(String(candidate.mode))
    && typeof candidate.text === 'string'
    && Array.isArray(candidate.attachments)
    && candidate.attachments.every(isAttachment)
}

export function saveHomeForwardTransfer(payload: HomeForwardTransferPayload): string {
  localStorage.setItem(payload.key, JSON.stringify(payload))
  return payload.key
}

export function loadHomeForwardTransfer(key: string): HomeForwardTransferPayload | null {
  const raw = localStorage.getItem(key)
  if (!raw) {
    return null
  }

  try {
    const parsed = JSON.parse(raw)
    return isPayload(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function deleteHomeForwardTransfer(key: string): void {
  localStorage.removeItem(key)
}

export function buildHomeForwardTransferReference(
  asset: Pick<HomeForwardTransferAttachment, 'url'>,
): MediaReferenceData | undefined {
  const url = normalizeHomeAssetUrl(asset.url)
  if (url) {
    return {
      id: `home-asset:${url}`,
      kind: 'home_asset',
      media_type: 'image',
      display_name: getAttachmentNameFromUrl(url),
      source: {
        type: 'home_asset',
        url,
      },
    }
  }

  const path = normalizeWorkspaceReferencePath(asset.url)
  if (path) {
    return {
      id: `workspace-file:${path}`,
      kind: 'workspace_file',
      media_type: 'image',
      display_name: getAttachmentNameFromUrl(path),
      source: {
        type: 'workspace_file',
        path,
      },
    }
  }

  return undefined
}

function normalizeHomeAssetUrl(value: string | undefined): string | null {
  const url = String(value || '').trim()
  if (!url || /\s/.test(url)) return null
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/api/v1/')) return url
  return null
}

function normalizeWorkspaceReferencePath(value: string | undefined): string | null {
  const path = String(value || '').trim().replace(/\\/g, '/').replace(/^\.\//, '').replace(/^\/+/, '')
  if (!path) return null
  if (path.split('/').some((part) => part === '' || part === '.' || part === '..')) return null
  if (
    path.startsWith('published/')
    || path.startsWith('project/')
    || path.startsWith('references/sources/')
    || path.startsWith('references/generated/')
  ) {
    return path
  }
  return null
}

function getAttachmentNameFromUrl(url: string): string {
  const clean = String(url || '').split(/[?#]/)[0]
  return clean.split('/').filter(Boolean).pop() || 'image'
}
