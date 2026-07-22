import { useEffect, useState } from 'react'

import {
  agentApi,
  isHarnessWorkspaceRelativePath,
  normalizeHarnessWorkspacePath,
  resolveHarnessWorkspaceUrl,
} from '@/api/endpoints/agent'
import { getAgentMediaVariantWidth, type AgentMediaVariant } from '../../agentMedia/agentMediaTypes'

export function useHarnessMediaSource(
  conversationId: string | number | null | undefined,
  sourceUrl: string | null | undefined,
  options?: { preferPreviewUrl?: boolean; reloadToken?: number; variant?: AgentMediaVariant; enabled?: boolean },
) {
  const preferPreviewUrl = options?.preferPreviewUrl === true
  const reloadToken = options?.reloadToken ?? 0
  const variant = options?.variant || 'original'
  const enabled = options?.enabled !== false
  const [resolvedUrl, setResolvedUrl] = useState<string | undefined>(() => {
    if (!enabled || !sourceUrl) {
      return undefined
    }
    if (!conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
      return resolveHarnessWorkspaceUrl(conversationId, sourceUrl)
    }
    return ''
  })

  useEffect(() => {
    if (!enabled) {
      setResolvedUrl(undefined)
      return
    }
    if (!sourceUrl) {
      setResolvedUrl(undefined)
      return
    }

    if (!conversationId || !isHarnessWorkspaceRelativePath(sourceUrl)) {
      setResolvedUrl(resolveHarnessWorkspaceUrl(conversationId, sourceUrl))
      return
    }

    let active = true
    let objectUrl: string | null = null
    const normalizedPath = normalizeHarnessWorkspacePath(sourceUrl)

    const loadMedia = async () => {
      try {
        if (preferPreviewUrl) {
          const { preview_token } = await agentApi.createWorkspacePreviewToken(String(conversationId))
          if (!active) {
            return
          }
          const variantWidth = getAgentMediaVariantWidth(variant)
          const previewUrl = agentApi.getWorkspacePreviewFileUrl(
            String(conversationId),
            normalizedPath,
            preview_token,
            variantWidth ? { width: variantWidth } : undefined,
          )
          // Bust the browser cache on retries so a previously-503 asset is refetched.
          setResolvedUrl(reloadToken > 0 ? `${previewUrl}&_r=${reloadToken}` : previewUrl)
          return
        }

        const blob = await agentApi.fetchWorkspaceFileBlob(String(conversationId), normalizedPath)
        if (!active) {
          return
        }
        objectUrl = URL.createObjectURL(blob)
        setResolvedUrl(objectUrl)
      } catch {
        if (active) {
          setResolvedUrl(resolveHarnessWorkspaceUrl(conversationId, sourceUrl))
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
  }, [conversationId, enabled, preferPreviewUrl, sourceUrl, reloadToken, variant])

  return resolvedUrl
}
