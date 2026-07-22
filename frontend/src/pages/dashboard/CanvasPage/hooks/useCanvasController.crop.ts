/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useCallback, useEffect } from 'react'
import { toast } from 'sonner'

import {
  CROP_PRESET_GROUPS,
  clampCropRect,
  createCenteredCropRectFromPreset,
  createInitialCropRect,
  getPresetById,
  moveCropRect,
  resizeCropRectFromDimensions,
} from '../cropUtils'
import { CROP_POINTER_SENSITIVITY } from '../constants'

export function useCanvasControllerCrop(args: any) {
  const {
    t,
    canvasItems,
    cropState,
    setCropState,
    cropDragState,
    setCropDragState,
    getItemDims,
    loadImageElement,
    saveCanvasItems,
    updateCanvasItems,
    uploadCanvasImageFile,
  } = args

  const handleOpenCropPanel = useCallback(async (itemId: string) => {
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === itemId)
    if (!item || !['image', 'image_generator'].includes(item.type) || !item.url) return

    try {
      const image = await loadImageElement(item.url)
      const initialRect = createInitialCropRect({
        sourceWidth: image.naturalWidth || item.width || 0,
        sourceHeight: image.naturalHeight || item.height || 0,
      })
      setCropState({
        itemId,
        sourceWidth: image.naturalWidth || item.width || 0,
        sourceHeight: image.naturalHeight || item.height || 0,
        ...initialRect,
        presetId: null,
        isApplying: false,
      })
    } catch (error) {
      console.error('Failed to open crop panel:', error)
      toast.error(t('canvas.crop.open_failed', '打开裁剪失败'))
    }
  }, [canvasItems, loadImageElement, setCropState, t])

  const handleSelectCropPreset = useCallback((presetId: string) => {
    setCropState((prev: any) => {
      if (!prev) return prev
      const preset = getPresetById(CROP_PRESET_GROUPS, presetId)
      if (!preset) return prev
      const nextRect = createCenteredCropRectFromPreset({
        sourceWidth: prev.sourceWidth,
        sourceHeight: prev.sourceHeight,
        preset,
      })
      return {
        ...prev,
        ...nextRect,
        presetId,
      }
    })
  }, [setCropState])

  const handleCropDimensionChange = useCallback((dimension: 'width' | 'height', rawValue: string) => {
    const parsedValue = Number(rawValue)
    if (!Number.isFinite(parsedValue)) return

    setCropState((prev: any) => {
      if (!prev) return prev
      const nextRect = resizeCropRectFromDimensions({
        rect: {
          x: prev.x,
          y: prev.y,
          width: prev.width,
          height: prev.height,
        },
        nextWidth: dimension === 'width' ? parsedValue : undefined,
        nextHeight: dimension === 'height' ? parsedValue : undefined,
        sourceWidth: prev.sourceWidth,
        sourceHeight: prev.sourceHeight,
        minWidth: 1,
        minHeight: 1,
      })
      return {
        ...prev,
        ...nextRect,
        presetId: null,
      }
    })
  }, [setCropState])

  const handleCropHandleMouseDown = useCallback((handle: any, event: React.MouseEvent) => {
    event.stopPropagation()
    event.preventDefault()
    if (!cropState) return

    setCropDragState({
      handle,
      startClientX: event.clientX,
      startClientY: event.clientY,
      startRect: {
        x: cropState.x,
        y: cropState.y,
        width: cropState.width,
        height: cropState.height,
      },
    })
  }, [cropState, setCropDragState])

  const handleCropMoveMouseDown = useCallback((event: React.MouseEvent) => {
    handleCropHandleMouseDown('move', event)
  }, [handleCropHandleMouseDown])

  useEffect(() => {
    if (!cropDragState) return

    const minSize = 40
    const handleMouseMove = (event: MouseEvent) => {
      setCropState((prev: any) => {
        if (!prev) return prev

        const selectedItem = canvasItems.find((canvasItem: any) => canvasItem.id === prev.itemId)
        if (!selectedItem) return prev

        const itemDims = getItemDims(selectedItem)
        const displayWidth = selectedItem.width || itemDims.width
        const displayHeight = selectedItem.height || itemDims.height
        const scaleX = prev.sourceWidth / Math.max(1, displayWidth)
        const scaleY = prev.sourceHeight / Math.max(1, displayHeight)
        const deltaX = (event.clientX - cropDragState.startClientX) * scaleX * CROP_POINTER_SENSITIVITY
        const deltaY = (event.clientY - cropDragState.startClientY) * scaleY * CROP_POINTER_SENSITIVITY

        let nextRect: any
        switch (cropDragState.handle) {
          case 'move':
            nextRect = moveCropRect({
              rect: cropDragState.startRect,
              deltaX,
              deltaY,
              sourceWidth: prev.sourceWidth,
              sourceHeight: prev.sourceHeight,
            })
            return {
              ...prev,
              ...nextRect,
              presetId: null,
            }
          case 'top-left':
            nextRect = {
              x: cropDragState.startRect.x + deltaX,
              y: cropDragState.startRect.y + deltaY,
              width: cropDragState.startRect.width - deltaX,
              height: cropDragState.startRect.height - deltaY,
            }
            break
          case 'top-right':
            nextRect = {
              x: cropDragState.startRect.x,
              y: cropDragState.startRect.y + deltaY,
              width: cropDragState.startRect.width + deltaX,
              height: cropDragState.startRect.height - deltaY,
            }
            break
          case 'bottom-left':
            nextRect = {
              x: cropDragState.startRect.x + deltaX,
              y: cropDragState.startRect.y,
              width: cropDragState.startRect.width - deltaX,
              height: cropDragState.startRect.height + deltaY,
            }
            break
          default:
            nextRect = {
              x: cropDragState.startRect.x,
              y: cropDragState.startRect.y,
              width: cropDragState.startRect.width + deltaX,
              height: cropDragState.startRect.height + deltaY,
            }
        }

        return {
          ...prev,
          ...clampCropRect({
            rect: nextRect,
            sourceWidth: prev.sourceWidth,
            sourceHeight: prev.sourceHeight,
            minWidth: minSize,
            minHeight: minSize,
          }),
          presetId: null,
        }
      })
    }

    const handleMouseUp = () => {
      setCropDragState(null)
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [canvasItems, cropDragState, getItemDims, setCropDragState, setCropState])

  const handleApplyCrop = useCallback(async () => {
    if (!cropState) return
    const item = canvasItems.find((canvasItem: any) => canvasItem.id === cropState.itemId)
    if (!item || !item.url) return

    setCropState((prev: any) => prev ? { ...prev, isApplying: true } : prev)

    try {
      const image = await loadImageElement(item.url)
      const cropArea = clampCropRect({
        rect: {
          x: cropState.x,
          y: cropState.y,
          width: cropState.width,
          height: cropState.height,
        },
        sourceWidth: cropState.sourceWidth,
        sourceHeight: cropState.sourceHeight,
      })
      const outputSize = {
        width: cropArea.width,
        height: cropArea.height,
      }

      const canvas = document.createElement('canvas')
      canvas.width = Math.round(outputSize.width)
      canvas.height = Math.round(outputSize.height)
      const context = canvas.getContext('2d')
      if (!context) throw new Error('missing_canvas_context')

      context.drawImage(
        image,
        cropArea.x,
        cropArea.y,
        cropArea.width,
        cropArea.height,
        0,
        0,
        canvas.width,
        canvas.height,
      )

      const blob = await new Promise<Blob>((resolve, reject) => {
        canvas.toBlob((result) => {
          if (result) {
            resolve(result)
            return
          }
          reject(new Error('failed_to_export_crop'))
        }, 'image/png')
      })

      const uploadedUrl = await uploadCanvasImageFile(
        new File([blob], `crop-${item.id}.png`, { type: 'image/png' }),
      )

      const itemDims = getItemDims(item)
      const displayWidth = item.width || itemDims.width
      const displayHeight = item.height || itemDims.height
      const previewFrame = {
        x: (cropArea.x / cropState.sourceWidth) * displayWidth,
        y: (cropArea.y / cropState.sourceHeight) * displayHeight,
        width: (cropArea.width / cropState.sourceWidth) * displayWidth,
        height: (cropArea.height / cropState.sourceHeight) * displayHeight,
      }

      const nextItems = canvasItems.map((canvasItem: any) => {
        if (canvasItem.id !== item.id) return canvasItem
        return {
          ...canvasItem,
          url: uploadedUrl,
          x: canvasItem.x + previewFrame.x,
          y: canvasItem.y + previewFrame.y,
          width: previewFrame.width,
          height: previewFrame.height,
        }
      })

      updateCanvasItems(nextItems)
      await saveCanvasItems(nextItems)
      setCropState(null)
      toast.success(t('canvas.crop.success', '裁剪完成'))
    } catch (error) {
      console.error('Failed to apply crop:', error)
      toast.error(t('canvas.crop.failed', '裁剪失败'))
      setCropState((prev: any) => prev ? { ...prev, isApplying: false } : prev)
    }
  }, [
    canvasItems,
    cropState,
    getItemDims,
    loadImageElement,
    saveCanvasItems,
    setCropState,
    t,
    updateCanvasItems,
    uploadCanvasImageFile,
  ])

  return {
    handleOpenCropPanel,
    handleSelectCropPreset,
    handleCropDimensionChange,
    handleCropHandleMouseDown,
    handleCropMoveMouseDown,
    handleApplyCrop,
  }
}
