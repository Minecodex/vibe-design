import type { MediaReferenceData } from '@/api/endpoints/agent'
import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'
import {
  CANVAS_MARK_TOKEN_PATTERN,
  CANVAS_MENTION_TOKEN_PATTERN,
  parseCanvasMarkToken,
  parseCanvasMentionToken,
} from './canvasReferenceTokens'

export function buildCanvasMentionReferences(
  content: string,
  canvasItems: CanvasItem[],
  marks: CanvasMark[] = [],
): MediaReferenceData[] | null {
  const itemMap = new Map(canvasItems.map((item) => [String(item.id), item]))
  const seen = new Set<string>()
  const references: MediaReferenceData[] = []

  for (const match of content.matchAll(CANVAS_MENTION_TOKEN_PATTERN)) {
    const parsed = parseCanvasMentionToken(match)
    if (!parsed) continue
    const displayName = parsed.label
    const itemId = parsed.itemId
    if (!itemId || seen.has(itemId)) continue
    const item = itemMap.get(itemId)
    if (!item || !isReferenceableImageItem(item)) continue

    seen.add(itemId)
    references.push({
      id: `canvas:${itemId}`,
      kind: 'canvas_item',
      media_type: 'image',
      display_name: displayName || String(item.name || 'image'),
      source: {
        type: 'canvas_item',
        item_id: itemId,
      },
    })
  }

  const markMap = new Map(marks.map((mark) => [String(mark.id), mark]))
  for (const match of content.matchAll(CANVAS_MARK_TOKEN_PATTERN)) {
    const parsed = parseCanvasMarkToken(match)
    if (!parsed) continue
    const label = parsed.label
    const imageItemId = parsed.imageItemId
    const mark = markMap.get(parsed.markId)
    if (!mark || seen.has(`mark:${mark.id}`)) continue
    if (String(mark.imageItemId) !== imageItemId) continue
    const sourceItem = itemMap.get(imageItemId)
    if (!sourceItem || !isReferenceableImageItem(sourceItem)) continue

    const displayName = label || mark.customLabel || mark.selectedLabel || `mark ${mark.number}`
    seen.add(`mark:${mark.id}`)
    references.push({
      id: `canvas-mark:${mark.id}`,
      kind: 'canvas_mark',
      media_type: 'image',
      display_name: displayName,
      source: {
        type: 'canvas_mark',
        mark_id: String(mark.id),
        image_item_id: imageItemId,
      },
      mark: {
        id: String(mark.id),
        image_item_id: imageItemId,
        number: mark.number,
        label: displayName,
        position: { x: parsed.x, y: parsed.y },
      },
    })
  }

  return references.length > 0 ? references : null
}

function isReferenceableImageItem(item: CanvasItem): boolean {
  const type = String(item.type || '')
  const origin = String((item as any).asset_origin || '')
  const url = String((item as any).url || '')
  const artifactRef = String((item as any).artifact_ref || '')
  const isImageLike = type === 'image' || type === 'image_generator'
  if (!isImageLike) return false
  if (type === 'image_generator' && artifactRef) {
    return true
  }
  if (origin === 'local_upload') {
    return url.startsWith('/api/v1/uploads/canvas/')
  }
  return Boolean(artifactRef) && origin === 'ai_generated'
}
