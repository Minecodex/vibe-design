import { describe, expect, it } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import {
  buildTextRedrawResultItem,
  createEditableTextRedrawSegments,
  createTextRedrawTaskItem,
  getTextRedrawPanelPosition,
} from './textRedraw'
import {
  TEXT_REDRAW_PANEL_TOKENS,
  getTextRedrawExtractingBadgeStyle,
} from './textRedrawUi'

describe('textRedraw', () => {
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
    const taskItem = createTextRedrawTaskItem({
      sourceItem,
      canvasItems: [sourceItem],
      taskId: 'text-redraw-task',
    })

    expect(taskItem.type).toBe('image_generator')
    expect(taskItem.width).toBe(320)
    expect(taskItem.height).toBe(180)
    expect(taskItem.status).toBe('generating')
    expect(taskItem.generation_kind).toBe('text_redraw')
    expect(taskItem.x).toBe(464)
    expect(taskItem.y).toBe(64)
  })

  it('creates editable segments while preserving original text', () => {
    const segments = createEditableTextRedrawSegments([
      { id: 'seg-1', text: 'MARSHALL', order: 1 },
      { id: 'seg-2', text: 'EST.1962', order: 2 },
    ])

    expect(segments).toEqual([
      { id: 'seg-1', text: 'MARSHALL', originalText: 'MARSHALL', order: 1 },
      { id: 'seg-2', text: 'EST.1962', originalText: 'EST.1962', order: 2 },
    ])
  })

  it('replaces a completed text redraw placeholder with a final image item', () => {
    const taskItem = createTextRedrawTaskItem({
      sourceItem,
      canvasItems: [sourceItem],
      taskId: 'text-redraw-task',
    })

    const resultItem = buildTextRedrawResultItem({
      taskItem,
      resultUrl: 'https://example.com/result.png',
    })

    expect(resultItem).toMatchObject({
      id: taskItem.id,
      type: 'image',
      url: 'https://example.com/result.png',
      asset_origin: 'ai_generated',
    })
  })

  it('uses the generated image size and preserves the placeholder center point', () => {
    const taskItem = createTextRedrawTaskItem({
      sourceItem,
      canvasItems: [sourceItem],
      taskId: 'text-redraw-task',
    })

    const resultItem = buildTextRedrawResultItem({
      taskItem,
      resultUrl: 'https://example.com/result.png',
      resultSize: {
        width: 640,
        height: 320,
      },
    })

    expect(resultItem.width).toBe(640)
    expect(resultItem.height).toBe(320)
    expect(resultItem.x + (resultItem.width || 0) / 2).toBe(taskItem.x + (taskItem.width || 0) / 2)
    expect(resultItem.y + (resultItem.height || 0) / 2).toBe(taskItem.y + (taskItem.height || 0) / 2)
  })

  it('falls back to the placeholder size when the generated size is unavailable', () => {
    const taskItem = createTextRedrawTaskItem({
      sourceItem,
      canvasItems: [sourceItem],
      taskId: 'text-redraw-task',
    })

    const resultItem = buildTextRedrawResultItem({
      taskItem,
      resultUrl: 'https://example.com/result.png',
    })

    expect(resultItem.width).toBe(taskItem.width)
    expect(resultItem.height).toBe(taskItem.height)
  })

  it('uses the shared compact panel dimensions for placement', () => {
    const position = getTextRedrawPanelPosition({
      item: {
        x: 120,
        y: 64,
        width: 320,
        height: 180,
      },
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1280, height: 900 },
    })

    expect(position.width).toBe(TEXT_REDRAW_PANEL_TOKENS.panelWidth)
    expect(position.height).toBe(TEXT_REDRAW_PANEL_TOKENS.panelHeight)
  })

  it('keeps the extracting badge fixed in screen space and wide enough for longer copy', () => {
    const badge = getTextRedrawExtractingBadgeStyle({
      zoom: 200,
    })

    expect(badge.transform).toBe('scale(0.5)')
    expect(badge.minWidth).toBe(TEXT_REDRAW_PANEL_TOKENS.extractingBadgeMinWidth)
    expect(badge.padding).toContain(`${TEXT_REDRAW_PANEL_TOKENS.extractingBadgePaddingX}px`)
  })
})
