import { agentApi } from '@/api/endpoints/agent'
import { normalizeWorkspaceAttachmentPathByPolicy } from '@/utils/harnessWorkspacePathPolicy'
import { getImageUrl } from '@/utils/imageUrl'

export function normalizeWorkspaceAttachmentPath(url: string): string | null {
  return normalizeWorkspaceAttachmentPathByPolicy(url)
}

export function requiresWorkspaceAttachmentFetch(
  url: string,
  conversationId?: string | number | null,
): boolean {
  return Boolean(conversationId && normalizeWorkspaceAttachmentPath(url))
}

export function resolveAttachmentDisplayUrl(
  url: string,
  conversationId?: string | number | null,
): string {
  if (isDirectDisplayUrl(url)) {
    return url
  }

  const workspacePath = normalizeWorkspaceAttachmentPath(url)
  if (workspacePath && conversationId) {
    return agentApi.getWorkspaceFileUrl(String(conversationId), workspacePath)
  }

  return getImageUrl(url) ?? url
}

function isDirectDisplayUrl(url: string) {
  return (
    url.startsWith('http://')
    || url.startsWith('https://')
    || url.startsWith('data:')
    || url.startsWith('blob:')
  )
}
