import { normalizeHarnessWorkspacePath } from '@/api/endpoints/agent'

import {
  isSessionHtmlFile,
  isSessionMarkdownFile,
  isSessionOfficeDocFile,
  isSessionOfficeSheetFile,
  isSessionPresentationFile,
  isSessionTextLikeFile,
} from './homeChatWorkspaceFileKinds'
import type { SessionFileItem } from '../homeHarnessPageUtils'

export const HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME = 'workspace-file-reference:'

const WORKSPACE_ROOT_PREFIXES = [
  'references/inputs/',
  'references/sources/',
  'references/generated/',
  'file_versions/',
  'project/',
  'published/',
  'skill/',
]

const SUPPORTED_FILE_EXTENSIONS = [
  'png',
  'jpg',
  'jpeg',
  'gif',
  'webp',
  'bmp',
  'svg',
  'mp4',
  'webm',
  'mov',
  'm4v',
  'avi',
  'md',
  'markdown',
  'html',
  'htm',
  'doc',
  'docx',
  'xls',
  'xlsx',
  'csv',
  'ppt',
  'pptx',
  'zip',
  'txt',
  'text',
  'json',
  'jsonl',
  'ts',
  'tsx',
  'js',
  'jsx',
  'py',
  'css',
  'scss',
  'sass',
  'less',
  'java',
  'go',
  'rs',
  'c',
  'cpp',
  'h',
  'hpp',
  'cs',
  'php',
  'rb',
  'sh',
  'bash',
  'zsh',
  'sql',
  'yaml',
  'yml',
  'toml',
  'ini',
  'log',
] as const

const SUPPORTED_EXTENSION_PATTERN = [...SUPPORTED_FILE_EXTENSIONS].sort((a, b) => b.length - a.length).join('|')
const FILE_REFERENCE_TOKEN_PATTERN = new RegExp(
  String.raw`(?:sandbox:\/+)?(?:(?:code\/files|files|references\/(?:inputs|sources|generated)|file_versions|project|published|skill|code)\/)?[^\s"'<>()[\]{}，。！？、；：,.!?;:]+?\.(${SUPPORTED_EXTENSION_PATTERN})`,
  'gi',
)

export interface WorkspaceFileReferenceResolver {
  getFileForHref: (href: string | null | undefined) => SessionFileItem | null
  getFileForInlineCode: (value: string) => SessionFileItem | null
  remarkPlugin: () => (tree: Record<string, unknown>) => void
}

export function encodeWorkspaceFileReferenceHref(file: SessionFileItem): string {
  return `${HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME}${encodeURIComponent(normalizeFilePath(file.path))}`
}

export function decodeWorkspaceFileReferenceHref(href: string | null | undefined): string | null {
  const value = String(href || '')
  if (!value.startsWith(HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME)) {
    return null
  }
  try {
    return decodeURIComponent(value.slice(HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME.length))
  } catch {
    return value.slice(HOME_CHAT_WORKSPACE_FILE_REFERENCE_SCHEME.length)
  }
}

export function createWorkspaceFileReferenceResolver(
  workspaceFiles: SessionFileItem[] | null | undefined,
): WorkspaceFileReferenceResolver | null {
  const supportedFiles = (workspaceFiles || []).filter(isPreviewableSessionFile)
  if (supportedFiles.length === 0) {
    return null
  }

  const byPath = new Map<string, SessionFileItem>()
  const byName = new Map<string, SessionFileItem | null>()

  for (const file of supportedFiles) {
    const candidatePaths = getWorkspaceFileReferenceCandidatePaths(file)
    const normalizedPath = normalizeFilePath(candidatePaths[0] || file.path)
    for (const candidatePath of candidatePaths) {
      const normalizedCandidate = normalizeFilePath(candidatePath)
      if (!normalizedCandidate) {
        continue
      }
      byPath.set(toLookupKey(normalizedCandidate), file)
      byPath.set(toLookupKey(String(candidatePath || '').replace(/\\/g, '/')), file)
    }

    const name = String(file.name || normalizedPath.split('/').pop() || '').trim()
    if (!name) {
      continue
    }
    const nameKey = toLookupKey(name)
    byName.set(nameKey, byName.has(nameKey) ? null : file)
  }

  const getFileForPath = (rawValue: string, allowUniqueNameFallback: boolean): SessionFileItem | null => {
    const trimmed = trimFileReferenceToken(rawValue)
    if (!trimmed || isExternalReference(trimmed)) {
      return null
    }

    const explicitReferencePath = decodeWorkspaceFileReferenceHref(trimmed)
    const lookupValue = explicitReferencePath || trimmed
    const normalized = normalizeFilePath(lookupValue)
    if (!normalized) {
      return null
    }

    const exactMatch = byPath.get(toLookupKey(normalized)) || byPath.get(toLookupKey(lookupValue.replace(/\\/g, '/')))
    if (exactMatch) {
      return exactMatch
    }

    if (!allowUniqueNameFallback || lookupValue.includes('/') || lookupValue.includes('\\')) {
      return null
    }

    return byName.get(toLookupKey(lookupValue)) || null
  }

  const resolver: WorkspaceFileReferenceResolver = {
    getFileForHref: (href) => getFileForPath(String(href || ''), false),
    getFileForInlineCode: (value) => getFileForPath(value, true),
    remarkPlugin: () => (tree) => {
      visitMarkdownTextNodes(tree, (text) => splitTextWithFileReferenceLinks(text, getFileForPath))
    },
  }

  return resolver
}

