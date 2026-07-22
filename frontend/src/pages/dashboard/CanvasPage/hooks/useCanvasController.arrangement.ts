/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment, react-hooks/exhaustive-deps */
// @ts-nocheck
import { useCallback, useEffect } from 'react'
import { toast } from 'sonner'

import { apiClient } from '@/api/client'
import { photoshopEditJobsApi } from '@/api/endpoints/photoshopEditJobs'
import { validateUploadFileSize } from '@/utils/uploadLimits'

import { recordDeletedAgentMediaKey } from '../agentGeneratedMedia'
import { rasterizeBrushPathToCanvas } from '../brushRasterization'
import { buildCanvasExportFilenameMap } from '../canvasExportFilename'
import {
  CANVAS_CLIPBOARD_EVENT_MIME,
  CANVAS_CLIPBOARD_MIME,
  inspectSystemClipboardPasteKind,
  serializeCanvasClipboardPayload,
  serializeCanvasClipboardTextMarker,
} from '../canvasClipboard'
import { getImageExportDimensions, getMediaRestoreRect } from '../imageActions'
import {
  normalizeTextCanvasItem,
  getTextItemVariantStyle,
  formatTextContentForDisplay,
  DEFAULT_TEXT_FILL,
} from '../textTypography'
import { buildPhotoshopEditPayload } from '../photoshopEdit'

const IMAGE_ITEM_TYPES = new Set(['image', 'image_generator'])

export async function copySingleCanvasImageToSystemClipboard(item: any) {
  return writeCanvasClipboardToSystemClipboard([item])
}

export async function writeCanvasClipboardToSystemClipboard(items: any[]) {
  if (!Array.isArray(items) || items.length === 0) {
    return false
  }

  const [singleItem] = items
  const canWriteImagePayload = (
    items.length === 1
    && IMAGE_ITEM_TYPES.has(singleItem?.type)
    && singleItem?.url
  )

  if (
    typeof window === 'undefined'
    || typeof navigator === 'undefined'
    || !navigator.clipboard?.write
    || typeof ClipboardItem === 'undefined'
  ) {
    return false
  }

  const clipboardItemPayload: Record<string, Blob | Promise<Blob>> = {
    [CANVAS_CLIPBOARD_MIME]: new Blob(
      [serializeCanvasClipboardPayload(items)],
      { type: CANVAS_CLIPBOARD_EVENT_MIME },
    ),
    'text/plain': new Blob(
      [serializeCanvasClipboardTextMarker(items)],
      { type: 'text/plain' },
    ),
  }

  if (canWriteImagePayload) {
    clipboardItemPayload['image/png'] = (async () => {
      const response = await fetch(singleItem.url)
      if (!response.ok) {
        throw new Error(`Failed to fetch canvas image: ${response.status}`)
      }

      const blob = await response.blob()
      if (blob.type === 'image/png') {
        return blob
      }

      return new Blob([await blob.arrayBuffer()], { type: 'image/png' })
    })()
  }

  await navigator.clipboard.write([
    new ClipboardItem(clipboardItemPayload),
  ])
  return true
}

function getCanvasRect(item: any) {
  return {
    x: item.x,
    y: item.y,
    width: item.width || 1024,
    height: item.height || 1024,
  }
}

function getRectOverlapArea(a: { x: number, y: number, width: number, height: number }, b: { x: number, y: number, width: number, height: number }) {
  const overlapWidth = Math.max(0, Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x))
  const overlapHeight = Math.max(0, Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y))
  return overlapWidth * overlapHeight
}

export function findNonOverlappingGroupPosition({
  target,
  obstacles,
}: {
  target: { x: number, y: number, width: number, height: number }
  obstacles: Array<{ x: number, y: number, width?: number, height?: number }>
}) {
  const baseRect = {
    x: Math.round(target.x),
    y: Math.round(target.y),
    width: Math.max(1, Math.round(target.width)),
    height: Math.max(1, Math.round(target.height)),
  }

  const normalizedObstacles = obstacles.map((item) => getCanvasRect(item))
  const spacing = 48
  const stepX = Math.max(Math.round(baseRect.width / 2), 120)
  const stepY = Math.max(Math.round(baseRect.height / 2), 120)
  let bestCandidate = { x: baseRect.x, y: baseRect.y }
  let bestScore = Number.POSITIVE_INFINITY

  const scoreCandidate = (candidateX: number, candidateY: number) => {
    const candidateRect = {
      x: candidateX,
      y: candidateY,
      width: baseRect.width,
      height: baseRect.height,
    }

    let overlapArea = 0
    for (const obstacle of normalizedObstacles) {
      const expandedObstacle = {
        x: obstacle.x - spacing,
        y: obstacle.y - spacing,
        width: obstacle.width + spacing * 2,
        height: obstacle.height + spacing * 2,
      }
      overlapArea += getRectOverlapArea(candidateRect, expandedObstacle)
    }

    const distance = Math.abs(candidateX - baseRect.x) + Math.abs(candidateY - baseRect.y)
    const score = overlapArea * 1000000 + distance

    if (score < bestScore) {
      bestScore = score
      bestCandidate = { x: candidateX, y: candidateY }
    }

    return overlapArea === 0
  }

  if (scoreCandidate(baseRect.x, baseRect.y)) {
    return bestCandidate
  }

  for (let ring = 1; ring <= 8; ring++) {
    for (let gridX = -ring; gridX <= ring; gridX++) {
      for (let gridY = -ring; gridY <= ring; gridY++) {
        if (Math.max(Math.abs(gridX), Math.abs(gridY)) !== ring) continue
        const candidateX = baseRect.x + gridX * stepX
        const candidateY = baseRect.y + gridY * stepY
        if (scoreCandidate(candidateX, candidateY)) {
          return bestCandidate
        }
      }
    }
  }

  return bestCandidate
}

