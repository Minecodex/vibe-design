import { describe, expect, it, vi } from 'vitest'

vi.mock('pixi.js', () => ({
  Texture: {
    from: vi.fn((source) => source),
  },
}))

import {
  CanvasImageResourceManager,
  selectCanvasImageTextureTier,
  type CanvasImageTextureTier,
} from './canvasImageResourceManager'

function texture(id: string) {
  return {
    id,
    destroy: vi.fn(),
  } as any
}

async function flushMicrotasks() {
  await Promise.resolve()
  await Promise.resolve()
}

describe('selectCanvasImageTextureTier', () => {
  it('selects lower tiers during interaction and progressive idle tiers before full size', () => {
    expect(selectCanvasImageTextureTier({
      displayWidth: 300,
      displayHeight: 200,
      zoom: 50,
      interactionMode: 'interactive',
    })).toBe(256)
    expect(selectCanvasImageTextureTier({
      displayWidth: 900,
      displayHeight: 700,
      zoom: 100,
      interactionMode: 'interactive',
    })).toBe(1024)
    expect(selectCanvasImageTextureTier({
      displayWidth: 1400,
      displayHeight: 900,
      zoom: 100,
      interactionMode: 'idle',
    })).toBe(2048)
    expect(selectCanvasImageTextureTier({
      displayWidth: 2400,
      displayHeight: 1600,
      zoom: 100,
      interactionMode: 'idle',
    })).toBe('full')
  })
})

