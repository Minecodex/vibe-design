import { Texture } from 'pixi.js'
import { assetsApi } from '@/api/endpoints/assets'

export type CanvasImageTextureTier = 256 | 512 | 1024 | 2048 | 'full'

export type CanvasTextureRequest = {
  url: string
  displayWidth: number
  displayHeight: number
  zoom: number
  interactionMode?: 'idle' | 'interactive'
  projectId?: number | null
}

export type CanvasLoadedTexture = {
  texture: Texture
  width: number
  height: number
}

type TextureEntry = CanvasLoadedTexture & {
  tier: CanvasImageTextureTier
  lastUsedAt: number
}

type TextureLoader = (args: {
  url: string
  tier: CanvasImageTextureTier
  maxDimension: number | null
}) => Promise<CanvasLoadedTexture | null>

type VideoFrameTextureLoader = (args: {
  url: string
  tier: CanvasImageTextureTier
  maxDimension: number | null
}) => Promise<CanvasLoadedTexture | null>

type PreviewUrlResolver = (args: {
  projectId: number
  url: string
  tier: Exclude<CanvasImageTextureTier, 'full'>
}) => Promise<string | null>

export type CanvasTileRequest = {
  projectId: number
  url: string
  z: number
  x: number
  y: number
}

export type CanvasTileDescriptor = {
  url: string | null
  status: 'ready' | 'pending' | 'missing' | null
  tileSize: number
  sourceWidth: number | null
  sourceHeight: number | null
  levelWidth: number | null
  levelHeight: number | null
  columns: number | null
  rows: number | null
}

type TileUrlResolver = (request: CanvasTileRequest) => Promise<CanvasTileDescriptor | null>

type QueuedLoad = {
  run: () => void
}

const DEFAULT_MAX_TEXTURES = 192
const DEFAULT_MAX_CONCURRENT_LOADS = 4
const TIER_ORDER: CanvasImageTextureTier[] = [256, 512, 1024, 2048, 'full']

function now() {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now()
  }
  return Date.now()
}

function getTierRank(tier: CanvasImageTextureTier) {
  return TIER_ORDER.indexOf(tier)
}

function getTierMaxDimension(tier: CanvasImageTextureTier) {
  return tier === 'full' ? null : tier
}

function getCacheKey(url: string, tier: CanvasImageTextureTier, kind: 'image' | 'video-frame' = 'image') {
  return `${kind}:${url}::${tier}`
}

function isSameOriginUrl(url: string) {
  if (typeof window === 'undefined') return false
  try {
    return new URL(url, window.location.href).origin === window.location.origin
  } catch {
    return false
  }
}

function getNumericDimension(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (value && typeof value === 'object' && 'baseVal' in value) {
    const baseValue = (value as { baseVal?: { value?: number } }).baseVal?.value
    if (typeof baseValue === 'number' && Number.isFinite(baseValue)) return baseValue
  }
  return 1
}

function chooseTierForScreenPixels(screenPixels: number, interactionMode: 'idle' | 'interactive'): CanvasImageTextureTier {
  if (interactionMode === 'interactive') {
    if (screenPixels <= 256) return 256
    if (screenPixels <= 512) return 512
    return 1024
  }

  if (screenPixels <= 256) return 256
  if (screenPixels <= 512) return 512
  if (screenPixels <= 1024) return 1024
  if (screenPixels <= 2048) return 2048
  return 'full'
}

function getDrawableDimensions(source: CanvasImageSource) {
  const dimensionSource = source as {
    naturalWidth?: number
    naturalHeight?: number
    width?: unknown
    height?: unknown
    displayWidth?: number
    displayHeight?: number
    videoWidth?: number
    videoHeight?: number
  }
  if (dimensionSource.naturalWidth || dimensionSource.naturalHeight) {
    return {
      width: dimensionSource.naturalWidth || getNumericDimension(dimensionSource.width),
      height: dimensionSource.naturalHeight || getNumericDimension(dimensionSource.height),
    }
  }
  return {
    width: dimensionSource.videoWidth
      || dimensionSource.displayWidth
      || getNumericDimension(dimensionSource.width),
    height: dimensionSource.videoHeight
      || dimensionSource.displayHeight
      || getNumericDimension(dimensionSource.height),
  }
}

