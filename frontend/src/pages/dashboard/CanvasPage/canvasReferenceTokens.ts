export interface ParsedCanvasMentionToken {
  label: string
  itemId: string
}

export interface ParsedCanvasMarkToken {
  label: string
  markId: string
  imageItemId: string
  x: number
  y: number
}

export const CANVAS_MENTION_TOKEN_PATTERN = /@\[([^\]]+)\]\((canvas:[^)]+)\)/g
export const CANVAS_MARK_TOKEN_PATTERN = /#\[([^\]]*)\]\((canvas-mark:[^)]*)\)/g

export function serializeCanvasMentionToken(label: string, itemId: string): string {
  return `@[${label}](canvas:${itemId})`
}

export function serializeCanvasMarkToken(
  label: string,
  markId: string,
  imageItemId: string,
  x: string | number,
  y: string | number,
): string {
  return `#[${label}](canvas-mark:${markId}:image:${imageItemId}:x:${x}:y:${y})`
}

export function parseCanvasMentionTarget(target: string | null | undefined): string | null {
  const raw = String(target || '').trim()
  if (!raw.startsWith('canvas:')) return null
  const itemId = raw.slice('canvas:'.length).trim()
  return itemId && !itemId.includes('/') && !itemId.includes('\\') ? itemId : null
}

export function parseCanvasMentionToken(match: RegExpMatchArray): ParsedCanvasMentionToken | null {
  const label = String(match[1] || '').trim()
  const itemId = parseCanvasMentionTarget(match[2])
  if (!label || !itemId) return null
  return { label, itemId }
}

export function parseCanvasMarkTarget(target: string | null | undefined): Omit<ParsedCanvasMarkToken, 'label'> | null {
  const raw = String(target || '').trim()
  const match = /^canvas-mark:([^:]+):image:([^:]+):x:([0-9.]+):y:([0-9.]+)$/.exec(raw)
  if (!match) return null
  const x = Number(match[3])
  const y = Number(match[4])
  if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || x > 1 || y < 0 || y > 1) return null
  return {
    markId: match[1],
    imageItemId: match[2],
    x,
    y,
  }
}

export function parseCanvasMarkToken(match: RegExpMatchArray): ParsedCanvasMarkToken | null {
  const label = String(match[1] || '').trim()
  const parsed = parseCanvasMarkTarget(match[2])
  if (!parsed) return null
  return { label, ...parsed }
}
