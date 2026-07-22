// @ts-nocheck

import React, { useEffect, useLayoutEffect, useMemo, useReducer, useRef, useState } from 'react'

import type { CanvasItem } from '@/api/endpoints/projects'

import { scaleBrushPathPoint } from '../brushPaths'
import {
  getVisibleCanvasSceneItems,
  shouldUseCanvasSceneRenderer,
} from '../canvasScene'
import { isGenerationTaskPendingStatus } from '../generationTaskBinding'

function resolveThemeColor(name: string, fallback: string) {
  if (typeof window === 'undefined') return fallback
  const value = window.getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

function parseColorChannel(value: string) {
  const numeric = Number.parseFloat(value.trim())
  return Number.isFinite(numeric) ? numeric : 0
}

function parseThemeColor(color: string) {
  const normalized = color.trim()
  const hex = normalized.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i)
  if (hex) {
    const raw = hex[1].length === 3
      ? hex[1].split('').map((char) => `${char}${char}`).join('')
      : hex[1]
    return {
      r: Number.parseInt(raw.slice(0, 2), 16),
      g: Number.parseInt(raw.slice(2, 4), 16),
      b: Number.parseInt(raw.slice(4, 6), 16),
      a: 1,
    }
  }

  const rgb = normalized.match(/^rgba?\((.+)\)$/i)
  if (rgb) {
    const parts = rgb[1].split(',').map((part) => part.trim())
    return {
      r: parseColorChannel(parts[0]),
      g: parseColorChannel(parts[1]),
      b: parseColorChannel(parts[2]),
      a: parts[3] === undefined ? 1 : parseColorChannel(parts[3]),
    }
  }

  return null
}

function mixThemeColor(color: string, surface: string, amount: number) {
  const foreground = parseThemeColor(color)
  const background = parseThemeColor(surface)
  if (!foreground || !background) return surface
  const ratio = Math.max(0, Math.min(amount, 100)) / 100
  const inverse = 1 - ratio
  const alpha = foreground.a * ratio + background.a * inverse
  return `rgba(${Math.round(foreground.r * ratio + background.r * inverse)}, ${Math.round(foreground.g * ratio + background.g * inverse)}, ${Math.round(foreground.b * ratio + background.b * inverse)}, ${alpha})`
}

function drawRoundedRect(ctx: CanvasRenderingContext2D, x: number, y: number, width: number, height: number, radius: number) {
  if (typeof ctx.roundRect === 'function') {
    ctx.beginPath()
    ctx.roundRect(x, y, width, height, radius)
    return
  }

  const safeRadius = Math.min(radius, width / 2, height / 2)
  ctx.beginPath()
  ctx.moveTo(x + safeRadius, y)
  ctx.lineTo(x + width - safeRadius, y)
  ctx.arc(x + width - safeRadius, y + safeRadius, safeRadius, -Math.PI / 2, 0)
  ctx.lineTo(x + width, y + height - safeRadius)
  ctx.arc(x + width - safeRadius, y + height - safeRadius, safeRadius, 0, Math.PI / 2)
  ctx.lineTo(x + safeRadius, y + height)
  ctx.arc(x + safeRadius, y + height - safeRadius, safeRadius, Math.PI / 2, Math.PI)
  ctx.lineTo(x, y + safeRadius)
  ctx.arc(x + safeRadius, y + safeRadius, safeRadius, Math.PI, Math.PI * 1.5)
}

function drawSceneCard(ctx: CanvasRenderingContext2D, args: {
  item: CanvasItem
  left: number
  top: number
  width: number
  height: number
  isDark: boolean
}) {
  const { item, left, top, width, height, isDark } = args
  const radius = Math.max(6, Math.min(width, height) * 0.06)

  ctx.save()
  drawRoundedRect(ctx, left, top, width, height, radius)
  const surfaceMuted = resolveThemeColor('--app-surface-muted', isDark ? 'rgba(120, 120, 128, 0.12)' : 'rgba(118, 118, 128, 0.09)')
  const surfaceSolid = resolveThemeColor('--app-surface-solid', isDark ? '#1c1c1e' : '#ffffff')
  const primary = resolveThemeColor('--app-primary', isDark ? '#0a84ff' : '#007aff')
  const danger = resolveThemeColor('--app-danger', isDark ? '#ff453a' : '#ff3b30')
  const border = resolveThemeColor('--app-border', isDark ? 'rgba(84, 84, 88, 0.48)' : 'rgba(60, 60, 67, 0.13)')
  const foregroundMuted = resolveThemeColor('--app-foreground-muted', isDark ? 'rgba(235, 235, 245, 0.68)' : 'rgba(60, 60, 67, 0.72)')

  ctx.fillStyle = item.status === 'failed'
    ? mixThemeColor(danger, surfaceMuted, 16)
    : isGenerationTaskPendingStatus(item.status)
      ? surfaceMuted
      : item.type === 'image_generator' || item.type === 'video_generator'
        ? mixThemeColor(primary, surfaceMuted, 12)
        : surfaceSolid
  ctx.fill()

  ctx.strokeStyle = border
  ctx.lineWidth = Math.max(1, Math.min(width, height) * 0.01)
  ctx.stroke()

  ctx.fillStyle = primary
  ctx.fillRect(left + width * 0.1, top + height * 0.18, width * 0.22, Math.max(8, height * 0.16))

  if (isGenerationTaskPendingStatus(item.status)) {
    ctx.fillStyle = foregroundMuted
    ctx.fillRect(left + width * 0.1, top + height * 0.76, width * 0.8, Math.max(4, height * 0.05))
    ctx.fillStyle = primary
    ctx.fillRect(left + width * 0.1, top + height * 0.76, width * 0.8 * ((item.progress ?? 0) / 100), Math.max(4, height * 0.05))
  }

  ctx.restore()
}