async function createScaledCanvasSource(source: CanvasImageSource, maxDimension: number | null) {
  const dims = getDrawableDimensions(source)
  const sourceWidth = Math.max(1, dims.width)
  const sourceHeight = Math.max(1, dims.height)
  if (!maxDimension || Math.max(sourceWidth, sourceHeight) <= maxDimension) {
    return {
      source,
      width: sourceWidth,
      height: sourceHeight,
    }
  }

  const scale = maxDimension / Math.max(sourceWidth, sourceHeight)
  const targetWidth = Math.max(1, Math.round(sourceWidth * scale))
  const targetHeight = Math.max(1, Math.round(sourceHeight * scale))

  if (typeof createImageBitmap === 'function') {
    try {
      const bitmap = await createImageBitmap(source, {
        resizeWidth: targetWidth,
        resizeHeight: targetHeight,
        resizeQuality: 'medium',
      })
      return {
        source: bitmap,
        width: targetWidth,
        height: targetHeight,
      }
    } catch {
      // Canvas fallback below handles browsers without bitmap resize support.
    }
  }

  const canvas = typeof OffscreenCanvas !== 'undefined'
    ? new OffscreenCanvas(targetWidth, targetHeight)
    : document.createElement('canvas')
  canvas.width = targetWidth
  canvas.height = targetHeight
  const context = canvas.getContext('2d')
  if (!context || !('drawImage' in context)) {
    return {
      source,
      width: sourceWidth,
      height: sourceHeight,
    }
  }
  context.drawImage(source, 0, 0, targetWidth, targetHeight)
  return {
    source: canvas,
    width: targetWidth,
    height: targetHeight,
  }
}

async function createSnapshotCanvasSource(source: CanvasImageSource, maxDimension: number | null) {
  const dims = getDrawableDimensions(source)
  const sourceWidth = Math.max(1, dims.width)
  const sourceHeight = Math.max(1, dims.height)
  const scale = maxDimension && Math.max(sourceWidth, sourceHeight) > maxDimension
    ? maxDimension / Math.max(sourceWidth, sourceHeight)
    : 1
  const targetWidth = Math.max(1, Math.round(sourceWidth * scale))
  const targetHeight = Math.max(1, Math.round(sourceHeight * scale))
  const canvas = typeof OffscreenCanvas !== 'undefined'
    ? new OffscreenCanvas(targetWidth, targetHeight)
    : document.createElement('canvas')
  canvas.width = targetWidth
  canvas.height = targetHeight
  const context = canvas.getContext('2d')
  if (!context || !('drawImage' in context)) {
    throw new Error('Canvas snapshot is unavailable')
  }
  context.drawImage(source, 0, 0, targetWidth, targetHeight)
  return {
    source: canvas,
    width: targetWidth,
    height: targetHeight,
  }
}

async function defaultTextureLoader({
  url,
  tier,
  maxDimension,
}: {
  url: string
  tier: CanvasImageTextureTier
  maxDimension: number | null
}): Promise<CanvasLoadedTexture | null> {
  if (typeof Image === 'undefined') return null

  return new Promise((resolve) => {
    const image = new Image()
    if (!isSameOriginUrl(url)) {
      image.crossOrigin = 'anonymous'
    }
    image.decoding = 'async'
    image.onload = () => {
      void (async () => {
        try {
          if (typeof image.decode === 'function') {
            await image.decode().catch(() => undefined)
          }
          const scaled = await createScaledCanvasSource(image, maxDimension)
          const texture = Texture.from(scaled.source)
          resolve({
            texture,
            width: scaled.width,
            height: scaled.height,
          })
        } catch {
          try {
            const texture = Texture.from(image)
            resolve({
              texture,
              width: image.naturalWidth || image.width || 1,
              height: image.naturalHeight || image.height || 1,
            })
          } catch {
            resolve(null)
          }
        }
      })()
    }
    image.onerror = () => resolve(null)
    image.src = url
    void tier
  })
}

