import React, { useEffect, useMemo, useRef, useState } from 'react'
import { Application, Container, Graphics, Sprite, Text as PixiText, Texture } from 'pixi.js'

import { CanvasImageResourceManager, type CanvasTileDescriptor } from '../canvasImageResourceManager'
import {
  buildVisibleCanvasTileSlots,
  selectCanvasTileLevel,
  type CanvasTileSlot,
  type CanvasTileViewport,
} from '../canvasImageTiles'
import type { CanvasRenderNode } from '../canvasRenderModel'
import type { CanvasInteractionPreviewController } from '../canvasInteractionPreview'
import { recordCanvasPerfSnapshot } from '../canvasPerfHarness'
import { scaleBrushPathPoint } from '../brushPaths'
import {
  formatTextContentForDisplay,
  getTextItemVariantStyle,
  normalizeTextCanvasItem,
} from '../textTypography'

type CanvasWebGLStageProps = {
  canvasRef: React.RefObject<HTMLElement>
  canvasCamera: any
  projectId?: number | null
  nodes: CanvasRenderNode[]
  zoom: number
  offset: { x: number; y: number }
  isDark: boolean
  isInteracting?: boolean
  interactionPreview?: CanvasInteractionPreviewController | null
  onReadyChange?: (ready: boolean) => void
  onFallback?: () => void
}

type DisplayRecord = {
  container: Container
  committedBounds: { x: number; y: number; width: number; height: number }
  imageSourceUrl?: string
  imageSprite?: Sprite
  tileContainer?: Container
  tileState?: TileDisplayState
  placeholder?: Graphics
  videoPlayOverlay?: Graphics
  brushGraphics?: Graphics
  textDisplay?: PixiText
}

type TileDisplayState = {
  level: number
  sourceKey: string
  metadata?: CanvasTileDescriptor
  descriptors: Map<string, CanvasTileDescriptor>
  loadingDescriptors: Set<string>
  retryingDescriptors: Set<string>
  loadingTextures: Set<string>
  sprites: Map<string, Sprite>
}

const EMPTY_TEXTURE = Texture.EMPTY

