import type { AttachmentData, MediaReferenceData } from '@/api/endpoints/agent'
import { normalizeWorkspaceAttachmentPathByPolicy } from '@/utils/harnessWorkspacePathPolicy'

export function buildCanvasAttachmentReferences(
  attachments: AttachmentData[] | null | undefined,
): MediaReferenceData[] | null {
  const references: MediaReferenceData[] = []
  const seen = new Set<string>()

  for (const attachment of attachments || []) {
    if (attachment.type !== 'image') {
      continue
    }

    const reference = normalizeAttachmentReference(attachment)
    if (!reference || seen.has(reference.id)) {
      continue
    }
    seen.add(reference.id)
    references.push(reference)
  }

  return references.length > 0 ? references : null
}

export function buildCanvasAssetAttachmentReference(
  asset: { url: string; name?: string | null },
): MediaReferenceData | undefined {
  return (
    buildWorkspaceFileReference(asset.url, asset.name)
    || buildHomeAssetReference(asset.url, asset.name)
    || undefined
  )
}

export function mergeCanvasMessageReferences(
  ...groups: Array<MediaReferenceData[] | null | undefined>
): MediaReferenceData[] | null {
  const merged: MediaReferenceData[] = []
  const seen = new Set<string>()

  for (const group of groups) {
    for (const reference of group || []) {
      if (!reference || seen.has(reference.id)) {
        continue
      }
      seen.add(reference.id)
      merged.push(reference)
    }
  }

  return merged.length > 0 ? merged : null
}

function normalizeAttachmentReference(attachment: AttachmentData): MediaReferenceData | null {
  const explicit = normalizeExplicitAttachmentReference(attachment)
  if (explicit) {
    return explicit
  }

  return (
    buildUploadAttachmentReference(attachment.url, attachment.name)
    || buildWorkspaceFileReference(attachment.url, attachment.name)
    || buildHomeAssetReference(attachment.url, attachment.name)
  )
}

function normalizeExplicitAttachmentReference(attachment: AttachmentData): MediaReferenceData | null {
  const reference = attachment.reference
  if (!reference || reference.media_type !== 'image') {
    return null
  }

  if (reference.source.type === 'harness_input') {
    const attachmentPath = normalizeReferenceInputPath(attachment.url)
    const referencePath = normalizeReferenceInputPath(reference.source.path)
    return attachmentPath && referencePath && attachmentPath === referencePath ? reference : null
  }

  if (reference.source.type === 'workspace_file') {
    const attachmentPath = normalizeWorkspaceReferencePath(attachment.url)
    const referencePath = normalizeWorkspaceReferencePath(reference.source.path)
    return attachmentPath && referencePath && attachmentPath === referencePath ? reference : null
  }

  if (reference.source.type === 'home_asset') {
    const attachmentUrl = normalizeHomeAssetUrl(attachment.url)
    const referenceUrl = normalizeHomeAssetUrl(reference.source.url)
    return attachmentUrl && referenceUrl && attachmentUrl === referenceUrl ? reference : null
  }

  return null
}

function buildUploadAttachmentReference(url: string | undefined, name?: string): MediaReferenceData | null {
  const path = normalizeReferenceInputPath(url)
  if (!path) {
    return null
  }

  return {
    id: `upload:${path}`,
    kind: 'upload_attachment',
    media_type: 'image',
    display_name: name || getAttachmentName(path),
    source: {
      type: 'harness_input',
      path,
    },
  }
}

function buildWorkspaceFileReference(url: string | undefined, name?: string | null): MediaReferenceData | null {
  const path = normalizeWorkspaceReferencePath(url)
  if (!path) {
    return null
  }

  return {
    id: `workspace-file:${path}`,
    kind: 'workspace_file',
    media_type: 'image',
    display_name: name || getAttachmentName(path),
    source: {
      type: 'workspace_file',
      path,
    },
  }
}

function buildHomeAssetReference(url: string | undefined, name?: string | null): MediaReferenceData | null {
  const normalizedUrl = normalizeHomeAssetUrl(url)
  if (!normalizedUrl) {
    return null
  }

  return {
    id: `home-asset:${normalizedUrl}`,
    kind: 'home_asset',
    media_type: 'image',
    display_name: name || getAttachmentName(normalizedUrl),
    source: {
      type: 'home_asset',
      url: normalizedUrl,
    },
  }
}

function normalizeReferenceInputPath(value: string | undefined): string | null {
  const path = String(value || '').trim().replace(/\\/g, '/').replace(/^\.\//, '')
  if (!path.startsWith('references/inputs/')) return null
  if (path.split('/').some((part) => part === '' || part === '.' || part === '..')) return null
  return path
}

function normalizeWorkspaceReferencePath(value: string | undefined): string | null {
  const path = normalizeWorkspaceAttachmentPathByPolicy(value)
  if (!path || path.startsWith('references/inputs/')) {
    return null
  }
  if (path.split('/').some((part) => part === '' || part === '.' || part === '..')) return null
  return path
}

function normalizeHomeAssetUrl(value: string | undefined): string | null {
  const url = String(value || '').trim()
  if (!url || /\s/.test(url)) return null
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/api/v1/')) return url
  return null
}

function getAttachmentName(value: string): string {
  const clean = String(value || '').split(/[?#]/)[0]
  return clean.split('/').filter(Boolean).pop() || 'image'
}
