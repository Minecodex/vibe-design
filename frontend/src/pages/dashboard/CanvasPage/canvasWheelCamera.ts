import { getCanvasWheelZoomUpdate } from './canvasZoom'
import type { CanvasCamera } from './hooks/useCanvasCamera'

export const CANVAS_WHEEL_IDLE_MS = 150

type WheelCameraSchedulerOptions = {
  camera: {
    setCamera: (
      next: Partial<CanvasCamera>,
      options?: { commit?: boolean; reason?: 'wheel-idle' },
    ) => CanvasCamera
    commitCamera: (reason?: 'wheel-idle') => CanvasCamera
  }
  zoomRef: React.MutableRefObject<number>
  offsetRef: React.MutableRefObject<{ x: number; y: number }>
  getViewportElement: () => HTMLElement | null
  setIsWheeling?: (value: boolean) => void
  idleMs?: number
}

type WheelInput = {
  clientX: number
  clientY: number
  deltaX: number
  deltaY: number
  deltaMode: number
  ctrlKey: boolean
  metaKey: boolean
}

export type CanvasWheelCameraScheduler = {
  handleWheel: (event: WheelEvent) => boolean
  flush: () => void
  cancel: () => void
}

export function createCanvasWheelCameraScheduler({
  camera,
  zoomRef,
  offsetRef,
  getViewportElement,
  setIsWheeling,
  idleMs = CANVAS_WHEEL_IDLE_MS,
}: WheelCameraSchedulerOptions): CanvasWheelCameraScheduler {
  let frameId = 0
  let idleId: ReturnType<typeof setTimeout> | null = null
  let pendingWheel: WheelInput | null = null
  let wheelActive = false

  const endWheel = () => {
    if (!wheelActive) return
    camera.commitCamera('wheel-idle')
    wheelActive = false
    setIsWheeling?.(false)
  }

  const scheduleIdleCommit = () => {
    if (idleId != null) {
      clearTimeout(idleId)
    }
    idleId = setTimeout(() => {
      idleId = null
      endWheel()
    }, idleMs)
  }

  const applyPendingWheel = () => {
    frameId = 0
    const input = pendingWheel
    pendingWheel = null
    if (!input) return

    const viewport = getViewportElement()
    if (!viewport) return

    if (input.ctrlKey || input.metaKey) {
      const zoomUpdate = getCanvasWheelZoomUpdate({
        oldZoom: zoomRef.current,
        oldOffset: offsetRef.current,
        client: { x: input.clientX, y: input.clientY },
        viewportRect: viewport.getBoundingClientRect(),
        deltaY: input.deltaY,
        deltaMode: input.deltaMode,
      })
      if (!zoomUpdate) return
      camera.setCamera(
        { zoom: zoomUpdate.newZoom, offset: zoomUpdate.newOffset },
        { commit: false, reason: 'wheel-idle' },
      )
      return
    }

    camera.setCamera(
      {
        offset: {
          x: offsetRef.current.x - input.deltaX,
          y: offsetRef.current.y - input.deltaY,
        },
      },
      { commit: false, reason: 'wheel-idle' },
    )
  }

  const scheduleFrame = () => {
    if (frameId !== 0) return
    frameId = window.requestAnimationFrame(applyPendingWheel)
  }

  return {
    handleWheel(event: WheelEvent) {
      const isZoomWheel = event.ctrlKey || event.metaKey
      if (
        pendingWheel
        && pendingWheel.ctrlKey === event.ctrlKey
        && pendingWheel.metaKey === event.metaKey
        && pendingWheel.deltaMode === event.deltaMode
      ) {
        pendingWheel = {
          clientX: event.clientX,
          clientY: event.clientY,
          deltaX: pendingWheel.deltaX + event.deltaX,
          deltaY: pendingWheel.deltaY + event.deltaY,
          deltaMode: event.deltaMode,
          ctrlKey: event.ctrlKey,
          metaKey: event.metaKey,
        }
      } else {
        pendingWheel = {
          clientX: event.clientX,
          clientY: event.clientY,
          deltaX: event.deltaX,
          deltaY: event.deltaY,
          deltaMode: event.deltaMode,
          ctrlKey: event.ctrlKey,
          metaKey: event.metaKey,
        }
      }

      if (!wheelActive) {
        wheelActive = true
        setIsWheeling?.(true)
      }
      scheduleFrame()
      scheduleIdleCommit()
      return isZoomWheel
    },
    flush() {
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId)
        frameId = 0
      }
      applyPendingWheel()
      if (idleId != null) {
        clearTimeout(idleId)
        idleId = null
      }
      endWheel()
    },
    cancel() {
      if (frameId !== 0) {
        window.cancelAnimationFrame(frameId)
        frameId = 0
      }
      pendingWheel = null
      if (idleId != null) {
        clearTimeout(idleId)
        idleId = null
      }
      wheelActive = false
      setIsWheeling?.(false)
    },
  }
}
