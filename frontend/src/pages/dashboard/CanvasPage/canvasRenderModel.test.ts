import { afterEach, describe, expect, it, vi } from 'vitest'

import type { CanvasItem } from '@/api/endpoints/projects'

import { createCanvasRenderSnapshot, getCanvasRendererPreference } from './canvasRenderModel'

afterEach(() => {
  vi.unstubAllEnvs()
})

function item(overrides: Partial<CanvasItem>): CanvasItem {
  return {
    id: overrides.id || 'item',
    type: overrides.type || 'image',
    url: overrides.url ?? '/image.png',
    x: overrides.x ?? 0,
    y: overrides.y ?? 0,
    width: overrides.width ?? 100,
    height: overrides.height ?? 100,
    z_index: overrides.z_index ?? 0,
    ...overrides,
  }
}

describe('createCanvasRenderSnapshot', () => {
  it('keeps selected media visually in WebGL while DOM renders only the interaction shell', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'plain', z_index: 1 }),
        item({ id: 'selected', z_index: 2 }),
        item({ id: 'video', type: 'video', url: '/video.mp4', z_index: 3 }),
      ],
      selectedItems: ['selected'],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.webglNodes.map((node) => node.id)).toEqual(['plain', 'selected', 'video'])
    expect(snapshot.overlayNodes.map((node) => node.id)).toEqual(['selected'])
    expect(snapshot.nodes.find((node) => node.id === 'selected')?.overlayKind).toBe('interaction-shell')
    expect(snapshot.nodes.find((node) => node.id === 'plain')?.overlayKind).toBe('none')
    expect(snapshot.nodes.find((node) => node.id === 'video')?.renderKind).toBe('video-poster')
  })

  it('switches hovered video nodes back to DOM overlay for playback controls', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'video', type: 'video', url: '/video.mp4', z_index: 1 }),
        item({ id: 'video-generator', type: 'video_generator', url: '/generated.mp4', z_index: 2 }),
      ],
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      hoverDomItemId: 'video',
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.webglNodes.map((node) => node.id)).toEqual(['video', 'video-generator'])
    expect(snapshot.overlayNodes.map((node) => node.id)).toEqual(['video'])
  })

  it('hit-tests visible nodes from highest z-index to lowest', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'bottom', x: 0, y: 0, width: 120, height: 120, z_index: 1 }),
        item({ id: 'top', x: 10, y: 10, width: 120, height: 120, z_index: 10 }),
      ],
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.hitTest({ x: 20, y: 20 })?.id).toBe('top')
    expect(snapshot.hitTest({ x: 5, y: 5 })?.id).toBe('bottom')
    expect(snapshot.hitTest({ x: 500, y: 500 })).toBeNull()
  })

  it('keeps selected offscreen nodes in the overlay snapshot while culling other offscreen nodes', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'selected-offscreen', x: 5000, y: 5000, z_index: 1 }),
        item({ id: 'plain-offscreen', x: 5200, y: 5200, z_index: 2 }),
      ],
      selectedItems: ['selected-offscreen'],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.visibleNodes.map((node) => node.id)).toEqual(['selected-offscreen'])
    expect(snapshot.webglNodes.map((node) => node.id)).toEqual(['selected-offscreen'])
    expect(snapshot.overlayNodes.map((node) => node.id)).toEqual(['selected-offscreen'])
    expect(snapshot.hitTest({ x: 5250, y: 5250 })).toBeNull()
  })

  it('limits anchored generator overlays to the source image without removing other images from WebGL', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'source', z_index: 1 }),
        item({ id: 'other', x: 140, z_index: 2 }),
      ],
      selectedItems: ['source'],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      imageAnchoredImageDraft: { sourceImageItemId: 'source' },
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.webglNodes.map((node) => node.id)).toEqual(['source', 'other'])
    expect(snapshot.overlayNodes.map((node) => node.id)).toEqual(['source'])
    expect(snapshot.nodes.find((node) => node.id === 'source')?.overlayKind).toBe('interaction-shell')
    expect(snapshot.nodes.find((node) => node.id === 'other')?.overlayKind).toBe('none')
  })

  it('renders pending generator cards only in the DOM overlay so focused and unfocused states match', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({
          id: 'pending',
          type: 'image_generator',
          url: '',
          status: 'generating',
          progress: 10,
          z_index: 1,
        }),
      ],
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.webglNodes.map((node) => node.id)).toEqual([])
    expect(snapshot.overlayNodes.map((node) => node.id)).toEqual(['pending'])
    expect(snapshot.nodes[0].overlayKind).toBe('full-dom')
  })

  it('keeps marked images in the DOM overlay while preserving the WebGL base image', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'marked', z_index: 1 }),
      ],
      selectedItems: ['marked'],
      marks: [{ id: 'mark-1', imageItemId: 'marked', relativeX: 0.5, relativeY: 0.5,
        imageUrl: '/marked.png', number: 1, aiLabels: [], selectedLabel: null,
        customLabel: null, isAnalyzing: false }],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.webglNodes.map((node) => node.id)).toEqual(['marked'])
    expect(snapshot.overlayNodes.map((node) => node.id)).toEqual(['marked'])
    expect(snapshot.nodes[0].overlayKind).toBe('full-dom')
  })

  it('places group backgrounds behind grouped children and hit-tests children before the group', () => {
    const snapshot = createCanvasRenderSnapshot({
      canvasItems: [
        item({ id: 'group-1', type: 'group', url: '', x: 0, y: 0, width: 200, height: 200, z_index: 99 }),
        item({ id: 'child', x: 40, y: 40, width: 80, height: 80, groupId: 'group-1', z_index: 1 }),
      ],
      selectedItems: [],
      marks: [],
      cropState: null,
      textRedrawExtractingItemIds: new Set<string>(),
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: 1000, height: 800 },
      getItemDims: (canvasItem) => ({ width: canvasItem.width || 1, height: canvasItem.height || 1 }),
    })

    expect(snapshot.nodes.find((node) => node.id === 'group-1')?.zIndex).toBe(0)
    expect(snapshot.webglNodes.map((node) => node.id)).toEqual(['group-1', 'child'])
    expect(snapshot.hitTest({ x: 60, y: 60 })?.id).toBe('child')
    expect(snapshot.hitTest({ x: 10, y: 10 })?.id).toBe('group-1')
  })
})

describe('getCanvasRendererPreference', () => {
  it('defaults to WebGL and allows an explicit DOM fallback override', () => {
    expect(getCanvasRendererPreference()).toBe('webgl')

    vi.stubEnv('VITE_CANVAS_RENDERER', 'dom')
    expect(getCanvasRendererPreference()).toBe('dom')

    vi.stubEnv('VITE_CANVAS_RENDERER', 'webgl')
    expect(getCanvasRendererPreference()).toBe('webgl')
  })
})