const VIDEO_FRAME_CAPTURE_TIMEOUT_MS = 8000
const VIDEO_FRAME_SEEK_SECONDS = 0.001

async function defaultVideoFrameTextureLoader({
  url,
  tier,
  maxDimension,
}: {
  url: string
  tier: CanvasImageTextureTier
  maxDimension: number | null
}): Promise<CanvasLoadedTexture | null> {
  if (typeof document === 'undefined') return null

  return new Promise((resolve) => {
    const video = document.createElement('video')
    let settled = false
    let timeoutId: ReturnType<typeof setTimeout> | null = null

    function finish(value: CanvasLoadedTexture | null) {
      if (settled) return
      settled = true
      if (timeoutId != null) {
        clearTimeout(timeoutId)
      }
      video.removeEventListener('loadedmetadata', handleLoadedMetadata)
      video.removeEventListener('loadeddata', captureFrame)
      video.removeEventListener('seeked', captureFrame)
      video.removeEventListener('error', handleError)
      video.pause()
      video.removeAttribute('src')
      video.load()
      resolve(value)
    }

    function captureFrame() {
      if (settled || video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return
      void (async () => {
        try {
          const snapshot = await createSnapshotCanvasSource(video, maxDimension)
          const texture = Texture.from(snapshot.source)
          finish({
            texture,
            width: snapshot.width,
            height: snapshot.height,
          })
        } catch {
          finish(null)
        }
      })()
    }

    function handleLoadedMetadata() {
      if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
        captureFrame()
        return
      }
      const duration = Number.isFinite(video.duration) ? video.duration : 0
      if (duration > 0) {
        try {
          video.currentTime = Math.min(VIDEO_FRAME_SEEK_SECONDS, Math.max(0, duration - VIDEO_FRAME_SEEK_SECONDS))
        } catch {
          // Some browsers disallow seeking before enough data is buffered; loadeddata will retry.
        }
      }
    }

    function handleError() {
      finish(null)
    }

    timeoutId = setTimeout(() => finish(null), VIDEO_FRAME_CAPTURE_TIMEOUT_MS)
    if (!isSameOriginUrl(url)) {
      video.crossOrigin = 'anonymous'
    }
    video.muted = true
    video.playsInline = true
    video.preload = 'auto'
    video.addEventListener('loadedmetadata', handleLoadedMetadata)
    video.addEventListener('loadeddata', captureFrame)
    video.addEventListener('seeked', captureFrame)
    video.addEventListener('error', handleError)
    video.src = url
    video.load()
    void tier
  })
}

async function defaultPreviewUrlResolver({ projectId, url, tier }: {
  projectId: number
  url: string
  tier: Exclude<CanvasImageTextureTier, 'full'>
}) {
  try {
    const response = await assetsApi.getCanvasPreview(projectId, { url, width: tier })
    return response.data.status === 'ready' && response.data.url ? response.data.url : null
  } catch {
    return null
  }
}

async function defaultTileUrlResolver({ projectId, url, z, x, y }: CanvasTileRequest) {
  try {
    const response = await assetsApi.getCanvasTile(projectId, { url, z, x, y })
    return {
      url: response.data.url ?? null,
      status: response.data.status ?? null,
      tileSize: response.data.tile_size,
      sourceWidth: response.data.source_width ?? null,
      sourceHeight: response.data.source_height ?? null,
      levelWidth: response.data.level_width ?? null,
      levelHeight: response.data.level_height ?? null,
      columns: response.data.columns ?? null,
      rows: response.data.rows ?? null,
    }
  } catch {
    return null
  }
}

export function selectCanvasImageTextureTier(request: Omit<CanvasTextureRequest, 'url'>): CanvasImageTextureTier {
  const scale = Math.max(0.01, request.zoom / 100)
  const screenWidth = Math.max(1, request.displayWidth * scale)
  const screenHeight = Math.max(1, request.displayHeight * scale)
  const screenPixels = Math.max(screenWidth, screenHeight)
  return chooseTierForScreenPixels(screenPixels, request.interactionMode ?? 'idle')
}

