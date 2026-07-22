import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { act, renderHook } from '@testing-library/react'
import { useRef, useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCanvasControllerMedia } from './hooks/useCanvasController.media'
import { useAppConfigStore } from '@/store/appConfigStore'

const currentDir = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(
  resolve(currentDir, 'hooks', 'useCanvasController.media.ts'),
  'utf8',
)
const batchImportSource = readFileSync(
  resolve(currentDir, 'canvasImageBatchImport.ts'),
  'utf8',
)
const pageSource = readFileSync(resolve(currentDir, 'index.tsx'), 'utf8')

const {
  toastError,
  toastSuccess,
  toastWarning,
  generateHDUpscale,
  extractTextRedraw,
  generateTextRedraw,
  generateImageErase,
  apiPost,
  readClipboardImageFileFromNavigator,
} = vi.hoisted(() => ({
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastWarning: vi.fn(),
  generateHDUpscale: vi.fn(),
  extractTextRedraw: vi.fn(),
  generateTextRedraw: vi.fn(),
  generateImageErase: vi.fn(),
  apiPost: vi.fn(),
  readClipboardImageFileFromNavigator: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    error: toastError,
    success: toastSuccess,
    warning: toastWarning,
  },
}))

vi.mock('@/api/endpoints/generation', () => ({
  generationApi: {
    generateHDUpscale,
    extractTextRedraw,
    generateTextRedraw,
    generateImageErase,
  },
}))

vi.mock('@/api/client', () => ({
  apiClient: {
    post: apiPost,
  },
}))

vi.mock('./clipboardImage', () => ({
  readClipboardImageFileFromNavigator,
}))

function createMediaHookArgs(overrides: Record<string, unknown> = {}) {
  const imageItem = {
    id: 'image-1',
    type: 'image',
    url: '/image.png',
    x: 0,
    y: 0,
    width: 256,
    height: 256,
  }

  const imageEraseSession = {
    tool: 'erase',
    itemId: imageItem.id,
    imageUrl: imageItem.url,
    displayWidth: 256,
    displayHeight: 256,
    sourceWidth: 256,
    sourceHeight: 256,
    mode: 'brush',
    brushSize: 24,
    history: [{ maskDataUrl: null }],
    future: [],
    isSubmitting: false,
    hasMask: false,
  }

  return {
    t: (_key: string, fallback?: string) => fallback ?? _key,
    user: { balance_cents: 0 },
    id: 1,
    isGuest: false,
    canvasRef: { current: { getBoundingClientRect: () => ({ width: 1440, height: 900, left: 0, top: 0 }) } },
    canvasItems: [imageItem],
    selectedItems: [],
    setSelectedItems: vi.fn(),
    saveCanvasItems: vi.fn(),
    updateCanvasItems: vi.fn(),
    updateItem: vi.fn(),
    getItemDims: vi.fn(() => ({ width: 256, height: 256 })),
    loadIntrinsicImageSize: vi.fn().mockResolvedValue({ width: 256, height: 256 }),
    imageDetailItemId: null,
    setImageDetailItemId: vi.fn(),
    setImageDetailPanelPosition: vi.fn(),
    imageDetailSizeBytes: null,
    setImageDetailSizeBytes: vi.fn(),
    projectAssets: {},
    setProjectAssets: vi.fn(),
    deletedAgentMediaKeys: [],
    setDeletedAgentMediaKeys: vi.fn(),
    textRedrawState: null,
    setTextRedrawState: vi.fn(),
    textRedrawExtractingItemIds: new Set(),
    setTextRedrawExtractingItemIds: vi.fn(),
    setTextRedrawPanelPosition: vi.fn(),
    imageEraseSession,
    setImageEraseSession: vi.fn(),
    setImageErasePreviewRect: vi.fn(),
    imageEraseCanvasRef: { current: null },
    imageEraseBrushCanvasRef: { current: null },
    imageEraseSessionRef: { current: imageEraseSession },
    imageErasePointerRef: { current: null },
    imageEraseCheckerboardPatternRef: { current: null },
    handleJumpToItem: vi.fn(),
    setActiveTool: vi.fn(),
    selectAndCenterCanvasItem: vi.fn(),
    loadProjectAssets: vi.fn(),
    zoomRef: { current: 100 },
    offsetRef: { current: { x: 0, y: 0 } },
    latestCanvasItemsRef: { current: [imageItem] },
    setZoom: vi.fn(),
    setOffset: vi.fn(),
    setClipboardSource: vi.fn(),
    ...overrides,
  }
}

