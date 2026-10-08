import { useCallback, useEffect, useMemo, useRef } from 'react'

import {
  applyCanvasViewportTransform,
} from '../canvasViewportTransform'

export type CanvasCamera = {
  offset: { x: number; y: number }
  zoom: number
}

type CameraUpdate = Partial<CanvasCamera> & {
  offset?: { x: number; y: number }
}

type CameraSetOptions = {
  commit?: boolean
}

type CameraCommitReason =
  | 'blur'
  | 'fit-view'
  | 'focus-item'
  | 'initial-sync'
  | 'jump-to-item'
  | 'pan-end'
  | 'reset-zoom'
  | 'select-and-center'
  | 'sync'
  | 'wheel-idle'
  | 'zoom-button'

type CameraListener = (camera: CanvasCamera, options?: { committed: boolean; reason?: CameraCommitReason }) => void

function cloneCamera(camera: CanvasCamera): CanvasCamera {
  return {
    zoom: camera.zoom,
    offset: { ...camera.offset },
  }
}

export function useCanvasCamera(args: {
  canvasContentRef: React.RefObject<HTMLElement>
  zoom: number
  setZoom: (zoom: number) => void
  zoomRef: React.MutableRefObject<number>
  offset: { x: number; y: number }
  setOffset: (offset: { x: number; y: number }) => void
  offsetRef: React.MutableRefObject<{ x: number; y: number }>
}) {
  const {
    canvasContentRef,
    zoom,
    setZoom,
    zoomRef,
    offset,
    setOffset,
    offsetRef,
  } = args

  const cameraRef = useRef<CanvasCamera>({
    offset: { ...offsetRef.current },
    zoom: zoomRef.current,
  })
  const committedCameraRef = useRef<CanvasCamera>(cloneCamera(cameraRef.current))
  const listenersRef = useRef(new Set<CameraListener>())

  const notify = useCallback((camera: CanvasCamera, options?: { committed: boolean; reason?: CameraCommitReason }) => {
    listenersRef.current.forEach((listener) => listener(cloneCamera(camera), options))
  }, [])

  const applyCamera = useCallback((camera: CanvasCamera) => {
    zoomRef.current = camera.zoom
    offsetRef.current = camera.offset
    cameraRef.current = camera
    applyCanvasViewportTransform(canvasContentRef.current, camera.offset, camera.zoom)
  }, [canvasContentRef, offsetRef, zoomRef])

  const commitCamera = useCallback((reason: CameraCommitReason = 'sync') => {
    const camera = cloneCamera(cameraRef.current)
    committedCameraRef.current = camera
    zoomRef.current = camera.zoom
    offsetRef.current = camera.offset
    setZoom(camera.zoom)
    setOffset(camera.offset)
    notify(camera, { committed: true, reason })
    return camera
  }, [notify, offsetRef, setOffset, setZoom, zoomRef])

  const setCamera = useCallback((next: CameraUpdate, options?: CameraSetOptions & { reason?: CameraCommitReason }) => {
    const previous = cameraRef.current
    const nextCamera: CanvasCamera = {
      zoom: next.zoom ?? previous.zoom,
      offset: next.offset ? { ...next.offset } : previous.offset,
    }
    applyCamera(nextCamera)
    notify(nextCamera, { committed: false, reason: options?.reason })
    if (options?.commit) {
      return commitCamera(options.reason)
    }
    return nextCamera
  }, [applyCamera, commitCamera, notify])

  const panToOffset = useCallback((nextOffset: { x: number; y: number }) => (
    setCamera({ offset: nextOffset }, { commit: false })
  ), [setCamera])

  const getCamera = useCallback(() => cloneCamera(cameraRef.current), [])
  const getCommittedCamera = useCallback(() => cloneCamera(committedCameraRef.current), [])

  const subscribe = useCallback((listener: CameraListener) => {
    listenersRef.current.add(listener)
    return () => {
      listenersRef.current.delete(listener)
    }
  }, [])

  useEffect(() => {
    const nextCamera = {
      offset: { ...offset },
      zoom,
    }
    cameraRef.current = nextCamera
    committedCameraRef.current = cloneCamera(nextCamera)
    zoomRef.current = zoom
    offsetRef.current = nextCamera.offset
    applyCanvasViewportTransform(canvasContentRef.current, nextCamera.offset, zoom)
    notify(nextCamera, { committed: true, reason: 'initial-sync' })
  }, [canvasContentRef, notify, offset, offsetRef, zoom, zoomRef])

  return useMemo(() => ({
    cameraRef,
    committedCameraRef,
    getCamera,
    getCommittedCamera,
    setCamera,
    panToOffset,
    commitCamera,
    subscribe,
  }), [commitCamera, getCamera, getCommittedCamera, panToOffset, setCamera, subscribe])
}
