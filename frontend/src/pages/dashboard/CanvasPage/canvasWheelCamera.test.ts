import { describe, expect, it, vi } from 'vitest'

import { createCanvasWheelCameraScheduler } from './canvasWheelCamera'

describe('createCanvasWheelCameraScheduler', () => {
  function setup() {
    const setCamera = vi.fn((next) => next)
    const commitCamera = vi.fn(() => ({ zoom: 100, offset: { x: 0, y: 0 } }))
    const setIsWheeling = vi.fn()
    const viewport = document.createElement('div')
    viewport.getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 1000,
      height: 800,
      right: 1000,
      bottom: 800,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    const scheduler = createCanvasWheelCameraScheduler({
      camera: {
        setCamera,
        commitCamera,
      },
      zoomRef: { current: 100 },
      offsetRef: { current: { x: 0, y: 0 } },
      getViewportElement: () => viewport,
      setIsWheeling,
    })
    return { scheduler, setCamera, commitCamera, setIsWheeling }
  }

  it('applies wheel zoom as transient camera updates before one idle commit', () => {
    vi.useFakeTimers()
    const rafSpy = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      callback(0)
      return 1
    })
    const cancelSpy = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    const { scheduler, setCamera, commitCamera, setIsWheeling } = setup()

    scheduler.handleWheel(new WheelEvent('wheel', {
      ctrlKey: true,
      deltaY: 100,
      clientX: 500,
      clientY: 400,
    }))

    expect(setIsWheeling).toHaveBeenCalledWith(true)
    expect(setCamera).toHaveBeenCalledWith(
      expect.objectContaining({ zoom: 94 }),
      { commit: false, reason: 'wheel-idle' },
    )
    expect(commitCamera).not.toHaveBeenCalled()

    vi.advanceTimersByTime(150)

    expect(commitCamera).toHaveBeenCalledTimes(1)
    expect(commitCamera).toHaveBeenCalledWith('wheel-idle')
    expect(setIsWheeling).toHaveBeenLastCalledWith(false)

    scheduler.cancel()
    rafSpy.mockRestore()
    cancelSpy.mockRestore()
    vi.useRealTimers()
  })

  it('coalesces multiple wheel events into one frame while preserving accumulated delta', () => {
    vi.useFakeTimers()
    const queuedFrames: FrameRequestCallback[] = []
    const rafSpy = vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback) => {
      queuedFrames.push(callback)
      return 1
    })
    const cancelSpy = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {})
    const { scheduler, setCamera, commitCamera } = setup()

    scheduler.handleWheel(new WheelEvent('wheel', { deltaX: 10, deltaY: 15 }))
    scheduler.handleWheel(new WheelEvent('wheel', { deltaX: 20, deltaY: 25 }))

    expect(setCamera).not.toHaveBeenCalled()
    const frame = queuedFrames[0]
    if (!frame) {
      throw new Error('expected queued animation frame')
    }
    frame(0)

    expect(setCamera).toHaveBeenCalledTimes(1)
    expect(setCamera).toHaveBeenCalledWith(
      { offset: { x: -30, y: -40 } },
      { commit: false, reason: 'wheel-idle' },
    )
    vi.advanceTimersByTime(150)
    expect(commitCamera).toHaveBeenCalledTimes(1)

    scheduler.cancel()
    rafSpy.mockRestore()
    cancelSpy.mockRestore()
    vi.useRealTimers()
  })
})
