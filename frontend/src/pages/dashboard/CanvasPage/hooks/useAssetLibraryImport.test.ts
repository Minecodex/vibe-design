import { act, renderHook } from '@testing-library/react'
import type { TFunction } from 'i18next'
import { describe, expect, it, vi } from 'vitest'

import { useAssetLibraryImport } from './useAssetLibraryImport'

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
  },
}))

describe('useAssetLibraryImport', () => {
  it('switches back to select after importing assets', async () => {
    class MockImage {
      naturalWidth = 800
      naturalHeight = 600
      onload: null | (() => void) = null
      onerror: null | (() => void) = null

      set src(_value: string) {
        queueMicrotask(() => {
          this.onload?.()
        })
      }
    }

    const restoreImage = globalThis.Image
    vi.stubGlobal('Image', MockImage as unknown as typeof Image)

    const setActiveTool = vi.fn()
    const updateCanvasItems = vi.fn((updater) => updater([]))
    const saveCanvasItems = vi.fn()
    const setSelectedItems = vi.fn()
    const handleJumpToItem = vi.fn()
    const t = (((key: string, fallback?: string) => fallback ?? key) as unknown) as TFunction

    try {
      const { result } = renderHook(() => useAssetLibraryImport({
        canvasItems: [],
        zoomRef: { current: 100 },
        offsetRef: { current: { x: 0, y: 0 } },
        updateCanvasItems,
        saveCanvasItems,
        setSelectedItems,
        setActiveTool,
        handleJumpToItem,
        t,
        findPosition: vi.fn(() => ({ x: 120, y: 240 })),
      }))

      await act(async () => {
        await result.current([
          {
            id: 1,
            url: '/asset.png',
            type: 'image',
            origin_kind: 'local_upload',
          },
        ])
      })

      expect(setActiveTool).toHaveBeenCalledWith('select')
      expect(updateCanvasItems).toHaveBeenCalledTimes(1)
      expect(saveCanvasItems).toHaveBeenCalledTimes(1)
      expect(setSelectedItems).toHaveBeenCalledTimes(1)
      expect(handleJumpToItem).toHaveBeenCalledTimes(1)
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })
})
