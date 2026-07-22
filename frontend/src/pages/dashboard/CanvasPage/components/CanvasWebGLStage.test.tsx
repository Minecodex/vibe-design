import { act, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CanvasRenderNode } from '../canvasRenderModel'
import { createCanvasInteractionPreviewController } from '../canvasInteractionPreview'

const pixiMock = vi.hoisted(() => {
  const applications: any[] = []
  const initResolvers: Array<() => void> = []
  let initMode: 'resolved' | 'pending' = 'resolved'
  let destroyedBeforeInit = 0

  class MockContainer {
    children: any[] = []
    eventMode = 'none'
    visible = true
    zIndex = 0
    position = { set: vi.fn() }
    scale = { set: vi.fn() }

    addChild(child: any) {
      this.children.push(child)
      return child
    }

    removeChild(child: any) {
      this.children = this.children.filter((candidate) => candidate !== child)
      return child
    }

    destroy = vi.fn()
    sortChildren = vi.fn()
  }

  class MockGraphics extends MockContainer {
    clear = vi.fn(() => this)
    roundRect = vi.fn(() => this)
    fill = vi.fn(() => this)
    rect = vi.fn(() => this)
    circle = vi.fn(() => this)
    moveTo = vi.fn(() => this)
    lineTo = vi.fn(() => this)
    closePath = vi.fn(() => this)
    stroke = vi.fn(() => this)
  }

  class MockSprite extends MockContainer {
    texture: any
    width = 0
    height = 0

    constructor(texture: any) {
      super()
      this.texture = texture
    }
  }

  class MockText extends MockContainer {
    text = ''
    style: any = {}
    rotation = 0

    constructor(options: { text?: string } = {}) {
      super()
      this.text = options.text || ''
    }
  }

  class MockApplication {
    stage = new MockContainer()
    canvas = document.createElement('canvas')
    renderer = { resize: vi.fn() }
    initialized = false
    init = vi.fn(() => {
      if (initMode === 'pending') {
        return new Promise<void>((resolve) => {
          initResolvers.push(() => {
            this.initialized = true
            resolve()
          })
        })
      }
      this.initialized = true
      return Promise.resolve()
    })
    destroy = vi.fn(() => {
      if (!this.initialized) {
        destroyedBeforeInit += 1
      }
    })

    constructor() {
      applications.push(this)
    }
  }

  return {
    applications,
    initResolvers,
    get initMode() {
      return initMode
    },
    set initMode(value: 'resolved' | 'pending') {
      initMode = value
    },
    get destroyedBeforeInit() {
      return destroyedBeforeInit
    },
    reset() {
      applications.length = 0
      initResolvers.length = 0
      initMode = 'resolved'
      destroyedBeforeInit = 0
    },
    MockApplication,
    MockContainer,
    MockGraphics,
    MockSprite,
    MockText,
  }
})

const resourceMock = vi.hoisted(() => {
  const instances: any[] = []
  const initialTextures = new Map<string, any>()
  const defaultTileDescriptor = {
    url: '/image__tile_256_4_0_0.webp?v=1',
    status: 'ready',
    tileSize: 256,
    sourceWidth: 2048,
    sourceHeight: 2048,
    levelWidth: 2048,
    levelHeight: 2048,
    columns: 8,
    rows: 8,
  }

  class MockResourceManager {
    textures = new Map<string, any>()
    getStats = vi.fn(() => ({
      textureCount: this.textures.size,
      loadingCount: 0,
    }))
    getTexture = vi.fn((request: string | { url: string }) => {
      const url = typeof request === 'string' ? request : request.url
      return this.textures.get(url) ?? null
    })
    getVideoFrameTexture = vi.fn((request: string | { url: string }) => {
      const url = typeof request === 'string' ? request : request.url
      return this.textures.get(`video-frame:${url}`) ?? null
    })
    loadTexture = vi.fn(async (request: string | { url: string }) => {
      const url = typeof request === 'string' ? request : request.url
      const texture = { id: `texture:${url}` }
      this.textures.set(url, texture)
      return texture
    })
    loadVideoFrameTexture = vi.fn(async (request: string | { url: string }) => {
      const url = typeof request === 'string' ? request : request.url
      const texture = { id: `video-frame-texture:${url}` }
      this.textures.set(`video-frame:${url}`, texture)
      return texture
    })
    resolveTile = vi.fn(async (request: { z: number, x: number, y: number }) => ({
      ...defaultTileDescriptor,
      url: `/image__tile_256_${request.z}_${request.x}_${request.y}.webp?v=1`,
    }))
    destroy = vi.fn()

    constructor() {
      initialTextures.forEach((texture, url) => {
        this.textures.set(url, texture)
      })
      instances.push(this)
    }
  }

  return {
    instances,
    initialTextures,
    MockResourceManager,
    reset() {
      instances.length = 0
      initialTextures.clear()
    },
  }
})

vi.mock('pixi.js', () => ({
  Application: pixiMock.MockApplication,
  Container: pixiMock.MockContainer,
  Graphics: pixiMock.MockGraphics,
  Sprite: pixiMock.MockSprite,
  Text: pixiMock.MockText,
  Texture: {
    EMPTY: { id: 'empty' },
    from: vi.fn((source) => ({ source })),
  },
}))

