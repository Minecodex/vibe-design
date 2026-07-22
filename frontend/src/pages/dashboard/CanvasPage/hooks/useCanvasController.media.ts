/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment, react-hooks/exhaustive-deps */
// @ts-nocheck
import { useCallback, useEffect, useRef } from 'react'
import { toast } from 'sonner'

import { apiClient } from '@/api/client'
import { extractApiErrorMessage, toastApiError } from '@/api/errorHandling'
import { assetsApi } from '@/api/endpoints/assets'
import { generationApi } from '@/api/endpoints/generation'
import { ensureBalanceOrNotify } from '@/utils/balanceGuard'
import { validateUploadFileSize } from '@/utils/uploadLimits'

import { buildCutoutResultItem, getOpaqueBoundsFromAlphaChannel } from '../cutout'
import { createImageEraseTaskItem } from '../imageErase'
import {
  createEditableTextRedrawSegments,
  createTextRedrawTaskItem,
  getTextRedrawPanelPosition,
} from '../textRedraw'
import { createHDUpscaleTaskItem } from '../hdUpscale'
import { recordDeletedAgentMediaKey } from '../agentGeneratedMedia'
import { planUploadedCanvasImages, uploadCanvasImageFiles } from '../canvasImageBatchImport'
import {
  closeImageDetails,
  formatImageDetails,
  getNextCanvasStackZIndex,
  getImageDetailAsset,
  getImageDetailPanelPosition,
  openImageDetails,
  removeCanvasImage,
} from '../imageActions'
import { clampCanvasZoom } from '../canvasZoom'
import { findEmptyPosition } from '../canvasLayout'
import { readClipboardImageFileFromNavigator } from '../clipboardImage'
import { getDefaultMediaSize } from '../mediaDimensions'

