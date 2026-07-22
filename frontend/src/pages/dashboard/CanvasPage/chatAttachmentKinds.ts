import type { AttachmentData } from '@/api/endpoints/agent'
import {
  createPendingAttachmentId,
  enqueueLocalImageThumbnail,
  type PendingAttachmentPreviewResult,
} from '../agentMedia/agentPendingAttachmentPreview'

export type CanvasChatAttachmentKind =
  | 'image'
  | 'text'
  | 'document'
  | 'spreadsheet'
  | 'html'
  | 'other'

const CANVAS_CHAT_ATTACHMENT_EXTENSIONS = [
  'txt',
  'md',
  'doc',
  'docx',
  'xlsx',
  'csv',
  'html',
  'htm',
] as const

const CANVAS_CHAT_ATTACHMENT_ACCEPT_EXTENSIONS = CANVAS_CHAT_ATTACHMENT_EXTENSIONS
  .map((extension) => `.${extension}`)
  .join(',')

export const CANVAS_CHAT_ATTACHMENT_ACCEPT = `image/*,${CANVAS_CHAT_ATTACHMENT_ACCEPT_EXTENSIONS}`

const IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'])
const TEXT_EXTENSIONS = new Set(['txt', 'md'])
const DOCUMENT_EXTENSIONS = new Set(['doc', 'docx'])
const SPREADSHEET_EXTENSIONS = new Set(['xlsx', 'csv'])
const HTML_EXTENSIONS = new Set(['html', 'htm'])

export interface CanvasChatAttachmentLike {
  name?: string
  path?: string
  type?: string | null
}

export function inferCanvasChatAttachmentKind(file: CanvasChatAttachmentLike): CanvasChatAttachmentKind {
  const extension = getFileExtension(file)
  const fileType = String(file.type || '').toLowerCase()

  if (fileType.startsWith('image/') || IMAGE_EXTENSIONS.has(extension)) {
    return 'image'
  }
  if (TEXT_EXTENSIONS.has(extension) || fileType === 'text/plain' || fileType === 'text/markdown') {
    return 'text'
  }
  if (
    DOCUMENT_EXTENSIONS.has(extension)
    || fileType === 'application/msword'
    || fileType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
  ) {
    return 'document'
  }
  if (
    SPREADSHEET_EXTENSIONS.has(extension)
    || fileType === 'text/csv'
    || fileType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ) {
    return 'spreadsheet'
  }
  if (HTML_EXTENSIONS.has(extension) || fileType === 'text/html' || fileType === 'application/xhtml+xml') {
    return 'html'
  }
  return 'other'
}

export function isSupportedCanvasChatAttachmentFile(file: Pick<CanvasChatAttachmentLike, 'name' | 'type'>): boolean {
  return inferCanvasChatAttachmentKind(file) !== 'other'
}

export function filterSupportedCanvasChatAttachmentFiles(files: File[]): { supported: File[]; unsupported: File[] } {
  const supported: File[] = []
  const unsupported: File[] = []

  for (const file of files) {
    if (isSupportedCanvasChatAttachmentFile(file)) {
      supported.push(file)
    } else {
      unsupported.push(file)
    }
  }

  return { supported, unsupported }
}

export async function buildCanvasPendingAttachment(file: File): Promise<AttachmentData> {
  const kind = inferCanvasChatAttachmentKind(file)
  return {
    type: kind === 'image' ? 'image' : 'file',
    url: '',
    name: file.name,
    _localFile: file,
    _clientAttachmentId: createPendingAttachmentId(),
  }
}

export function loadCanvasPendingAttachmentPreview(file: File): Promise<PendingAttachmentPreviewResult> {
  if (inferCanvasChatAttachmentKind(file) !== 'image') {
    return Promise.resolve({})
  }
  return enqueueLocalImageThumbnail(file)
}

function getFileExtension(file: Pick<CanvasChatAttachmentLike, 'name' | 'path'>): string {
  return String(file.name || file.path || '').split('.').pop()?.toLowerCase() || ''
}
