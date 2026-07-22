import type { AttachmentData } from '@/api/endpoints/agent'

export const PENDING_ATTACHMENT_THUMBNAIL_MAX_SIZE = 256
export const PENDING_ATTACHMENT_THUMBNAIL_QUALITY = 0.82
const PENDING_ATTACHMENT_PREVIEW_CONCURRENCY = 2

export interface PendingAttachmentPreviewOptions {
  maxSize?: number
  mimeType?: string
  quality?: number
}

export interface PendingAttachmentPreviewResult {
  preview_url?: string
  _previewObjectUrl?: string
}

type QueueTask<T> = {
  run: () => Promise<T>
  resolve: (value: T) => void
  reject: (error: unknown) => void
}

let activePreviewTasks = 0
const pendingPreviewTasks: QueueTask<unknown>[] = []

export function createPendingAttachmentId(): string {
  return `pending-${globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`}`
}

export function enqueueLocalImageThumbnail(
  file: File,
  options: PendingAttachmentPreviewOptions = {},
): Promise<PendingAttachmentPreviewResult> {
  return enqueuePreviewTask(async () => {
    try {
      const objectUrl = await createLocalImageThumbnailUrl(file, options)
      return objectUrl
        ? { preview_url: objectUrl, _previewObjectUrl: objectUrl }
        : {}
    } finally {
      await yieldToMainThread()
    }
  })
}

export async function createLocalImageThumbnailUrl(
  file: File,
  options: PendingAttachmentPreviewOptions = {},
): Promise<string | null> {
  if (!String(file.type || '').toLowerCase().startsWith('image/')) {
    return null
  }

  const maxSize = options.maxSize ?? PENDING_ATTACHMENT_THUMBNAIL_MAX_SIZE
  const mimeType = options.mimeType ?? 'image/webp'
  const quality = options.quality ?? PENDING_ATTACHMENT_THUMBNAIL_QUALITY

  let decoded: DecodedImageSource | null = null
  try {
    decoded = await decodeImageSource(file)
    const { width, height } = fitInside(decoded.width, decoded.height, maxSize)
    const blob = await renderImageSourceToBlob(decoded.source, width, height, mimeType, quality)
    return blob ? URL.createObjectURL(blob) : null
  } catch {
    return null
  } finally {
    decoded?.close?.()
  }
}

export function collectAttachmentBlobUrls(attachments: Array<AttachmentData | null | undefined>): string[] {
  const urls = new Set<string>()
  for (const attachment of attachments) {
    if (!attachment) continue
    for (const value of [attachment.url, attachment.preview_url, attachment._previewObjectUrl]) {
      if (typeof value === 'string' && value.startsWith('blob:')) {
        urls.add(value)
      }
    }
  }
  return Array.from(urls)
}

export function revokeAttachmentBlobUrls(attachments: Array<AttachmentData | null | undefined>): void {
  for (const url of collectAttachmentBlobUrls(attachments)) {
    URL.revokeObjectURL(url)
  }
}

export function stripTransientAttachmentFields(attachment: AttachmentData): AttachmentData {
  const {
    _localFile: _localFile,
    _previewObjectUrl: _previewObjectUrl,
    _clientAttachmentId: _clientAttachmentId,
    preview_url: _previewUrl,
    ...rest
  } = attachment
  return rest
}

function enqueuePreviewTask<T>(run: () => Promise<T>): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    pendingPreviewTasks.push({ run, resolve, reject } as QueueTask<unknown>)
    drainPreviewQueue()
  })
}

function drainPreviewQueue(): void {
  while (activePreviewTasks < PENDING_ATTACHMENT_PREVIEW_CONCURRENCY && pendingPreviewTasks.length > 0) {
    const task = pendingPreviewTasks.shift()
    if (!task) return
    activePreviewTasks += 1
    task.run()
      .then(task.resolve, task.reject)
      .finally(() => {
        activePreviewTasks -= 1
        drainPreviewQueue()
      })
  }
}

interface DecodedImageSource {
  source: CanvasImageSource
  width: number
  height: number
  close?: () => void
}

async function decodeImageSource(file: File): Promise<DecodedImageSource> {
  if (typeof createImageBitmap === 'function') {
    const bitmap = await createImageBitmap(file)
    return {
      source: bitmap,
      width: bitmap.width,
      height: bitmap.height,
      close: () => bitmap.close?.(),
    }
  }
  return decodeImageElement(file)
}

function decodeImageElement(file: File): Promise<DecodedImageSource> {
  return new Promise((resolve, reject) => {
    const objectUrl = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      resolve({
        source: image,
        width: image.naturalWidth || image.width,
        height: image.naturalHeight || image.height,
        close: () => URL.revokeObjectURL(objectUrl),
      })
    }
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl)
      reject(new Error('Failed to decode pending attachment image'))
    }
    image.decoding = 'async'
    image.src = objectUrl
  })
}

async function renderImageSourceToBlob(
  source: CanvasImageSource,
  width: number,
  height: number,
  mimeType: string,
  quality: number,
): Promise<Blob | null> {
  if (typeof OffscreenCanvas !== 'undefined') {
    const canvas = new OffscreenCanvas(width, height)
    const context = canvas.getContext('2d')
    if (!context) return null
    context.drawImage(source, 0, 0, width, height)
    return canvas.convertToBlob({ type: mimeType, quality })
  }

  if (typeof document === 'undefined') {
    return null
  }

  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const context = canvas.getContext('2d')
  if (!context) return null
  context.drawImage(source, 0, 0, width, height)
  return new Promise((resolve) => {
    canvas.toBlob((blob) => resolve(blob), mimeType, quality)
  })
}

function fitInside(width: number, height: number, maxSize: number): { width: number; height: number } {
  const safeWidth = Math.max(1, width)
  const safeHeight = Math.max(1, height)
  const scale = Math.min(1, maxSize / Math.max(safeWidth, safeHeight))
  return {
    width: Math.max(1, Math.round(safeWidth * scale)),
    height: Math.max(1, Math.round(safeHeight * scale)),
  }
}

function yieldToMainThread(): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, 0))
}