vi.mock('../canvasImageResourceManager', () => ({
  CanvasImageResourceManager: resourceMock.MockResourceManager,
}))

import { CanvasWebGLStage } from './CanvasWebGLStage'

function createNode(overrides: Partial<CanvasRenderNode> = {}): CanvasRenderNode {
  const item = {
    id: 'node-1',
    type: 'image_generator',
    url: '',
    x: 0,
    y: 0,
    width: 240,
    height: 160,
    z_index: 1,
    status: 'generating',
    progress: 42,
  } as CanvasRenderNode['item']

  return {
    id: 'node-1',
    item,
    type: 'image_generator',
    renderKind: 'generator-card',
    overlayKind: 'none',
    bounds: { x: 0, y: 0, width: 240, height: 160 },
    zIndex: 1,
    hidden: false,
    locked: false,
    selected: false,
    visible: true,
    webglRenderable: true,
    ...overrides,
  }
}

function renderStage(overrides: Partial<React.ComponentProps<typeof CanvasWebGLStage>> = {}) {
  const host = document.createElement('div')
  Object.defineProperty(host, 'clientWidth', { configurable: true, value: 1000 })
  Object.defineProperty(host, 'clientHeight', { configurable: true, value: 800 })
  host.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 1000,
    height: 800,
    right: 1000,
    bottom: 800,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  })
  const canvasRef = { current: host }

  return render(
    <CanvasWebGLStage
      canvasRef={canvasRef}
      canvasCamera={null}
      projectId={null}
      nodes={[createNode()]}
      zoom={100}
      offset={{ x: 0, y: 0 }}
      isDark={false}
      {...overrides}
    />,
  )
}

