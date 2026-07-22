/* eslint-disable @typescript-eslint/no-explicit-any, @typescript-eslint/ban-ts-comment */
// @ts-nocheck
import { useCallback } from 'react'

import { clampCanvasZoom } from '../canvasZoom'
import { getCenteredCanvasOffset } from '../canvasFocus'

export function useCanvasViewportActions(args: any) {
  const {
    camera,
    canvasRef,
    canvasContentRef,
    canvasItems,
    getItemDims,
    isChatSidebarOpen,
    itemIndex,
    setSelectedItems,
    zoom,
    zoomRef,
  } = args

  const handleFocusItem = useCallback((itemId: string) => {
    const item = itemIndex.get(itemId)
    if (!item) return
    const targetZoom = 100
    const scale = targetZoom / 100
    const cx = item.x + (item.width || 1024) / 2
    const cy = item.y + (item.height || 1024) / 2
    const newOffset = { x: -cx * scale, y: -cy * scale }
    camera.setCamera({ zoom: targetZoom, offset: newOffset }, { commit: true, reason: 'focus-item' })
    setSelectedItems([itemId])
  }, [camera, itemIndex, setSelectedItems])

  const handleJumpToItem = useCallback((itemId: string, itemOverride?: any, fitZoom?: boolean) => {
    if (!canvasContentRef.current) return
    const item = itemOverride ?? itemIndex.get(itemId)
    if (!item) return
    const { width, height } = getItemDims(item)

    let targetZoom = zoom
    if (fitZoom && canvasRef.current) {
      const bWidth = item.width || width
      const bHeight = item.height || height
      const zX = (canvasRef.current.clientWidth - 120) / bWidth
      const zY = (canvasRef.current.clientHeight - 120) / bHeight
      const calculatedZoom = Math.min(zX, zY) * 100
      targetZoom = clampCanvasZoom(Math.floor(Math.min(100, calculatedZoom)))
    }

    const newOffset = getCenteredCanvasOffset({
      item,
      fallbackSize: { width, height },
      viewport: {
        width: canvasContentRef.current.offsetWidth,
        height: canvasContentRef.current.offsetHeight,
      },
      zoom: targetZoom,
    })
    if (isChatSidebarOpen) {
      newOffset.x -= (500 + 16) / 2
    }
    camera.setCamera({ zoom: targetZoom, offset: newOffset }, { commit: true, reason: 'jump-to-item' })
  }, [camera, canvasContentRef, itemIndex, canvasRef, getItemDims, isChatSidebarOpen, zoom])

  const selectAndCenterCanvasItem = useCallback((item: any) => {
    setSelectedItems([item.id])
    if (!canvasContentRef.current) return

    const { width, height } = getItemDims(item)
    const newOffset = getCenteredCanvasOffset({
      item,
      fallbackSize: { width, height },
      viewport: {
        width: canvasContentRef.current.offsetWidth,
        height: canvasContentRef.current.offsetHeight,
      },
      zoom: zoomRef.current,
    })
    if (isChatSidebarOpen) {
      newOffset.x -= (500 + 16) / 2
    }

    camera.setCamera({ offset: newOffset }, { commit: true, reason: 'select-and-center' })
  }, [camera, canvasContentRef, getItemDims, isChatSidebarOpen, setSelectedItems, zoomRef])

  const handleFitView = useCallback(() => {
    if (!canvasRef.current) return
    const itemsToFit = canvasItems.filter((item: any) => !item.is_hidden)
    if (itemsToFit.length === 0) {
      camera.setCamera({ zoom: 100, offset: { x: 0, y: 0 } }, { commit: true, reason: 'fit-view' })
      return
    }
    let minX = Infinity
    let minY = Infinity
    let maxX = -Infinity
    let maxY = -Infinity
    itemsToFit.forEach((item: any) => {
      const { width, height } = getItemDims(item)
      minX = Math.min(minX, item.x)
      minY = Math.min(minY, item.y)
      maxX = Math.max(maxX, item.x + (item.width || width))
      maxY = Math.max(maxY, item.y + (item.height || height))
    })
    const bWidth = maxX - minX
    const bHeight = maxY - minY
    const newZoom = clampCanvasZoom(Math.min(Math.floor(Math.min((canvasRef.current.clientWidth - 120) / bWidth, (canvasRef.current.clientHeight - 120) / bHeight) * 100), 200))
    const nextOffset = {
      x: -(minX + bWidth / 2) * (newZoom / 100),
      y: -(minY + bHeight / 2) * (newZoom / 100),
    }
    camera.setCamera({ zoom: newZoom, offset: nextOffset }, { commit: true, reason: 'fit-view' })
  }, [camera, canvasItems, canvasRef, getItemDims])

  return {
    handleFocusItem,
    handleJumpToItem,
    selectAndCenterCanvasItem,
    handleFitView,
  }
}
