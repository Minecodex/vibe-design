import { isHtmlWorkspaceFilePath, type WorkspaceFileRead } from '@/api/endpoints/agent'
import { inferHomeHarnessAttachmentKind } from './homeChatAttachmentKinds'

export interface HomeChatSessionFileLike extends WorkspaceFileRead {
  previewUrl?: string
  source?: 'workspace' | 'generated'
}

function getWorkspaceFileExtension(file: Pick<HomeChatSessionFileLike, 'name' | 'path'>): string {
  return String(file.name || file.path || '').split('.').pop()?.toLowerCase() || ''
}

export function isSessionMarkdownFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'>) {
  return ['md', 'markdown'].includes(getWorkspaceFileExtension(file))
}

type HtmlPreviewableFile = Pick<HomeChatSessionFileLike, 'name' | 'path'> & {
  type?: string | null
  artifact_kind?: string | null
  artifact_metadata?: Record<string, unknown> | null
}

function isHtmlBundleArtifact(file: HtmlPreviewableFile) {
  const artifactMetadata = file.artifact_metadata || {}
  const artifactKind = String(file.artifact_kind || artifactMetadata.artifact_kind || '')
  const bundleFormat = String(artifactMetadata.bundle_format || '')
  const entry = String(artifactMetadata.entry || '').trim()
  return file.type === 'html_bundle'
    || artifactKind === 'web_bundle'
    || (bundleFormat === 'zip' && !!entry)
}

export function isSessionHtmlFile(file: HtmlPreviewableFile) {
  return isHtmlBundleArtifact(file) || isHtmlWorkspaceFilePath(file.name || file.path || '')
}

export function isSessionOfficeDocFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'>) {
  return ['doc', 'docx'].includes(getWorkspaceFileExtension(file))
}

export function isSessionOfficeSheetFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'>) {
  return ['xls', 'xlsx', 'csv'].includes(getWorkspaceFileExtension(file))
}

export function isSessionPresentationFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'>) {
  return ['ppt', 'pptx'].includes(getWorkspaceFileExtension(file))
}

export function isSessionTextLikeFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'> & { type?: string | null }) {
  if (
    isSessionMarkdownFile(file)
    || isSessionHtmlFile(file)
    || isSessionOfficeDocFile(file)
    || isSessionOfficeSheetFile(file)
    || isSessionPresentationFile(file)
  ) {
    return false
  }
  return ['code', 'text'].includes(inferHomeHarnessAttachmentKind(file))
}

export function isSessionOfficeEditableFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'>) {
  return isSessionOfficeDocFile(file) || isSessionOfficeSheetFile(file)
}

export function isSessionRailPreviewFile(file: Pick<HomeChatSessionFileLike, 'name' | 'path'> & { type?: string | null }) {
  return isSessionMarkdownFile(file)
    || isSessionHtmlFile(file)
    || isSessionOfficeDocFile(file)
    || isSessionOfficeSheetFile(file)
    || isSessionPresentationFile(file)
    || isSessionTextLikeFile(file)
}
