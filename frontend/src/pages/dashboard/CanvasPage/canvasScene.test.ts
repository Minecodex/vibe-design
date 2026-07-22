import { describe, expect, it } from 'vitest'

import type { CanvasItem, CanvasMark } from '@/api/endpoints/projects'

import {
  getCanvasViewportCullBounds,
  isCanvasItemVisibleInViewport,
  getCanvasSceneItemRenderMode,
  getVisibleCanvasSceneItems,
  shouldUseCanvasSceneRenderer,
} from './canvasScene'

function createItem(overrides: Partial<CanvasItem> = {}): CanvasItem {
  return {
    id: overrides.id || 'item-1',
    type: overrides.type || 'image_generator',
    url: overrides.url || '',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 320,
    height: overrides.height ?? 180,
    z_index: overrides.z_index ?? 0,
    ...overrides,
  }
}

describe('canvasScene helpers', () => {
  it('only enables the scene renderer when zoom is low and enough items are visible', () => {
    expect(shouldUseCanvasSceneRenderer({ zoom: 40, visibleItemCount: 30 })).toBe(true)
    expect(shouldUseCanvasSceneRenderer({ zoom: 90, visibleItemCount: 30 })).toBe(false)
    expect(shouldUseCanvasSceneRenderer({ zoom: 40, visibleItemCount: 6 })).toBe(false)
  })

  it('filters scene items down to low-risk non-selected visuals', () => {
    const marks: CanvasMark[] = [
      {
        id: 'mark-1',
        imageItemId: 'marked-image',
        imageUrl: '/marked.png',
        relativeX: 0.5,
        relativeY: 0.5,
        number: 1,
        aiLabels: [],
        selectedLabel: null,
        customLabel: null,
        isAnalyzing: false,
      },
    ]

    const items = [
      createItem({ id: 'image-visible', type: 'image', url: '/visible.png', x: 10, y: 10 }),
      createItem({ id: 'selected-generator', type: 'image_generator', x: 20, y: 20 }),
      createItem({ id: 'brush-visible', type: 'brush_path', x: 30, y: 30, points: [{ x: 0.5, y: 0.5 }], brushColor: '#111', brushSize: 8 }),
      createItem({ id: 'text-item', type: 'text', text: 'hello', x: 40, y: 40 }),
      createItem({ id: 'marked-image', type: 'image', url: '/marked.png', x: 50, y: 50 }),
      createItem({ id: 'cropping-item', type: 'image', url: '/crop.png', x: 60, y: 60 }),
      createItem({ id: 'hidden-item', type: 'image_generator', is_hidden: true, x: 70, y: 70 }),
      createItem({ id: 'far-away', type: 'image_generator', x: 6000, y: 6000 }),
    ]

    const result = getVisibleCanvasSceneItems({
      canvasItems: items,
      selectedItems: ['selected-generator'],
      marks,
      cropState: { itemId: 'cropping-item' },
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 40,
      offset: { x: 0, y: 0 },
      viewport: { width: 1200, height: 800 },
      getItemDims: (item) => ({ width: item.width || 1, height: item.height || 1 }),
    })

    expect(result.map((item) => item.id)).toEqual(['image-visible', 'brush-visible'])
  })

  it('builds shared viewport cull bounds and checks visibility against them', () => {
    const viewportBounds = getCanvasViewportCullBounds({
      zoom: 50,
      offset: { x: 100, y: -50 },
      viewport: { width: 1200, height: 800 },
    })

    expect(viewportBounds.left).toBe(-2400)
    expect(viewportBounds.right).toBe(2000)
    expect(viewportBounds.top).toBe(-1700)
    expect(viewportBounds.bottom).toBe(1900)

    expect(isCanvasItemVisibleInViewport(
      createItem({ id: 'nearby', type: 'image', x: 1200, y: 900, width: 100, height: 100 }),
      {
        viewportBounds,
        getItemDims: (item) => ({ width: item.width || 1, height: item.height || 1 }),
      },
    )).toBe(true)

    expect(isCanvasItemVisibleInViewport(
      createItem({ id: 'far-away', type: 'image', x: 2600, y: 2100, width: 100, height: 100 }),
      {
        viewportBounds,
        getItemDims: (item) => ({ width: item.width || 1, height: item.height || 1 }),
      },
    )).toBe(false)
  })

  it('switches eligible low-zoom items into interaction-shell mode while keeping risky states on full DOM', () => {
    expect(getCanvasSceneItemRenderMode({
      useSceneRenderer: true,
      item: createItem({ id: 'plain-image', type: 'image', url: '/plain.png' }),
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
    })).toBe('interaction-shell')

    expect(getCanvasSceneItemRenderMode({
      useSceneRenderer: true,
      item: createItem({ id: 'generator-visible', type: 'image_generator' }),
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
    })).toBe('full-dom')

    expect(getCanvasSceneItemRenderMode({
      useSceneRenderer: true,
      item: createItem({ id: 'selected-image', type: 'image', url: '/a.png' }),
      selectedItems: ['selected-image'],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
    })).toBe('full-dom')

    expect(getCanvasSceneItemRenderMode({
      useSceneRenderer: true,
      item: createItem({ id: 'marked-image', type: 'image', url: '/b.png' }),
      selectedItems: [],
      marks: [{
        id: 'mark-1',
        imageItemId: 'marked-image',
        imageUrl: '/b.png',
        relativeX: 0.25,
        relativeY: 0.25,
        number: 1,
        aiLabels: [],
        selectedLabel: null,
        customLabel: null,
        isAnalyzing: false,
      }],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
    })).toBe('full-dom')
  })

  it('keeps grouped images on full DOM so they stay visually above group backgrounds', () => {
    expect(getCanvasSceneItemRenderMode({
      useSceneRenderer: true,
      item: createItem({ id: 'grouped-image', type: 'image', url: '/grouped.png', groupId: 'group-1' }),
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
    })).toBe('full-dom')

    const result = getVisibleCanvasSceneItems({
      canvasItems: [
        createItem({ id: 'grouped-image', type: 'image', url: '/grouped.png', groupId: 'group-1', x: 10, y: 10 }),
        createItem({ id: 'plain-image', type: 'image', url: '/plain.png', x: 40, y: 40 }),
        createItem({ id: 'brush-visible', type: 'brush_path', x: 30, y: 30, points: [{ x: 0.5, y: 0.5 }], brushColor: '#111', brushSize: 8 }),
      ],
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 40,
      offset: { x: 0, y: 0 },
      viewport: { width: 1200, height: 800 },
      getItemDims: (item) => ({ width: item.width || 1, height: item.height || 1 }),
    })

    expect(result.map((item) => item.id)).toEqual(['plain-image', 'brush-visible'])
  })
})
