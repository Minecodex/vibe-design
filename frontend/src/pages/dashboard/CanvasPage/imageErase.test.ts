import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  buildImageEraseResultItem,
  createImageEraseTaskItem,
} from './imageErase'

describe('imageErase', () => {
  const sourceItem: CanvasItem = {
    id: 'image-1',
    type: 'image',
    url: 'https://example.com/source.png',
    x: 120,
    y: 64,
    width: 320,
    height: 180,
    z_index: 8,
    asset_origin: 'local_upload',
  }

  it('creates a nearby generating placeholder that preserves the source display size', () => {
    const taskItem = createImageEraseTaskItem({
      sourceItem,
      canvasItems: [sourceItem],
      taskId: 'image-erase-task',
    })

    expect(taskItem.type).toBe('image_generator')
    expect(taskItem.width).toBe(320)
    expect(taskItem.height).toBe(180)
    expect(taskItem.status).toBe('generating')
    expect(taskItem.generation_kind).toBe('image_erase')
    expect(taskItem.x).toBe(464)
    expect(taskItem.y).toBe(64)
  })

  it('replaces a completed erase placeholder with a final image item', () => {
    const taskItem = createImageEraseTaskItem({
      sourceItem,
      canvasItems: [sourceItem],
      taskId: 'image-erase-task',
    })

    const resultItem = buildImageEraseResultItem({
      taskItem,
      resultUrl: 'https://example.com/result.png',
      resultSize: { width: 640, height: 320 },
    })

    expect(resultItem).toMatchObject({
      id: taskItem.id,
      type: 'image',
      url: 'https://example.com/result.png',
      asset_origin: 'ai_generated',
      generation_kind: 'image_erase',
    })
    expect(resultItem.x + (resultItem.width || 0) / 2).toBe(taskItem.x + (taskItem.width || 0) / 2)
    expect(resultItem.y + (resultItem.height || 0) / 2).toBe(taskItem.y + (taskItem.height || 0) / 2)
  })
})
