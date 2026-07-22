import type { CanvasItem } from '@/api/endpoints/projects'

export function canPhotoshopEditSelection(selectedItems: string[], firstSelectedItemType?: string | null) {
  return selectedItems.length === 1 && firstSelectedItemType === 'image'
}

export function buildPhotoshopEditPayload(item: Pick<CanvasItem, 'id' | 'url'>) {
  return {
    source_canvas_item_id: item.id,
    svg_url: item.url,
  }
}