export function shiftCanvasItemsOneLayer(items: any[], targetIds: string[], direction: 'forward' | 'backward') {
  if (targetIds.length === 0) return items

  const zIndexMap = new Map(items.map((item) => [item.id, item.z_index || 0]))
  const sorted = [...items].sort((a, b) => {
    const zDiff = (a.z_index || 0) - (b.z_index || 0)
    if (zDiff !== 0) return zDiff
    return items.findIndex((item) => item.id === a.id) - items.findIndex((item) => item.id === b.id)
  })

  const orderedTargets = sorted.filter((item) => targetIds.includes(item.id))
  const traversal = direction === 'forward' ? [...orderedTargets].reverse() : orderedTargets

  traversal.forEach((target) => {
    const targetZ = zIndexMap.get(target.id) || 0
    const candidate = direction === 'forward'
      ? sorted.find((item) => !targetIds.includes(item.id) && (zIndexMap.get(item.id) || 0) > targetZ)
      : [...sorted].reverse().find((item) => !targetIds.includes(item.id) && (zIndexMap.get(item.id) || 0) < targetZ)

    if (!candidate) return

    const candidateZ = zIndexMap.get(candidate.id) || 0
    zIndexMap.set(target.id, candidateZ)
    zIndexMap.set(candidate.id, targetZ)
  })

  return items.map((item) => {
    const nextZIndex = zIndexMap.get(item.id)
    return nextZIndex === undefined ? item : { ...item, z_index: nextZIndex }
  })
}

export function collectCanvasClipboardItems(canvasItems: any[], targetIds: string[]) {
  if (targetIds.length === 0) return []

  const itemIndex = new Map(canvasItems.map((item) => [item.id, item]))
  const includedIds = new Set(targetIds)
  const selectedGroupIds = new Set<string>()

  targetIds.forEach((itemId) => {
    const item = itemIndex.get(itemId)
    if (!item) return

    if (item.type === 'group') {
      selectedGroupIds.add(item.id)
    }
  })

  canvasItems.forEach((item) => {
    if (item.groupId && selectedGroupIds.has(item.groupId)) {
      includedIds.add(item.id)
    }
  })

  return canvasItems.filter((item) => includedIds.has(item.id))
}

export function duplicateCanvasClipboardItems({
  canvasItems,
  clipboardItems,
  pastePoint,
}: {
  canvasItems: any[]
  clipboardItems: any[]
  pastePoint: { x: number, y: number } | null
}) {
  if (clipboardItems.length === 0) {
    return {
      nextItems: canvasItems,
      pastedItems: [],
    }
  }

  let minX = Infinity
  let minY = Infinity
  clipboardItems.forEach((item: any) => {
    minX = Math.min(minX, item.x)
    minY = Math.min(minY, item.y)
  })

  const offsetX = pastePoint ? (pastePoint.x - minX) : 20
  const offsetY = pastePoint ? (pastePoint.y - minY) : 20

  const idMap: Record<string, string> = {}
  const newItems = clipboardItems.map((item: any) => {
    const newId = Date.now().toString() + Math.random().toString().slice(2, 6)
    idMap[item.id] = newId
    return {
      ...item,
      id: newId,
      x: item.x + offsetX,
      y: item.y + offsetY,
      z_index: (item.z_index || 0) + 1,
    }
  })

  const finalizedItems = newItems.map((item: any) => {
    if (item.groupId) {
      if (idMap[item.groupId]) {
        return { ...item, groupId: idMap[item.groupId] }
      }
      return { ...item, groupId: undefined }
    }
    return item
  })

  return {
    nextItems: [...canvasItems, ...finalizedItems],
    pastedItems: finalizedItems,
  }
}

