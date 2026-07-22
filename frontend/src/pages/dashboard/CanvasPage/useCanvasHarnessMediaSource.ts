import { useEffect, useState } from 'react'

import {
  agentApi,
  isHarnessWorkspaceRelativePath,
  normalizeHarnessWorkspacePath,
} from '@/api/endpoints/agent'
import { getAgentMediaVariantWidth, type AgentMediaVariant } from '../agentMedia/agentMediaTypes'
import { enqueueAgentMediaRequest } from '../agentMedia/agentMediaRequestQueue'

import { resolveCanvasAgentMediaUrl } from './canvasMediaUrl'

const PREVIEW_TOKEN_EXPIRY_SKEW_MS = 30_000
const DEFAULT_PREVIEW_TOKEN_TTL_MS = 5 * 60 * 1000

interface PreviewTokenCacheEntry {
  token: string
  expiresAt: number
}

interface ResolvedWorkspaceMediaCacheEntry {
  url: string
  expiresAt: number
}

const previewTokenCache = new Map<string, PreviewTokenCacheEntry>()
const previewTokenInflight = new Map<string, Promise<PreviewTokenCacheEntry>>()
const resolvedWorkspaceMediaCache = new Map<string, ResolvedWorkspaceMediaCacheEntry>()

function shouldResolveDirectly(sourceUrl: string | null | undefined): boolean {
  const raw = String(sourceUrl || '').trim()
  return raw.startsWith('generated/') || raw.startsWith('/generated/')
}

function nowMs(): number {
  return Date.now()
}

function isFresh(expiresAt: number): boolean {
  return expiresAt - PREVIEW_TOKEN_EXPIRY_SKEW_MS > nowMs()
}

function getConversationCacheKey(conversationId: string | number): string {
  return String(conversationId)
}

function getMediaCacheKey(conversationId: string | number, normalizedPath: string, variant?: AgentMediaVariant): string {
  return `${String(conversationId)}:${variant || 'original'}:${normalizedPath}`
}

function getCachedPreviewToken(conversationId: string | number): PreviewTokenCacheEntry | undefined {
  const cached = previewTokenCache.get(getConversationCacheKey(conversationId))
  if (!cached || !isFresh(cached.expiresAt)) {
    return undefined
  }
  return cached
}

async function getWorkspacePreviewToken(conversationId: string | number): Promise<PreviewTokenCacheEntry> {
  const cacheKey = getConversationCacheKey(conversationId)
  const cached = getCachedPreviewToken(conversationId)
  if (cached) {
    return cached
  }

  const existingRequest = previewTokenInflight.get(cacheKey)
  if (existingRequest) {
    return existingRequest
  }

  const request = agentApi.createWorkspacePreviewToken(String(conversationId))
    .then((response) => {
      const ttlMs = Math.max(0, Number(response.expires_in_seconds || 0) * 1000) || DEFAULT_PREVIEW_TOKEN_TTL_MS
      const entry = {
        token: response.preview_token,
        expiresAt: nowMs() + ttlMs,
      }
      previewTokenCache.set(cacheKey, entry)
      return entry
    })
    .finally(() => {
      previewTokenInflight.delete(cacheKey)
    })

  previewTokenInflight.set(cacheKey, request)
  return request
}

function getCachedWorkspaceMediaUrl(
  conversationId: string | number,
  normalizedPath: string,
  variant?: AgentMediaVariant,
): string | undefined {
  const cached = resolvedWorkspaceMediaCache.get(getMediaCacheKey(conversationId, normalizedPath, variant))
  if (!cached || !isFresh(cached.expiresAt)) {
    return undefined
  }
  return cached.url
}

function cacheWorkspaceMediaUrl(
  conversationId: string | number,
  normalizedPath: string,
  url: string,
  expiresAt: number,
  variant?: AgentMediaVariant,
): void {
  resolvedWorkspaceMediaCache.set(getMediaCacheKey(conversationId, normalizedPath, variant), { url, expiresAt })
}

function getInitialResolvedUrl(
  conversationId: string | number | null | undefined,
  sourceUrl: string | null | undefined,
  variant?: AgentMediaVariant,
): string | undefined {
  if (!sourceUrl) {
    return undefined
  }
  if (shouldResolveDirectly(sourceUrl) || !conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
    return resolveCanvasAgentMediaUrl(sourceUrl, conversationId)
  }
  const normalizedPath = normalizeHarnessWorkspacePath(sourceUrl)
  return getCachedWorkspaceMediaUrl(conversationId, normalizedPath, variant)
}

export function __resetCanvasHarnessMediaSourceCacheForTests(): void {
  previewTokenCache.clear()
  previewTokenInflight.clear()
  resolvedWorkspaceMediaCache.clear()
}

export function useCanvasHarnessMediaSource(
  conversationId: string | number | null | undefined,
  sourceUrl: string | null | undefined,
  options?: { variant?: AgentMediaVariant; enabled?: boolean },
) {
  const variant = options?.variant || 'original'
  const enabled = options?.enabled !== false
  const [resolvedUrl, setResolvedUrl] = useState<string | undefined>(() => (
    enabled ? getInitialResolvedUrl(conversationId, sourceUrl, variant) : undefined
  ))

  useEffect(() => {
    if (!enabled) {
      setResolvedUrl(undefined)
      return
    }
    if (!sourceUrl) {
      setResolvedUrl(undefined)
      return
    }

    if (shouldResolveDirectly(sourceUrl) || !conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
      setResolvedUrl(resolveCanvasAgentMediaUrl(sourceUrl, conversationId))
      return
    }

    let active = true
    let objectUrl: string | null = null
    const normalizedPath = normalizeHarnessWorkspacePath(sourceUrl)
    const cachedUrl = getCachedWorkspaceMediaUrl(conversationId, normalizedPath, variant)
    if (cachedUrl) {
      setResolvedUrl(cachedUrl)
      return
    }

    const loadMedia = async () => {
      try {
        const previewToken = await getWorkspacePreviewToken(conversationId)
        if (!active) {
          return
        }
        const variantWidth = getAgentMediaVariantWidth(variant)
        const previewUrl = agentApi.getWorkspacePreviewFileUrl(
          String(conversationId),
          normalizedPath,
          previewToken.token,
          variantWidth ? { width: variantWidth } : undefined,
        )
        cacheWorkspaceMediaUrl(conversationId, normalizedPath, previewUrl, previewToken.expiresAt, variant)
        setResolvedUrl(previewUrl)
        return
      } catch {
        // Fall through to authenticated blob loading.
      }

      try {
        const blob = await enqueueAgentMediaRequest(() => (
          agentApi.fetchWorkspaceFileBlob(String(conversationId), normalizedPath)
        ))
        if (!active) {
          return
        }
        objectUrl = URL.createObjectURL(blob)
        setResolvedUrl(objectUrl)
        return
      } catch {
        if (active) {
          setResolvedUrl('')
        }
      }
    }

    void loadMedia()

    return () => {
      active = false
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl)
      }
    }
  }, [conversationId, enabled, sourceUrl, variant])

  return resolvedUrl
}