function drawBrushPath(ctx: CanvasRenderingContext2D, item: CanvasItem, left: number, top: number, width: number, height: number) {
  const points = item.points || []
  if (points.length === 0) return

  const strokeWidth = Math.max((item.brushSize || 1) * (width / Math.max(item.width || width, 1)), 1)
  ctx.save()
  ctx.strokeStyle = item.brushColor || '#111111'
  ctx.lineWidth = strokeWidth
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.beginPath()

  points.forEach((point, index) => {
    const scaled = scaleBrushPathPoint(point, { width, height })
    const px = left + scaled.x
    const py = top + scaled.y
    if (index === 0) ctx.moveTo(px, py)
    else ctx.lineTo(px, py)
  })

  ctx.stroke()

  if (points.length === 1) {
    const single = scaleBrushPathPoint(points[0], { width, height })
    ctx.beginPath()
    ctx.fillStyle = item.brushColor || '#111111'
    ctx.arc(left + single.x, top + single.y, Math.max(strokeWidth / 2, 1), 0, Math.PI * 2)
    ctx.fill()
  }

  ctx.restore()
}

function getSceneRect(item: CanvasItem, args: {
  zoom: number
  offset: { x: number; y: number }
  viewportWidth: number
  viewportHeight: number
  getItemDims: (item: CanvasItem) => { width: number; height: number }
}) {
  const scale = args.zoom / 100
  const dims = args.getItemDims(item)
  const width = (item.width || dims.width) * scale
  const height = (item.height || dims.height) * scale
  return {
    left: args.viewportWidth / 2 + args.offset.x + item.x * scale,
    top: args.viewportHeight / 2 + args.offset.y + item.y * scale,
    width,
    height,
  }
}