export function isPreviewableSessionFile(file: SessionFileItem): boolean {
  return isImageLikeSessionFile(file)
    || isVideoLikeSessionFile(file)
    || isSessionMarkdownFile(file)
    || isSessionHtmlFile(file)
    || isSessionOfficeDocFile(file)
    || isSessionOfficeSheetFile(file)
    || isSessionPresentationFile(file)
    || isSessionTextLikeFile(file)
    || getWorkspaceFileReferenceCandidatePaths(file).some((candidatePath) => (
      isKnownPreviewableExtension(getFileExtension(candidatePath))
    ))
}

export function inferWorkspaceFileTypeFromPath(filePath: string): string {
  const extension = getFileExtension(filePath)
  if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].includes(extension)) {
    return 'image'
  }
  if (['mp4', 'webm', 'mov', 'm4v', 'avi'].includes(extension)) {
    return 'video'
  }
  if (['md', 'markdown'].includes(extension)) {
    return 'text'
  }
  if (['html', 'htm'].includes(extension)) {
    return 'html'
  }
  if (['doc', 'docx'].includes(extension)) {
    return 'document'
  }
  if (['xls', 'xlsx', 'csv'].includes(extension)) {
    return 'spreadsheet'
  }
  if (['ppt', 'pptx'].includes(extension)) {
    return 'presentation'
  }
  if (SUPPORTED_FILE_EXTENSIONS.includes(extension as typeof SUPPORTED_FILE_EXTENSIONS[number])) {
    return 'code'
  }
  return 'text'
}

function splitTextWithFileReferenceLinks(
  text: string,
  getFileForPath: (rawValue: string, allowUniqueNameFallback: boolean) => SessionFileItem | null,
): Array<Record<string, unknown>> {
  const nodes: Array<Record<string, unknown>> = []
  let cursor = 0

  FILE_REFERENCE_TOKEN_PATTERN.lastIndex = 0
  for (const match of text.matchAll(FILE_REFERENCE_TOKEN_PATTERN)) {
    const token = match[0]
    const index = match.index ?? 0
    const file = getFileForPath(token, true)
    if (!file) {
      continue
    }

    if (index > cursor) {
      nodes.push({ type: 'text', value: text.slice(cursor, index) })
    }
    nodes.push({
      type: 'link',
      url: encodeWorkspaceFileReferenceHref(file),
      title: null,
      children: [{ type: 'text', value: file.name || token }],
    })
    cursor = index + token.length
  }

  if (nodes.length === 0) {
    return [{ type: 'text', value: text }]
  }
  if (cursor < text.length) {
    nodes.push({ type: 'text', value: text.slice(cursor) })
  }
  return nodes
}

function visitMarkdownTextNodes(
  node: Record<string, unknown>,
  transformText: (text: string) => Array<Record<string, unknown>>,
) {
  if (!node || typeof node !== 'object' || !Array.isArray(node.children)) {
    return
  }

  if (['link', 'image', 'code', 'inlineCode'].includes(String(node.type || ''))) {
    return
  }

  const nextChildren: Array<Record<string, unknown>> = []
  for (const child of node.children) {
    if (child?.type === 'text' && typeof child.value === 'string') {
      nextChildren.push(...transformText(child.value))
      continue
    }
    visitMarkdownTextNodes(child, transformText)
    nextChildren.push(child)
  }
  node.children = nextChildren
}

function trimFileReferenceToken(value: string): string {
  return String(value || '').trim().replace(/[，。！？、；：,.!?;:]+$/u, '')
}

function normalizeFilePath(value: string): string {
  return normalizeHarnessWorkspacePath(trimFileReferenceToken(value)).replace(/\\/g, '/')
}

function isExternalReference(value: string): boolean {
  const trimmed = String(value || '').trim()
  if (/^(https?:|data:|blob:)/i.test(trimmed)) {
    return true
  }
  if (!trimmed.startsWith('/')) {
    return false
  }
  const normalized = normalizeFilePath(trimmed)
  return !WORKSPACE_ROOT_PREFIXES.some((prefix) => normalized.startsWith(prefix))
}

function isImageLikeSessionFile(file: SessionFileItem): boolean {
  return file.type === 'image'
    || ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'].some((extension) => hasCandidateExtension(file, extension))
}

function isVideoLikeSessionFile(file: SessionFileItem): boolean {
  return file.type === 'video'
    || ['mp4', 'webm', 'mov', 'm4v', 'avi'].some((extension) => hasCandidateExtension(file, extension))
}

function getWorkspaceFileReferenceCandidatePaths(file: SessionFileItem): string[] {
  const artifactMetadata = file.artifact_metadata || {}
  return [
    file.path,
    file.current_version_path,
    artifactMetadata.relative_path,
    artifactMetadata.source_path,
    artifactMetadata.original_path,
    artifactMetadata.preview_path,
  ]
    .map((value) => String(value || '').trim())
    .filter((value, index, values) => value && values.indexOf(value) === index)
}

function hasCandidateExtension(file: SessionFileItem, extension: string): boolean {
  return [file.name, ...getWorkspaceFileReferenceCandidatePaths(file)]
    .some((value) => getFileExtension(value) === extension)
}

function isKnownPreviewableExtension(extension: string): boolean {
  return SUPPORTED_FILE_EXTENSIONS.includes(extension as typeof SUPPORTED_FILE_EXTENSIONS[number])
}

function getFileExtension(filePath: string): string {
  return String(filePath || '').split('?')[0]?.split('#')[0]?.split('.').pop()?.toLowerCase() || ''
}

function toLookupKey(value: string): string {
  return String(value || '').trim().replace(/\\/g, '/').toLowerCase()
}