function numberToColor(value: string | undefined, fallback: number) {
  if (!value) return fallback
  const match = value.match(/#([0-9a-f]{6})/i)
  if (!match) return fallback
  return Number.parseInt(match[1], 16)
}

function parseCanvasColor(value: string | undefined, fallback: { color: number; alpha: number }) {
  if (!value || value === 'transparent') return fallback
  const hexMatch = value.match(/#([0-9a-f]{6})([0-9a-f]{2})?/i)
  if (hexMatch) {
    return {
      color: Number.parseInt(hexMatch[1], 16),
      alpha: hexMatch[2] ? Number.parseInt(hexMatch[2], 16) / 255 : fallback.alpha,
    }
  }
  const rgbaMatch = value.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/i)
  if (rgbaMatch) {
    const red = Math.max(0, Math.min(255, Number(rgbaMatch[1]) || 0))
    const green = Math.max(0, Math.min(255, Number(rgbaMatch[2]) || 0))
    const blue = Math.max(0, Math.min(255, Number(rgbaMatch[3]) || 0))
    const alpha = rgbaMatch[4] == null
      ? fallback.alpha
      : Math.max(0, Math.min(1, Number(rgbaMatch[4]) || 0))
    return {
      color: (red << 16) + (green << 8) + blue,
      alpha,
    }
  }
  return fallback
}

function drawPlaceholder(graphics: Graphics, node: CanvasRenderNode, isDark: boolean) {
  graphics.clear()
  const width = Math.max(1, node.bounds.width)
  const height = Math.max(1, node.bounds.height)
  const groupFill = parseCanvasColor(node.item.background_color, {
    color: isDark ? 0x1677ff : 0x1677ff,
    alpha: 0.08,
  })
  const fillColor = node.renderKind === 'group'
    ? groupFill.color
    : node.item.status === 'failed'
      ? (isDark ? 0x4a1f1f : 0xffe3e3)
      : node.renderKind === 'generator-card'
        ? (isDark ? 0x1a2233 : 0xeaf2ff)
        : (isDark ? 0x262626 : 0xf8fafc)
  const fillAlpha = node.renderKind === 'group' ? groupFill.alpha : 1

  graphics
    .roundRect(0, 0, width, height, Math.min(12, Math.max(4, Math.min(width, height) * 0.04)))
    .fill({ color: fillColor, alpha: fillAlpha })

  if (node.renderKind === 'generator-card') {
    graphics
      .rect(width * 0.1, height * 0.18, Math.max(16, width * 0.22), Math.max(8, height * 0.14))
      .fill({ color: 0x3b82f6, alpha: 0.85 })
    graphics
      .rect(width * 0.1, height * 0.76, width * 0.8, Math.max(4, height * 0.04))
      .fill({ color: isDark ? 0xffffff : 0x0f172a, alpha: 0.12 })
    if (typeof node.item.progress === 'number') {
      graphics
        .rect(width * 0.1, height * 0.76, width * 0.8 * Math.max(0, Math.min(100, node.item.progress)) / 100, Math.max(4, height * 0.04))
        .fill({ color: 0x3b82f6, alpha: 1 })
    }
  }
}

function getVideoPosterUrl(item: CanvasRenderNode['item']) {
  const source = item as CanvasRenderNode['item'] & {
    poster_url?: string
    posterUrl?: string
    thumbnail_url?: string
    thumbnailUrl?: string
    cover_url?: string
    coverUrl?: string
  }
  return source.poster_url
    || source.posterUrl
    || source.thumbnail_url
    || source.thumbnailUrl
    || source.cover_url
    || source.coverUrl
    || ''
}

function drawVideoPosterPlaceholder(graphics: Graphics, node: CanvasRenderNode, isDark: boolean) {
  graphics.clear()
  const width = Math.max(1, node.bounds.width)
  const height = Math.max(1, node.bounds.height)
  graphics
    .roundRect(0, 0, width, height, Math.min(10, Math.max(4, Math.min(width, height) * 0.04)))
    .fill({ color: isDark ? 0x171717 : 0x111827, alpha: isDark ? 0.9 : 0.82 })

  const stripeCount = Math.max(3, Math.min(8, Math.floor(width / 80)))
  for (let index = 0; index < stripeCount; index += 1) {
    const x = (width / stripeCount) * index
    graphics
      .rect(x, 0, Math.max(1, width / stripeCount - 2), height)
      .fill({ color: index % 2 === 0 ? 0xffffff : 0x000000, alpha: index % 2 === 0 ? 0.04 : 0.06 })
  }
}

function drawVideoPlayOverlay(graphics: Graphics, node: CanvasRenderNode) {
  graphics.clear()
  const width = Math.max(1, node.bounds.width)
  const height = Math.max(1, node.bounds.height)
  const radius = Math.max(18, Math.min(34, Math.min(width, height) * 0.16))
  const centerX = width / 2
  const centerY = height / 2
  graphics
    .circle(centerX, centerY, radius)
    .fill({ color: 0x000000, alpha: 0.42 })
  graphics
    .moveTo(centerX - radius * 0.28, centerY - radius * 0.42)
    .lineTo(centerX - radius * 0.28, centerY + radius * 0.42)
    .lineTo(centerX + radius * 0.48, centerY)
    .closePath()
    .fill({ color: 0xffffff, alpha: 0.92 })
}

function ensureVideoPlayOverlay(record: DisplayRecord) {
  if (!record.videoPlayOverlay) {
    record.videoPlayOverlay = new Graphics()
    record.videoPlayOverlay.eventMode = 'none'
  }
  record.container.addChild(record.videoPlayOverlay)
  return record.videoPlayOverlay
}

function drawBrushPath(graphics: Graphics, node: CanvasRenderNode) {
  graphics.clear()
  const points = node.item.points || []
  if (points.length === 0) return

  const width = Math.max(1, node.bounds.width)
  const height = Math.max(1, node.bounds.height)
  const firstPoint = scaleBrushPathPoint(points[0], { width, height })

  graphics.moveTo(firstPoint.x, firstPoint.y)
  if (points.length === 1) {
    graphics.lineTo(firstPoint.x, firstPoint.y)
  } else {
    points.slice(1).forEach((point) => {
      const scaled = scaleBrushPathPoint(point, { width, height })
      graphics.lineTo(scaled.x, scaled.y)
    })
  }
  graphics.stroke({
    color: numberToColor(node.item.brushColor, 0x111111),
    width: Math.max(1, node.item.brushSize || 1),
    cap: 'round',
    join: 'round',
  })
}

function updateTextDisplay(textDisplay: PixiText, node: CanvasRenderNode) {
  const textItem = normalizeTextCanvasItem(node.item)
  const variant = getTextItemVariantStyle(textItem)
  textDisplay.text = formatTextContentForDisplay(textItem).join('\n')
  textDisplay.style = {
    fontFamily: textItem.fontFamily,
    fontSize: textItem.fontSize,
    fontStyle: variant.fontStyle,
    fontWeight: variant.fontWeight >= 700 ? 'bold' : 'normal',
    fill: textItem.fillColor,
    stroke: textItem.strokeColor === 'transparent' || !textItem.strokeWidth
      ? undefined
      : {
        color: textItem.strokeColor,
        width: textItem.strokeWidth,
      },
    align: textItem.textAlign,
    lineHeight: textItem.fontSize * textItem.lineHeight,
    wordWrap: true,
    wordWrapWidth: Math.max(1, node.bounds.width),
    breakWords: true,
  }
  textDisplay.rotation = textItem.writingMode === 'vertical' ? Math.PI / 2 : 0
}

function setRecordVisibility(record: DisplayRecord, visible: {
  image?: boolean
  placeholder?: boolean
  videoPlay?: boolean
  brush?: boolean
  text?: boolean
}) {
  if (record.imageSprite) record.imageSprite.visible = Boolean(visible.image)
  if (record.placeholder) record.placeholder.visible = Boolean(visible.placeholder)
  if (record.videoPlayOverlay) record.videoPlayOverlay.visible = Boolean(visible.videoPlay)
  if (record.brushGraphics) record.brushGraphics.visible = Boolean(visible.brush)
  if (record.textDisplay) record.textDisplay.visible = Boolean(visible.text)
}

function destroyTileSprites(record: DisplayRecord) {
  if (!record.tileState) return
  record.tileState.sprites.forEach((sprite) => {
    record.tileContainer?.removeChild(sprite)
    sprite.destroy()
  })
  record.tileState.sprites.clear()
  record.tileState.loadingDescriptors.clear()
  record.tileState.retryingDescriptors.clear()
  record.tileState.loadingTextures.clear()
}

function disableTileOverlay(record: DisplayRecord) {
  if (record.tileContainer) {
    record.tileContainer.visible = false
  }
  destroyTileSprites(record)
  record.tileState = undefined
}

function ensureTileOverlay(record: DisplayRecord, level: number, sourceKey: string) {
  if (!record.tileContainer) {
    record.tileContainer = new Container()
    record.tileContainer.eventMode = 'none'
    record.container.addChild(record.tileContainer)
  }
  record.tileContainer.visible = true

  if (!record.tileState || record.tileState.level !== level || record.tileState.sourceKey !== sourceKey) {
    destroyTileSprites(record)
    record.tileState = {
      level,
      sourceKey,
      descriptors: new Map(),
      loadingDescriptors: new Set(),
      retryingDescriptors: new Set(),
      loadingTextures: new Set(),
      sprites: new Map(),
    }
  }
  return record.tileState
}

function getTileKey(level: number, x: number, y: number) {
  return `${level}:${x}:${y}`
}

function applyTileTexture({
  descriptor,
  resources,
  sprite,
  tileState,
  tileKey,
}: {
  descriptor: CanvasTileDescriptor
  resources: CanvasImageResourceManager
  sprite: Sprite
  tileState: TileDisplayState
  tileKey: string
}) {
  if (descriptor.status !== 'ready' || !descriptor.url) return

  const cached = resources.getTexture(descriptor.url)
  if (cached) {
    sprite.texture = cached
    return
  }
  if (tileState.loadingTextures.has(tileKey)) return

  tileState.loadingTextures.add(tileKey)
  void resources.loadTexture(descriptor.url).then((texture) => {
    tileState.loadingTextures.delete(tileKey)
    if (!texture || tileState.sprites.get(tileKey) !== sprite) return
    sprite.texture = texture
  })
}

function requestTileDescriptor({
  projectId,
  url,
  level,
  slot,
  resources,
  tileState,
  onMetadataReady,
}: {
  projectId: number
  url: string
  level: number
  slot: Pick<CanvasTileSlot, 'x' | 'y'>
  resources: CanvasImageResourceManager
  tileState: TileDisplayState
  onMetadataReady?: () => void
}) {
  const tileKey = getTileKey(level, slot.x, slot.y)
  if (tileState.descriptors.has(tileKey) || tileState.loadingDescriptors.has(tileKey)) return

  tileState.loadingDescriptors.add(tileKey)
  void resources.resolveTile({
    projectId,
    url,
    z: level,
    x: slot.x,
    y: slot.y,
  }).then((descriptor) => {
    tileState.loadingDescriptors.delete(tileKey)
    if (!descriptor || tileState.level !== level) return

    const isReady = descriptor.status === 'ready' && Boolean(descriptor.url)
    if (!tileState.metadata && descriptor.levelWidth && descriptor.levelHeight) {
      tileState.metadata = descriptor
      onMetadataReady?.()
    }

    if (!isReady) {
      const sprite = tileState.sprites.get(tileKey)
      if (sprite) sprite.texture = EMPTY_TEXTURE
      if (onMetadataReady && !tileState.retryingDescriptors.has(tileKey)) {
        tileState.retryingDescriptors.add(tileKey)
        window.setTimeout(() => {
          tileState.retryingDescriptors.delete(tileKey)
          if (tileState.level === level) onMetadataReady()
        }, tileState.metadata ? 800 : 300)
      }
      return
    }

    tileState.descriptors.set(tileKey, descriptor)

    const sprite = tileState.sprites.get(tileKey)
    if (sprite) {
      applyTileTexture({ descriptor, resources, sprite, tileState, tileKey })
    }
  }).catch(() => {
    tileState.loadingDescriptors.delete(tileKey)
  })
}

function updateTileOverlay({
  record,
  node,
  projectId,
  resources,
  viewport,
  zoom,
  isInteracting,
  minTiledScreenPixels,
  onMetadataReady,
}: {
  record: DisplayRecord
  node: CanvasRenderNode
  projectId: number | null | undefined
  resources: CanvasImageResourceManager
  viewport: CanvasTileViewport
  zoom: number
  isInteracting: boolean
  minTiledScreenPixels?: number
  onMetadataReady: () => void
}) {
  if (!projectId || node.renderKind !== 'image' || !node.item.url) {
    disableTileOverlay(record)
    return
  }

  const level = selectCanvasTileLevel({
    displayWidth: node.bounds.width,
    displayHeight: node.bounds.height,
    zoom,
    interactionMode: isInteracting ? 'interactive' : 'idle',
    minTiledScreenPixels,
  })
  if (level === null) {
    disableTileOverlay(record)
    return
  }

  const tileState = ensureTileOverlay(record, level, `${projectId}:${node.item.url}`)
  if (!tileState.metadata) {
    requestTileDescriptor({
      projectId,
      url: node.item.url,
      level,
      slot: { x: 0, y: 0 },
      resources,
      tileState,
      onMetadataReady,
    })
    return
  }

  const slots = buildVisibleCanvasTileSlots({
    bounds: node.bounds,
    descriptor: tileState.metadata,
    viewport,
  })
  const nextKeys = new Set(slots.map((slot) => getTileKey(level, slot.x, slot.y)))
  tileState.sprites.forEach((sprite, tileKey) => {
    if (nextKeys.has(tileKey)) return
    record.tileContainer?.removeChild(sprite)
    sprite.destroy()
    tileState.sprites.delete(tileKey)
  })

  slots.forEach((slot) => {
    const tileKey = getTileKey(level, slot.x, slot.y)
    let sprite = tileState.sprites.get(tileKey)
    if (!sprite) {
      sprite = new Sprite(EMPTY_TEXTURE)
      sprite.eventMode = 'none'
      tileState.sprites.set(tileKey, sprite)
      record.tileContainer?.addChild(sprite)
    }
    sprite.position.set(slot.left, slot.top)
    sprite.width = slot.width
    sprite.height = slot.height

    const descriptor = tileState.descriptors.get(tileKey)
    if (descriptor) {
      applyTileTexture({ descriptor, resources, sprite, tileState, tileKey })
    } else {
      requestTileDescriptor({
        projectId,
        url: node.item.url,
        level,
        slot,
        resources,
        tileState,
      })
    }
  })
}

function applyCamera(stage: Container, viewport: { width: number; height: number }, camera: { zoom: number; offset: { x: number; y: number } }) {
  const scale = camera.zoom / 100
  stage.position.set(viewport.width / 2 + camera.offset.x, viewport.height / 2 + camera.offset.y)
  stage.scale.set(scale)
}

function applyRecordRect(record: DisplayRecord, rect: { x: number; y: number; width?: number; height?: number }) {
  const width = Math.max(1, rect.width ?? record.committedBounds.width)
  const height = Math.max(1, rect.height ?? record.committedBounds.height)
  const committedWidth = Math.max(1, record.committedBounds.width)
  const committedHeight = Math.max(1, record.committedBounds.height)

  record.container.position.set(rect.x, rect.y)
  record.container.scale.set(width / committedWidth, height / committedHeight)
}

function restoreRecordRect(record: DisplayRecord) {
  applyRecordRect(record, record.committedBounds)
}

export const CanvasWebGLStage = React.memo(function CanvasWebGLStage({
  canvasRef,
  canvasCamera,
  projectId,
  nodes,
  zoom,
  offset,
  isDark,
  isInteracting = false,
  interactionPreview,
  onReadyChange,
  onFallback,
}: CanvasWebGLStageProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const appRef = useRef<Application | null>(null)
  const worldRef = useRef<Container | null>(null)
  const recordsRef = useRef(new Map<string, DisplayRecord>())
  const previewIdsRef = useRef(new Set<string>())
  const resourcesRef = useRef<CanvasImageResourceManager | null>(null)
  const onReadyChangeRef = useRef(onReadyChange)
  const onFallbackRef = useRef(onFallback)
  const mountedRef = useRef(false)
  const [viewport, setViewport] = useState({ width: 0, height: 0 })
  const [ready, setReady] = useState(false)
  const [tileRefreshKey, setTileRefreshKey] = useState(0)

  const nodeKey = useMemo(() => nodes.map((node) => `${node.id}:${node.zIndex}:${node.bounds.x}:${node.bounds.y}:${node.bounds.width}:${node.bounds.height}:${node.item.url}:${node.item.status}:${node.item.progress}:${node.item.text}:${node.item.brushColor}:${node.item.brushSize}:${node.renderKind}`).join('|'), [nodes])

  useEffect(() => {
    onReadyChangeRef.current = onReadyChange
  }, [onReadyChange])

  useEffect(() => {
    onFallbackRef.current = onFallback
  }, [onFallback])

  useEffect(() => {
    mountedRef.current = true
    let disposed = false
    let initialized = false
    const host = hostRef.current
    if (!host) return undefined

    const app = new Application()
    const world = new Container()
    const resources = new CanvasImageResourceManager()
    resourcesRef.current = resources

    app.init({
      width: 1,
      height: 1,
      preference: 'webgl',
      backgroundAlpha: 0,
      antialias: false,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    }).then(() => {
      initialized = true
      if (disposed) {
        app.destroy(true)
        return
      }
      app.stage.addChild(world)
      app.canvas.style.position = 'absolute'
      app.canvas.style.inset = '0'
      app.canvas.style.width = '100%'
      app.canvas.style.height = '100%'
      app.canvas.style.pointerEvents = 'none'
      const handleContextLost = (event: Event) => {
        event.preventDefault()
        setReady(false)
        onReadyChangeRef.current?.(false)
        onFallbackRef.current?.()
      }
      const handleContextRestored = () => {
        onReadyChangeRef.current?.(false)
      }
      app.canvas.addEventListener('webglcontextlost', handleContextLost)
      app.canvas.addEventListener('webglcontextrestored', handleContextRestored)
      host.appendChild(app.canvas)
      ;(app.canvas as any).__canvasWebglHandlers = {
        handleContextLost,
        handleContextRestored,
      }
      appRef.current = app
      worldRef.current = world
      setReady(true)
      onReadyChangeRef.current?.(true)
    }).catch(() => {
      if (!disposed) {
        onReadyChangeRef.current?.(false)
        onFallbackRef.current?.()
      }
    })

    return () => {
      mountedRef.current = false
      disposed = true
      setReady(false)
      onReadyChangeRef.current?.(false)
      recordsRef.current.forEach((record) => record.container.destroy({ children: true }))
      recordsRef.current.clear()
      resources.destroy()
      resourcesRef.current = null
      if (appRef.current) {
        const handlers = (appRef.current.canvas as any).__canvasWebglHandlers
        if (handlers) {
          appRef.current.canvas.removeEventListener('webglcontextlost', handlers.handleContextLost)
          appRef.current.canvas.removeEventListener('webglcontextrestored', handlers.handleContextRestored)
        }
        appRef.current.destroy(true)
        appRef.current = null
      } else if (initialized) {
        app.destroy(true)
      }
      worldRef.current = null
    }
  }, [])

  useEffect(() => {
    const element = canvasRef.current || hostRef.current?.parentElement
    if (!element) return undefined
    const measure = () => {
      const width = Math.max(1, Math.round(element.clientWidth || element.getBoundingClientRect().width || 1))
      const height = Math.max(1, Math.round(element.clientHeight || element.getBoundingClientRect().height || 1))
      setViewport((current) => current.width === width && current.height === height ? current : { width, height })
    }
    measure()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(measure) : null
    observer?.observe(element)
    window.addEventListener('resize', measure)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [canvasRef])

  useEffect(() => {
    const app = appRef.current
    const world = worldRef.current
    if (!ready || !app || !world || !viewport.width || !viewport.height) return
    app.renderer.resize(viewport.width, viewport.height)
    applyCamera(world, viewport, { zoom, offset })
  }, [offset, ready, viewport, zoom])

  useEffect(() => {
    if (!canvasCamera?.subscribe) return undefined
    return canvasCamera.subscribe((camera: any) => {
      const world = worldRef.current
      if (!world) return
      applyCamera(world, viewport, camera)
    })
  }, [canvasCamera, viewport])

  useEffect(() => {
    if (!interactionPreview?.subscribe) return undefined
    return interactionPreview.subscribe((items, options) => {
      if (items?.length) {
        const nextIds = new Set(items.map((item) => item.id))
        previewIdsRef.current.forEach((id) => {
          if (nextIds.has(id)) return
          const record = recordsRef.current.get(id)
          if (record) restoreRecordRect(record)
        })
        items.forEach((item) => {
          const record = recordsRef.current.get(item.id)
          if (!record) return
          applyRecordRect(record, {
            x: item.x,
            y: item.y,
            width: item.width,
            height: item.height,
          })
        })
        previewIdsRef.current = nextIds
        return
      }

      if (options?.restore === false) {
        previewIdsRef.current.clear()
        return
      }
      previewIdsRef.current.forEach((id) => {
        const record = recordsRef.current.get(id)
        if (record) restoreRecordRect(record)
      })
      previewIdsRef.current.clear()
    })
  }, [interactionPreview])

  useEffect(() => {
    const world = worldRef.current
    const resources = resourcesRef.current
    if (!ready || !world || !resources) return

    const nextIds = new Set(nodes.map((node) => node.id))
    recordsRef.current.forEach((record, id) => {
      if (nextIds.has(id)) return
      world.removeChild(record.container)
      record.container.destroy({ children: true })
      recordsRef.current.delete(id)
    })

    nodes.forEach((node) => {
      let record = recordsRef.current.get(node.id)
      if (!record) {
        const container = new Container()
        container.eventMode = 'none'
        record = {
          container,
          committedBounds: node.bounds,
        }
        recordsRef.current.set(node.id, record)
        world.addChild(container)
      }

      const { container } = record
      record.committedBounds = node.bounds
      if (!previewIdsRef.current.has(node.id)) {
        container.position.set(node.bounds.x, node.bounds.y)
        container.scale.set(1)
      }
      container.zIndex = node.zIndex
      container.visible = !node.hidden && node.visible

      const posterUrl = node.renderKind === 'video-poster' ? getVideoPosterUrl(node.item) : ''
      const videoFrameUrl = node.renderKind === 'video-poster' && !posterUrl ? node.item.url : ''
      const textureUrl = node.renderKind === 'image' ? node.item.url : (posterUrl || videoFrameUrl)
      const isVideoFrameTexture = node.renderKind === 'video-poster' && Boolean(videoFrameUrl)
      if ((node.renderKind === 'image' && node.item.url) || (node.renderKind === 'video-poster' && textureUrl)) {
        if (!record.imageSprite) {
          record.imageSprite = new Sprite(EMPTY_TEXTURE)
          record.imageSprite.eventMode = 'none'
          container.addChild(record.imageSprite)
        }
        if (isVideoFrameTexture && !record.placeholder) {
          record.placeholder = new Graphics()
          record.placeholder.eventMode = 'none'
          container.addChild(record.placeholder)
        }
        if (node.renderKind === 'video-poster') {
          drawVideoPlayOverlay(ensureVideoPlayOverlay(record), node)
        }
        if (!previewIdsRef.current.has(node.id)) {
          record.imageSprite.width = Math.max(1, node.bounds.width)
          record.imageSprite.height = Math.max(1, node.bounds.height)
        }
        if (isVideoFrameTexture && record.placeholder) {
          drawVideoPosterPlaceholder(record.placeholder, node, isDark)
        }

        const textureRequest = {
          url: textureUrl,
          projectId,
          displayWidth: node.bounds.width,
          displayHeight: node.bounds.height,
          zoom,
          interactionMode: isInteracting ? 'interactive' as const : 'idle' as const,
        }
        const imageSourceKey = `${isVideoFrameTexture ? 'video-frame' : 'image'}:${textureRequest.url}`
        record.imageSourceUrl = imageSourceKey
        const cached = isVideoFrameTexture
          ? resources.getVideoFrameTexture(textureRequest)
          : resources.getTexture(textureRequest)
        if (cached) {
          record.imageSprite.texture = cached
        } else {
          record.imageSprite.texture = EMPTY_TEXTURE
        }
        setRecordVisibility(record, {
          image: true,
          placeholder: Boolean(isVideoFrameTexture && !cached),
          videoPlay: node.renderKind === 'video-poster',
        })
        const loadTexture = isVideoFrameTexture
          ? resources.loadVideoFrameTexture(textureRequest)
          : resources.loadTexture(textureRequest)
        void loadTexture.then((texture) => {
          if (!texture) return
          const latest = recordsRef.current.get(node.id)
          if (latest?.imageSprite && latest.container.visible && latest.imageSourceUrl === imageSourceKey) {
            latest.imageSprite.texture = texture
            if (latest.placeholder) latest.placeholder.visible = false
          }
        })
        updateTileOverlay({
          record,
          node,
          projectId,
          resources,
          viewport: {
            width: viewport.width,
            height: viewport.height,
            zoom,
            offset,
          },
          zoom,
          isInteracting,
          minTiledScreenPixels: node.selected ? 768 : undefined,
          onMetadataReady: () => {
            if (mountedRef.current) {
              setTileRefreshKey((value) => value + 1)
            }
          },
        })
      } else if (node.renderKind === 'video-poster') {
        disableTileOverlay(record)
        if (!record.placeholder) {
          record.placeholder = new Graphics()
          record.placeholder.eventMode = 'none'
          container.addChild(record.placeholder)
        }
        drawVideoPosterPlaceholder(record.placeholder, node, isDark)
        drawVideoPlayOverlay(ensureVideoPlayOverlay(record), node)
        setRecordVisibility(record, { placeholder: true, videoPlay: true })
      } else if (node.renderKind === 'brush-path') {
        disableTileOverlay(record)
        if (!record.brushGraphics) {
          record.brushGraphics = new Graphics()
          record.brushGraphics.eventMode = 'none'
          container.addChild(record.brushGraphics)
        }
        drawBrushPath(record.brushGraphics, node)
        setRecordVisibility(record, { brush: true })
      } else if (node.renderKind === 'text') {
        disableTileOverlay(record)
        if (!record.textDisplay) {
          record.textDisplay = new PixiText({ text: '' })
          record.textDisplay.eventMode = 'none'
          container.addChild(record.textDisplay)
        }
        updateTextDisplay(record.textDisplay, node)
        setRecordVisibility(record, { text: true })
      } else {
        disableTileOverlay(record)
        if (!record.placeholder) {
          record.placeholder = new Graphics()
          record.placeholder.eventMode = 'none'
          container.addChild(record.placeholder)
        }
        drawPlaceholder(record.placeholder, node, isDark)
        setRecordVisibility(record, { placeholder: true })
      }
    })

    world.sortChildren()
    const stats = resources.getStats()
    recordCanvasPerfSnapshot({
      renderer: 'webgl',
      visibleItems: nodes.length,
      webglItems: nodes.length,
      overlayItems: 0,
      domImages: document.querySelectorAll('[data-canvas-media-img="true"]').length,
      textureCount: stats.textureCount,
      loadingTextures: stats.loadingCount,
    })
  }, [isDark, isInteracting, nodeKey, nodes, offset, projectId, ready, tileRefreshKey, viewport, zoom])

  return (
    <div
      ref={hostRef}
      data-testid="canvas-webgl-stage"
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
      }}
    />
  )
})
