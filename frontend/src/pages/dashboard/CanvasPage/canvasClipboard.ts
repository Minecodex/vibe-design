export const CANVAS_CLIPBOARD_EVENT_MIME = 'application/x-openai-canvas-items+json'
export const CANVAS_CLIPBOARD_MIME = `web ${CANVAS_CLIPBOARD_EVENT_MIME}`
export const CANVAS_CLIPBOARD_TEXT_PREFIX = '__OPENAI_CANVAS__:'

export function serializeCanvasClipboardPayload(items: any[]) {
  return JSON.stringify({
    version: 1,
    items,
  })
}

export function serializeCanvasClipboardTextMarker(items: any[]) {
  return `${CANVAS_CLIPBOARD_TEXT_PREFIX}${serializeCanvasClipboardPayload(items)}`
}

export function writeCanvasClipboardMarkerToClipboardData(clipboardData: DataTransfer | null | undefined, items: any[]) {
  if (!clipboardData || !Array.isArray(items) || items.length === 0 || typeof clipboardData.setData !== 'function') {
    return false
  }

  const serializedPayload = serializeCanvasClipboardPayload(items)
  clipboardData.setData(
    CANVAS_CLIPBOARD_EVENT_MIME,
    serializedPayload,
  )
  clipboardData.setData('text/plain', `${CANVAS_CLIPBOARD_TEXT_PREFIX}${serializedPayload}`)
  return true
}

export function clipboardDataHasCanvasClipboardMarker(clipboardData?: DataTransfer | null) {
  if (!clipboardData) return false
  const types = Array.from(clipboardData.types || [])
  if (
    types.includes(CANVAS_CLIPBOARD_EVENT_MIME)
    || types.includes(CANVAS_CLIPBOARD_MIME)
  ) {
    return true
  }

  if (types.includes('text/plain') && typeof clipboardData.getData === 'function') {
    return clipboardData.getData('text/plain').startsWith(CANVAS_CLIPBOARD_TEXT_PREFIX)
  }

  return false
}

export async function inspectSystemClipboardPasteKind() {
  if (typeof navigator === 'undefined' || typeof navigator.clipboard?.read !== 'function') {
    return null
  }

  try {
    const clipboardItems = await navigator.clipboard.read()
    return {
      hasCanvasClipboardMarker: clipboardItems.some((item) => item.types.includes(CANVAS_CLIPBOARD_MIME)),
      hasImage: clipboardItems.some((item) => item.types.some((type) => type.startsWith('image/'))),
    }
  } catch (error) {
    console.warn('[canvas clipboard] Failed to inspect system clipboard:', error)
    return null
  }
}