describe('useCanvasController media detail flow', () => {
  beforeEach(() => {
    toastError.mockReset()
    toastSuccess.mockReset()
    toastWarning.mockReset()
    generateHDUpscale.mockReset()
    extractTextRedraw.mockReset()
    generateTextRedraw.mockReset()
    generateImageErase.mockReset()
    apiPost.mockReset()

    generateHDUpscale.mockResolvedValue({
      data: {
        calculated_width: 512,
        calculated_height: 512,
        task: { id: 99 },
      },
    })
    extractTextRedraw.mockResolvedValue({
      data: {
        segments: [{ id: 'seg-1', text: 'Hello', order: 1 }],
      },
    })
    generateTextRedraw.mockResolvedValue({ data: { id: 77 } })
    generateImageErase.mockResolvedValue({ data: { id: 66 } })
    apiPost.mockResolvedValue({ data: { url: '/uploaded-image.png' } })
    readClipboardImageFileFromNavigator.mockReset()
    useAppConfigStore.setState({
      appName: '像素重组',
      appNameEn: 'Pixel Reorganization',
      uploadLimits: null,
      isLoaded: false,
    })
  })

  it('refreshes project assets when opening image details for newly synced canvas images', () => {
    expect(source).toContain('const handleOpenImageDetails = useCallback')
    expect(source).toContain('void loadProjectAssets()')
  })

  it('persists deleted chat-generated media keys when a canvas image is removed', () => {
    expect(source).toContain('recordDeletedAgentMediaKey')
    expect(source).toContain("saveCanvasItems(deleteResult.canvasItems, { deletedAgentMediaKeys: nextDeletedAgentMediaKeys })")
  })

  it('places newly uploaded media on the current top layer', () => {
    expect(batchImportSource).toContain('z_index: getNextCanvasStackZIndex(occupiedItems)')
  })

  it('allows the canvas image picker to select multiple files', () => {
    expect(pageSource).toContain('ref={imageInputRef} type="file" accept="image/*" multiple')
  })

  it('switches back to select after uploading an image', async () => {
    const setActiveTool = vi.fn()
    const setSelectedItems = vi.fn()
    const updateCanvasItems = vi.fn()
    const saveCanvasItems = vi.fn()
    const handleJumpToItem = vi.fn()

    class MockImage {
      naturalWidth = 640
      naturalHeight = 480
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

    try {
      const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
        user: { balance_cents: 100 },
        setActiveTool,
        setSelectedItems,
        updateCanvasItems,
        saveCanvasItems,
        handleJumpToItem,
      })))

      await act(async () => {
        await result.current.handleUploadImage({
          target: {
            files: [new File(['img'], 'test.png', { type: 'image/png' })],
            value: 'C:/fakepath/test.png',
          },
        } as unknown as React.ChangeEvent<HTMLInputElement>)
      })

      expect(setActiveTool).toHaveBeenCalledWith('select')
      expect(setSelectedItems).toHaveBeenCalledTimes(1)
      expect(updateCanvasItems).toHaveBeenCalledTimes(1)
      expect(saveCanvasItems).toHaveBeenCalledTimes(1)
      expect(handleJumpToItem).toHaveBeenCalledTimes(1)
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })

  it('uploads multiple selected images and commits them to the canvas once', async () => {
    const setSelectedItems = vi.fn()
    const updateCanvasItems = vi.fn()
    const saveCanvasItems = vi.fn()
    const latestCanvasItemsRef = { current: createMediaHookArgs().canvasItems }

    class MockImage {
      naturalWidth = 400
      naturalHeight = 300
      onload: null | (() => void) = null
      onerror: null | (() => void) = null

      set src(_value: string) {
        queueMicrotask(() => this.onload?.())
      }
    }

    apiPost.mockImplementation(async (_url: string, formData: FormData) => {
      const file = formData.get('file') as File
      return { data: { url: `/uploads/${file.name}` } }
    })
    const restoreImage = globalThis.Image
    vi.stubGlobal('Image', MockImage as unknown as typeof Image)

    try {
      const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
        latestCanvasItemsRef,
        setSelectedItems,
        updateCanvasItems,
        saveCanvasItems,
      })))
      const inputTarget = {
        files: [
          new File(['first'], 'first.png', { type: 'image/png' }),
          new File(['second'], 'second.png', { type: 'image/png' }),
        ],
        value: 'selected',
      }

      await act(async () => {
        await result.current.handleUploadImage({
          target: inputTarget,
        } as unknown as React.ChangeEvent<HTMLInputElement>)
      })

      expect(apiPost).toHaveBeenCalledTimes(2)
      expect(updateCanvasItems).toHaveBeenCalledTimes(1)
      expect(saveCanvasItems).toHaveBeenCalledTimes(1)
      const nextItems = updateCanvasItems.mock.calls[0][0]
      const uploadedItems = nextItems.slice(-2)
      expect(uploadedItems.map((item: { url: string }) => item.url)).toEqual([
        '/uploads/first.png',
        '/uploads/second.png',
      ])
      expect(new Set(uploadedItems.map((item: { id: string }) => item.id)).size).toBe(2)
      expect(uploadedItems[0].x === uploadedItems[1].x && uploadedItems[0].y === uploadedItems[1].y).toBe(false)
      expect(setSelectedItems).toHaveBeenCalledWith(uploadedItems.map((item: { id: string }) => item.id))
      expect(latestCanvasItemsRef.current).toBe(nextItems)
      expect(inputTarget.value).toBe('')
      expect(toastSuccess).toHaveBeenCalledTimes(1)
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })

  it('imports a canvas image file directly without opening the upload picker', async () => {
    const setActiveTool = vi.fn()
    const setSelectedItems = vi.fn()
    const updateCanvasItems = vi.fn()
    const saveCanvasItems = vi.fn()
    const handleJumpToItem = vi.fn()

    class MockImage {
      naturalWidth = 640
      naturalHeight = 480
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

    try {
      const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
        user: { balance_cents: 100 },
        setActiveTool,
        setSelectedItems,
        updateCanvasItems,
        saveCanvasItems,
        handleJumpToItem,
      })))

      await act(async () => {
        await result.current.importCanvasImageFile(new File(['img'], 'paste.png', { type: 'image/png' }))
      })

      expect(setActiveTool).toHaveBeenCalledWith('select')
      expect(setSelectedItems).toHaveBeenCalledTimes(1)
      expect(updateCanvasItems).toHaveBeenCalledTimes(1)
      expect(saveCanvasItems).toHaveBeenCalledTimes(1)
      expect(handleJumpToItem).toHaveBeenCalledTimes(1)
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })

  it('does not send oversized canvas image uploads when public config has a limit', async () => {
    useAppConfigStore.setState({
      uploadLimits: {
        avatar_max_bytes: 10,
        canvas_image_max_bytes: 3,
        canvas_video_max_bytes: 10,
        harness_attachment_max_bytes: 10,
      },
    })
    const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
      user: { balance_cents: 100 },
    })))

    await act(async () => {
      const imported = await result.current.importCanvasImageFile(new File(['toolarge'], 'paste.png', { type: 'image/png' }))
      expect(imported).toBe(false)
    })

    expect(apiPost).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })

  it('switches back to select after uploading a video', async () => {
    const setActiveTool = vi.fn()
    const setSelectedItems = vi.fn()
    const updateCanvasItems = vi.fn()
    const saveCanvasItems = vi.fn()
    const handleJumpToItem = vi.fn()
    const originalCreateElement = document.createElement.bind(document)

    class MockVideoElement {
      videoWidth = 1920
      videoHeight = 1080
      onloadedmetadata: ((this: GlobalEventHandlers, ev: Event) => unknown) | null = null
      onerror: OnErrorEventHandler = null

      set src(_value: string) {
        queueMicrotask(() => {
          this.onloadedmetadata?.call(this as unknown as GlobalEventHandlers, new Event('loadedmetadata'))
        })
      }
    }

    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'video') {
        return new MockVideoElement() as unknown as HTMLVideoElement
      }
      return originalCreateElement(tagName)
    }) as typeof document.createElement)

    try {
      const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
        user: { balance_cents: 100 },
        setActiveTool,
        setSelectedItems,
        updateCanvasItems,
        saveCanvasItems,
        handleJumpToItem,
      })))

      await act(async () => {
        await result.current.handleUploadVideo({
          target: {
            files: [new File(['video'], 'test.mp4', { type: 'video/mp4' })],
            value: 'C:/fakepath/test.mp4',
          },
        } as unknown as React.ChangeEvent<HTMLInputElement>)
      })

      expect(setActiveTool).toHaveBeenCalledWith('select')
      expect(setSelectedItems).toHaveBeenCalledTimes(1)
      expect(updateCanvasItems).toHaveBeenCalledTimes(1)
      expect(saveCanvasItems).toHaveBeenCalledTimes(1)
      expect(handleJumpToItem).toHaveBeenCalledTimes(1)
    } finally {
      createElementSpy.mockRestore()
    }
  })

  it('blocks HD upscale requests when balance is zero', async () => {
    const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs()))

    await act(async () => {
      await result.current.handleOpenHDUpscale('image-1')
    })

    expect(generateHDUpscale).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })

  it('blocks text redraw extraction requests when balance is zero', async () => {
    const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs()))

    await act(async () => {
      await result.current.handleOpenTextRedraw('image-1')
    })

    expect(extractTextRedraw).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })

  it('blocks text redraw submit when balance is zero', async () => {
    const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
      textRedrawState: {
        itemId: 'image-1',
        status: 'editing',
        segments: [
          { id: 'seg-1', originalText: 'Hello', text: 'World', order: 1 },
        ],
      },
    })))

    await act(async () => {
      await result.current.handleSubmitTextRedraw()
    })

    expect(generateTextRedraw).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })

  it('blocks erase submit when balance is zero', async () => {
    const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
      imageEraseSession: {
        tool: 'erase',
        itemId: 'image-1',
        imageUrl: '/image.png',
        displayWidth: 256,
        displayHeight: 256,
        sourceWidth: 256,
        sourceHeight: 256,
        mode: 'brush',
        brushSize: 24,
        history: [{ maskDataUrl: null }],
        future: [],
        isSubmitting: false,
        hasMask: false,
      },
      imageEraseSessionRef: {
        current: {
          tool: 'erase',
          itemId: 'image-1',
          imageUrl: '/image.png',
          displayWidth: 256,
          displayHeight: 256,
          sourceWidth: 256,
          sourceHeight: 256,
          mode: 'brush',
          brushSize: 24,
          history: [{ maskDataUrl: null }],
          future: [],
          isSubmitting: false,
          hasMask: false,
        },
      },
    })))

    await act(async () => {
      await result.current.handleSubmitImageErase()
    })

    expect(generateImageErase).not.toHaveBeenCalled()
    expect(toastError).toHaveBeenCalled()
  })

  it('clears the erase session immediately after submit while the generation task is still pending', async () => {
    let resolveGeneration: ((value: any) => void) | null = null
    generateImageErase.mockImplementation(() => new Promise((resolve) => {
      resolveGeneration = resolve
    }))

    const canvasContext = {
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      fillRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      createPattern: vi.fn(() => '#pattern'),
      getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(4) })),
    }

    const getContextSpy = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext as any)
    const toBlobSpy = vi.spyOn(HTMLCanvasElement.prototype, 'toBlob').mockImplementation((callback) => {
      callback?.(new Blob(['erase'], { type: 'image/png' }))
    })

    class MockImage {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      crossOrigin = ''

      set src(_value: string) {
        queueMicrotask(() => {
          this.onload?.()
        })
      }
    }

    const restoreImage = globalThis.Image
    vi.stubGlobal('Image', MockImage as any)

    try {
      const initialSession = {
        tool: 'erase',
        itemId: 'image-1',
        imageUrl: '/image.png',
        displayWidth: 256,
        displayHeight: 256,
        sourceWidth: 256,
        sourceHeight: 256,
        mode: 'brush',
        brushSize: 24,
        history: [{ maskDataUrl: null }],
        future: [],
        isSubmitting: false,
        hasMask: true,
      }

      const { result } = renderHook(() => {
        const [imageEraseSession, setImageEraseSession] = useState<any>(initialSession)
        const imageEraseSessionRef = useRef<any>(imageEraseSession)

        return {
          ...useCanvasControllerMedia(createMediaHookArgs({
            user: { balance_cents: 100 },
            imageEraseSession,
            setImageEraseSession,
            imageEraseSessionRef,
          })),
          imageEraseSession,
        }
      })

      await act(async () => {
        void result.current.handleSubmitImageErase()
        await Promise.resolve()
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(generateImageErase).toHaveBeenCalledTimes(1)
      expect(result.current.imageEraseSession).toBeNull()

      await act(async () => {
        resolveGeneration?.({ data: { id: 66 } })
        await Promise.resolve()
      })
    } finally {
      vi.stubGlobal('Image', restoreImage)
      getContextSpy.mockRestore()
      toBlobSpy.mockRestore()
    }
  })

  it('preserves the brush mask in the exported composite even after the UI session is cleared', async () => {
    let resolveGeneration: ((value: any) => void) | null = null
    generateImageErase.mockImplementation(() => new Promise((resolve) => {
      resolveGeneration = resolve
    }))

    const originalCreateElement = document.createElement.bind(document)
    const originalImage = globalThis.Image

    let brushMaskCleared = false

    const displayContext = {
      clearRect: vi.fn(),
    }
    const displayCanvas = {
      width: 256,
      height: 256,
      getContext: vi.fn(() => displayContext),
    }

    const brushContext = {
      clearRect: vi.fn(() => {
        brushMaskCleared = true
      }),
      getImageData: vi.fn(() => ({
        data: new Uint8ClampedArray(brushMaskCleared ? [0, 0, 0, 0] : [0, 0, 0, 255]),
      })),
    }
    const brushCanvas = {
      width: 256,
      height: 256,
      getContext: vi.fn(() => brushContext),
      toDataURL: vi.fn(() => 'data:image/png;base64,mask'),
    }

    const exportContext = {
      drawImage: vi.fn(),
      fillRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      fill: vi.fn(),
      save: vi.fn(),
      restore: vi.fn(),
      createPattern: vi.fn(() => '#pattern'),
    }
    const exportCanvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => exportContext),
      toBlob: vi.fn((callback: BlobCallback) => {
        callback(new Blob(['erase'], { type: 'image/png' }))
      }),
    }

    const patternContext = {
      fillRect: vi.fn(),
      fillStyle: '',
    }
    const patternCanvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => patternContext),
    }

    let canvasCreateCount = 0
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation(((tagName: string) => {
      if (tagName === 'canvas') {
        canvasCreateCount += 1
        if (canvasCreateCount === 1) return exportCanvas as any
        if (canvasCreateCount === 2) return patternCanvas as any
      }
      return originalCreateElement(tagName)
    }) as typeof document.createElement)

    class MockImage {
      onload: null | (() => void) = null
      onerror: null | (() => void) = null
      crossOrigin = ''

      set src(_value: string) {
        queueMicrotask(() => {
          this.onload?.()
        })
      }
    }

    vi.stubGlobal('Image', MockImage as any)

    try {
      const initialSession = {
        tool: 'erase',
        itemId: 'image-1',
        imageUrl: '/image.png',
        displayWidth: 256,
        displayHeight: 256,
        sourceWidth: 256,
        sourceHeight: 256,
        mode: 'brush',
        brushSize: 24,
        history: [{ maskDataUrl: null }],
        future: [],
        isSubmitting: false,
        hasMask: true,
      }

      const { result } = renderHook(() => {
        const [imageEraseSession, setImageEraseSession] = useState<any>(initialSession)
        const imageEraseSessionRef = useRef<any>(imageEraseSession)

        return useCanvasControllerMedia(createMediaHookArgs({
          user: { balance_cents: 100 },
          imageEraseSession,
          setImageEraseSession,
          imageEraseSessionRef,
          imageEraseCanvasRef: { current: displayCanvas as any },
          imageEraseBrushCanvasRef: { current: brushCanvas as any },
        }))
      })

      await act(async () => {
        void result.current.handleSubmitImageErase()
        await Promise.resolve()
        await Promise.resolve()
        await Promise.resolve()
      })

      expect(brushContext.clearRect).toHaveBeenCalled()
      expect(exportContext.drawImage).toHaveBeenCalledTimes(2)

      await act(async () => {
        resolveGeneration?.({ data: { id: 66 } })
        await Promise.resolve()
      })
    } finally {
      vi.stubGlobal('Image', originalImage)
      createElementSpy.mockRestore()
    }
  })

  it('keeps cutout exempt from the paid guard', () => {
    expect(source).toContain("if (session.tool === 'erase' && !ensurePaidActionAllowed()) return")
    expect(source).toContain("if (session.tool === 'cutout') {")
  })

  it('tracks text redraw extraction status per item so multiple images can extract in parallel', async () => {
    let resolveFirst: ((value: any) => void) | null = null
    let resolveSecond: ((value: any) => void) | null = null

    extractTextRedraw
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveFirst = resolve
      }))
      .mockImplementationOnce(() => new Promise((resolve) => {
        resolveSecond = resolve
      }))

    const { result } = renderHook(() => {
      const [textRedrawState, setTextRedrawState] = useState<any>(null)
      const [textRedrawExtractingItemIds, setTextRedrawExtractingItemIds] = useState<Set<string>>(new Set())

      return useCanvasControllerMedia(createMediaHookArgs({
        user: { balance_cents: 100 },
        canvasItems: [
          {
            id: 'image-1',
            type: 'image',
            url: '/image-1.png',
            x: 0,
            y: 0,
            width: 256,
            height: 256,
          },
          {
            id: 'image-2',
            type: 'image',
            url: '/image-2.png',
            x: 300,
            y: 0,
            width: 256,
            height: 256,
          },
        ],
        textRedrawState,
        setTextRedrawState,
        textRedrawExtractingItemIds,
        setTextRedrawExtractingItemIds,
      }))
    })

    await act(async () => {
      void result.current.handleOpenTextRedraw('image-1')
      await Promise.resolve()
    })

    expect(Array.from(result.current.textRedrawExtractingItemIds)).toEqual(['image-1'])

    await act(async () => {
      void result.current.handleOpenTextRedraw('image-2')
      await Promise.resolve()
    })

    expect(new Set(result.current.textRedrawExtractingItemIds)).toEqual(new Set(['image-1', 'image-2']))

    await act(async () => {
      resolveFirst?.({
        data: {
          segments: [{ id: 'seg-1', text: 'Hello', order: 1 }],
        },
      })
      await Promise.resolve()
    })

    expect(Array.from(result.current.textRedrawExtractingItemIds)).toEqual(['image-2'])

    await act(async () => {
      resolveSecond?.({
        data: {
          segments: [{ id: 'seg-2', text: 'World', order: 1 }],
        },
      })
      await Promise.resolve()
    })

    expect(Array.from(result.current.textRedrawExtractingItemIds)).toEqual([])
  })

  it('pastes an image from the system clipboard through the upload pipeline', async () => {
    const setActiveTool = vi.fn()
    const setSelectedItems = vi.fn()
    const updateCanvasItems = vi.fn()
    const saveCanvasItems = vi.fn()
    const handleJumpToItem = vi.fn()

    class MockImage {
      naturalWidth = 640
      naturalHeight = 480
      onload: null | (() => void) = null
      onerror: null | (() => void) = null

      set src(_value: string) {
        queueMicrotask(() => {
          this.onload?.()
        })
      }
    }

    readClipboardImageFileFromNavigator.mockResolvedValue(new File(['img'], 'clipboard.png', { type: 'image/png' }))

    const restoreImage = globalThis.Image
    vi.stubGlobal('Image', MockImage as unknown as typeof Image)

    try {
      const { result } = renderHook(() => useCanvasControllerMedia(createMediaHookArgs({
        user: { balance_cents: 100 },
        setActiveTool,
        setSelectedItems,
        updateCanvasItems,
        saveCanvasItems,
        handleJumpToItem,
      })))

      await act(async () => {
        await result.current.handlePasteClipboardImage()
      })

      expect(readClipboardImageFileFromNavigator).toHaveBeenCalledTimes(1)
      expect(setActiveTool).toHaveBeenCalledWith('select')
      expect(setSelectedItems).toHaveBeenCalledTimes(1)
      expect(updateCanvasItems).toHaveBeenCalledTimes(1)
      expect(saveCanvasItems).toHaveBeenCalledTimes(1)
      expect(handleJumpToItem).toHaveBeenCalledTimes(1)
    } finally {
      vi.stubGlobal('Image', restoreImage)
    }
  })
})