export class CanvasImageResourceManager {
  private textures = new Map<string, TextureEntry>()
  private loading = new Map<string, Promise<Texture | null>>()
  private maxTextures: number
  private maxConcurrentLoads: number
  private activeLoads = 0
  private queue: QueuedLoad[] = []
  private loader: TextureLoader
  private videoFrameLoader: VideoFrameTextureLoader
  private previewUrlResolver: PreviewUrlResolver
  private tileUrlResolver: TileUrlResolver

  constructor(options: {
    maxTextures?: number
    maxConcurrentLoads?: number
    loader?: TextureLoader
    videoFrameLoader?: VideoFrameTextureLoader
    previewUrlResolver?: PreviewUrlResolver
    tileUrlResolver?: TileUrlResolver
  } = {}) {
    this.maxTextures = options.maxTextures ?? DEFAULT_MAX_TEXTURES
    this.maxConcurrentLoads = options.maxConcurrentLoads ?? DEFAULT_MAX_CONCURRENT_LOADS
    this.loader = options.loader ?? defaultTextureLoader
    this.videoFrameLoader = options.videoFrameLoader ?? defaultVideoFrameTextureLoader
    this.previewUrlResolver = options.previewUrlResolver ?? defaultPreviewUrlResolver
    this.tileUrlResolver = options.tileUrlResolver ?? defaultTileUrlResolver
  }

  getTexture(urlOrRequest: string | CanvasTextureRequest) {
    if (typeof urlOrRequest === 'string') {
      return this.getBestCachedTexture(urlOrRequest)?.texture ?? null
    }

    const preferredTier = selectCanvasImageTextureTier(urlOrRequest)
    return this.getCachedTexture(urlOrRequest.url, preferredTier)?.texture
      ?? this.getBestCachedTexture(urlOrRequest.url, preferredTier)?.texture
      ?? null
  }

  getVideoFrameTexture(urlOrRequest: string | CanvasTextureRequest) {
    if (typeof urlOrRequest === 'string') {
      return this.getBestCachedTexture(urlOrRequest, undefined, 'video-frame')?.texture ?? null
    }

    const preferredTier = selectCanvasImageTextureTier(urlOrRequest)
    return this.getCachedTexture(urlOrRequest.url, preferredTier, 'video-frame')?.texture
      ?? this.getBestCachedTexture(urlOrRequest.url, preferredTier, 'video-frame')?.texture
      ?? null
  }

  loadTexture(urlOrRequest: string | CanvasTextureRequest) {
    const request = typeof urlOrRequest === 'string'
      ? {
        url: urlOrRequest,
        displayWidth: Number.POSITIVE_INFINITY,
        displayHeight: Number.POSITIVE_INFINITY,
        zoom: 100,
        interactionMode: 'idle' as const,
      }
      : urlOrRequest
    const tier = typeof urlOrRequest === 'string'
      ? 'full'
      : selectCanvasImageTextureTier(request)
    const cached = this.getCachedTexture(request.url, tier)
    if (cached) return Promise.resolve(cached.texture)

    const key = getCacheKey(request.url, tier)
    const loading = this.loading.get(key)
    if (loading) return loading

    const promise = this.enqueue(async () => {
      const sourceUrl = await this.resolveTextureUrl(request, tier)
      const loaded = await this.loader({
        url: sourceUrl,
        tier,
        maxDimension: getTierMaxDimension(tier),
      }) ?? (sourceUrl === request.url
        ? null
        : await this.loader({
          url: request.url,
          tier,
          maxDimension: getTierMaxDimension(tier),
        }))
      if (!loaded) return null

      const entry = {
        ...loaded,
        tier,
        lastUsedAt: now(),
      }
      this.textures.set(key, entry)
      this.prune()
      return loaded.texture
    }).finally(() => {
      this.loading.delete(key)
    })

    this.loading.set(key, promise)
    return promise
  }

