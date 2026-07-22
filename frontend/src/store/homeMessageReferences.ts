import type { AttachmentData, MediaReferenceData } from '@/api/endpoints/agent'
import { normalizeWorkspaceAttachmentPathByPolicy } from '@/utils/harnessWorkspacePathPolicy'

export function buildHomeMediaReferences(
    attachments: AttachmentData[] | null | undefined,
): MediaReferenceData[] | null {
    const seen = new Set<string>()
    const references: MediaReferenceData[] = []

    for (const attachment of attachments || []) {
        if (attachment.type !== 'image') {
            continue
        }

        const explicitReference = normalizeExplicitAttachmentReference(attachment)
        if (explicitReference) {
            if (seen.has(explicitReference.id)) continue
            seen.add(explicitReference.id)
            references.push(explicitReference)
            continue
        }

        const path = normalizeReferenceInputPath(attachment.url)
        if (path) {
            const id = `upload:${path}`
            if (seen.has(id)) continue
            seen.add(id)
            references.push({
                id,
                kind: 'upload_attachment' as const,
                media_type: 'image' as const,
                display_name: attachment.name || path.split('/').pop() || 'image',
                source: {
                    type: 'harness_input' as const,
                    path,
                },
            })
            continue
        }

        const workspacePath = normalizeWorkspaceReferencePath(attachment.url)
        if (workspacePath) {
            const id = `workspace-file:${workspacePath}`
            if (seen.has(id)) continue
            seen.add(id)
            references.push({
                id,
                kind: 'workspace_file' as const,
                media_type: 'image' as const,
                display_name: attachment.name || workspacePath.split('/').pop() || 'image',
                source: {
                    type: 'workspace_file' as const,
                    path: workspacePath,
                },
            })
            continue
        }

        const assetUrl = normalizeHomeAssetUrl(attachment.url)
        if (assetUrl) {
            const id = `home-asset:${assetUrl}`
            if (seen.has(id)) continue
            seen.add(id)
            references.push({
                id,
                kind: 'home_asset' as const,
                media_type: 'image' as const,
                display_name: attachment.name || assetUrl.split('/').pop() || 'image',
                source: {
                    type: 'home_asset' as const,
                    url: assetUrl,
                },
            })
        }
    }

    return references.length > 0 ? references : null
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

export function buildHomeUploadReferences(
    attachments: AttachmentData[] | null | undefined,
): MediaReferenceData[] | null {
    return buildHomeMediaReferences(attachments)
}

function normalizeReferenceInputPath(value: string | undefined): string | null {
    const path = String(value || '').trim().replace(/\\/g, '/').replace(/^\.\//, '')
    if (!path.startsWith('references/inputs/')) return null
    if (path.split('/').some((part) => part === '' || part === '.' || part === '..')) return null
    return path
}

function normalizeWorkspaceReferencePath(value: string | undefined): string | null {
    const path = normalizeWorkspaceAttachmentPathByPolicy(value)
    if (!path) return null
    if (path.startsWith('references/inputs/')) return null
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