export const CanvasSceneLayer = React.memo(function CanvasSceneLayer(props: any) {
  const {
    canvasRef,
    canvasItems,
    selectedItems,
    marks,
    cropState,
    textRedrawExtractingItemIds,
    zoom,
    offset,
    canvasCamera,
    isDark,
    getItemDims,
    onReadyChange,
  } = props

  const sceneCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const imageCacheRef = useRef(new Map<string, { status: 'loading' | 'loaded' | 'error'; image?: HTMLImageElement }>())
  const [renderVersion, forceRefresh] = useReducer((value) => value + 1, 0)
  const [viewport, setViewport] = useState({ width: 0, height: 0 })

  useEffect(() => {
    if (!canvasCamera?.subscribe) return undefined

    return canvasCamera.subscribe((camera: any, options: any) => {
      if (options?.committed) {
        return
      }
      const canvas = sceneCanvasRef.current
      if (!canvas) return

      const committedCamera = canvasCamera.getCommittedCamera()
      const committedScale = committedCamera.zoom / 100
      const nextScale = camera.zoom / 100
      const scaleRatio = committedScale > 0 ? nextScale / committedScale : 1
      const deltaX = camera.offset.x - (committedCamera.offset.x * scaleRatio)
      const deltaY = camera.offset.y - (committedCamera.offset.y * scaleRatio)
      canvas.style.transform = `translate(${deltaX}px, ${deltaY}px) scale(${scaleRatio})`
      canvas.style.transformOrigin = '0 0'
      canvas.style.willChange = 'transform'
    })
  }, [canvasCamera])

  useLayoutEffect(() => {
    const element = canvasRef?.current || sceneCanvasRef.current?.parentElement
    if (!element) return

    const measure = () => {
      const rect = typeof element.getBoundingClientRect === 'function'
        ? element.getBoundingClientRect()
        : { width: 0, height: 0 }
      const nextWidth = Math.round(element.clientWidth || rect.width || 0)
      const nextHeight = Math.round(element.clientHeight || rect.height || 0)
      setViewport((current) => (
        current.width === nextWidth && current.height === nextHeight
          ? current
          : { width: nextWidth, height: nextHeight }
      ))
    }

    measure()
    const frameId = window.requestAnimationFrame(measure)

    if (typeof ResizeObserver !== 'undefined') {
      const observer = new ResizeObserver(() => measure())
      observer.observe(element)
      return () => {
        window.cancelAnimationFrame(frameId)
        observer.disconnect()
      }
    }

    window.addEventListener('resize', measure)
    return () => {
      window.cancelAnimationFrame(frameId)
      window.removeEventListener('resize', measure)
    }
  }, [canvasRef])

  const viewportWidth = viewport.width
  const viewportHeight = viewport.height

  const visibleSceneItems = useMemo(() => {
    if (!viewportWidth || !viewportHeight) return []
    return getVisibleCanvasSceneItems({
      canvasItems,
      selectedItems,
      marks,
      cropState,
      textRedrawExtractingItemIds,
      zoom,
      offset,
      viewport: { width: viewportWidth, height: viewportHeight },
      getItemDims,
    })
  }, [
    canvasItems,
    selectedItems,
    marks,
    cropState,
    textRedrawExtractingItemIds,
    zoom,
    offset,
    viewportWidth,
    viewportHeight,
    getItemDims,
  ])

  const useSceneRenderer = shouldUseCanvasSceneRenderer({
    zoom,
    visibleItemCount: visibleSceneItems.length,
  })

  useEffect(() => {
    if (!useSceneRenderer) {
      if (sceneCanvasRef.current) {
        sceneCanvasRef.current.style.transform = ''
        sceneCanvasRef.current.style.willChange = ''
      }
      onReadyChange?.(false)
    }
  }, [useSceneRenderer, onReadyChange])

  useEffect(() => {
    if (!useSceneRenderer) return

    visibleSceneItems.forEach((item) => {
      if (!item.url || item.type === 'video_generator') return
      if (imageCacheRef.current.has(item.url)) return

      const image = new Image()
      image.decoding = 'async'
      imageCacheRef.current.set(item.url, { status: 'loading' })
      image.onload = () => {
        imageCacheRef.current.set(item.url!, { status: 'loaded', image })
        forceRefresh()
      }
      image.onerror = () => {
        imageCacheRef.current.set(item.url!, { status: 'error' })
        forceRefresh()
      }
      image.src = item.url
    })
  }, [visibleSceneItems, useSceneRenderer])

  useEffect(() => {
    const canvas = sceneCanvasRef.current
    if (!canvas || !useSceneRenderer || !viewportWidth || !viewportHeight) return

    const dpr = window.devicePixelRatio || 1
    const nextWidth = Math.max(1, Math.round(viewportWidth * dpr))
    const nextHeight = Math.max(1, Math.round(viewportHeight * dpr))
    if (canvas.width !== nextWidth) canvas.width = nextWidth
    if (canvas.height !== nextHeight) canvas.height = nextHeight

    const context = canvas.getContext('2d')
    if (!context) return

    if (typeof context.setTransform === 'function') {
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    } else if (typeof context.scale === 'function') {
      context.scale(dpr, dpr)
    }

    context.clearRect(0, 0, viewportWidth, viewportHeight)

    visibleSceneItems.forEach((item) => {
      const rect = getSceneRect(item, { zoom, offset, viewportWidth, viewportHeight, getItemDims })
      if (rect.width <= 0 || rect.height <= 0) return

      if (item.type === 'brush_path') {
        drawBrushPath(context, item, rect.left, rect.top, rect.width, rect.height)
        return
      }

      const cachedImage = item.url ? imageCacheRef.current.get(item.url) : null
      if (cachedImage?.status === 'loaded' && cachedImage.image) {
        context.drawImage(cachedImage.image, rect.left, rect.top, rect.width, rect.height)
        return
      }

      drawSceneCard(context, {
        item,
        left: rect.left,
        top: rect.top,
        width: rect.width,
        height: rect.height,
        isDark,
      })
    })

    canvas.style.transform = ''
    canvas.style.willChange = ''
    onReadyChange?.(true)
  }, [
    visibleSceneItems,
    useSceneRenderer,
    viewportWidth,
    viewportHeight,
    renderVersion,
    zoom,
    offset,
    isDark,
    getItemDims,
    onReadyChange,
  ])

  return (
    <canvas
      ref={sceneCanvasRef}
      data-testid="canvas-scene-layer"
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        display: useSceneRenderer ? 'block' : 'none',
        pointerEvents: 'none',
        zIndex: 0,
      }}
    />
  )
})