  loadVideoFrameTexture(urlOrRequest: string | CanvasTextureRequest) {
    const request = typeof urlOrRequest === 'string'
      ? {
        url: urlOrRequest,
        displayWidth: Number.POSITIVE_INFINITY,
        displayHeight: Number.POSITIVE_INFINITY,
        zoom: 100,
        interactionMode: 'idle' as const,
      }
      : urlOrRequest
    const tier = typeof urlOrRequest === 'string'
      ? 'full'
      : selectCanvasImageTextureTier(request)
    const cached = this.getCachedTexture(request.url, tier, 'video-frame')
    if (cached) return Promise.resolve(cached.texture)

    const key = getCacheKey(request.url, tier, 'video-frame')
    const loading = this.loading.get(key)
    if (loading) return loading

    const promise = this.enqueue(async () => {
      const loaded = await this.videoFrameLoader({
        url: request.url,
        tier,
        maxDimension: getTierMaxDimension(tier),
      })
      if (!loaded) return null

      const entry = {
        ...loaded,
        tier,
        lastUsedAt: now(),
      }
      this.textures.set(key, entry)
      this.prune()
      return loaded.texture
    }).finally(() => {
      this.loading.delete(key)
    })

    this.loading.set(key, promise)
    return promise
  }

  preload(urls: string[] | CanvasTextureRequest[]) {
    urls.forEach((entry) => {
      if (typeof entry === 'string') {
        if (entry) void this.loadTexture(entry)
      } else if (entry.url) {
        void this.loadTexture(entry)
      }
    })
  }

  resolveTile(request: CanvasTileRequest) {
    return this.tileUrlResolver(request)
  }

  getStats() {
    return {
      textureCount: this.textures.size,
      loadingCount: this.loading.size,
      queuedLoads: this.queue.length,
      activeLoads: this.activeLoads,
    }
  }

  destroy() {
    this.queue = []
    this.loading.clear()
    this.textures.forEach(({ texture }) => texture.destroy(true))
    this.textures.clear()
  }

  private getCachedTexture(url: string, tier: CanvasImageTextureTier, kind: 'image' | 'video-frame' = 'image') {
    const entry = this.textures.get(getCacheKey(url, tier, kind))
    if (!entry) return null
    entry.lastUsedAt = now()
    return entry
  }

  private getBestCachedTexture(
    url: string,
    preferredTier?: CanvasImageTextureTier,
    kind: 'image' | 'video-frame' = 'image',
  ) {
    const entries = TIER_ORDER
      .map((tier) => this.textures.get(getCacheKey(url, tier, kind)))
      .filter((entry): entry is TextureEntry => Boolean(entry))
    if (entries.length === 0) return null

    const preferredRank = preferredTier ? getTierRank(preferredTier) : TIER_ORDER.length - 1
    const best = entries
      .filter((entry) => getTierRank(entry.tier) <= preferredRank)
      .sort((a, b) => getTierRank(b.tier) - getTierRank(a.tier))[0]
      ?? entries.sort((a, b) => getTierRank(a.tier) - getTierRank(b.tier))[0]

    best.lastUsedAt = now()
    return best
  }

  private enqueue(task: () => Promise<Texture | null>) {
    return new Promise<Texture | null>((resolve) => {
      const run = () => {
        this.activeLoads += 1
        task()
          .then(resolve)
          .catch(() => resolve(null))
          .finally(() => {
            this.activeLoads = Math.max(0, this.activeLoads - 1)
            this.pumpQueue()
          })
      }
      this.queue.push({ run })
      this.pumpQueue()
    })
  }

  private pumpQueue() {
    while (this.activeLoads < this.maxConcurrentLoads && this.queue.length > 0) {
      const next = this.queue.shift()
      next?.run()
    }
  }

  private prune() {
    if (this.textures.size <= this.maxTextures) return
    const entries = Array.from(this.textures.entries())
      .sort((a, b) => a[1].lastUsedAt - b[1].lastUsedAt)
    const removeCount = this.textures.size - this.maxTextures
    entries.slice(0, removeCount).forEach(([key, entry]) => {
      entry.texture.destroy(true)
      this.textures.delete(key)
    })
  }

  private async resolveTextureUrl(request: CanvasTextureRequest, tier: CanvasImageTextureTier) {
    if (tier === 'full' || !request.projectId) {
      return request.url
    }

    const previewUrl = await this.previewUrlResolver({
      projectId: request.projectId,
      url: request.url,
      tier,
    })
    return previewUrl || request.url
  }
}
