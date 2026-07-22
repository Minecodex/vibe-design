import {
  File,
  FileCode,
  FileText,
  Image as ImageIcon,
  LayoutTemplate,
  Presentation,
  TableProperties,
  Video,
} from 'lucide-react'

export type HomeHarnessAttachmentKind =
  | 'image'
  | 'video'
  | 'document'
  | 'spreadsheet'
  | 'presentation'
  | 'html'
  | 'code'
  | 'text'
  | 'other'

export interface HomeHarnessAttachmentLike {
  name?: string
  path?: string
  type?: string | null
}

export interface HomeHarnessAttachmentPresentation {
  icon: typeof File
  color: string
  bg: string
}

const HOME_HARNESS_ATTACHMENT_EXTENSIONS = [
  'txt',
  'md',
  'markdown',
  'csv',
  'json',
  'jsonl',
  'yaml',
  'yml',
  'toml',
  'xml',
  'html',
  'htm',
  'css',
  'js',
  'ts',
  'jsx',
  'tsx',
  'py',
  'sh',
  'sql',
  'ini',
  'conf',
  'log',
  'doc',
  'docx',
  'xlsx',
] as const

const HOME_HARNESS_ATTACHMENT_ACCEPT_EXTENSIONS = HOME_HARNESS_ATTACHMENT_EXTENSIONS
  .map(extension => `.${extension}`)
  .join(',')

export const HOME_HARNESS_ATTACHMENT_ACCEPT = `image/*,${HOME_HARNESS_ATTACHMENT_ACCEPT_EXTENSIONS}`

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg', 'avif', 'heic'])
const VIDEO_EXTENSIONS = new Set(['mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv'])
const DOCUMENT_EXTENSIONS = new Set(['doc', 'docx'])
const SPREADSHEET_EXTENSIONS = new Set(['xls', 'xlsx', 'csv'])
const PRESENTATION_EXTENSIONS = new Set(['ppt', 'pptx'])
const HTML_EXTENSIONS = new Set(['html', 'htm'])
const CODE_EXTENSIONS = new Set(['js', 'ts', 'jsx', 'tsx', 'py', 'sh', 'sql'])
const TEXT_EXTENSIONS = new Set(['txt', 'md', 'markdown', 'json', 'jsonl', 'yaml', 'yml', 'toml', 'xml', 'css', 'ini', 'conf', 'log'])

const PRESENTATIONS: Record<HomeHarnessAttachmentKind, HomeHarnessAttachmentPresentation> = {
  image: { icon: ImageIcon, color: 'text-amber-500', bg: 'bg-amber-500/10' },
  video: { icon: Video, color: 'text-violet-500', bg: 'bg-violet-500/10' },
  document: { icon: FileText, color: 'text-indigo-500', bg: 'bg-indigo-500/10' },
  spreadsheet: { icon: TableProperties, color: 'text-emerald-500', bg: 'bg-emerald-500/10' },
  presentation: { icon: Presentation, color: 'text-rose-500', bg: 'bg-rose-500/10' },
  html: { icon: LayoutTemplate, color: 'text-purple-500', bg: 'bg-purple-500/10' },
  code: { icon: FileCode, color: 'text-blue-500', bg: 'bg-blue-500/10' },
  text: { icon: FileText, color: 'text-zinc-500', bg: 'bg-zinc-500/10' },
  other: { icon: File, color: 'text-zinc-400', bg: 'bg-zinc-400/10' },
}

export function getHomeHarnessAttachmentPresentation(kind: HomeHarnessAttachmentKind): HomeHarnessAttachmentPresentation {
  return PRESENTATIONS[kind] || PRESENTATIONS.other
}

export function isSupportedHomeHarnessAttachmentFile(file: Pick<HomeHarnessAttachmentLike, 'name' | 'type'>): boolean {
  return inferHomeHarnessAttachmentKind(file) !== 'other'
}

export function filterSupportedHomeHarnessAttachmentFiles(files: File[]): { supported: File[]; unsupported: File[] } {
  const supported: File[] = []
  const unsupported: File[] = []

  for (const file of files) {
    if (isSupportedHomeHarnessAttachmentFile(file)) {
      supported.push(file)
    } else {
      unsupported.push(file)
    }
  }

  return { supported, unsupported }
}

export function inferHomeHarnessAttachmentKind(file: HomeHarnessAttachmentLike): HomeHarnessAttachmentKind {
  const extension = getFileExtension(file)
  const fileType = String(file.type || '').toLowerCase()

  if (fileType.startsWith('image/') || IMAGE_EXTENSIONS.has(extension)) {
    return 'image'
  }
  if (fileType.startsWith('video/') || VIDEO_EXTENSIONS.has(extension)) {
    return 'video'
  }
  if (DOCUMENT_EXTENSIONS.has(extension) || fileType === 'application/msword' || fileType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') {
    return 'document'
  }
  if (SPREADSHEET_EXTENSIONS.has(extension) || fileType === 'application/vnd.ms-excel' || fileType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') {
    return 'spreadsheet'
  }
  if (PRESENTATION_EXTENSIONS.has(extension) || fileType === 'application/vnd.ms-powerpoint' || fileType === 'application/vnd.openxmlformats-officedocument.presentationml.presentation') {
    return 'presentation'
  }
  if (HTML_EXTENSIONS.has(extension) || fileType === 'text/html' || fileType === 'application/xhtml+xml') {
    return 'html'
  }
  if (CODE_EXTENSIONS.has(extension)) {
    return 'code'
  }
  if (TEXT_EXTENSIONS.has(extension) || fileType.startsWith('text/') || fileType === 'application/json' || fileType === 'application/xml') {
    return 'text'
  }
  return 'other'
}

export function getHomeHarnessAttachmentAccept(): string {
  return HOME_HARNESS_ATTACHMENT_ACCEPT
}

function getFileExtension(file: Pick<HomeHarnessAttachmentLike, 'name' | 'path'>): string {
  return String(file.name || file.path || '').split('.').pop()?.toLowerCase() || ''
}