export function useCanvasControllerMedia(args: any) {
  const {
    t,
    user,
    id,
    isGuest,
    canvasRef,
    canvasItems,
    selectedItems,
    setSelectedItems,
    saveCanvasItems,
    updateCanvasItems,
    updateItem,
    getItemDims,
    loadIntrinsicImageSize,
    imageDetailItemId,
    setImageDetailItemId,
    setImageDetailPanelPosition,
    imageDetailSizeBytes,
    setImageDetailSizeBytes,
    projectAssets,
    setProjectAssets,
    deletedAgentMediaKeys,
    setDeletedAgentMediaKeys,
    textRedrawState,
    setTextRedrawState,
    textRedrawExtractingItemIds,
    setTextRedrawExtractingItemIds,
    setTextRedrawPanelPosition,
    imageEraseSession,
    setImageEraseSession,
    setImageErasePreviewRect,
    imageEraseCanvasRef,
    imageEraseBrushCanvasRef,
    imageEraseSessionRef,
    imageErasePointerRef,
    imageEraseCheckerboardPatternRef,
    handleJumpToItem,
    setActiveTool,
    selectAndCenterCanvasItem,
    loadProjectAssets,
    zoomRef,
    offsetRef,
    setCamera,
    setClipboardSource,
    latestCanvasItemsRef,
  } = args

  useEffect(() => {
    imageEraseSessionRef.current = imageEraseSession
  }, [imageEraseSession, imageEraseSessionRef])

  const textRedrawCacheRef = useRef<Record<string, any>>({})

  const ensurePaidActionAllowed = useCallback(() => ensureBalanceOrNotify(user?.balance_cents, t), [t, user?.balance_cents])

  const getImageEraseCheckerboardPattern = useCallback((context: CanvasRenderingContext2D) => {
    if (imageEraseCheckerboardPatternRef.current) {
      return imageEraseCheckerboardPatternRef.current
    }

    const patternCanvas = document.createElement('canvas')
    patternCanvas.width = 16
    patternCanvas.height = 16
    const patternContext = patternCanvas.getContext('2d')
    if (!patternContext) return '#000'

    // 使用不透明颜色：重叠绘制时只会覆盖（不会叠加变深）
    // 透明度由 canvas 容器的 opacity: 0.75 统一控制
    patternContext.fillStyle = '#ffffff'
    patternContext.fillRect(0, 0, 16, 16)
    patternContext.fillStyle = '#aaaaaa'
    patternContext.fillRect(0, 0, 8, 8)
    patternContext.fillRect(8, 8, 8, 8)

    imageEraseCheckerboardPatternRef.current = context.createPattern(patternCanvas, 'repeat')
    return imageEraseCheckerboardPatternRef.current
  }, [imageEraseCheckerboardPatternRef])

  // 确保离屏画笔 canvas 已创建并与显示 canvas 同尺寸
  const ensureBrushCanvas = useCallback(() => {
    const displayCanvas = imageEraseCanvasRef.current
    if (!displayCanvas) return null
    let brushCanvas = imageEraseBrushCanvasRef.current
    if (!brushCanvas || brushCanvas.width !== displayCanvas.width || brushCanvas.height !== displayCanvas.height) {
      brushCanvas = document.createElement('canvas')
      brushCanvas.width = displayCanvas.width
      brushCanvas.height = displayCanvas.height
      imageEraseBrushCanvasRef.current = brushCanvas
    }
    return brushCanvas
  }, [imageEraseCanvasRef, imageEraseBrushCanvasRef])

  // 重新合成显示 canvas = 画笔/框选层
  const recompositeEraseCanvas = useCallback(() => {
    const displayCanvas = imageEraseCanvasRef.current
    const brushCanvas = imageEraseBrushCanvasRef.current
    const session = imageEraseSessionRef.current
    if (!displayCanvas || !session) return
    const ctx = displayCanvas.getContext('2d')
    if (!ctx) return

    // 1. 清除显示 canvas
    ctx.clearRect(0, 0, displayCanvas.width, displayCanvas.height)

    // 2. 绘制画笔/框选层
    if (brushCanvas) {
      ctx.drawImage(brushCanvas, 0, 0)
    }

  }, [imageEraseCanvasRef, imageEraseBrushCanvasRef, imageEraseSessionRef])

  const clearImageEraseCanvas = useCallback(() => {
    const canvas = imageEraseCanvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    context.clearRect(0, 0, canvas.width, canvas.height)
    // 同时清除离屏画笔 canvas
    const brushCanvas = imageEraseBrushCanvasRef.current
    if (brushCanvas) {
      const bCtx = brushCanvas.getContext('2d')
      if (bCtx) bCtx.clearRect(0, 0, brushCanvas.width, brushCanvas.height)
    }
  }, [imageEraseCanvasRef, imageEraseBrushCanvasRef])

  const restoreImageEraseMask = useCallback((maskDataUrl: string | null) => {
    clearImageEraseCanvas()
    if (!maskDataUrl) return
    const brushCanvas = ensureBrushCanvas()
    if (!brushCanvas) return
    const bCtx = brushCanvas.getContext('2d')
    if (!bCtx) return

    const image = new Image()
    image.onload = () => {
      // 恢复到离屏画笔 canvas，然后重新合成显示
      bCtx.clearRect(0, 0, brushCanvas.width, brushCanvas.height)
      bCtx.drawImage(image, 0, 0, brushCanvas.width, brushCanvas.height)
      recompositeEraseCanvas()
    }
    image.src = maskDataUrl
  }, [clearImageEraseCanvas, ensureBrushCanvas, recompositeEraseCanvas])

  const getImageEraseMaskDataUrl = useCallback(() => {
    // 从离屏画笔 canvas 获取（不含 segment 填充）
    const brushCanvas = imageEraseBrushCanvasRef.current
    if (!brushCanvas) return null
    const context = brushCanvas.getContext('2d')
    if (!context) return null
    const imageData = context.getImageData(0, 0, brushCanvas.width, brushCanvas.height)
    const hasOpaquePixel = imageData.data.some((value, index) => index % 4 === 3 && value > 0)
    return hasOpaquePixel ? brushCanvas.toDataURL('image/png') : null
  }, [imageEraseBrushCanvasRef])

  const pushImageEraseSnapshot = useCallback(() => {
    const current = imageEraseSessionRef.current
    if (!current) return
    const snapshot = {
      maskDataUrl: getImageEraseMaskDataUrl(),
    }

    setImageEraseSession((session: any) => session ? {
      ...session,
      history: [...session.history, snapshot],
      future: [],
      hasMask: Boolean(snapshot.maskDataUrl),
    } : session)
  }, [getImageEraseMaskDataUrl, imageEraseSessionRef, setImageEraseSession])

  const applyImageEraseSnapshot = useCallback((snapshot: any) => {
    setImageEraseSession((session: any) => session ? {
      ...session,
      hasMask: Boolean(snapshot.maskDataUrl),
    } : session)
    restoreImageEraseMask(snapshot.maskDataUrl)
  }, [restoreImageEraseMask, setImageEraseSession])

  const handleCancelImageErase = useCallback(() => {
    imageErasePointerRef.current = null
    clearImageEraseCanvas()
    setImageErasePreviewRect(null)
    setImageEraseSession(null)
  }, [clearImageEraseCanvas, imageErasePointerRef, setImageErasePreviewRect, setImageEraseSession])

  const handleChangeImageEraseMode = useCallback((mode: any) => {
    setImageErasePreviewRect(null)
    setImageEraseSession((current: any) => current ? { ...current, mode } : current)
  }, [setImageErasePreviewRect, setImageEraseSession])

  const handleChangeImageEraseBrushSize = useCallback((brushSize: number) => {
    setImageEraseSession((current: any) => current ? { ...current, brushSize } : current)
  }, [setImageEraseSession])

  const handleUndoImageErase = useCallback(() => {
    const current = imageEraseSessionRef.current
    if (!current || current.history.length <= 1) return
    const history = current.history.slice(0, -1)
    const previousSnapshot = history[history.length - 1]
    const currentSnapshot = current.history[current.history.length - 1]

    setImageEraseSession((session: any) => session ? {
      ...session,
      history,
      future: [currentSnapshot, ...session.future],
    } : session)
    applyImageEraseSnapshot(previousSnapshot)
  }, [applyImageEraseSnapshot, imageEraseSessionRef, setImageEraseSession])

  const handleRedoImageErase = useCallback(() => {
    const current = imageEraseSessionRef.current
    if (!current || current.future.length === 0) return
    const [nextSnapshot, ...restFuture] = current.future

    setImageEraseSession((session: any) => session ? {
      ...session,
      history: [...session.history, nextSnapshot],
      future: restFuture,
      hasMask: Boolean(nextSnapshot.maskDataUrl),
    } : session)
    applyImageEraseSnapshot(nextSnapshot)
  }, [applyImageEraseSnapshot, imageEraseSessionRef, setImageEraseSession])

  const getImageErasePointerPosition = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const session = imageEraseSessionRef.current
    const canvas = imageEraseCanvasRef.current
    if (!session || !canvas) return null
    const rect = canvas.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return null
    const x = Math.max(0, Math.min(session.displayWidth, ((event.clientX - rect.left) / rect.width) * session.displayWidth))
    const y = Math.max(0, Math.min(session.displayHeight, ((event.clientY - rect.top) / rect.height) * session.displayHeight))
    return { x, y }
  }, [imageEraseCanvasRef, imageEraseSessionRef])

  const drawImageEraseStroke = useCallback((fromX: number, fromY: number, toX: number, toY: number) => {
    const session = imageEraseSessionRef.current
    const displayCanvas = imageEraseCanvasRef.current
    if (!session || !displayCanvas) return
    const brushCanvas = ensureBrushCanvas()

    // 同时在离屏画笔 canvas 和显示 canvas 上绘制
    for (const canvas of [brushCanvas, displayCanvas]) {
      if (!canvas) continue
      const context = canvas.getContext('2d')
      if (!context) continue
      context.save()
      context.strokeStyle = getImageEraseCheckerboardPattern(context)
      context.lineCap = 'round'
      context.lineJoin = 'round'
      context.lineWidth = session.brushSize
      context.beginPath()
      context.moveTo(fromX, fromY)
      context.lineTo(toX, toY)
      context.stroke()
      context.restore()
    }
  }, [ensureBrushCanvas, getImageEraseCheckerboardPattern, imageEraseCanvasRef, imageEraseSessionRef])

  const fillImageEraseRect = useCallback((x: number, y: number, width: number, height: number) => {
    const displayCanvas = imageEraseCanvasRef.current
    if (!displayCanvas) return
    const brushCanvas = ensureBrushCanvas()

    // 同时在离屏画笔 canvas 和显示 canvas 上绘制
    for (const canvas of [brushCanvas, displayCanvas]) {
      if (!canvas) continue
      const context = canvas.getContext('2d')
      if (!context) continue
      context.save()
      context.fillStyle = getImageEraseCheckerboardPattern(context)
      context.fillRect(x, y, width, height)
      context.restore()
    }
  }, [ensureBrushCanvas, getImageEraseCheckerboardPattern, imageEraseCanvasRef])

  const handleImageErasePointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const session = imageEraseSessionRef.current
    if (!session) return
    const point = getImageErasePointerPosition(event)
    if (!point) return

    if (session.mode === 'brush') {
      drawImageEraseStroke(point.x, point.y, point.x, point.y)
    } else {
      setImageErasePreviewRect({ x: point.x, y: point.y, width: 0, height: 0 })
    }

    imageErasePointerRef.current = {
      mode: session.mode,
      isDrawing: true,
      lastX: point.x,
      lastY: point.y,
      startX: point.x,
      startY: point.y,
    }
  }, [drawImageEraseStroke, getImageErasePointerPosition, imageErasePointerRef, imageEraseSessionRef, setImageErasePreviewRect])

  const handleImageErasePointerMove = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    const pointer = imageErasePointerRef.current
    if (!pointer?.isDrawing) return
    const point = getImageErasePointerPosition(event)
    if (!point) return

    if (pointer.mode === 'brush') {
      drawImageEraseStroke(pointer.lastX, pointer.lastY, point.x, point.y)
      imageErasePointerRef.current = { ...pointer, lastX: point.x, lastY: point.y }
      return
    }

    setImageErasePreviewRect({
      x: Math.min(pointer.startX, point.x),
      y: Math.min(pointer.startY, point.y),
      width: Math.abs(point.x - pointer.startX),
      height: Math.abs(point.y - pointer.startY),
    })
  }, [drawImageEraseStroke, getImageErasePointerPosition, imageErasePointerRef, setImageErasePreviewRect])

  const handleImageErasePointerUp = useCallback((event?: React.PointerEvent<HTMLDivElement>) => {
    const pointer = imageErasePointerRef.current
    if (!pointer?.isDrawing) return
    if (pointer.mode === 'rect') {
      const point = event ? getImageErasePointerPosition(event) : { x: pointer.lastX, y: pointer.lastY }
      if (point) {
        const x = Math.min(pointer.startX, point.x)
        const y = Math.min(pointer.startY, point.y)
        const width = Math.abs(point.x - pointer.startX)
        const height = Math.abs(point.y - pointer.startY)
        if (width > 0 && height > 0) {
          fillImageEraseRect(x, y, width, height)
        }
      }
    }

    imageErasePointerRef.current = null
    setImageErasePreviewRect(null)
    pushImageEraseSnapshot()
  }, [fillImageEraseRect, getImageErasePointerPosition, imageErasePointerRef, pushImageEraseSnapshot, setImageErasePreviewRect])

  const resolveCanvasMediaUrl = useCallback((url: string) => {
    if (!url) return url
    if (url.startsWith('http:') || url.startsWith('https:') || url.startsWith('data:')) return url
    return `${import.meta.env.VITE_API_URL || ''}${url.startsWith('/') ? '' : '/'}${url}`
  }, [])

  const loadImageElement = useCallback((url: string) => {
    return new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('failed_to_load_image'))
      img.src = resolveCanvasMediaUrl(url)
    })
  }, [resolveCanvasMediaUrl])

  const loadVideoElement = useCallback((url: string) => {
    return new Promise<HTMLVideoElement>((resolve, reject) => {
      const video = document.createElement('video')
      video.preload = 'metadata'
      video.onloadedmetadata = () => resolve(video)
      video.onerror = () => reject(new Error('failed_to_load_video'))
      video.src = resolveCanvasMediaUrl(url)
    })
  }, [resolveCanvasMediaUrl])

  const exportImageEraseCompositeFile = useCallback(async (
    session: any,
    originalImageUrl: string,
    maskDataUrlOverride?: string | null,
  ) => {
    const exportCanvas = document.createElement('canvas')
    exportCanvas.width = session.sourceWidth
    exportCanvas.height = session.sourceHeight
    const context = exportCanvas.getContext('2d')
    if (!context) throw new Error('missing_composite_canvas')

    const originalImage = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('failed_to_load_original'))
      let resolvedUrl = originalImageUrl
      if (resolvedUrl && !resolvedUrl.startsWith('http:') && !resolvedUrl.startsWith('https:') && !resolvedUrl.startsWith('data:')) {
        resolvedUrl = `${import.meta.env.VITE_API_URL || ''}${resolvedUrl.startsWith('/') ? '' : '/'}${resolvedUrl}`
      }
      img.src = resolvedUrl
    })
    context.drawImage(originalImage, 0, 0, exportCanvas.width, exportCanvas.height)

    const maskDataUrl = maskDataUrlOverride ?? getImageEraseMaskDataUrl()
    if (maskDataUrl) {
      const maskImage = await new Promise<HTMLImageElement>((resolve, reject) => {
        const image = new Image()
        image.onload = () => resolve(image)
        image.onerror = () => reject(new Error('failed_to_load_mask'))
        image.src = maskDataUrl
      })
      context.drawImage(maskImage, 0, 0, exportCanvas.width, exportCanvas.height)
    }

    const blob = await new Promise<Blob>((resolve, reject) => {
      exportCanvas.toBlob((result) => {
        if (result) resolve(result)
        else reject(new Error('failed_to_export_composite'))
      }, 'image/png')
    })

    return new File([blob], `erase-composite-${session.itemId}.png`, { type: 'image/png' })
  }, [getImageEraseMaskDataUrl])

  const exportCutoutFile = useCallback(async (session: any, originalImageUrl: string) => {
    const exportCanvas = document.createElement('canvas')
    exportCanvas.width = session.sourceWidth
    exportCanvas.height = session.sourceHeight
    const context = exportCanvas.getContext('2d')
    if (!context) throw new Error('missing_cutout_canvas')

    const originalImage = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => resolve(img)
      img.onerror = () => reject(new Error('failed_to_load_original'))
      let resolvedUrl = originalImageUrl
      if (resolvedUrl && !resolvedUrl.startsWith('http:') && !resolvedUrl.startsWith('https:') && !resolvedUrl.startsWith('data:')) {
        resolvedUrl = `${import.meta.env.VITE_API_URL || ''}${resolvedUrl.startsWith('/') ? '' : '/'}${resolvedUrl}`
      }
      img.src = resolvedUrl
    })

    context.clearRect(0, 0, exportCanvas.width, exportCanvas.height)
    context.drawImage(originalImage, 0, 0, exportCanvas.width, exportCanvas.height)

    const maskCanvas = document.createElement('canvas')
    maskCanvas.width = session.sourceWidth
    maskCanvas.height = session.sourceHeight
    const maskContext = maskCanvas.getContext('2d')
    if (!maskContext) throw new Error('missing_cutout_mask_canvas')

    const maskDataUrl = getImageEraseMaskDataUrl()
    if (maskDataUrl) {
      const maskImage = await new Promise<HTMLImageElement>((resolve, reject) => {
        const image = new Image()
        image.onload = () => resolve(image)
        image.onerror = () => reject(new Error('failed_to_load_mask'))
        image.src = maskDataUrl
      })
      maskContext.drawImage(maskImage, 0, 0, maskCanvas.width, maskCanvas.height)
    }

    context.save()
    context.globalCompositeOperation = 'destination-in'
    context.drawImage(maskCanvas, 0, 0, exportCanvas.width, exportCanvas.height)
    context.restore()

    const imageData = context.getImageData(0, 0, exportCanvas.width, exportCanvas.height)
    const opaqueBounds = getOpaqueBoundsFromAlphaChannel(imageData.data, exportCanvas.width, exportCanvas.height)

    const finalCanvas = document.createElement('canvas')

    if (opaqueBounds) {
      finalCanvas.width = opaqueBounds.width
      finalCanvas.height = opaqueBounds.height
      const finalContext = finalCanvas.getContext('2d')
      if (!finalContext) throw new Error('missing_cropped_cutout_canvas')
      finalContext.clearRect(0, 0, finalCanvas.width, finalCanvas.height)
      finalContext.drawImage(
        exportCanvas,
        opaqueBounds.left,
        opaqueBounds.top,
        opaqueBounds.width,
        opaqueBounds.height,
        0,
        0,
        opaqueBounds.width,
        opaqueBounds.height,
      )
    } else {
      finalCanvas.width = exportCanvas.width
      finalCanvas.height = exportCanvas.height
      const finalContext = finalCanvas.getContext('2d')
      if (!finalContext) throw new Error('missing_cropped_cutout_canvas')
      finalContext.clearRect(0, 0, finalCanvas.width, finalCanvas.height)
      finalContext.drawImage(exportCanvas, 0, 0)
    }

    const blob = await new Promise<Blob>((resolve, reject) => {
      finalCanvas.toBlob((result) => {
        if (result) resolve(result)
        else reject(new Error('failed_to_export_cutout'))
      }, 'image/png')
    })

    return {
      file: new File([blob], `cutout-${session.itemId}.png`, { type: 'image/png' }),
      width: finalCanvas.width,
      height: finalCanvas.height,
    }
  }, [getImageEraseMaskDataUrl])

  const uploadCanvasImageFile = useCallback(async (file: File) => {
    if (!id) throw new Error('missing_project_id')
    if (!validateUploadFileSize(file, 'canvas_image_max_bytes', t)) {
      throw new Error('canvas_image_upload_too_large')
    }
    const formData = new FormData()
    formData.append('file', file)
    const res = await apiClient.post(`/projects/${id}/upload/image`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return res.data.url as string
  }, [id, t])

  const handleSubmitImageErase = useCallback(async () => {
    const session = imageEraseSessionRef.current
    if (!session || !id) return
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === session.itemId)
    if (!item || !item.url) return
    let placeholderId: string | null = null

    if (session.tool === 'erase' && !ensurePaidActionAllowed()) return

    setImageEraseSession((current: any) => current ? { ...current, isSubmitting: true } : current)

    try {
      const submittedMaskDataUrl = session.tool === 'erase' ? getImageEraseMaskDataUrl() : null

      if (session.tool === 'cutout') {
        const cutoutResult = await exportCutoutFile(session, item.url)
        const uploadedCutoutUrl = await uploadCanvasImageFile(cutoutResult.file)
        const resultItem = buildCutoutResultItem({
          sourceItem: item,
          canvasItems,
          resultUrl: uploadedCutoutUrl,
          resultWidth: cutoutResult.width,
          resultHeight: cutoutResult.height,
        })
        const nextItems = [...canvasItems, resultItem]
        updateCanvasItems(nextItems)
        saveCanvasItems(nextItems)
        selectAndCenterCanvasItem(resultItem)
        toast.success(t('canvas.tools.upload_success'))
        handleCancelImageErase()
        return
      }

      placeholderId = `image-erase-${Date.now()}-${Math.random().toString().slice(2, 6)}`
      const placeholder = createImageEraseTaskItem({
        sourceItem: item,
        canvasItems,
        taskId: placeholderId,
      })
      const nextItems = [...canvasItems, placeholder]
      updateCanvasItems(nextItems, { skipHistory: true })
      saveCanvasItems(nextItems)
      selectAndCenterCanvasItem(placeholder)
      handleCancelImageErase()

      const compositeFile = await exportImageEraseCompositeFile(session, item.url, submittedMaskDataUrl)
      const uploadedCompositeUrl = await uploadCanvasImageFile(compositeFile)
      const response = await generationApi.generateImageErase(Number(id), {
        source_image_url: uploadedCompositeUrl,
        source_width: session.sourceWidth,
        source_height: session.sourceHeight,
      })
      updateItem(placeholderId, { task_id: response.data.id })
      toast.success(t('canvas.generator.submit_success'))
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_image'))
      if (session.tool === 'erase' && placeholderId) {
        updateItem(placeholderId, {
          status: 'failed',
          error_message: errorMessage,
        })
      }
      toastApiError(error, t('canvas.generator.failed_image'))
      setImageEraseSession((current: any) => current ? { ...current, isSubmitting: false } : current)
    }
  }, [canvasItems, exportCutoutFile, exportImageEraseCompositeFile, getImageEraseMaskDataUrl, handleCancelImageErase, id, imageEraseSessionRef, saveCanvasItems, selectAndCenterCanvasItem, setImageEraseSession, t, updateCanvasItems, updateItem, uploadCanvasImageFile])

  const updateImageDetailPanelPosition = useCallback((itemId: string) => {
    const canvasRect = canvasRef.current?.getBoundingClientRect()
    const itemRect = document.getElementById(`item-${itemId}`)?.getBoundingClientRect()

    if (!canvasRect || !itemRect) {
      setImageDetailPanelPosition(null)
      return
    }

    const position = getImageDetailPanelPosition({
      item: {
        id: itemId,
        type: 'image',
        url: '',
        x: itemRect.left - canvasRect.left,
        y: itemRect.top - canvasRect.top,
        width: itemRect.width,
        height: itemRect.height,
      },
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: canvasRect.width, height: canvasRect.height },
    })

    setImageDetailPanelPosition(position)
  }, [canvasRef, setImageDetailPanelPosition])

  const updateTextRedrawPanelPosition = useCallback((itemId: string) => {
    const canvasRect = canvasRef.current?.getBoundingClientRect()
    const itemRect = document.getElementById(`item-${itemId}`)?.getBoundingClientRect()

    if (!canvasRect || !itemRect) {
      setTextRedrawPanelPosition(null)
      return
    }

    const position = getTextRedrawPanelPosition({
      item: {
        id: itemId,
        type: 'image',
        url: '',
        x: itemRect.left - canvasRect.left,
        y: itemRect.top - canvasRect.top,
        width: itemRect.width,
        height: itemRect.height,
      },
      zoom: 100,
      offset: { x: 0, y: 0 },
      viewport: { width: canvasRect.width, height: canvasRect.height },
    })

    setTextRedrawPanelPosition(position)
  }, [canvasRef, setTextRedrawPanelPosition])

  const getCanvasItemOverlayRect = useCallback((itemId: string) => {
    const canvasRect = canvasRef.current?.getBoundingClientRect()
    const itemRect = document.getElementById(`item-${itemId}`)?.getBoundingClientRect()

    if (!canvasRect || !itemRect) {
      return null
    }

    return {
      left: itemRect.left - canvasRect.left,
      top: itemRect.top - canvasRect.top,
      width: itemRect.width,
      height: itemRect.height,
    }
  }, [canvasRef])

  const handleOpenImageDetails = useCallback((itemId: string) => {
    const nextState = openImageDetails({ itemId, selectedItems })
    setSelectedItems(nextState.selectedItems)
    setImageDetailItemId(nextState.detailItemId)
    void loadProjectAssets()
  }, [loadProjectAssets, selectedItems, setImageDetailItemId, setSelectedItems])

  const handleCloseImageDetails = useCallback(() => {
    if (!imageDetailItemId) return
    const nextState = closeImageDetails(imageDetailItemId)
    setImageDetailItemId(nextState.detailItemId)
    setImageDetailPanelPosition(null)
    setSelectedItems(nextState.selectedItems)
  }, [imageDetailItemId, setImageDetailItemId, setImageDetailPanelPosition, setSelectedItems])

  const handleDeleteCanvasImage = useCallback(async (itemId: string) => {
    const deletedItem = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    const nextDeletedAgentMediaKeys =
      deletedItem?.asset_origin === 'ai_generated'
        ? recordDeletedAgentMediaKey(deletedAgentMediaKeys, deletedItem.agent_media_key || deletedItem.id)
        : deletedAgentMediaKeys
    const deleteResult = removeCanvasImage({
      canvasItems,
      selectedItems,
      itemId,
      projectAssets,
    })

    setDeletedAgentMediaKeys(nextDeletedAgentMediaKeys)
    updateCanvasItems(deleteResult.canvasItems)
    setSelectedItems(deleteResult.selectedItems)
    setImageDetailItemId((current: any) => current === itemId ? null : current)
    setImageDetailPanelPosition((current: any) => imageDetailItemId === itemId ? null : current)
    await saveCanvasItems(deleteResult.canvasItems, { deletedAgentMediaKeys: nextDeletedAgentMediaKeys })

    if (deleteResult.assetIdsToDelete.length === 0 || !id || isGuest) {
      return
    }

    setProjectAssets((current: any) => {
      const next = { ...current }
      deleteResult.assetIdsToDelete.forEach((assetId: number) => {
        delete next[assetId]
      })
      return next
    })

    try {
      await assetsApi.batch(Number(id), {
        asset_ids: deleteResult.assetIdsToDelete,
        action: 'delete',
      })
    } catch (error) {
      toast.error(t('action_failed', '操作失败'))
      console.error('Failed to delete project asset:', error)
    }
  }, [canvasItems, deletedAgentMediaKeys, id, imageDetailItemId, isGuest, saveCanvasItems, selectedItems, setDeletedAgentMediaKeys, setImageDetailItemId, setImageDetailPanelPosition, setProjectAssets, setSelectedItems, t, updateCanvasItems])

  const handleOpenHDUpscale = useCallback(async (itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || item.type !== 'image' || !item.url) return
    if (!ensurePaidActionAllowed()) return

    const placeholderId = `hd-upscale-task-${Date.now()}`

    try {
      const intrinsicSize = await loadIntrinsicImageSize(item.url, {
        width: Math.max(1, Math.round(item.width || 0)),
        height: Math.max(1, Math.round(item.height || 0)),
      })

      const res = await generationApi.generateHDUpscale(Number(id), {
        source_image_url: item.url,
        source_width: intrinsicSize.width,
        source_height: intrinsicSize.height,
      })

      const placeholder = createHDUpscaleTaskItem({
        sourceItem: item,
        canvasItems,
        taskId: placeholderId,
        width: res.data.calculated_width,
        height: res.data.calculated_height,
      })
      const nextItems = [...canvasItems, placeholder]
      updateCanvasItems(nextItems, { skipHistory: true })
      saveCanvasItems(nextItems)
      selectAndCenterCanvasItem(placeholder)
      updateItem(placeholderId, { task_id: res.data.task.id })
    } catch (error) {
      console.error('Failed to open HD upscale:', error)
      toastApiError(error, t('canvas.generator.failed_image'))
    }
  }, [canvasItems, id, loadIntrinsicImageSize, saveCanvasItems, selectAndCenterCanvasItem, updateCanvasItems, updateItem])

  useEffect(() => {
    if (textRedrawState && textRedrawState.status === 'editing' && textRedrawState.itemId) {
      textRedrawCacheRef.current[textRedrawState.itemId] = textRedrawState.segments
    }
  }, [textRedrawState])

  const handleOpenTextRedraw = useCallback(async (itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || item.type !== 'image' || !item.url || !id) return
    if (!ensurePaidActionAllowed()) return

    if (textRedrawCacheRef.current[itemId]) {
      setTextRedrawPanelPosition(null)
      setTextRedrawState({
        itemId,
        status: 'editing',
        segments: textRedrawCacheRef.current[itemId],
        isSubmitting: false,
      })
      return
    }

    setTextRedrawExtractingItemIds((current: Set<string>) => {
      const next = new Set(current)
      next.add(itemId)
      return next
    })

    try {
      const response = await generationApi.extractTextRedraw(Number(id), { image_url: item.url })
      const segments = createEditableTextRedrawSegments(response.data.segments)
      if (segments.length === 0) {
        setTextRedrawExtractingItemIds((current: Set<string>) => {
          const next = new Set(current)
          next.delete(itemId)
          return next
        })
        toast.error(t('canvas.text_redraw.no_text_found', '未检测到可编辑文字'))
        return
      }
      textRedrawCacheRef.current[itemId] = segments
      setTextRedrawExtractingItemIds((current: Set<string>) => {
        const next = new Set(current)
        next.delete(itemId)
        return next
      })
      setTextRedrawState((current: any) => current ?? {
        itemId,
        status: 'editing',
        segments,
        isSubmitting: false,
      })
    } catch (error: any) {
      console.error('Failed to extract text for redraw:', error)
      setTextRedrawExtractingItemIds((current: Set<string>) => {
        const next = new Set(current)
        next.delete(itemId)
        return next
      })
      toast.error(error.response?.data?.detail || t('canvas.action_failed'))
    }
  }, [canvasItems, ensurePaidActionAllowed, id, setTextRedrawExtractingItemIds, setTextRedrawPanelPosition, setTextRedrawState, t])

  const handleChangeTextRedrawSegment = useCallback((segmentId: string, text: string) => {
    setTextRedrawState((current: any) => {
      if (!current) return null
      return {
        ...current,
        segments: current.segments.map((segment: any) => (
          segment.id === segmentId
            ? { ...segment, text }
            : segment
        )),
      }
    })
  }, [setTextRedrawState])

  const handleCancelTextRedraw = useCallback(() => {
    setTextRedrawState(null)
    setTextRedrawPanelPosition(null)
  }, [setTextRedrawPanelPosition, setTextRedrawState])

  const handleSubmitTextRedraw = useCallback(async () => {
    if (!textRedrawState || textRedrawState.status !== 'editing' || !id) return

    const item = canvasItems.find((canvasItem: any) => canvasItem.id === textRedrawState.itemId)
    if (!item || item.type !== 'image' || !item.url) return
    if (!ensurePaidActionAllowed()) return

    const placeholderId = `text-redraw-${Date.now()}-${Math.random().toString().slice(2, 6)}`
    const placeholder = createTextRedrawTaskItem({
      sourceItem: item,
      canvasItems,
      taskId: placeholderId,
    })
    const nextItems = [...canvasItems, placeholder]

    setTextRedrawState((current: any) => current ? { ...current, isSubmitting: true } : current)
    updateCanvasItems(nextItems, { skipHistory: true })
    saveCanvasItems(nextItems)
    selectAndCenterCanvasItem(placeholder)
    setTextRedrawState(null)
    setTextRedrawPanelPosition(null)

    try {
      const intrinsicSize = await loadIntrinsicImageSize(item.url, {
        width: Math.max(1, Math.round(item.width || 0)),
        height: Math.max(1, Math.round(item.height || 0)),
      })

      const response = await generationApi.generateTextRedraw(Number(id), {
        source_image_url: item.url,
        source_width: intrinsicSize.width,
        source_height: intrinsicSize.height,
        original_segments: textRedrawState.segments.map((segment: any) => ({
          id: segment.id,
          text: segment.originalText,
          order: segment.order,
        })),
        edited_segments: textRedrawState.segments.map((segment: any) => ({
          id: segment.id,
          text: segment.text,
          order: segment.order,
        })),
      })

      updateItem(placeholderId, { task_id: response.data.id })
      toast.success(t('canvas.generator.submit_success'))
    } catch (error: any) {
      const errorMessage = extractApiErrorMessage(error, t('canvas.generator.failed_image'))
      updateItem(placeholderId, {
        status: 'failed',
        error_message: errorMessage,
      })
      toastApiError(error, t('canvas.generator.failed_image'))
    }
  }, [canvasItems, id, loadIntrinsicImageSize, saveCanvasItems, selectAndCenterCanvasItem, setTextRedrawPanelPosition, setTextRedrawState, t, textRedrawState, updateCanvasItems, updateItem])

  useEffect(() => {
    if (!textRedrawState) {
      setTextRedrawPanelPosition(null)
      return
    }

    const activeItem = canvasItems.find((item: any) => item.id === textRedrawState.itemId)
    if (!activeItem) {
      setTextRedrawState(null)
      setTextRedrawPanelPosition(null)
      return
    }

    if (textRedrawState.status === 'editing') {
      updateTextRedrawPanelPosition(textRedrawState.itemId)
    }
  }, [canvasItems, textRedrawState, updateTextRedrawPanelPosition, setTextRedrawPanelPosition, setTextRedrawState])

  useEffect(() => {
    if (!imageDetailItemId) {
      setImageDetailPanelPosition(null)
      return
    }

    const detailItemExists = canvasItems.some((item: any) => item.id === imageDetailItemId)
    if (!detailItemExists) {
      setImageDetailItemId(null)
      setImageDetailPanelPosition(null)
      return
    }

    updateImageDetailPanelPosition(imageDetailItemId)
  }, [canvasItems, imageDetailItemId, setImageDetailItemId, setImageDetailPanelPosition, updateImageDetailPanelPosition])

  useEffect(() => {
    const activeImageDetailItem = imageDetailItemId
      ? canvasItems.find((item: any) => item.id === imageDetailItemId) || null
      : null

    if (!activeImageDetailItem?.url) {
      setImageDetailSizeBytes(null)
      return
    }

    const controller = new AbortController()
    let isMounted = true

    const loadImageDetailSize = async () => {
      try {
        const headResponse = await fetch(activeImageDetailItem.url, { method: 'HEAD', signal: controller.signal })
        const contentLength = headResponse.headers.get('content-length')
        const parsedLength = contentLength ? Number(contentLength) : NaN
        if (isMounted && Number.isFinite(parsedLength) && parsedLength > 0) {
          setImageDetailSizeBytes(parsedLength)
          return
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') return
      }

      try {
        const blobResponse = await fetch(activeImageDetailItem.url, { signal: controller.signal })
        const blob = await blobResponse.blob()
        if (isMounted && blob.size > 0) {
          setImageDetailSizeBytes(blob.size)
          return
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') return
      }

      if (isMounted) setImageDetailSizeBytes(null)
    }

    setImageDetailSizeBytes(null)
    loadImageDetailSize()

    return () => {
      isMounted = false
      controller.abort()
    }
  }, [canvasItems, imageDetailItemId, setImageDetailSizeBytes])

  const openImageEditSession = useCallback(async (itemId: string, tool: any) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || !['image', 'image_generator'].includes(item.type) || !item.url) return

    const intrinsicSize = await loadIntrinsicImageSize(item.url, {
      width: Math.max(1, Math.round(item.width || 1)),
      height: Math.max(1, Math.round(item.height || 1)),
    })

    clearImageEraseCanvas()
    setImageErasePreviewRect(null)
    setImageEraseSession({
      tool,
      itemId,
      imageUrl: item.url,
      displayWidth: Math.max(1, Math.round(item.width || intrinsicSize.width)),
      displayHeight: Math.max(1, Math.round(item.height || intrinsicSize.height)),
      sourceWidth: intrinsicSize.width,
      sourceHeight: intrinsicSize.height,
      mode: 'brush',
      brushSize: 24,
      history: [{ maskDataUrl: null }],
      future: [],
      isSubmitting: false,
      hasMask: false,
    })
    setSelectedItems([itemId])

    const canvasRect = canvasRef.current?.getBoundingClientRect()
    if (canvasRect && item) {
      const dims = getItemDims(item)
      const itemW = item.width || dims.width || 1
      const itemH = item.height || dims.height || 1
      const targetZoom = Math.min((canvasRect.width * 0.5) / itemW, (canvasRect.height * 0.5) / itemH) * 100
      const newZoom = clampCanvasZoom(targetZoom)
      const scale = newZoom / 100
      const centerX = item.x + itemW / 2
      const centerY = item.y + itemH / 2
      const newOffset = { x: -centerX * scale, y: -centerY * scale }
      setCamera({ zoom: newZoom, offset: newOffset }, { commit: true, reason: 'focus-item' })
    } else {
      handleJumpToItem(itemId)
    }
  }, [canvasItems, canvasRef, clearImageEraseCanvas, getItemDims, handleJumpToItem, loadIntrinsicImageSize, setCamera, setImageErasePreviewRect, setImageEraseSession, setSelectedItems])

  const handleOpenImageErase = useCallback(async (itemId: string) => {
    await openImageEditSession(itemId, 'erase')
  }, [openImageEditSession])

  const handleOpenCutout = useCallback(async (itemId: string) => {
    await openImageEditSession(itemId, 'cutout')
  }, [openImageEditSession])

  const importCanvasImageFiles = useCallback(async (files: File[]) => {
    if (files.length === 0) return { successCount: 0, failedCount: 0 }

    const uploadResult = await uploadCanvasImageFiles(files, uploadCanvasImageFile)
    if (uploadResult.successful.length === 0) {
      toast.error(t('canvas.tools.upload_failed'))
      return { successCount: 0, failedCount: uploadResult.failedCount }
    }

    const viewportCenter = {
      x: -offsetRef.current.x / (zoomRef.current / 100),
      y: -offsetRef.current.y / (zoomRef.current / 100),
    }
    const currentItems = latestCanvasItemsRef?.current || canvasItems
    const newImageItems = planUploadedCanvasImages(
      uploadResult.successful,
      currentItems,
      viewportCenter,
    )
    const nextItems = [...currentItems, ...newImageItems]

    if (latestCanvasItemsRef) latestCanvasItemsRef.current = nextItems
    updateCanvasItems(nextItems)
    saveCanvasItems(nextItems)
    setActiveTool('select')
    setSelectedItems(newImageItems.map((item) => item.id))
    handleJumpToItem(newImageItems[0].id, newImageItems[0], true)

    if (uploadResult.failedCount > 0) {
      toast.warning(t('canvas.tools.upload_partial', {
        successCount: newImageItems.length,
        failedCount: uploadResult.failedCount,
      }))
    } else if (newImageItems.length > 1) {
      toast.success(t('canvas.tools.upload_success_count', { count: newImageItems.length }))
    } else {
      toast.success(t('canvas.tools.upload_success'))
    }

    return {
      successCount: newImageItems.length,
      failedCount: uploadResult.failedCount,
    }
  }, [canvasItems, handleJumpToItem, latestCanvasItemsRef, offsetRef, saveCanvasItems, setActiveTool, setSelectedItems, t, updateCanvasItems, uploadCanvasImageFile, zoomRef])

  const importCanvasImageFile = useCallback(async (file: File) => {
    if (!file) return false
    const result = await importCanvasImageFiles([file])
    return result.successCount === 1
  }, [importCanvasImageFiles])

  const handleUploadImage = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (files.length === 0) return
    try {
      await importCanvasImageFiles(files)
    } finally {
      e.target.value = ''
    }
  }, [importCanvasImageFiles])

  const handleCanvasPaste = useCallback(async (file: File) => {
    try {
      // Pasting an external image clears any stale internal copy intent.
      setClipboardSource('external')
      await importCanvasImageFile(file)
    } catch (err) {
      console.error('Failed to paste image into canvas:', err)
    }
  }, [id, importCanvasImageFile, setClipboardSource])

  const handlePasteClipboardImage = useCallback(async () => {
    try {
      const file = await readClipboardImageFileFromNavigator()
      if (!file) {
        return false
      }

      // Reading an image from the system clipboard means this is an external paste.
      setClipboardSource('external')
      return await importCanvasImageFile(file)
    } catch (error) {
      console.warn('Failed to read image from system clipboard:', error)
      return false
    }
  }, [importCanvasImageFile, setClipboardSource])

  const handleUploadVideo = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!validateUploadFileSize(file, 'canvas_video_max_bytes', t)) return
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await apiClient.post(`/projects/${id}/upload/video`, formData, { headers: { 'Content-Type': 'multipart/form-data' } })
      const vcx = -offsetRef.current.x / (zoomRef.current / 100)
      const vcy = -offsetRef.current.y / (zoomRef.current / 100)
      const fallbackSize = getDefaultMediaSize('video')
      const video = document.createElement('video')
      video.src = res.data.url
      await new Promise((resolve) => {
        video.onloadedmetadata = resolve
        video.onerror = resolve
      })

      const videoW = video.videoWidth || fallbackSize.width
      const videoH = video.videoHeight || fallbackSize.height
      const pos = findEmptyPosition(vcx, vcy, videoW, videoH, canvasItems)
      const newVideoItem = { id: Date.now().toString(), type: 'video', url: res.data.url, x: pos.x, y: pos.y, width: videoW, height: videoH, z_index: getNextCanvasStackZIndex(canvasItems), asset_origin: 'local_upload', created_at: new Date().toISOString() }
      const nextItems = [...canvasItems, newVideoItem]
      updateCanvasItems(nextItems)
      saveCanvasItems(nextItems)
      setActiveTool('select')
      setSelectedItems([newVideoItem.id])
      handleJumpToItem(newVideoItem.id, newVideoItem, true)
      toast.success(t('canvas.tools.upload_success'))
    } catch {
      toast.error(t('canvas.tools.upload_failed'))
    }
    e.target.value = ''
  }, [canvasItems, handleJumpToItem, id, offsetRef, saveCanvasItems, setActiveTool, setSelectedItems, t, updateCanvasItems, zoomRef])

  const imageDetailItem = imageDetailItemId
    ? canvasItems.find((item: any) => item.id === imageDetailItemId) || null
    : null
  const imageDetailAsset = imageDetailItem ? getImageDetailAsset(imageDetailItem, projectAssets) : null
  const imageDetailCreatorFallback = {
    creatorName: user?.nickname || user?.username || null,
    creatorAvatar: user?.avatar_url || null,
  }
  const imageDetailData = imageDetailItem
    ? formatImageDetails(imageDetailItem, imageDetailAsset, imageDetailSizeBytes, imageDetailCreatorFallback)
    : null

  return {
    handleCancelImageErase,
    handleChangeImageEraseMode,
    handleChangeImageEraseBrushSize,
    handleUndoImageErase,
    handleRedoImageErase,
    handleImageErasePointerDown,
    handleImageErasePointerMove,
    handleImageErasePointerUp,
    handleSubmitImageErase,
    handleOpenCutout,
    handleOpenImageErase,
    handleOpenHDUpscale,
    handleOpenTextRedraw,
    handleChangeTextRedrawSegment,
    handleCancelTextRedraw,
    handleSubmitTextRedraw,
    textRedrawExtractingItemIds,
    resolveCanvasMediaUrl,
    loadImageElement,
    loadVideoElement,
    uploadCanvasImageFile,
    handleOpenImageDetails,
    handleCloseImageDetails,
    handleDeleteCanvasImage,
    importCanvasImageFile,
    handleUploadImage,
    handlePasteClipboardImage,
    handleCanvasPaste,
    handleUploadVideo,
    getCanvasItemOverlayRect,
    imageDetailItem,
    imageDetailData,
    clearImageEraseCanvas,
  }
}

