import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useCanvasControllerCrop } from './useCanvasController.crop'

describe('useCanvasControllerCrop', () => {
  it('lets width and height inputs change independently and only clamps them to the source image bounds', () => {
    let cropState = {
      itemId: 'image-1',
      sourceWidth: 1920,
      sourceHeight: 1080,
      x: 100,
      y: 120,
      width: 400,
      height: 500,
      presetId: 'general-1-1',
      isApplying: false,
    }

    const setCropState = vi.fn((next) => {
      cropState = typeof next === 'function' ? next(cropState) : next
    })

    const { result } = renderHook(() =>
      useCanvasControllerCrop({
        t: (_key: string, fallback: string) => fallback,
        canvasItems: [],
        cropState,
        setCropState,
        cropDragState: null,
        setCropDragState: vi.fn(),
        getItemDims: () => ({ width: 0, height: 0 }),
        loadImageElement: vi.fn(),
        saveCanvasItems: vi.fn(),
        updateCanvasItems: vi.fn(),
        uploadCanvasImageFile: vi.fn(),
      }),
    )

    act(() => {
      result.current.handleCropDimensionChange('width', '12')
    })

    expect(cropState.width).toBe(12)
    expect(cropState.height).toBe(500)
    expect(cropState.presetId).toBeNull()

    act(() => {
      result.current.handleCropDimensionChange('height', '5000')
    })

    expect(cropState.width).toBe(12)
    expect(cropState.height).toBe(1080)
  })
})