describe('CanvasImageResourceManager', () => {
  it('loads and reuses tiered textures by request size', async () => {
    const loader = vi.fn(async ({ url, tier }: { url: string; tier: CanvasImageTextureTier }) => ({
      texture: texture(`${url}-${tier}`),
      width: tier === 'full' ? 2048 : tier,
      height: tier === 'full' ? 2048 : tier,
    }))
    const manager = new CanvasImageResourceManager({ loader })

    const request = {
      url: '/image.png',
      displayWidth: 200,
      displayHeight: 200,
      zoom: 100,
      interactionMode: 'idle' as const,
    }

    const loaded = await manager.loadTexture(request)
    expect((loaded as any)?.id).toBe('/image.png-256')
    expect(manager.getTexture(request)).toBe(loaded)
    expect(loader).toHaveBeenCalledTimes(1)

    await manager.loadTexture(request)
    expect(loader).toHaveBeenCalledTimes(1)
  })

  it('loads and caches video frame textures separately from image textures', async () => {
    const loader = vi.fn(async ({ url, tier }: { url: string; tier: CanvasImageTextureTier }) => ({
      texture: texture(`image-${url}-${tier}`),
      width: 256,
      height: 256,
    }))
    const videoFrameLoader = vi.fn(async ({ url, tier }: { url: string; tier: CanvasImageTextureTier }) => ({
      texture: texture(`video-${url}-${tier}`),
      width: 256,
      height: 144,
    }))
    const manager = new CanvasImageResourceManager({ loader, videoFrameLoader })
    const request = {
      url: '/shared.mp4',
      displayWidth: 320,
      displayHeight: 180,
      zoom: 100,
      interactionMode: 'idle' as const,
    }

    const imageTexture = await manager.loadTexture(request)
    const videoTexture = await manager.loadVideoFrameTexture(request)

    expect((imageTexture as any)?.id).toBe('image-/shared.mp4-512')
    expect((videoTexture as any)?.id).toBe('video-/shared.mp4-512')
    expect(manager.getTexture(request)).toBe(imageTexture)
    expect(manager.getVideoFrameTexture(request)).toBe(videoTexture)
    expect(videoFrameLoader).toHaveBeenCalledTimes(1)

    await manager.loadVideoFrameTexture(request)
    expect(videoFrameLoader).toHaveBeenCalledTimes(1)
  })

  it('falls back to the best cached lower tier while a higher idle tier loads', async () => {
    const highResolvers: Array<(value: any) => void> = []
    const low = texture('low')
    const high = texture('high')
    const loader = vi.fn(({ tier }: { tier: CanvasImageTextureTier }) => {
      if (tier === 2048) {
        return new Promise<any>((resolve) => {
          highResolvers.push(resolve)
        })
      }
      return Promise.resolve({
        texture: low,
        width: 256,
        height: 256,
      })
    })
    const manager = new CanvasImageResourceManager({ loader })

    await manager.loadTexture({
      url: '/image.png',
      displayWidth: 900,
      displayHeight: 900,
      zoom: 100,
      interactionMode: 'interactive',
    })

    const loadFull = manager.loadTexture({
      url: '/image.png',
      displayWidth: 1400,
      displayHeight: 1400,
      zoom: 100,
      interactionMode: 'idle',
    })
    await flushMicrotasks()

    expect(manager.getTexture({
      url: '/image.png',
      displayWidth: 1400,
      displayHeight: 1400,
      zoom: 100,
      interactionMode: 'idle',
    })).toBe(low)

    highResolvers[0]({ texture: high, width: 2048, height: 2048 })
    await loadFull

    expect(manager.getTexture({
      url: '/image.png',
      displayWidth: 1400,
      displayHeight: 1400,
      zoom: 100,
      interactionMode: 'idle',
    })).toBe(high)
  })

  it('limits concurrent loads and evicts least recently used textures', async () => {
    const resolvers: Array<(value: any) => void> = []
    const loader = vi.fn(({ url }: { url: string }) => new Promise<any>((resolve) => {
      resolvers.push(resolve)
      void url
    }))
    const manager = new CanvasImageResourceManager({
      loader,
      maxConcurrentLoads: 1,
      maxTextures: 2,
    })

    const first = manager.loadTexture('/one.png')
    const second = manager.loadTexture('/two.png')
    const third = manager.loadTexture('/three.png')
    await flushMicrotasks()
    expect(manager.getStats()).toMatchObject({ activeLoads: 1, queuedLoads: 2 })

    const one = texture('one')
    resolvers[0]({ texture: one, width: 1, height: 1 })
    await first
    expect(manager.getStats().activeLoads).toBe(1)

    const two = texture('two')
    resolvers[1]({ texture: two, width: 1, height: 1 })
    await second

    const three = texture('three')
    resolvers[2]({ texture: three, width: 1, height: 1 })
    await third

    expect(one.destroy).toHaveBeenCalledWith(true)
    expect(manager.getStats().textureCount).toBe(2)
  })

  it('loads backend preview URLs for project tier textures', async () => {
    const previewUrlResolver = vi.fn(async () => '/image__canvas_2048.webp?v=1')
    const loader = vi.fn(async ({ url, tier }: { url: string; tier: CanvasImageTextureTier }) => ({
      texture: texture(`${url}-${tier}`),
      width: tier === 'full' ? 2048 : tier,
      height: tier === 'full' ? 2048 : tier,
    }))
    const manager = new CanvasImageResourceManager({ loader, previewUrlResolver })

    const loaded = await manager.loadTexture({
      projectId: 7,
      url: '/image.png',
      displayWidth: 1400,
      displayHeight: 1400,
      zoom: 100,
      interactionMode: 'idle',
    })

    expect(previewUrlResolver).toHaveBeenCalledWith({
      projectId: 7,
      url: '/image.png',
      tier: 2048,
    })
    expect(loader).toHaveBeenCalledWith({
      url: '/image__canvas_2048.webp?v=1',
      tier: 2048,
      maxDimension: 2048,
    })
    expect((loaded as any)?.id).toBe('/image__canvas_2048.webp?v=1-2048')
  })

  it('falls back to original URLs when preview URLs are unavailable or fail to load', async () => {
    const previewUrlResolver = vi.fn(async () => '/image__canvas_256.webp?v=1')
    const loader = vi.fn(async ({ url, tier }: { url: string; tier: CanvasImageTextureTier }) => {
      if (url.includes('__canvas_')) return null
      return {
        texture: texture(`${url}-${tier}`),
        width: 256,
        height: 256,
      }
    })
    const manager = new CanvasImageResourceManager({ loader, previewUrlResolver })

    const loaded = await manager.loadTexture({
      projectId: 7,
      url: '/image.png',
      displayWidth: 200,
      displayHeight: 200,
      zoom: 100,
      interactionMode: 'idle',
    })

    expect(loader).toHaveBeenNthCalledWith(1, {
      url: '/image__canvas_256.webp?v=1',
      tier: 256,
      maxDimension: 256,
    })
    expect(loader).toHaveBeenNthCalledWith(2, {
      url: '/image.png',
      tier: 256,
      maxDimension: 256,
    })
    expect((loaded as any)?.id).toBe('/image.png-256')
  })

  it('does not request backend previews without project context or for full textures', async () => {
    const previewUrlResolver = vi.fn(async () => '/unused.webp')
    const loader = vi.fn(async ({ url, tier }: { url: string; tier: CanvasImageTextureTier }) => ({
      texture: texture(`${url}-${tier}`),
      width: 2048,
      height: 2048,
    }))
    const manager = new CanvasImageResourceManager({ loader, previewUrlResolver })

    await manager.loadTexture({
      url: '/image.png',
      displayWidth: 200,
      displayHeight: 200,
      zoom: 100,
      interactionMode: 'idle',
    })
    await manager.loadTexture({
      projectId: 7,
      url: '/large.png',
      displayWidth: 2400,
      displayHeight: 2400,
      zoom: 100,
      interactionMode: 'idle',
    })

    expect(previewUrlResolver).toHaveBeenCalledTimes(0)
    expect(loader).toHaveBeenNthCalledWith(1, {
      url: '/image.png',
      tier: 256,
      maxDimension: 256,
    })
    expect(loader).toHaveBeenNthCalledWith(2, {
      url: '/large.png',
      tier: 'full',
      maxDimension: null,
    })
  })

  it('resolves backend canvas tiles through the injected tile resolver', async () => {
    const tileUrlResolver = vi.fn(async () => ({
      url: '/image__tile_256_2_3_1.webp?v=1',
      status: 'ready' as const,
      tileSize: 256,
      sourceWidth: 1024,
      sourceHeight: 512,
      levelWidth: 1024,
      levelHeight: 512,
      columns: 4,
      rows: 2,
    }))
    const manager = new CanvasImageResourceManager({ tileUrlResolver })

    const tile = await manager.resolveTile({
      projectId: 7,
      url: '/image.png',
      z: 2,
      x: 3,
      y: 1,
    })

    expect(tileUrlResolver).toHaveBeenCalledWith({
      projectId: 7,
      url: '/image.png',
      z: 2,
      x: 3,
      y: 1,
    })
    expect(tile).toMatchObject({
      url: '/image__tile_256_2_3_1.webp?v=1',
      status: 'ready',
      tileSize: 256,
      columns: 4,
      rows: 2,
    })
  })
})
