import type { CanvasTileDescriptor } from './canvasImageResourceManager'

export type CanvasTileBounds = {
  x: number
  y: number
  width: number
  height: number
}

export type CanvasTileViewport = {
  width: number
  height: number
  zoom: number
  offset: { x: number; y: number }
}

export type CanvasTileSlot = {
  key: string
  x: number
  y: number
  left: number
  top: number
  width: number
  height: number
}

const DEFAULT_TILE_SIZE = 256
const DEFAULT_MIN_TILED_SCREEN_PIXELS = 1024
const DEFAULT_MAX_Z = 12
const DEFAULT_MAX_VISIBLE_TILES = 256

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function getWorldRect(viewport: CanvasTileViewport) {
  const scale = Math.max(0.01, viewport.zoom / 100)
  const centerX = viewport.width / 2 + viewport.offset.x
  const centerY = viewport.height / 2 + viewport.offset.y
  return {
    left: (0 - centerX) / scale,
    top: (0 - centerY) / scale,
    right: (viewport.width - centerX) / scale,
    bottom: (viewport.height - centerY) / scale,
  }
}

export function selectCanvasTileLevel({
  displayWidth,
  displayHeight,
  zoom,
  interactionMode = 'idle',
  tileSize = DEFAULT_TILE_SIZE,
  minTiledScreenPixels = DEFAULT_MIN_TILED_SCREEN_PIXELS,
  maxZ = DEFAULT_MAX_Z,
}: {
  displayWidth: number
  displayHeight: number
  zoom: number
  interactionMode?: 'idle' | 'interactive'
  tileSize?: number
  minTiledScreenPixels?: number
  maxZ?: number
}) {
  if (interactionMode !== 'idle' || tileSize <= 0) return null

  const scale = Math.max(0.01, zoom / 100)
  const screenPixels = Math.max(1, Math.max(displayWidth, displayHeight) * scale)
  if (screenPixels < minTiledScreenPixels) return null

  return clamp(Math.ceil(Math.log2(screenPixels / tileSize)), 0, maxZ)
}

export function buildVisibleCanvasTileSlots({
  bounds,
  descriptor,
  viewport,
  maxVisibleTiles = DEFAULT_MAX_VISIBLE_TILES,
}: {
  bounds: CanvasTileBounds
  descriptor: CanvasTileDescriptor
  viewport: CanvasTileViewport
  maxVisibleTiles?: number
}) {
  const tileSize = descriptor.tileSize
  const levelWidth = descriptor.levelWidth
  const levelHeight = descriptor.levelHeight
  const columns = descriptor.columns
  const rows = descriptor.rows

  if (
    !tileSize
    || !levelWidth
    || !levelHeight
    || !columns
    || !rows
    || bounds.width <= 0
    || bounds.height <= 0
  ) {
    return []
  }

  const world = getWorldRect(viewport)
  const localLeft = clamp(world.left - bounds.x, 0, bounds.width)
  const localTop = clamp(world.top - bounds.y, 0, bounds.height)
  const localRight = clamp(world.right - bounds.x, 0, bounds.width)
  const localBottom = clamp(world.bottom - bounds.y, 0, bounds.height)
  if (localRight <= localLeft || localBottom <= localTop) return []

  const levelLeft = localLeft / bounds.width * levelWidth
  const levelTop = localTop / bounds.height * levelHeight
  const levelRight = localRight / bounds.width * levelWidth
  const levelBottom = localBottom / bounds.height * levelHeight
  const startX = clamp(Math.floor(levelLeft / tileSize), 0, columns - 1)
  const endX = clamp(Math.floor(Math.max(0, levelRight - 0.001) / tileSize), 0, columns - 1)
  const startY = clamp(Math.floor(levelTop / tileSize), 0, rows - 1)
  const endY = clamp(Math.floor(Math.max(0, levelBottom - 0.001) / tileSize), 0, rows - 1)
  const visibleCount = (endX - startX + 1) * (endY - startY + 1)
  if (visibleCount <= 0 || visibleCount > maxVisibleTiles) return []

  const slots: CanvasTileSlot[] = []
  for (let y = startY; y <= endY; y += 1) {
    for (let x = startX; x <= endX; x += 1) {
      const levelTileLeft = x * tileSize
      const levelTileTop = y * tileSize
      const levelTileWidth = Math.min(tileSize, levelWidth - levelTileLeft)
      const levelTileHeight = Math.min(tileSize, levelHeight - levelTileTop)
      slots.push({
        key: `${x}:${y}`,
        x,
        y,
        left: levelTileLeft / levelWidth * bounds.width,
        top: levelTileTop / levelHeight * bounds.height,
        width: Math.max(1, levelTileWidth / levelWidth * bounds.width),
        height: Math.max(1, levelTileHeight / levelHeight * bounds.height),
      })
    }
  }
  return slots
}