describe('CanvasWebGLStage', () => {
  beforeEach(() => {
    pixiMock.reset()
    resourceMock.reset()
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('does not recreate Pixi when callback props change', async () => {
    const onReadyChange = vi.fn()
    const firstFallback = vi.fn()
    const view = renderStage({ onReadyChange, onFallback: firstFallback })

    await waitFor(() => {
      expect(onReadyChange).toHaveBeenCalledWith(true)
    })

    const nextFallback = vi.fn()
    view.rerender(
      <CanvasWebGLStage
        canvasRef={{ current: document.createElement('div') }}
        canvasCamera={null}
        projectId={null}
        nodes={[createNode()]}
        zoom={100}
        offset={{ x: 0, y: 0 }}
        isDark={false}
        onReadyChange={onReadyChange}
        onFallback={nextFallback}
      />,
    )

    expect(pixiMock.applications).toHaveLength(1)
    expect(pixiMock.applications[0].destroy).not.toHaveBeenCalled()
  })

  it('reports fallback when the WebGL context is lost', async () => {
    const onReadyChange = vi.fn()
    const onFallback = vi.fn()
    renderStage({ onReadyChange, onFallback })

    await waitFor(() => {
      expect(pixiMock.applications[0]?.canvas.parentElement).not.toBeNull()
    })

    const event = new Event('webglcontextlost', { cancelable: true })
    act(() => {
      pixiMock.applications[0].canvas.dispatchEvent(event)
    })

    expect(event.defaultPrevented).toBe(true)
    expect(onReadyChange).toHaveBeenCalledWith(false)
    expect(onFallback).toHaveBeenCalledTimes(1)
  })

  it('does not destroy an uninitialized Pixi application during early unmount', async () => {
    pixiMock.initMode = 'pending'
    const view = renderStage()

    expect(pixiMock.applications).toHaveLength(1)
    view.unmount()

    expect(pixiMock.destroyedBeforeInit).toBe(0)
    expect(pixiMock.applications[0].destroy).not.toHaveBeenCalled()

    await act(async () => {
      pixiMock.initResolvers[0]?.()
      await Promise.resolve()
    })

    expect(pixiMock.applications[0].destroy).toHaveBeenCalledWith(true)
  })

  it('requests visible backend tiles for large idle images and overlays tile sprites', async () => {
    const imageNode = createNode({
      id: 'image-1',
      renderKind: 'image',
      type: 'image',
      item: {
        id: 'image-1',
        type: 'image',
        url: '/image.png',
        x: -1024,
        y: -1024,
        width: 2048,
        height: 2048,
        z_index: 1,
      } as CanvasRenderNode['item'],
      bounds: { x: -1024, y: -1024, width: 2048, height: 2048 },
    })

    renderStage({
      projectId: 7,
      nodes: [imageNode],
      zoom: 200,
      offset: { x: 0, y: 0 },
      isInteracting: false,
    })

    await waitFor(() => {
      expect(resourceMock.instances[0]?.resolveTile).toHaveBeenCalledWith({
        projectId: 7,
        url: '/image.png',
        z: 4,
        x: 0,
        y: 0,
      })
    })

    await waitFor(() => {
      expect(resourceMock.instances[0].resolveTile).toHaveBeenCalledWith({
        projectId: 7,
        url: '/image.png',
        z: 4,
        x: 4,
        y: 4,
      })
    })

    const world = pixiMock.applications[0].stage.children[0]
    const recordContainer = world.children[0]
    const tileContainer = recordContainer.children.find((child: any) => child instanceof pixiMock.MockContainer && child.children.length > 0)

    expect(tileContainer).toBeTruthy()
    expect(tileContainer.children.some((child: any) => child instanceof pixiMock.MockSprite)).toBe(true)
    expect(resourceMock.instances[0].loadTexture).toHaveBeenCalledWith('/image__tile_256_4_4_4.webp?v=1')
  })

  it('keeps a cached low-res texture visible while requesting the current zoom tier', async () => {
    const lowTexture = { id: 'low-res' }
    resourceMock.initialTextures.set('/image.png', lowTexture)
    const imageNode = createNode({
      id: 'image-1',
      renderKind: 'image',
      type: 'image',
      item: {
        id: 'image-1',
        type: 'image',
        url: '/image.png',
        x: 0,
        y: 0,
        width: 2048,
        height: 2048,
        z_index: 1,
      } as CanvasRenderNode['item'],
      bounds: { x: 0, y: 0, width: 2048, height: 2048 },
      selected: true,
    })

    renderStage({
      projectId: 7,
      nodes: [imageNode],
      zoom: 38,
      offset: { x: 0, y: 0 },
      isInteracting: false,
    })

    await waitFor(() => {
      expect(resourceMock.instances[0]?.loadTexture).toHaveBeenCalledWith(expect.objectContaining({
        url: '/image.png',
        displayWidth: 2048,
        displayHeight: 2048,
        zoom: 38,
        interactionMode: 'idle',
      }))
    })
    await waitFor(() => {
      expect(resourceMock.instances[0]?.resolveTile).toHaveBeenCalledWith({
        projectId: 7,
        url: '/image.png',
        z: 2,
        x: 0,
        y: 0,
      })
    })

    const world = pixiMock.applications[0].stage.children[0]
    const recordContainer = world.children[0]
    const imageSprite = recordContainer.children.find((child: any) => child instanceof pixiMock.MockSprite)

    expect(imageSprite.texture).toEqual({ id: 'texture:/image.png' })
  })

  it('loads a first-frame texture for WebGL videos without poster images', async () => {
    const videoNode = createNode({
      id: 'video-1',
      renderKind: 'video-poster',
      type: 'video',
      item: {
        id: 'video-1',
        type: 'video',
        url: '/movie.mp4',
        x: 0,
        y: 0,
        width: 320,
        height: 180,
        z_index: 1,
      } as CanvasRenderNode['item'],
      bounds: { x: 0, y: 0, width: 320, height: 180 },
    })

    renderStage({
      nodes: [videoNode],
      zoom: 100,
      offset: { x: 0, y: 0 },
    })

    await waitFor(() => {
      expect(resourceMock.instances[0]?.loadVideoFrameTexture).toHaveBeenCalledWith(expect.objectContaining({
        url: '/movie.mp4',
        displayWidth: 320,
        displayHeight: 180,
        zoom: 100,
      }))
    })

    const world = pixiMock.applications[0].stage.children[0]
    const recordContainer = world.children[0]
    const imageSprite = recordContainer.children.find((child: any) => child instanceof pixiMock.MockSprite)
    const graphicsChildren = recordContainer.children.filter((child: any) => child instanceof pixiMock.MockGraphics)
    const playOverlay = graphicsChildren[graphicsChildren.length - 1]

    await waitFor(() => {
      expect(imageSprite.texture).toEqual({ id: 'video-frame-texture:/movie.mp4' })
    })
    expect(playOverlay.visible).toBe(true)
    expect(playOverlay.circle).toHaveBeenCalled()
  })

  it('moves WebGL display records with transient interaction previews without React commits', async () => {
    const imageNode = createNode({
      id: 'image-1',
      renderKind: 'image',
      type: 'image',
      item: {
        id: 'image-1',
        type: 'image',
        url: '/image.png',
        x: 10,
        y: 20,
        width: 120,
        height: 90,
        z_index: 1,
      } as CanvasRenderNode['item'],
      bounds: { x: 10, y: 20, width: 120, height: 90 },
    })
    const interactionPreview = createCanvasInteractionPreviewController()

    renderStage({
      nodes: [imageNode],
      interactionPreview,
    })

    await waitFor(() => {
      expect(pixiMock.applications[0]?.stage.children[0]?.children[0]).toBeTruthy()
    })

    const world = pixiMock.applications[0].stage.children[0]
    const recordContainer = world.children[0]

    act(() => {
      interactionPreview.begin([imageNode.item])
      interactionPreview.apply([{
        ...imageNode.item,
        x: 40,
        y: 55,
        width: 160,
        height: 120,
      } as CanvasRenderNode['item']])
    })

    expect(recordContainer.position.set).toHaveBeenLastCalledWith(40, 55)
    expect(recordContainer.scale.set).toHaveBeenLastCalledWith(160 / 120, 120 / 90)

    act(() => {
      interactionPreview.clear({ restore: false })
    })

    expect(recordContainer.position.set).toHaveBeenLastCalledWith(40, 55)
  })
})