export function useCanvasControllerArrangement(args: any) {
  const {
    t,
    id,
    projectName,
    canvasRef,
    canvasItems,
    selectedItems,
    setSelectedItems,
    clipboardItems,
    setClipboardItems,
    setClipboardSource,
    contextMenu,
    zoom,
    offset,
    mousePosRef,
    saveCanvasItems,
    updateCanvasItems,
    deletedAgentMediaKeys,
    setDeletedAgentMediaKeys,
    getItemDims,
    layerDragId,
    setLayerDragId,
    layerDropTarget,
    setLayerDropTarget,
    setMultiSelectToolsOpen,
    loadImageElement,
    loadVideoElement,
    handlePasteClipboardImage,
    selectAndCenterCanvasItem,
  } = args

  const handleContextMenuAction = useCallback((action: string, specificItemId?: string | null) => {
    const targetIds = specificItemId ? [specificItemId] : selectedItems
    if (targetIds.length === 0 && action !== 'paste') return

    switch (action) {
      case 'copy':
        if (targetIds.length > 0) {
          const items = collectCanvasClipboardItems(canvasItems, targetIds)
          setClipboardItems(items)
          setClipboardSource('internal')

          void writeCanvasClipboardToSystemClipboard(items).catch((error) => {
            console.warn('Failed to write canvas clipboard marker to system clipboard:', error)
          })
        }
        break
      case 'paste': {
        const pasteInternalClipboardItems = () => {
          if (clipboardItems.length === 0) return false
          const rect = canvasRef.current?.getBoundingClientRect()
          let pastePoint = null

          if (rect) {
            const scale = zoom / 100
            const screenX = contextMenu ? contextMenu.x : mousePosRef.current.x
            const screenY = contextMenu ? contextMenu.y : mousePosRef.current.y
            pastePoint = {
              x: (screenX - rect.left - rect.width / 2 - offset.x) / scale,
              y: (screenY - rect.top - rect.height / 2 - offset.y) / scale,
            }
          }

          const { nextItems, pastedItems } = duplicateCanvasClipboardItems({
            canvasItems,
            clipboardItems,
            pastePoint,
          })
          updateCanvasItems(nextItems)
          setSelectedItems(pastedItems.map((item: any) => item.id))
          saveCanvasItems(nextItems)
          return true
        }

        // Decide from the live system clipboard, never from a sticky in-memory
        // flag. This is what keeps an external/OS image pasteable even after the
        // user has previously copied something inside the canvas.
        void (async () => {
          const kind = await inspectSystemClipboardPasteKind()

          // 1) Our own canvas marker is present → duplicate the copied items.
          if (kind?.hasCanvasClipboardMarker) {
            pasteInternalClipboardItems()
            return
          }

          // 2) A real image is on the clipboard, or we could not read the
          //    clipboard at all (kind === null) → try the system image import.
          if ((kind?.hasImage || kind === null) && handlePasteClipboardImage) {
            const pastedFromSystem = await handlePasteClipboardImage()
            if (pastedFromSystem) return
          }

          // 3) Nothing usable on the system clipboard → fall back to the
          //    in-memory canvas copy (covers blocked clipboard writes).
          pasteInternalClipboardItems()
        })()
        break
      }
      case 'restore': {
        const targetId = targetIds[0]
        const item = canvasItems.find((canvasItem: any) => canvasItem.id === targetId)
        if (!item || !item.url || !['image', 'video'].includes(item.type)) break

        ; (async () => {
          try {
            const intrinsicSize = item.type === 'image'
              ? await loadImageElement(item.url).then((media: any) => ({ width: media.naturalWidth, height: media.naturalHeight }))
              : await loadVideoElement(item.url).then((media: any) => ({ width: media.videoWidth, height: media.videoHeight }))
            if (!intrinsicSize.width || !intrinsicSize.height) return

            const nextRect = getMediaRestoreRect(item, intrinsicSize)
            const nextItems = canvasItems.map((canvasItem: any) =>
              canvasItem.id === item.id ? { ...canvasItem, ...nextRect } : canvasItem,
            )

            updateCanvasItems(nextItems)
            saveCanvasItems(nextItems)
          } catch (error) {
            console.error('Failed to restore media size:', error)
            toast.error(t('action_failed', '操作失败'))
          }
        })()
        break
      }
      case 'ps_edit': {
        const targetId = targetIds[0]
        const item = canvasItems.find((canvasItem: any) => canvasItem.id === targetId)
        if (!item || item.type !== 'image' || !item.url || !id) break

        void photoshopEditJobsApi.create(Number(id), buildPhotoshopEditPayload(item))
          .then(() => {
            toast.success(t('canvas.photoshop_edit.create_success', '已发送到 Photoshop 待处理列表'))
          })
          .catch((error) => {
            console.error('Failed to create Photoshop edit job:', error)
            toast.error(t('canvas.photoshop_edit.create_failed', '发送到 Photoshop 失败'))
          })
        break
      }
      case 'bring_forward':
        updateCanvasItems((prev: any[]) => shiftCanvasItemsOneLayer(prev, targetIds, 'forward'))
        break
      case 'send_backward':
        updateCanvasItems((prev: any[]) => shiftCanvasItemsOneLayer(prev, targetIds, 'backward'))
        break
      case 'bring_front':
        updateCanvasItems((prev: any[]) => {
          const maxZ = Math.max(0, ...prev.map((item) => item.z_index || 0))
          return prev.map((item) => targetIds.includes(item.id) ? { ...item, z_index: maxZ + 1 } : item)
        })
        break
      case 'send_back':
        updateCanvasItems((prev: any[]) => {
          const minZ = Math.min(0, ...prev.map((item) => item.z_index || 0))
          return prev.map((item) => targetIds.includes(item.id) ? { ...item, z_index: minZ - 1 } : item)
        })
        break
      case 'toggle_visible': {
        const groupIds = targetIds.filter((itemId) => canvasItems.find((item: any) => item.id === itemId)?.type === 'group')
        const groupHidden: Record<string, boolean> = {}
        groupIds.forEach((groupId) => { groupHidden[groupId] = !canvasItems.find((item: any) => item.id === groupId)?.is_hidden })
        const nextItems = canvasItems.map((item: any) => {
          if (targetIds.includes(item.id)) return { ...item, is_hidden: !item.is_hidden }
          if (item.groupId && groupIds.includes(item.groupId)) return { ...item, is_hidden: groupHidden[item.groupId] }
          return item
        })
        updateCanvasItems(nextItems)
        setSelectedItems((prev: string[]) => prev.filter((itemId) => !targetIds.includes(itemId)))
        saveCanvasItems(nextItems)
        break
      }
      case 'lock': {
        const groupIds = targetIds.filter((itemId) => canvasItems.find((item: any) => item.id === itemId)?.type === 'group')
        const groupLocked: Record<string, boolean> = {}
        groupIds.forEach((groupId) => { groupLocked[groupId] = !canvasItems.find((item: any) => item.id === groupId)?.is_locked })
        const nextItems = canvasItems.map((item: any) => {
          if (targetIds.includes(item.id)) return { ...item, is_locked: !item.is_locked }
          if (item.groupId && groupIds.includes(item.groupId)) return { ...item, is_locked: groupLocked[item.groupId] }
          return item
        })
        updateCanvasItems(nextItems)
        saveCanvasItems(nextItems)
        break
      }
      case 'delete': {
        const groupIds = targetIds.filter((itemId) => canvasItems.find((item: any) => item.id === itemId)?.type === 'group')
        const memberIds = groupIds.length > 0
          ? canvasItems.filter((item: any) => item.groupId && groupIds.includes(item.groupId)).map((item: any) => item.id)
          : []
        const allDeleteIds = [...targetIds, ...memberIds]
        const nextDeletedAgentMediaKeys = allDeleteIds.reduce((currentKeys: string[], deleteId) => {
          const item = canvasItems.find((canvasItem: any) => canvasItem.id === deleteId)
          if (item?.asset_origin !== 'ai_generated') {
            return currentKeys
          }

          return recordDeletedAgentMediaKey(currentKeys, item.agent_media_key || item.id)
        }, deletedAgentMediaKeys)
        const nextItems = canvasItems.filter((item: any) => !allDeleteIds.includes(item.id))
        setDeletedAgentMediaKeys(nextDeletedAgentMediaKeys)
        updateCanvasItems(nextItems)
        setSelectedItems([])
        saveCanvasItems(nextItems, { deletedAgentMediaKeys: nextDeletedAgentMediaKeys })
        break
      }
    }
  }, [canvasItems, canvasRef, clipboardItems, contextMenu, deletedAgentMediaKeys, handlePasteClipboardImage, loadImageElement, loadVideoElement, mousePosRef, offset.x, offset.y, saveCanvasItems, selectedItems, setClipboardItems, setDeletedAgentMediaKeys, setSelectedItems, t, updateCanvasItems, zoom])

  const handleBulkExport = useCallback(async (itemIds: string[], format?: string) => {
    const targets = canvasItems.filter((item: any) => itemIds.includes(item.id))
    const groupIds = targets.filter((item: any) => item.type === 'group').map((item: any) => item.id)
    const items = canvasItems.filter((item: any) => (itemIds.includes(item.id) || (item.groupId && groupIds.includes(item.groupId))) && item.url && item.type !== 'group')

    if (items.length === 0) {
      toast.error('没有可导出的图层')
      return
    }

    if (items.length > 1) {
      toast.info(`正在导出 ${items.length} 个项目...`)
    }

    const exportFilenameByItemId = buildCanvasExportFilenameMap({
      projectName,
      canvasItems,
      targetItemIds: itemIds,
      exportItems: items,
    })

    for (let idx = 0; idx < items.length; idx++) {
      const item = items[idx]
      try {
        const res = await fetch(item.url)
        const blob = await res.blob()

        if (item.type === 'video' || item.type === 'video_generator') {
          const tempUrl = URL.createObjectURL(blob)
          const anchor = document.createElement('a')
          anchor.href = tempUrl
          const filename = exportFilenameByItemId.get(item.id) || `video-${item.id}`
          anchor.download = `${filename}.mp4`
          anchor.click()
          URL.revokeObjectURL(tempUrl)
        } else {
          const exportFormat = format || 'PNG'
          if (exportFormat === 'SVG') {
            const reader = new FileReader()
            reader.onloadend = () => {
              const base64 = reader.result
              if (typeof base64 !== 'string') return
              const exportImage = new Image()
              exportImage.onload = () => {
                const { width, height } = getImageExportDimensions(item, {
                  width: exportImage.width,
                  height: exportImage.height,
                })
                const svgStr = `<svg xmlns="http://www.w3.org/2000/svg" width="${width || 512}" height="${height || 512}"><image href="${base64}" width="100%" height="100%"/></svg>`
                const svgBlob = new Blob([svgStr], { type: 'image/svg+xml' })
                const tempUrl = URL.createObjectURL(svgBlob)
                const anchor = document.createElement('a')
                anchor.href = tempUrl
                const filename = exportFilenameByItemId.get(item.id) || `image-${item.id}`
                anchor.download = `${filename}.svg`
                anchor.click()
                URL.revokeObjectURL(tempUrl)
              }
              exportImage.src = base64
            }
            reader.readAsDataURL(blob)
          } else {
            const img = new Image()
            img.crossOrigin = 'anonymous'
            img.onload = () => {
              const canvas = document.createElement('canvas')
              const { width, height } = getImageExportDimensions(item, { width: img.width, height: img.height })
              canvas.width = width
              canvas.height = height
              const ctx = canvas.getContext('2d')
              if (ctx) {
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height)
                const mimeType = exportFormat === 'JPG' ? 'image/jpeg' : 'image/png'
                canvas.toBlob((canvasBlob) => {
                  if (canvasBlob) {
                    const tempUrl = URL.createObjectURL(canvasBlob)
                    const anchor = document.createElement('a')
                    anchor.href = tempUrl
                    const filename = exportFilenameByItemId.get(item.id) || `image-${item.id}`
                    anchor.download = `${filename}.${exportFormat.toLowerCase()}`
                    anchor.click()
                    URL.revokeObjectURL(tempUrl)
                  }
                }, mimeType, 0.95)
              }
            }
            img.src = URL.createObjectURL(blob)
          }
        }

        if (idx < items.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 400))
        }
      } catch (error) {
        console.error('Export failed for item:', item.id, error)
      }
    }

    if (items.length > 1) {
      toast.success(t('canvas.export_success_count', { count: items.length }))
    }
  }, [canvasItems, getItemDims, projectName, t])

  const handleMergeLayers = useCallback(async () => {
    const MERGEABLE_TYPES = new Set(['image', 'video', 'text', 'brush_path'])
    const targetItems = selectedItems
      .map((itemId) => canvasItems.find((item: any) => item.id === itemId))
      .filter((item: any) => {
        if (!item) return false
        if (!MERGEABLE_TYPES.has(item.type)) return false
        if ((item.type === 'image' || item.type === 'video') && !item.url) return false
        return true
      })

    if (targetItems.length < 2) {
      toast.error(t('canvas.merge_min_selection'))
      return
    }

    toast.info(t('canvas.merging_layers'))

    try {
      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity
      targetItems.forEach((item: any) => {
        const dims = getItemDims(item)
        const w = item.width || dims.width
        const h = item.height || dims.height
        minX = Math.min(minX, item.x)
        minY = Math.min(minY, item.y)
        maxX = Math.max(maxX, item.x + w)
        maxY = Math.max(maxY, item.y + h)
      })

      const mergedW = Math.round(maxX - minX)
      const mergedH = Math.round(maxY - minY)
      const offscreen = document.createElement('canvas')
      offscreen.width = mergedW
      offscreen.height = mergedH
      const ctx = offscreen.getContext('2d')
      if (!ctx) {
        toast.error(t('canvas.merge_failed'))
        return
      }

      const sorted = [...targetItems].sort((a, b) => (a.z_index || 0) - (b.z_index || 0))
      for (const item of sorted) {
        const dims = getItemDims(item)
        const w = item.width || dims.width
        const h = item.height || dims.height
        const dx = item.x - minX
        const dy = item.y - minY

        if (item.type === 'image' || item.type === 'video') {
          try {
            const res = await fetch(item.url)
            const blob = await res.blob()
            const img = await new Promise<HTMLImageElement>((resolve, reject) => {
              const image = new Image()
              image.crossOrigin = 'anonymous'
              image.onload = () => resolve(image)
              image.onerror = reject
              image.src = URL.createObjectURL(blob)
            })
            ctx.drawImage(img, dx, dy, w, h)
            URL.revokeObjectURL(img.src)
          } catch (error) {
            console.error('Failed to load image for merge:', item.id, error)
          }
        } else if (item.type === 'text') {
          const normalized = normalizeTextCanvasItem(item)
          const variantStyle = getTextItemVariantStyle(normalized)
          const displayLines = formatTextContentForDisplay(normalized)

          ctx.save()
          ctx.textBaseline = 'top'
          ctx.font = `${variantStyle.fontStyle} ${variantStyle.fontWeight} ${normalized.fontSize}px ${normalized.fontFamily}`
          ctx.fillStyle = normalized.fillColor || DEFAULT_TEXT_FILL
          ctx.textAlign = normalized.textAlign as CanvasTextAlign

          let textX = dx
          if (normalized.textAlign === 'center') textX = dx + w / 2
          else if (normalized.textAlign === 'right') textX = dx + w

          const lineH = normalized.fontSize * (normalized.lineHeight || 1.2)
          displayLines.forEach((line, lineIdx) => {
            ctx.fillText(line, textX, dy + lineIdx * lineH)
          })

          if (normalized.strokeColor && normalized.strokeColor !== 'transparent' && normalized.strokeWidth) {
            ctx.strokeStyle = normalized.strokeColor
            ctx.lineWidth = normalized.strokeWidth
            displayLines.forEach((line, lineIdx) => {
              ctx.strokeText(line, textX, dy + lineIdx * lineH)
            })
          }
          ctx.restore()
        } else if (item.type === 'brush_path') {
          ctx.save()
          ctx.translate(dx, dy)
          rasterizeBrushPathToCanvas(ctx, { points: item.points, brushColor: item.brushColor, brushSize: item.brushSize, width: w, height: h })
          ctx.restore()
        }
      }

      const mergedBlob = await new Promise<Blob | null>((resolve) => offscreen.toBlob(resolve, 'image/png'))
      if (!mergedBlob) {
        toast.error(t('canvas.merge_failed'))
        return
      }

      const mergedFile = new File([mergedBlob], 'merged.png', { type: 'image/png' })
      if (!validateUploadFileSize(mergedFile, 'canvas_image_max_bytes', t)) {
        return
      }
      const formData = new FormData()
      formData.append('file', mergedFile)
      const uploadRes = await apiClient.post(`/projects/${id}/upload/image`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })

      const newItem = {
        id: Date.now().toString() + Math.random().toString().slice(2, 6),
        type: 'image',
        url: uploadRes.data.url,
        name: t('canvas.merge_layers'),
        x: Math.round(minX),
        y: Math.round(minY),
        width: mergedW,
        height: mergedH,
        z_index: Math.max(...targetItems.map((item: any) => item.z_index || 0)) + 1,
        groupId: targetItems[0].groupId,
        asset_origin: 'legacy',
      }

      const removeIds = new Set(targetItems.map((item: any) => item.id))
      updateCanvasItems((prev: any[]) => [...prev.filter((item) => !removeIds.has(item.id)), newItem])
      setSelectedItems([newItem.id])
      toast.success(t('canvas.merge_success'))
    } catch (error) {
      console.error('Merge layers failed:', error)
      toast.error(t('canvas.merge_failed'))
    }
  }, [canvasItems, getItemDims, id, selectedItems, setSelectedItems, t, updateCanvasItems])

  const handleAlign = useCallback((alignType: any) => {
    let targetIds = selectedItems
    let group
    if (selectedItems.length === 1) {
      const selectedItem = canvasItems.find((item: any) => item.id === selectedItems[0])
      if (selectedItem?.type === 'group') {
        group = selectedItem
        targetIds = canvasItems.filter((item: any) => item.groupId === selectedItem.id).map((item: any) => item.id)
      }
    }
    if (targetIds.length <= 1) return

    let minX
    let minY
    let maxX
    let maxY
    if (group) {
      minX = group.x
      minY = group.y
      maxX = group.x + (group.width || 0)
      maxY = group.y + (group.height || 0)
    } else {
      minX = Infinity
      minY = Infinity
      maxX = -Infinity
      maxY = -Infinity
      const targets = targetIds.map((itemId) => canvasItems.find((item: any) => item.id === itemId)).filter(Boolean)
      targets.forEach((item: any) => {
        const dims = getItemDims(item)
        const w = item.width || dims.width
        const h = item.height || dims.height
        minX = Math.min(minX, item.x)
        minY = Math.min(minY, item.y)
        maxX = Math.max(maxX, item.x + w)
        maxY = Math.max(maxY, item.y + h)
      })
    }

    const centerX = minX + (maxX - minX) / 2
    const centerY = minY + (maxY - minY) / 2

    updateCanvasItems((prev: any[]) => prev.map((item) => {
      if (!targetIds.includes(item.id)) return item
      const dims = getItemDims(item)
      const w = item.width || dims.width
      const h = item.height || dims.height
      switch (alignType) {
        case 'left': return { ...item, x: minX }
        case 'right': return { ...item, x: maxX - w }
        case 'center': return { ...item, x: centerX - w / 2 }
        case 'top': return { ...item, y: minY }
        case 'bottom': return { ...item, y: maxY - h }
        case 'middle': return { ...item, y: centerY - h / 2 }
        default: return item
      }
    }))
    toast.success(t('canvas.action_success'))
  }, [canvasItems, getItemDims, selectedItems, t, updateCanvasItems])

  const handleSpacing = useCallback((spacingType: any) => {
    let targetIds = selectedItems
    let group
    if (selectedItems.length === 1) {
      const selectedItem = canvasItems.find((item: any) => item.id === selectedItems[0])
      if (selectedItem?.type === 'group') {
        group = selectedItem
        targetIds = canvasItems.filter((item: any) => item.groupId === selectedItem.id).map((item: any) => item.id)
      }
    }
    if (targetIds.length <= 1) return
    const items = targetIds.map((itemId) => canvasItems.find((item: any) => item.id === itemId)).filter(Boolean)
    if (items.length === 0) return

    const padding = group ? 20 : 0
    const updates: Record<string, any> = {}
    if (spacingType === 'horizontal') {
      const sorted = [...items].sort((a: any, b: any) => a.x - b.x)
      const sumW = sorted.reduce((sum: number, item: any) => sum + (item.width || getItemDims(item).width), 0)
      const startX = group ? group.x + padding : sorted[0].x
      const endX = group ? group.x + (group.width || 0) - padding : sorted[sorted.length - 1].x + (sorted[sorted.length - 1].width || getItemDims(sorted[sorted.length - 1]).width)
      const gap = items.length > 1 ? (endX - startX - sumW) / (items.length - 1) : 0
      let currentX = startX
      sorted.forEach((item: any) => {
        updates[item.id] = { x: currentX }
        currentX += (item.width || getItemDims(item).width) + gap
      })
    } else {
      const sorted = [...items].sort((a: any, b: any) => a.y - b.y)
      const sumH = sorted.reduce((sum: number, item: any) => sum + (item.height || getItemDims(item).height), 0)
      const startY = group ? group.y + padding : sorted[0].y
      const endY = group ? group.y + (group.height || 0) - padding : sorted[sorted.length - 1].y + (sorted[sorted.length - 1].height || getItemDims(sorted[sorted.length - 1]).height)
      const gap = items.length > 1 ? (endY - startY - sumH) / (items.length - 1) : 0
      let currentY = startY
      sorted.forEach((item: any) => {
        updates[item.id] = { y: currentY }
        currentY += (item.height || getItemDims(item).height) + gap
      })
    }
    updateCanvasItems((prev: any[]) => prev.map((item) => updates[item.id] ? { ...item, ...updates[item.id] } : item))
    toast.success(t('canvas.action_success'))
  }, [canvasItems, getItemDims, selectedItems, t, updateCanvasItems])

  const handleAutoArrange = useCallback(() => {
    let targetIds = selectedItems
    let group
    if (selectedItems.length === 1) {
      const selectedItem = canvasItems.find((item: any) => item.id === selectedItems[0])
      if (selectedItem?.type === 'group') {
        group = selectedItem
        targetIds = canvasItems.filter((item: any) => item.groupId === selectedItem.id).map((item: any) => item.id)
      }
    }
    if (targetIds.length <= 1) return
    const items = targetIds.map((itemId) => canvasItems.find((item: any) => item.id === itemId)).filter(Boolean)
    if (items.length === 0) return

    const sorted = [...items].sort((a: any, b: any) => (a.z_index || 0) - (b.z_index || 0))
    const itemSizes = sorted.map((item: any) => ({ id: item.id, w: item.width || getItemDims(item).width, h: item.height || getItemDims(item).height }))
    const gap = 16
    const updates: Record<string, any> = {}

    if (group) {
      const padding = 20
      const areaW = (group.width || 0) - padding * 2
      const areaH = (group.height || 0) - padding * 2
      const startX = group.x + padding
      const startY = group.y + padding
      let bestCols = 1
      let bestScore = Infinity
      for (let col = 1; col <= sorted.length; col++) {
        const rows = Math.ceil(sorted.length / col)
        const maxW = Math.max(...itemSizes.slice(0, col).map((size) => size.w))
        const totalW = col * maxW + (col - 1) * gap
        const maxH = Math.max(...itemSizes.map((size) => size.h))
        const totalH = rows * maxH + (rows - 1) * gap
        const score = Math.abs(totalW / areaW - 1) + Math.abs(totalH / areaH - 1)
        if (totalW <= areaW + 1 && score < bestScore) {
          bestScore = score
          bestCols = col
        }
      }

      const cols = bestCols
      const maxItemW = Math.max(...itemSizes.map((size) => size.w))
      const maxItemH = Math.max(...itemSizes.map((size) => size.h))
      const totalGridW = cols * maxItemW + (cols - 1) * gap
      const rows = Math.ceil(sorted.length / cols)
      const totalGridH = rows * maxItemH + (rows - 1) * gap
      const offsetX = startX + Math.max(0, (areaW - totalGridW) / 2)
      const offsetY = startY + Math.max(0, (areaH - totalGridH) / 2)
      sorted.forEach((item: any, index: number) => {
        const col = index % cols
        const row = Math.floor(index / cols)
        const size = itemSizes[index]
        updates[item.id] = {
          x: offsetX + col * (maxItemW + gap) + (maxItemW - size.w) / 2,
          y: offsetY + row * (maxItemH + gap) + (maxItemH - size.h) / 2,
        }
      })
    } else {
      const minX = Math.min(...sorted.map((item: any) => item.x))
      const minY = Math.min(...sorted.map((item: any) => item.y))
      const cols = Math.ceil(Math.sqrt(sorted.length))
      const maxItemW = Math.max(...itemSizes.map((size) => size.w))
      const maxItemH = Math.max(...itemSizes.map((size) => size.h))
      sorted.forEach((item: any, index: number) => {
        const col = index % cols
        const row = Math.floor(index / cols)
        const size = itemSizes[index]
        updates[item.id] = {
          x: minX + col * (maxItemW + gap) + (maxItemW - size.w) / 2,
          y: minY + row * (maxItemH + gap) + (maxItemH - size.h) / 2,
        }
      })
    }

    updateCanvasItems((prev: any[]) => prev.map((item) => updates[item.id] ? { ...item, ...updates[item.id] } : item))
    toast.success(t('canvas.action_success'))
  }, [canvasItems, getItemDims, selectedItems, t, updateCanvasItems])

  useEffect(() => {
    const handleAlignKeys = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable) return
      if (event.altKey && selectedItems.length > 0) {
        const key = event.key.toLowerCase()
        if (key === 'a') { event.preventDefault(); handleAlign('left') }
        if (key === 'h') { event.preventDefault(); handleAlign('center') }
        if (key === 'd') { event.preventDefault(); handleAlign('right') }
        if (key === 'w') { event.preventDefault(); handleAlign('top') }
        if (key === 'v') { event.preventDefault(); handleAlign('middle') }
        if (key === 's') { event.preventDefault(); handleAlign('bottom') }
      }
      if (event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey && selectedItems.length > 0) {
        const key = event.key.toUpperCase()
        if (key === 'H') { event.preventDefault(); handleSpacing('horizontal') }
        if (key === 'V') { event.preventDefault(); handleSpacing('vertical') }
        if (key === 'A') { event.preventDefault(); handleAutoArrange() }
      }
    }
    window.addEventListener('keydown', handleAlignKeys)
    return () => window.removeEventListener('keydown', handleAlignKeys)
  }, [handleAlign, handleAutoArrange, handleSpacing, selectedItems])

  const handleCreateGroup = useCallback(() => {
    if (selectedItems.length <= 1) return
    const items = selectedItems.map((itemId) => canvasItems.find((item: any) => item.id === itemId)).filter(Boolean)
    if (items.some((item: any) => item.type === 'group')) {
      toast.error('编组不能再加入编组')
      return
    }
    if (items.some((item: any) => !['image', 'video', 'image_generator', 'video_generator', 'text'].includes(item.type))) {
      toast.error('编组仅支持图片、视频和文字元素')
      return
    }

    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    items.forEach((item: any) => {
      const dims = getItemDims(item)
      const w = item.width || dims.width
      const h = item.height || dims.height
      minX = Math.min(minX, item.x)
      minY = Math.min(minY, item.y)
      maxX = Math.max(maxX, item.x + w)
      maxY = Math.max(maxY, item.y + h)
    })

    const padding = 80
    const groupId = `group-${Date.now()}`
    const groupWidth = (maxX - minX) + padding * 2
    const groupHeight = (maxY - minY) + padding * 2
    const position = findNonOverlappingGroupPosition({
      target: {
        x: minX - padding,
        y: minY - padding,
        width: groupWidth,
        height: groupHeight,
      },
      obstacles: canvasItems.filter((item: any) => !selectedItems.includes(item.id)),
    })
    const newGroup = {
      id: groupId,
      type: 'group',
      name: `group ${canvasItems.filter((item: any) => item.type === 'group').length + 1}`,
      url: '',
      x: position.x,
      y: position.y,
      width: groupWidth,
      height: groupHeight,
      background_color: 'rgba(22, 119, 255, 0.2)',
      z_index: -999,
    }

    updateCanvasItems((prev: any[]) => [
      ...prev.map((item) => selectedItems.includes(item.id) ? { ...item, groupId } : item),
      newGroup,
    ])
    selectAndCenterCanvasItem(newGroup)
    toast.success('已创建编组')
  }, [canvasItems, getItemDims, selectedItems, selectAndCenterCanvasItem, updateCanvasItems])

  const handleUngroup = useCallback((groupId: string) => {
    updateCanvasItems((prev: any[]) => {
      const groupToRemove = prev.find((item) => item.id === groupId)
      if (!groupToRemove) return prev
      return prev.filter((item) => item.id !== groupId).map((item) => item.groupId === groupId ? { ...item, groupId: undefined } : item)
    })
    setSelectedItems([])
    toast.success('已解除编组')
  }, [setSelectedItems, updateCanvasItems])

  useEffect(() => {
    const handleGroupKeys = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement
      if (target?.tagName === 'INPUT' || target?.tagName === 'TEXTAREA' || target?.isContentEditable) return
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'g') {
        event.preventDefault()
        if (event.shiftKey) {
          if (selectedItems.length === 1) {
            const selectedItem = canvasItems.find((item: any) => item.id === selectedItems[0])
            if (selectedItem?.type === 'group') handleUngroup(selectedItem.id)
          }
        } else if (selectedItems.length > 1) {
          handleCreateGroup()
        }
      }
    }
    window.addEventListener('keydown', handleGroupKeys)
    return () => window.removeEventListener('keydown', handleGroupKeys)
  }, [canvasItems, handleCreateGroup, handleUngroup, selectedItems])

  const setGroupBackgroundColor = useCallback((groupId: string, color: string) => {
    updateCanvasItems((prev: any[]) => prev.map((item) => item.id === groupId ? { ...item, background_color: color } : item))
  }, [updateCanvasItems])

  const handleLayerDrop = useCallback(() => {
    if (!layerDragId || !layerDropTarget) return
    const draggedItem = canvasItems.find((item: any) => item.id === layerDragId)
    const targetItem = canvasItems.find((item: any) => item.id === layerDropTarget.id)
    if (!draggedItem || !targetItem || draggedItem.type === 'group') return

    const { position } = layerDropTarget
    let newGroupId
    const isAllowedInGroup = ['image', 'video', 'image_generator', 'video_generator', 'text'].includes(draggedItem.type)
    if (position === 'inside' && targetItem.type === 'group') {
      if (!isAllowedInGroup) { toast.error('编组仅支持图片、视频和文字元素'); return }
      newGroupId = targetItem.id
    } else if (targetItem.groupId) {
      if (!isAllowedInGroup) { toast.error('编组仅支持图片、视频和文字元素'); return }
      newGroupId = targetItem.groupId
    } else if (position === 'before' && targetItem.type === 'group') {
      newGroupId = undefined
    } else {
      newGroupId = undefined
    }

    let newZIndex
    if (position === 'inside') {
      const members = canvasItems.filter((item: any) => item.groupId === targetItem.id)
      newZIndex = members.length > 0 ? Math.max(...members.map((item: any) => item.z_index || 0)) + 1 : 1
    } else if (position === 'before') {
      newZIndex = (targetItem.z_index || 0) + 1
    } else {
      newZIndex = (targetItem.z_index || 0) - 1
    }

    updateCanvasItems((prev: any[]) => prev.map((item) =>
      item.id === layerDragId ? { ...item, groupId: newGroupId, z_index: newZIndex } : item
    ))
    setLayerDragId(null)
    setLayerDropTarget(null)
  }, [canvasItems, layerDragId, layerDropTarget, setLayerDragId, setLayerDropTarget, updateCanvasItems])

  useEffect(() => {
    const handleGlobalClick = () => {
      setMultiSelectToolsOpen(null)
    }
    window.addEventListener('mousedown', handleGlobalClick)
    return () => window.removeEventListener('mousedown', handleGlobalClick)
  }, [setMultiSelectToolsOpen])

  return {
    handleContextMenuAction,
    handleBulkExport,
    handleMergeLayers,
    handleAlign,
    handleSpacing,
    handleAutoArrange,
    handleCreateGroup,
    handleUngroup,
    setGroupBackgroundColor,
    handleLayerDrop,
  }
}
